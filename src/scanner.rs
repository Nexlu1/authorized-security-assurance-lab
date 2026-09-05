use crate::{
    archive::inspect_zip,
    hash::{sha256_canonical_json, sha256_file},
    magic::{detect_kind, mismatch_findings},
    model::{Finding, ItemRecord, Manifest, ScanPolicy, ScanSummary, Severity},
    path_checks::analyse_relative_path,
};
use anyhow::{Context, Result};
use chrono::{SecondsFormat, Utc};
use serde::Serialize;
use std::{
    fs::{self, File},
    io::Read,
    path::Path,
};
use uuid::Uuid;
use walkdir::WalkDir;

#[derive(Serialize)]
struct HashMaterial<'a> {
    schema_version: &'a str,
    tool_name: &'a str,
    tool_version: &'a str,
    root: &'a str,
    policy: &'a ScanPolicy,
    items: &'a [ItemRecord],
    summary: &'a ScanSummary,
}

pub fn scan(root: &Path, policy: ScanPolicy) -> Result<Manifest> {
    let canonical =
        fs::canonicalize(root).with_context(|| format!("canonicalize root: {}", root.display()))?;
    if !canonical.is_dir() {
        anyhow::bail!("scan root is not a directory: {}", canonical.display());
    }
    let mut items = Vec::new();

    for entry in WalkDir::new(&canonical)
        .follow_links(false)
        .sort_by_file_name()
    {
        match entry {
            Ok(entry) => {
                if entry.path() == canonical {
                    continue;
                }
                let rel = entry
                    .path()
                    .strip_prefix(&canonical)
                    .unwrap_or(entry.path());
                let rel_s = rel.to_string_lossy().replace('\\', "/");
                let ft = entry.file_type();
                let mut findings = analyse_relative_path(rel, &policy);
                if ft.is_symlink() {
                    findings.push(Finding::new(
                        "OBJECT_SYMLINK",
                        Severity::Critical,
                        "symbolic links are recorded but never followed",
                    ));
                    items.push(ItemRecord {
                        relative_path: rel_s,
                        object_type: "symlink".into(),
                        size_bytes: None,
                        sha256: None,
                        extension: None,
                        detected_kind: None,
                        findings,
                        archive: None,
                        error: None,
                    });
                    continue;
                }
                if ft.is_dir() {
                    items.push(ItemRecord {
                        relative_path: rel_s,
                        object_type: "directory".into(),
                        size_bytes: None,
                        sha256: None,
                        extension: None,
                        detected_kind: None,
                        findings,
                        archive: None,
                        error: None,
                    });
                    continue;
                }
                if !ft.is_file() {
                    findings.push(Finding::new(
                        "OBJECT_SPECIAL",
                        Severity::High,
                        "non-regular filesystem object",
                    ));
                    items.push(ItemRecord {
                        relative_path: rel_s,
                        object_type: "special".into(),
                        size_bytes: None,
                        sha256: None,
                        extension: None,
                        detected_kind: None,
                        findings,
                        archive: None,
                        error: None,
                    });
                    continue;
                }
                let metadata = match entry.metadata() {
                    Ok(m) => m,
                    Err(e) => {
                        items.push(ItemRecord {
                            relative_path: rel_s,
                            object_type: "file".into(),
                            size_bytes: None,
                            sha256: None,
                            extension: None,
                            detected_kind: None,
                            findings,
                            archive: None,
                            error: Some(e.to_string()),
                        });
                        continue;
                    }
                };
                let size = metadata.len();
                if size > policy.max_file_bytes {
                    findings.push(Finding::new(
                        "FILE_SIZE_LIMIT",
                        Severity::Critical,
                        format!("{size} bytes exceeds {}", policy.max_file_bytes),
                    ));
                    items.push(ItemRecord {
                        relative_path: rel_s,
                        object_type: "file".into(),
                        size_bytes: Some(size),
                        sha256: None,
                        extension: entry
                            .path()
                            .extension()
                            .map(|x| x.to_string_lossy().to_ascii_lowercase()),
                        detected_kind: None,
                        findings,
                        archive: None,
                        error: Some(
                            "file not opened or hashed because policy limit was exceeded".into(),
                        ),
                    });
                    continue;
                }
                let mut prefix = Vec::new();
                let prefix_result = (|| -> Result<()> {
                    let mut f = File::open(entry.path())?;
                    let mut limited = (&mut f).take(8192);
                    limited.read_to_end(&mut prefix)?;
                    Ok(())
                })();
                let detected = prefix_result
                    .as_ref()
                    .ok()
                    .map(|_| detect_kind(&prefix).to_string());
                if let Some(kind) = &detected {
                    findings.extend(mismatch_findings(entry.path(), kind));
                }
                let hash = sha256_file(entry.path());
                let archive = if detected.as_deref() == Some("zip") {
                    match inspect_zip(entry.path(), &policy) {
                        Ok(a) => Some(a),
                        Err(e) => {
                            findings.push(Finding::new(
                                "ARCHIVE_PARSE_ERROR",
                                Severity::High,
                                e.to_string(),
                            ));
                            None
                        }
                    }
                } else {
                    None
                };
                let error = match (prefix_result.err(), hash.as_ref().err()) {
                    (None, None) => None,
                    (a, b) => Some(
                        [a.map(|e| e.to_string()), b.map(|e| e.to_string())]
                            .into_iter()
                            .flatten()
                            .collect::<Vec<_>>()
                            .join("; "),
                    ),
                };
                items.push(ItemRecord {
                    relative_path: rel_s,
                    object_type: "file".into(),
                    size_bytes: Some(size),
                    sha256: hash.ok(),
                    extension: entry
                        .path()
                        .extension()
                        .map(|x| x.to_string_lossy().to_ascii_lowercase()),
                    detected_kind: detected,
                    findings,
                    archive,
                    error,
                });
            }
            Err(e) => items.push(ItemRecord {
                relative_path: e
                    .path()
                    .map(|p| p.to_string_lossy().replace('\\', "/"))
                    .unwrap_or_else(|| "<unknown>".into()),
                object_type: "error".into(),
                size_bytes: None,
                sha256: None,
                extension: None,
                detected_kind: None,
                findings: vec![],
                archive: None,
                error: Some(e.to_string()),
            }),
        }
    }
    items.sort_by(|a, b| a.relative_path.cmp(&b.relative_path));
    let summary = summarize(&items);
    let root_s = canonical.to_string_lossy().to_string();
    let material = HashMaterial {
        schema_version: "mcr.ingest.manifest/1",
        tool_name: "mcr-ingest",
        tool_version: env!("CARGO_PKG_VERSION"),
        root: &root_s,
        policy: &policy,
        items: &items,
        summary: &summary,
    };
    let manifest_sha256 = sha256_canonical_json(&material)?;
    Ok(Manifest {
        schema_version: "mcr.ingest.manifest/1".into(),
        tool_name: "mcr-ingest".into(),
        tool_version: env!("CARGO_PKG_VERSION").into(),
        run_id: Uuid::new_v4().to_string(),
        created_utc: Utc::now().to_rfc3339_opts(SecondsFormat::Secs, true),
        root: root_s,
        policy,
        items,
        summary,
        manifest_sha256,
    })
}

