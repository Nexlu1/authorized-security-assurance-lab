/// Lexical safety check for an untrusted archive member name.
///
/// This is deliberately stricter than ordinary path normalization:
/// - both slash and backslash are treated as separators;
/// - absolute/UNC/drive-qualified names are rejected;
/// - dot and parent components are rejected;
/// - colon is rejected to prevent Windows NTFS ADS-style names;
/// - NUL is rejected.
pub fn validate_member_name(name: &str) -> Result<(), String> {
    if name.is_empty() {
        return Err("empty archive member name".to_string());
    }
    if name.contains('\0') {
        return Err("NUL in archive member name".to_string());
    }
    if name.starts_with('/') || name.starts_with('\\') {
        return Err("absolute or UNC-like archive member name".to_string());
    }

    let bytes = name.as_bytes();
    if bytes.len() >= 2 && bytes[0].is_ascii_alphabetic() && bytes[1] == b':' {
        return Err("Windows drive-qualified archive member name".to_string());
    }

    for segment in name.split(['/', '\\']) {
        if segment.is_empty() {
            continue;
        }
        if segment == "." || segment == ".." {
            return Err("dot/parent traversal component".to_string());
        }
        if segment.contains(':') {
            return Err("colon/alternate-data-stream style component".to_string());
        }
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn accepts_normal_relative_names() {
        assert!(validate_member_name("word/document.xml").is_ok());
        assert!(validate_member_name("folder\\file.txt").is_ok());
    }

    #[test]
    fn rejects_common_traversal_forms() {
        for bad in [
            "../secret.txt",
            "..\\secret.txt",
            "a/../../secret.txt",
            "/absolute.txt",
            "\\\\server\\share\\x",
            "C:\\Windows\\x",
            "file.txt:evil",
        ] {
            assert!(validate_member_name(bad).is_err(), "should reject {bad:?}");
        }
    }
}
