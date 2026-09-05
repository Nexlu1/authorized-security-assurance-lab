use std::path::PathBuf;

/// Convert a lowercase SHA-256 hex digest into a content-addressed relative path.
///
/// Untrusted source filenames never participate in this storage path.
pub fn object_relpath(sha256: &str) -> Result<PathBuf, String> {
    if sha256.len() != 64 {
        return Err("SHA-256 must contain exactly 64 lowercase hex characters".to_string());
    }
    if !sha256
        .bytes()
        .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
    {
        return Err("SHA-256 must contain lowercase hexadecimal only".to_string());
    }

    Ok(PathBuf::from("objects")
        .join(&sha256[0..2])
        .join(&sha256[2..4])
        .join(sha256))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn valid_hash_maps_without_filename_input() {
        let h = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef";
        assert_eq!(
            object_relpath(h).unwrap(),
            PathBuf::from("objects").join("01").join("23").join(h)
        );
    }

    #[test]
    fn rejects_wrong_length() {
        assert!(object_relpath("00").is_err());
    }

    #[test]
    fn rejects_uppercase_and_nonhex() {
        let upper = "A".repeat(64);
        let nonhex = "g".repeat(64);
        assert!(object_relpath(&upper).is_err());
        assert!(object_relpath(&nonhex).is_err());
    }
}
