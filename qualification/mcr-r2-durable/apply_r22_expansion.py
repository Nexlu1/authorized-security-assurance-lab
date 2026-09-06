from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from datetime import datetime, timezone

src = Path(os.environ["MCR_R2_SRC"])
out = Path(os.environ["RUNNER_TEMP"]) / "mcr-r2-compile-evidence"
out.mkdir(parents=True, exist_ok=True)
repairs = []


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def replace_exact(path: Path, old: str, new: str, expected: int, kind: str, reason: str):
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != expected:
        raise SystemExit(f"expected {expected} target(s) in {path.relative_to(src)}, found {count}: {reason}")
    before = path.read_bytes()
    path.write_text(text.replace(old, new), encoding="utf-8", newline="\n")
    after = path.read_bytes()
    repairs.append({
        "file": path.relative_to(src).as_posix(),
        "kind": kind,
        "reason": reason,
        "occurrences": count,
        "before_sha256": sha256_bytes(before),
        "after_sha256": sha256_bytes(after),
    })

pdf = src / "src" / "pdf.rs"

# Make annotation/signature subtype state explicit rather than relying only on
# surrounding dictionary keys.
replace_exact(
    pdf,
    '''        "/Rendition" => Some("action:Rendition"),\n        "/Movie" => Some("action:Movie"),\n        "/Sound" => Some("action:Sound"),''',
    '''        "/Rendition" => Some("action:Rendition"),\n        "/RichMedia" => Some("annotation:RichMedia"),\n        "/Screen" => Some("annotation:Screen"),\n        "/FileAttachment" => Some("annotation:FileAttachment"),\n        "/Sig" => Some("type:Signature"),\n        "/Movie" => Some("action:Movie"),\n        "/Sound" => Some("action:Sound"),''',
    1,
    "pdf_subtype_precision",
    "Record high-risk annotation/signature subtype values explicitly in qpdf JSON inventory.",
)

# pdfcpu rejects extensionless inputs even when the bytes are a valid PDF. The
# content-addressed authority path intentionally has no extension, so validate a
# byte-identical disposable derivative named .pdf. Never rename/mutate authority.
old = '''    let pargs = vec![\n        OsString::from("validate"),\n        OsString::from("--mode"),\n        OsString::from("strict"),\n        object_path.as_os_str().to_owned(),\n    ];\n    let pdfcpu_status = match external_tools::run_to_files(pdfcpu, &pargs, &pdfcpu_out, &pdfcpu_err, policy) {'''
new = '''    let pdfcpu_input = derivative_dir.join("pdfcpu-input.pdf");\n    fs::copy(object_path, &pdfcpu_input)?;\n    let (pdfcpu_input_sha, _) = util::sha256_file(&pdfcpu_input)?;\n    if pdfcpu_input_sha != source_sha256 {\n        return Err("pdfcpu disposable input copy SHA-256 does not match authority object".into());\n    }\n    let pargs = vec![\n        OsString::from("validate"),\n        OsString::from("--mode"),\n        OsString::from("strict"),\n        pdfcpu_input.as_os_str().to_owned(),\n    ];\n    let pdfcpu_status = match external_tools::run_to_files(pdfcpu, &pargs, &pdfcpu_out, &pdfcpu_err, policy) {'''
replace_exact(
    pdf,
    old,
    new,
    1,
    "pdfcpu_extension_compatibility",
    "Validate a byte-identical .pdf derivative because pdfcpu rejects the SHA-only authority object path solely for lacking a .pdf extension.",
)

old = '''    tx.commit()?;\n    let risk_hits = signals.values().copied().sum();'''
new = '''    let (pdfcpu_input_after_sha, _) = util::sha256_file(&pdfcpu_input)?;\n    if pdfcpu_input_after_sha != source_sha256 {\n        return Err("pdfcpu altered its disposable validation input".into());\n    }\n    fs::remove_file(&pdfcpu_input)?;\n    let (authority_after_sha, _) = util::sha256_file(object_path)?;\n    if authority_after_sha != source_sha256 {\n        return Err("PDF authority object changed during specialist inventory".into());\n    }\n\n    tx.commit()?;\n    let risk_hits = signals.values().copied().sum();'''
replace_exact(
    pdf,
    old,
    new,
    1,
    "pdf_specialist_source_immutability",
    "Verify both disposable pdfcpu input and authority object hashes after specialist execution, then delete the disposable duplicate.",
)

# Add direct tests for MAIL-003, MAIL-004 and seven remaining constructible PDF cases.
tests = src / "tests" / "core_integration.rs"
before = tests.read_bytes()
text = before.decode("utf-8")
marker = "fn r22_empty_mbox_and_mutation_are_content_hash_bound()"
if marker in text:
    raise SystemExit("R2.2 tests already present")
