pub use mcr_safety_core as safety_core;

#[cfg(test)]
mod tests {
    use super::safety_core::{
        hash::sha256_bytes, model::ScanPolicy, path_checks::analyse_path_str,
    };

    #[test]
    fn qualified_dependency_is_callable_from_same_named_root_package() {
        assert_eq!(
            sha256_bytes(b"abc"),
            "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
        );
        let findings = analyse_path_str("../evidence.txt", &ScanPolicy::default());
        assert!(findings.iter().any(|f| f.code == "PATH_TRAVERSAL"));
    }
}
