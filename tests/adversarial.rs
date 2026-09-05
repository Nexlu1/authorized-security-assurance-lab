#![allow(clippy::field_reassign_with_default)]
use mcr_ingest::{
    archive::{archive_aggregate_findings, archive_entry_findings},
    hash::{sha256_bytes, sha256_canonical_json},
    magic::{detect_kind, mismatch_findings},
    model::ScanPolicy,
    path_checks::{analyse_path_str, collision_key},
    scanner::{scan, verify_manifest_hash},
};
use std::{fs, path::Path};

fn has_code(findings: &[mcr_ingest::model::Finding], code: &str) -> bool {
    findings.iter().any(|f| f.code == code)
}
macro_rules! path_bad {
    ($name:ident,$raw:expr,$code:expr) => {
        #[test]
        fn $name() {
            let p = ScanPolicy::default();
            assert!(has_code(&analyse_path_str($raw, &p), $code));
        }
    };
}
macro_rules! magic_is {
    ($name:ident,$bytes:expr,$kind:expr) => {
        #[test]
        fn $name() {
            assert_eq!(detect_kind($bytes), $kind);
        }
    };
}

path_bad!(t01_parent_traversal, "../secret.txt", "PATH_TRAVERSAL");
path_bad!(t02_absolute_posix, "/etc/passwd", "PATH_ABSOLUTE");
path_bad!(t03_windows_drive, "C:/secret.txt", "PATH_WINDOWS_DRIVE");
path_bad!(t04_unc_path, r"\\server\share\x", "PATH_ABSOLUTE");
path_bad!(t05_backslash_traversal, r"ok\..\x", "PATH_TRAVERSAL");
path_bad!(t06_trailing_dot, "report.pdf.", "NAME_TRAILING_DOT");
path_bad!(t07_trailing_space, "report.pdf ", "NAME_TRAILING_SPACE");
path_bad!(t08_ads, "report.pdf:evil.exe", "NAME_ALTERNATE_DATA_STREAM");
path_bad!(t09_reserved_con, "CON.txt", "NAME_WINDOWS_RESERVED");
path_bad!(t10_reserved_aux, "aux.pdf", "NAME_WINDOWS_RESERVED");
path_bad!(t11_reserved_com1, "COM1.log", "NAME_WINDOWS_RESERVED");
path_bad!(t12_reserved_lpt9, "LPT9.txt", "NAME_WINDOWS_RESERVED");
path_bad!(t13_bidi, "safe\u{202e}fdp.exe", "NAME_BIDI_OVERRIDE");
path_bad!(t14_control, "safe\u{0001}.txt", "NAME_CONTROL_CHARACTER");
path_bad!(
    t15_lookalike_slash,
    "safe\u{2215}evil.txt",
    "NAME_LOOKALIKE_SEPARATOR"
);
path_bad!(
    t16_double_extension_exe,
    "statement.pdf.exe",
    "NAME_DOUBLE_EXTENSION"
);
path_bad!(
    t17_double_extension_js,
    "photo.jpg.js",
    "NAME_DOUBLE_EXTENSION"
);
path_bad!(t18_hidden_dotfile, ".secret", "NAME_HIDDEN_DOTFILE");
#[test]
fn t19_long_segment() {
    let mut p = ScanPolicy::default();
    p.max_segment_bytes = 8;
    assert!(has_code(
        &analyse_path_str("123456789.txt", &p),
        "NAME_SEGMENT_LIMIT"
    ));
}
#[test]
fn t20_deep_path() {
    let mut p = ScanPolicy::default();
    p.max_path_depth = 2;
    assert!(has_code(
        &analyse_path_str("a/b/c.txt", &p),
        "PATH_DEPTH_LIMIT"
    ));
}
#[test]
fn t21_safe_path() {
    let p = ScanPolicy::default();
    let f = analyse_path_str("folder/report-01.pdf", &p);
    assert!(!f
        .iter()
        .any(|x| x.severity >= mcr_ingest::model::Severity::High));
}

magic_is!(t22_pdf, b"%PDF-1.7\n", "pdf");
magic_is!(t23_zip_local, &[0x50, 0x4b, 0x03, 0x04], "zip");
magic_is!(t24_zip_empty, &[0x50, 0x4b, 0x05, 0x06], "zip");
magic_is!(t25_png, &[0x89, b'P', b'N', b'G', 13, 10, 26, 10], "png");
magic_is!(t26_jpeg, &[0xff, 0xd8, 0xff, 0xe0], "jpeg");
magic_is!(t27_gif, b"GIF89a0000", "gif");
magic_is!(t28_gzip, &[0x1f, 0x8b, 0x08], "gzip");
magic_is!(t29_elf, &[0x7f, b'E', b'L', b'F'], "elf");
magic_is!(t30_pe, b"MZanything", "pe");
magic_is!(t31_rtf, br"{\rtf1 test}", "rtf");
magic_is!(
    t32_ole,
    &[0xd0, 0xcf, 0x11, 0xe0, 0xa1, 0xb1, 0x1a, 0xe1],
    "ole"
);
magic_is!(t33_html, b" <!DOCTYPE html><html>", "html");
magic_is!(t34_xml, b"\n<?xml version='1.0'?>", "xml");
magic_is!(t35_text, b"ordinary UTF-8 text", "text");
magic_is!(t36_binary, &[0, 1, 2, 3], "binary");

