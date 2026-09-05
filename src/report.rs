use crate::model::Manifest;
use anyhow::{Context, Result};
use std::{
    fs,
    io::{BufWriter, Write},
    path::Path,
};
use tempfile::NamedTempFile;

pub fn write_json_atomic(path: &Path, manifest: &Manifest) -> Result<()> {
    let parent = path.parent().unwrap_or_else(|| Path::new("."));
    fs::create_dir_all(parent)
        .with_context(|| format!("create output directory: {}", parent.display()))?;
    let mut temp = NamedTempFile::new_in(parent).context("create temporary output")?;
    {
        let mut writer = BufWriter::new(temp.as_file_mut());
        serde_json::to_writer_pretty(&mut writer, manifest).context("write manifest JSON")?;
        writer.write_all(b"\n")?;
        writer.flush()?;
    }
    temp.as_file()
        .sync_all()
        .context("sync temporary manifest")?;
    temp.persist(path)
        .map_err(|e| e.error)
        .with_context(|| format!("persist manifest: {}", path.display()))?;
    Ok(())
}

pub fn write_markdown_atomic(path: &Path, manifest: &Manifest) -> Result<()> {
    let parent = path.parent().unwrap_or_else(|| Path::new("."));
    fs::create_dir_all(parent)?;
    let mut temp = NamedTempFile::new_in(parent)?;
    writeln!(temp, "# MCR Ingest Scan Report\n")?;
    writeln!(temp, "- Root: `{}`", manifest.root)?;
    writeln!(temp, "- Created UTC: `{}`", manifest.created_utc)?;
    writeln!(temp, "- Manifest SHA-256: `{}`", manifest.manifest_sha256)?;
    writeln!(temp, "- Objects: {}", manifest.summary.objects_seen)?;
    writeln!(temp, "- Files: {}", manifest.summary.regular_files)?;
    writeln!(temp, "- Errors: {}", manifest.summary.errors)?;
    writeln!(
        temp,
        "- Critical findings: {}",
        manifest.summary.findings_critical
    )?;
    writeln!(
        temp,
        "- High findings: {}\n",
        manifest.summary.findings_high
    )?;
    writeln!(temp, "## Items\n")?;
    for item in &manifest.items {
        writeln!(temp, "### `{}`", item.relative_path)?;
        writeln!(temp, "- Type: {}", item.object_type)?;
        if let Some(size) = item.size_bytes {
            writeln!(temp, "- Bytes: {size}")?;
        }
        if let Some(hash) = &item.sha256 {
            writeln!(temp, "- SHA-256: `{hash}`")?;
        }
        if let Some(kind) = &item.detected_kind {
            writeln!(temp, "- Detected: {kind}")?;
        }
        if let Some(err) = &item.error {
            writeln!(temp, "- Error: `{err}`")?;
        }
        for f in &item.findings {
            writeln!(temp, "- **{:?} / {}:** {}", f.severity, f.code, f.message)?;
        }
        if let Some(a) = &item.archive {
            writeln!(temp, "- Archive entries seen: {}", a.entries_seen)?;
            for f in &a.findings {
                writeln!(temp, "- **{:?} / {}:** {}", f.severity, f.code, f.message)?;
            }
            for e in &a.entries {
                for f in &e.findings {
                    writeln!(
                        temp,
                        "  - `{}` — **{:?} / {}:** {}",
                        e.name, f.severity, f.code, f.message
                    )?;
                }
            }
        }
        writeln!(temp)?;
    }
    temp.as_file().sync_all()?;
    temp.persist(path).map_err(|e| e.error)?;
    Ok(())
}
