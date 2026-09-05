pub use mcr_safety_core as safety_core;

#[cfg(test)]
mod tests {
    use super::safety_core::{
        hash::sha256_bytes, model::ScanPolicy, path_checks::analyse_path_str,
    };

    #[test]
    fn pinned_dependency_detects_traversal() {
        let findings = analyse_path_str("../evidence.txt", &ScanPolicy::default());
        assert!(findings.iter().any(|f| f.code == "PATH_TRAVERSAL"));
    }

    #[test]
    fn pinned_dependency_accepts_safe_relative_path() {
        let findings = analyse_path_str("folder/evidence.txt", &ScanPolicy::default());
        assert!(!findings
            .iter()
            .any(|f| f.code == "PATH_TRAVERSAL" || f.code == "PATH_ABSOLUTE"));
    }

    #[test]
    fn pinned_dependency_sha256_matches_known_vector() {
        assert_eq!(
            sha256_bytes(b"abc"),
            "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
        );
    }
}