pub fn summarize(items: &[ItemRecord]) -> ScanSummary {
    let mut s = ScanSummary {
        objects_seen: items.len(),
        ..Default::default()
    };
    for item in items {
        match item.object_type.as_str() {
            "file" => s.regular_files += 1,
            "directory" => s.directories += 1,
            "symlink" => s.symlinks += 1,
            _ => {}
        }
        if item.error.is_some() {
            s.errors += 1;
        }
        for f in item
            .findings
            .iter()
            .chain(item.archive.iter().flat_map(|a| a.findings.iter()))
            .chain(
                item.archive
                    .iter()
                    .flat_map(|a| a.entries.iter().flat_map(|e| e.findings.iter())),
            )
        {
            match f.severity {
                Severity::Info => s.findings_info += 1,
                Severity::Warning => s.findings_warning += 1,
                Severity::High => s.findings_high += 1,
                Severity::Critical => s.findings_critical += 1,
            }
        }
    }
    s
}

pub fn verify_manifest_hash(manifest: &Manifest) -> Result<bool> {
    let material = HashMaterial {
        schema_version: &manifest.schema_version,
        tool_name: &manifest.tool_name,
        tool_version: &manifest.tool_version,
        root: &manifest.root,
        policy: &manifest.policy,
        items: &manifest.items,
        summary: &manifest.summary,
    };
    Ok(sha256_canonical_json(&material)? == manifest.manifest_sha256)
}
