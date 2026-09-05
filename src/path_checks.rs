use crate::model::{Finding, ScanPolicy, Severity};
use std::path::Path;

const BIDI: [char; 9] = [
    '\u{202A}', '\u{202B}', '\u{202C}', '\u{202D}', '\u{202E}', '\u{2066}', '\u{2067}', '\u{2068}',
    '\u{2069}',
];
const LOOKALIKE_SLASHES: [char; 5] = ['\u{2044}', '\u{2215}', '\u{29F8}', '\u{FF0F}', '\u{FF3C}'];

fn finding(code: &str, severity: Severity, msg: impl Into<String>) -> Finding {
    Finding::new(code, severity, msg)
}

pub fn normalise_slashes(raw: &str) -> String {
    raw.replace('\\', "/")
}

pub fn collision_key(raw: &str) -> String {
    let mut out = Vec::new();
    let normalized = normalise_slashes(raw);
    for seg in normalized.split('/') {
        if seg.is_empty() || seg == "." {
            continue;
        }
        if seg == ".." {
            out.push("..");
        } else {
            out.push(seg);
        }
    }
    out.join("/").to_lowercase()
}

pub fn analyse_path_str(raw: &str, policy: &ScanPolicy) -> Vec<Finding> {
    let mut f = Vec::new();
    let normalized = normalise_slashes(raw);
    let segments: Vec<&str> = normalized.split('/').collect();

    if raw.starts_with('/')
        || raw.starts_with('\\')
        || raw.starts_with("//")
        || raw.starts_with("\\\\")
    {
        f.push(finding(
            "PATH_ABSOLUTE",
            Severity::Critical,
            "absolute or UNC-style path",
        ));
    }
    if raw.len() >= 2 && raw.as_bytes()[1] == b':' && raw.as_bytes()[0].is_ascii_alphabetic() {
        f.push(finding(
            "PATH_WINDOWS_DRIVE",
            Severity::Critical,
            "Windows drive-qualified path",
        ));
    }
    if segments.contains(&"..") {
        f.push(finding(
            "PATH_TRAVERSAL",
            Severity::Critical,
            "parent-directory traversal segment",
        ));
    }
    if segments.contains(&".") {
        f.push(finding(
            "PATH_DOT_SEGMENT",
            Severity::Warning,
            "non-canonical dot segment",
        ));
    }
    if segments.len() > policy.max_path_depth {
        f.push(finding(
            "PATH_DEPTH_LIMIT",
            Severity::High,
            format!(
                "path depth {} exceeds {}",
                segments.len(),
                policy.max_path_depth
            ),
        ));
    }
    if raw.chars().any(|c| c.is_control()) {
        f.push(finding(
            "NAME_CONTROL_CHARACTER",
            Severity::High,
            "control character in path",
        ));
    }
    if raw.chars().any(|c| BIDI.contains(&c)) {
        f.push(finding(
            "NAME_BIDI_OVERRIDE",
            Severity::High,
            "bidirectional text control in path",
        ));
    }
    if raw.chars().any(|c| LOOKALIKE_SLASHES.contains(&c)) {
        f.push(finding(
            "NAME_LOOKALIKE_SEPARATOR",
            Severity::High,
            "Unicode lookalike path separator",
        ));
    }

    for seg in &segments {
        if seg.is_empty() {
            continue;
        }
        if seg.len() > policy.max_segment_bytes {
            f.push(finding(
                "NAME_SEGMENT_LIMIT",
                Severity::High,
                format!("segment exceeds {} bytes", policy.max_segment_bytes),
            ));
        }
        if seg.ends_with('.') {
            f.push(finding(
                "NAME_TRAILING_DOT",
                Severity::High,
                "segment ends with a dot",
            ));
        }
        if seg.ends_with(' ') {
            f.push(finding(
                "NAME_TRAILING_SPACE",
                Severity::High,
                "segment ends with a space",
            ));
        }
        if seg.contains(':')
            && !(segments.first() == Some(seg) && seg.len() == 2 && seg.ends_with(':'))
        {
            f.push(finding(
                "NAME_ALTERNATE_DATA_STREAM",
                Severity::Critical,
                "colon may address a Windows alternate data stream",
            ));
        }
        if seg.starts_with('.') && seg.len() > 1 {
            f.push(finding(
                "NAME_HIDDEN_DOTFILE",
                Severity::Info,
                "dot-prefixed hidden-style name",
            ));
        }
        let stem = seg
            .split('.')
            .next()
            .unwrap_or(seg)
            .trim_end_matches([' ', '.'])
            .to_ascii_uppercase();
        let reserved = matches!(stem.as_str(), "CON" | "PRN" | "AUX" | "NUL")
            || (stem.len() == 4
                && (stem.starts_with("COM") || stem.starts_with("LPT"))
                && stem[3..]
                    .chars()
                    .next()
                    .is_some_and(|c| ('1'..='9').contains(&c)));
        if reserved {
            f.push(finding(
                "NAME_WINDOWS_RESERVED",
                Severity::High,
                format!("Windows reserved device name: {stem}"),
            ));
        }
        let lower = seg.to_ascii_lowercase();
        let dangerous = [
            ".exe", ".com", ".scr", ".bat", ".cmd", ".ps1", ".js", ".jse", ".vbs", ".vbe", ".msi",
            ".dll",
        ];
        let decoy = [
            ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".jpg", ".jpeg", ".png", ".txt", ".rtf",
        ];
        if dangerous.iter().any(|x| lower.ends_with(x))
            && decoy
                .iter()
                .any(|x| lower[..lower.rfind('.').unwrap_or(0)].ends_with(x))
        {
            f.push(finding(
                "NAME_DOUBLE_EXTENSION",
                Severity::Critical,
                "document/image decoy followed by executable or script extension",
            ));
        }
    }
    f.sort_by(|a, b| a.code.cmp(&b.code).then(a.message.cmp(&b.message)));
    f.dedup_by(|a, b| a.code == b.code && a.message == b.message);
    f
}

pub fn analyse_relative_path(path: &Path, policy: &ScanPolicy) -> Vec<Finding> {
    analyse_path_str(&path.to_string_lossy(), policy)
}
