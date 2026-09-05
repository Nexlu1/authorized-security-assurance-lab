use crate::{
    model::{ArchiveEntryRecord, ArchiveSummary, Finding, ScanPolicy, Severity},
    path_checks::{analyse_path_str, collision_key},
};
use anyhow::{Context, Result};
use std::{
    collections::{HashMap, HashSet},
    fs::File,
    path::Path,
};
use zip::ZipArchive;

pub fn archive_entry_findings(
    name: &str,
    uncompressed: u64,
    compressed: u64,
    unix_mode: Option<u32>,
    policy: &ScanPolicy,
) -> Vec<Finding> {
    let mut out = analyse_path_str(name, policy);
    if let Some(mode) = unix_mode {
        if mode & 0o170000 == 0o120000 {
            out.push(Finding::new(
                "ARCHIVE_SYMLINK",
                Severity::Critical,
                "archive entry is a symbolic link",
            ));
        }
    }
    let ratio = if compressed == 0 {
        if uncompressed == 0 {
            1.0
        } else {
            f64::INFINITY
        }
    } else {
        uncompressed as f64 / compressed as f64
    };
    if ratio > policy.max_archive_entry_ratio {
        out.push(Finding::new(
            "ARCHIVE_COMPRESSION_RATIO",
            Severity::Critical,
            format!(
                "entry ratio {ratio:.2} exceeds {:.2}",
                policy.max_archive_entry_ratio
            ),
        ));
    }
    out.sort_by(|a, b| a.code.cmp(&b.code));
    out
}

pub fn archive_aggregate_findings(
    entries: usize,
    total_uncompressed: u64,
    policy: &ScanPolicy,
) -> Vec<Finding> {
    let mut out = Vec::new();
    if entries > policy.max_archive_entries {
        out.push(Finding::new(
            "ARCHIVE_ENTRY_LIMIT",
            Severity::Critical,
            format!("{entries} entries exceeds {}", policy.max_archive_entries),
        ));
    }
    if total_uncompressed > policy.max_archive_total_uncompressed_bytes {
        out.push(Finding::new(
            "ARCHIVE_TOTAL_UNCOMPRESSED_LIMIT",
            Severity::Critical,
            format!(
                "{total_uncompressed} bytes exceeds {}",
                policy.max_archive_total_uncompressed_bytes
            ),
        ));
    }
    out
}

pub fn inspect_zip(path: &Path, policy: &ScanPolicy) -> Result<ArchiveSummary> {
    let file = File::open(path).with_context(|| format!("open ZIP: {}", path.display()))?;
    let mut zip =
        ZipArchive::new(file).with_context(|| format!("parse ZIP: {}", path.display()))?;
    let entries_seen = zip.len();
    let mut total_uncompressed = 0_u64;
    let mut total_compressed = 0_u64;
    let mut entries =
        Vec::with_capacity(entries_seen.min(policy.max_archive_entries.saturating_add(1)));
    let mut exact = HashSet::new();
    let mut folded: HashMap<String, String> = HashMap::new();
    let mut aggregate = Vec::new();

    for i in 0..entries_seen {
        if i > policy.max_archive_entries {
            break;
        }
        let file = zip
            .by_index(i)
            .with_context(|| format!("read ZIP entry index {i}"))?;
        let name = file.name().to_string();
        let size = file.size();
        let compressed = file.compressed_size();
        total_uncompressed = total_uncompressed.saturating_add(size);
        total_compressed = total_compressed.saturating_add(compressed);
        let mut findings =
            archive_entry_findings(&name, size, compressed, file.unix_mode(), policy);
        if !exact.insert(name.clone()) {
            findings.push(Finding::new(
                "ARCHIVE_DUPLICATE_NAME",
                Severity::Critical,
                "duplicate exact entry name",
            ));
        }
        let key = collision_key(&name);
        if let Some(first) = folded.insert(key, name.clone()) {
            if first != name {
                findings.push(Finding::new(
                    "ARCHIVE_CASE_COLLISION",
                    Severity::Critical,
                    format!("case/normalisation collision with {first}"),
                ));
            }
        }
        entries.push(ArchiveEntryRecord {
            name,
            uncompressed_bytes: size,
            compressed_bytes: compressed,
            unix_mode: file.unix_mode(),
            findings,
        });
    }
    aggregate.extend(archive_aggregate_findings(
        entries_seen,
        total_uncompressed,
        policy,
    ));
    Ok(ArchiveSummary {
        entries_seen,
        total_uncompressed_bytes: total_uncompressed,
        total_compressed_bytes: total_compressed,
        entries,
        findings: aggregate,
    })
}