#[test]
fn t37_pdf_mismatch() {
    assert!(has_code(
        &mismatch_findings(Path::new("x.pdf"), "pe"),
        "CONTENT_EXTENSION_MISMATCH"
    ));
}
#[test]
fn t38_docx_mismatch() {
    assert!(has_code(
        &mismatch_findings(Path::new("x.docx"), "text"),
        "CONTENT_EXTENSION_MISMATCH"
    ));
}
#[test]
fn t39_png_mismatch() {
    assert!(has_code(
        &mismatch_findings(Path::new("x.png"), "jpeg"),
        "CONTENT_EXTENSION_MISMATCH"
    ));
}
#[test]
fn t40_active_html_in_txt() {
    assert!(has_code(
        &mismatch_findings(Path::new("x.txt"), "html"),
        "CONTENT_ACTIVE_IN_TEXT"
    ));
}
#[test]
fn t41_zip_match() {
    assert!(mismatch_findings(Path::new("x.zip"), "zip").is_empty());
}

#[test]
fn t42_archive_traversal() {
    let p = ScanPolicy::default();
    assert!(has_code(
        &archive_entry_findings("../x", 1, 1, None, &p),
        "PATH_TRAVERSAL"
    ));
}
#[test]
fn t43_archive_absolute() {
    let p = ScanPolicy::default();
    assert!(has_code(
        &archive_entry_findings("/x", 1, 1, None, &p),
        "PATH_ABSOLUTE"
    ));
}
#[test]
fn t44_archive_drive() {
    let p = ScanPolicy::default();
    assert!(has_code(
        &archive_entry_findings("C:/x", 1, 1, None, &p),
        "PATH_WINDOWS_DRIVE"
    ));
}
#[test]
fn t45_archive_symlink() {
    let p = ScanPolicy::default();
    assert!(has_code(
        &archive_entry_findings("x", 1, 1, Some(0o120777), &p),
        "ARCHIVE_SYMLINK"
    ));
}
#[test]
fn t46_archive_ratio() {
    let mut p = ScanPolicy::default();
    p.max_archive_entry_ratio = 10.0;
    assert!(has_code(
        &archive_entry_findings("x", 1000, 1, None, &p),
        "ARCHIVE_COMPRESSION_RATIO"
    ));
}
#[test]
fn t47_archive_zero_compressed() {
    let p = ScanPolicy::default();
    assert!(has_code(
        &archive_entry_findings("x", 1, 0, None, &p),
        "ARCHIVE_COMPRESSION_RATIO"
    ));
}
#[test]
fn t48_archive_normal() {
    let p = ScanPolicy::default();
    assert!(!archive_entry_findings("folder/x.txt", 10, 9, None, &p)
        .iter()
        .any(|x| x.severity >= mcr_ingest::model::Severity::High));
}
#[test]
fn t49_archive_reserved() {
    let p = ScanPolicy::default();
    assert!(has_code(
        &archive_entry_findings("folder/CON.txt", 1, 1, None, &p),
        "NAME_WINDOWS_RESERVED"
    ));
}
#[test]
fn t50_archive_bidi() {
    let p = ScanPolicy::default();
    assert!(has_code(
        &archive_entry_findings("x\u{202e}fdp.exe", 1, 1, None, &p),
        "NAME_BIDI_OVERRIDE"
    ));
}
#[test]
fn t51_archive_double_extension() {
    let p = ScanPolicy::default();
    assert!(has_code(
        &archive_entry_findings("x.pdf.exe", 1, 1, None, &p),
        "NAME_DOUBLE_EXTENSION"
    ));
}
#[test]
fn t52_archive_entry_limit() {
    let mut p = ScanPolicy::default();
    p.max_archive_entries = 2;
    assert!(has_code(
        &archive_aggregate_findings(3, 0, &p),
        "ARCHIVE_ENTRY_LIMIT"
    ));
}
#[test]
fn t53_archive_total_limit() {
    let mut p = ScanPolicy::default();
    p.max_archive_total_uncompressed_bytes = 2;
    assert!(has_code(
        &archive_aggregate_findings(1, 3, &p),
        "ARCHIVE_TOTAL_UNCOMPRESSED_LIMIT"
    ));
}
#[test]
fn t54_collision_casefold() {
    assert_eq!(collision_key("A/Report.PDF"), collision_key("a/report.pdf"));
}
#[test]
fn t55_sha256_known() {
    assert_eq!(
        sha256_bytes(b"abc"),
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    );
}
#[test]
fn t56_canonical_hash_changes() {
    let a = sha256_canonical_json(&vec!["a"]).unwrap();
    let b = sha256_canonical_json(&vec!["b"]).unwrap();
    assert_ne!(a, b);
}
#[test]
fn t57_end_to_end_manifest_verifies() {
    let td = tempfile::tempdir().unwrap();
    fs::write(td.path().join("evidence.txt"), b"evidence").unwrap();
    let m = scan(td.path(), ScanPolicy::default()).unwrap();
    assert_eq!(m.summary.regular_files, 1);
    assert!(verify_manifest_hash(&m).unwrap());
}