append = r'''

#[test]
fn r22_empty_mbox_and_mutation_are_content_hash_bound() {
    let w = temp_workspace("mbox-empty");
    let conn = database::open(&w).unwrap();
    let empty = store(&w, &conn, "mail_empty.mbox");
    assert_eq!(empty.size, 0);
    assert_eq!(mbox::index_mbox(&conn, &empty.object_path, &empty.sha256, empty.occurrence_id).unwrap(), 0);
    let rows: i64 = conn.query_row("SELECT COUNT(*) FROM mail_message WHERE source_sha256=?", [&empty.sha256], |r| r.get(0)).unwrap();
    assert_eq!(rows, 0);
    fs::remove_dir_all(&w).ok();

    let w = temp_workspace("mbox-mutation");
    let conn = database::open(&w).unwrap();
    let source = w.join("mutable-source.mbox");
    fs::copy(fixture("mail_mutation_base.mbox"), &source).unwrap();
    let first = object_store::store_file(&w, &conn, &source).unwrap();
    assert_eq!(mbox::index_mbox(&conn, &first.object_path, &first.sha256, first.occurrence_id).unwrap(), 5);
    let mut bytes = fs::read(&source).unwrap();
    bytes.extend_from_slice(b"From sender6@example.invalid Sat Jan 06 00:00:00 2024\nFrom: sender6@example.invalid\nTo: target@example.invalid\nSubject: Synthetic mutation message 6\nMessage-ID: <mutation-6@example.invalid>\n\nBody 6\n");
    fs::write(&source, bytes).unwrap();
    let second = object_store::store_file(&w, &conn, &source).unwrap();
    assert_ne!(first.sha256, second.sha256, "mutated MBOX must become a new content authority object");
    assert_eq!(mbox::index_mbox(&conn, &second.object_path, &second.sha256, second.occurrence_id).unwrap(), 6);
    let first_rows: i64 = conn.query_row("SELECT COUNT(*) FROM mail_message WHERE source_sha256=?", [&first.sha256], |r| r.get(0)).unwrap();
    let second_rows: i64 = conn.query_row("SELECT COUNT(*) FROM mail_message WHERE source_sha256=?", [&second.sha256], |r| r.get(0)).unwrap();
    assert_eq!(first_rows, 5);
    assert_eq!(second_rows, 6);
    fs::remove_dir_all(w).ok();
}

#[test]
fn r22_remaining_constructible_pdf_matrix_states_are_detected() {
    let Some(qpdf_exe) = std::env::var_os("MCR_QPDF_EXE") else { return; };
    let Some(qpdf_sha) = std::env::var_os("MCR_QPDF_SHA256") else { return; };
    let Some(pdfcpu_exe) = std::env::var_os("MCR_PDFCPU_EXE") else { return; };
    let Some(pdfcpu_sha) = std::env::var_os("MCR_PDFCPU_SHA256") else { return; };

    let cases: [(&str, &[&str]); 7] = [
        ("pdf_javascript_nametree.pdf", &["key:JavaScriptNameOrAction", "action:JavaScript"]),
        ("pdf_open_action.pdf", &["key:OpenAction", "action:JavaScript"]),
        ("pdf_additional_actions.pdf", &["key:AdditionalActions", "action:JavaScript"]),
        ("pdf_uri_action.pdf", &["key:URI", "action:URI"]),
        ("pdf_file_attachment_annotation.pdf", &["annotation:FileAttachment", "key:EmbeddedFileDictionary"]),
        ("pdf_richmedia_annotation.pdf", &["annotation:RichMedia", "key:RichMedia"]),
        ("pdf_signature_state.pdf", &["type:Signature", "key:SignatureByteRange"]),
    ];

    for (name, expected_signals) in cases {
        let w = temp_workspace("pdf-r22");
        let conn = database::open(&w).unwrap();
        let o = store(&w, &conn, name);
        let qpdf = ToolSpec {
            name: "qpdf".to_owned(), version: "12.4.1".to_owned(),
            executable: PathBuf::from(&qpdf_exe), expected_sha256: qpdf_sha.to_string_lossy().into_owned(),
        };
        let pdfcpu = ToolSpec {
            name: "pdfcpu".to_owned(), version: "0.15.0".to_owned(),
            executable: PathBuf::from(&pdfcpu_exe), expected_sha256: pdfcpu_sha.to_string_lossy().into_owned(),
        };
        let summary = pdf::inventory_pdf(&w, &conn, &o.object_path, &o.sha256, &qpdf, &pdfcpu).unwrap();
        assert_eq!(summary.pdfcpu_status, "STRICT_VALID", "{name} should reach real strict pdfcpu validation through the safe .pdf derivative");
        for signal in expected_signals {
            let count: i64 = conn.query_row(
                "SELECT COALESCE(SUM(signal_count),0) FROM pdf_signal WHERE source_sha256=? AND signal=?",
                rusqlite::params![&o.sha256, signal], |r| r.get(0),
            ).unwrap();
            assert!(count > 0, "{name} should expose PDF signal {signal}");
        }
        let (after, _) = util::sha256_file(&o.object_path).unwrap();
        assert_eq!(after, o.sha256);
        fs::remove_dir_all(w).ok();
    }
}
'''
tests.write_text(text.rstrip() + append + "\n", encoding="utf-8", newline="\n")
after = tests.read_bytes()
repairs.append({
    "file": "tests/core_integration.rs",
    "kind": "fixture_r2_2_coverage_expansion",
    "reason": "Directly exercise MAIL-003, MAIL-004 and PDF-002/003/004/006/008/010/011 from the R2.2 synthetic successor corpus.",
    "occurrences": 9,
    "before_sha256": sha256_bytes(before),
    "after_sha256": sha256_bytes(after),
})

receipt = {
    "schema": "mcr-r2-r2-2-expansion-v1",
    "generated_utc": datetime.now(timezone.utc).isoformat(),
    "immutable_source_zip_sha256": "a029571403ee89d42848b90e419384e9d9138534b43733b81483ee2d296d7215",
    "purpose": "Fix pdfcpu extension-only incompatibility and expand direct controlled matrix coverage to 48/57 using synthetic R2.2 fixtures.",
    "repair_records": len(repairs),
    "repairs": repairs,
    "expected_test_count_after_expansion": 26,
    "expected_direct_matrix_fixture_coverage_after_expansion": "48/57",
}
(out / "R2_2_EXPANSION_RECEIPT.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
print(json.dumps(receipt, indent=2))
