use crate::model::{Finding, Severity};
use std::path::Path;

pub fn detect_kind(bytes: &[u8]) -> &'static str {
    if bytes.starts_with(b"%PDF-") {
        return "pdf";
    }
    if bytes.starts_with(&[0x50, 0x4b, 0x03, 0x04])
        || bytes.starts_with(&[0x50, 0x4b, 0x05, 0x06])
        || bytes.starts_with(&[0x50, 0x4b, 0x07, 0x08])
    {
        return "zip";
    }
    if bytes.starts_with(&[0x89, b'P', b'N', b'G', 0x0d, 0x0a, 0x1a, 0x0a]) {
        return "png";
    }
    if bytes.starts_with(&[0xff, 0xd8, 0xff]) {
        return "jpeg";
    }
    if bytes.starts_with(b"GIF87a") || bytes.starts_with(b"GIF89a") {
        return "gif";
    }
    if bytes.starts_with(&[0x1f, 0x8b]) {
        return "gzip";
    }
    if bytes.starts_with(&[0x7f, b'E', b'L', b'F']) {
        return "elf";
    }
    if bytes.starts_with(b"MZ") {
        return "pe";
    }
    if bytes.starts_with(br"{\rtf") {
        return "rtf";
    }
    if bytes.starts_with(&[0xd0, 0xcf, 0x11, 0xe0, 0xa1, 0xb1, 0x1a, 0xe1]) {
        return "ole";
    }
    let trimmed = bytes
        .iter()
        .copied()
        .skip_while(|b| b.is_ascii_whitespace())
        .collect::<Vec<_>>();
    let lower = String::from_utf8_lossy(&trimmed[..trimmed.len().min(512)]).to_ascii_lowercase();
    if lower.starts_with("<!doctype html") || lower.starts_with("<html") {
        return "html";
    }
    if lower.starts_with("<?xml") {
        return "xml";
    }
    if !bytes.contains(&0) && std::str::from_utf8(bytes).is_ok() {
        return "text";
    }
    "binary"
}

pub fn extension_family(path: &Path) -> Option<&'static str> {
    let ext = path.extension()?.to_string_lossy().to_ascii_lowercase();
    Some(match ext.as_str() {
        "pdf" => "pdf",
        "zip" | "docx" | "xlsx" | "pptx" | "odt" | "ods" | "odp" | "epub" => "zip",
        "png" => "png",
        "jpg" | "jpeg" => "jpeg",
        "gif" => "gif",
        "gz" | "tgz" => "gzip",
        "rtf" => "rtf",
        "doc" | "xls" | "ppt" => "ole",
        "exe" | "dll" | "scr" => "pe",
        "html" | "htm" => "html",
        "xml" => "xml",
        "txt" | "md" | "csv" | "json" | "log" => "text",
        _ => return None,
    })
}

pub fn mismatch_findings(path: &Path, detected: &str) -> Vec<Finding> {
    let expected = match extension_family(path) {
        Some(x) => x,
        None => return vec![],
    };
    if expected == detected {
        return vec![];
    }
    if expected == "text" && matches!(detected, "xml" | "text") {
        return vec![];
    }
    let severity = Severity::High;
    let code = if expected == "text" && detected == "html" {
        "CONTENT_ACTIVE_IN_TEXT"
    } else {
        "CONTENT_EXTENSION_MISMATCH"
    };
    vec![Finding::new(
        code,
        severity,
        format!("extension expects {expected}, signature indicates {detected}"),
    )]
}
