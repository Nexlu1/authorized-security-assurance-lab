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

# qpdf's JSON schema always contains a non-empty `encrypt` object, even for an
# unencrypted PDF. Do not treat object presence as encryption. Only an explicit
# boolean `encrypted: true` or the independent --show-encryption control may do so.
replace_exact(
    pdf,
    '''        if child_count > 0 {\n            if parent.as_deref() == Some("encrypt") {\n                bump(signals, "summary:EncryptionPresent");\n            } else if parent.as_deref() == Some("attachments") {\n                bump(signals, "summary:AttachmentSummaryNonEmpty");\n            }\n        }''',
    '''        if child_count > 0 && parent.as_deref() == Some("attachments") {\n            bump(signals, "summary:AttachmentSummaryNonEmpty");\n        }''',
    2,
    "pdf_encryption_false_positive_repair",
    "qpdf JSON includes an encrypt status object for clean PDFs; object presence must not imply encryption.",
)

replace_exact(
    pdf,
    '''    fn visit_bool<E>(self, _v: bool) -> std::result::Result<(), E> { Ok(()) }''',
    '''    fn visit_bool<E>(self, v: bool) -> std::result::Result<(), E> {\n        if self.current_key.as_deref() == Some("encrypted") && v {\n            bump(self.signals, "summary:EncryptionPresent");\n        }\n        Ok(())\n    }''',
    1,
    "pdf_encryption_boolean_signal",
    "Record encryption only when qpdf JSON explicitly reports encrypted=true.",
)

replace_exact(
    pdf,
    '''    let qpdf_json = derivative_dir.join("qpdf.json");\n    let qpdf_err = derivative_dir.join("qpdf.stderr.txt");\n    let pdfcpu_out = derivative_dir.join("pdfcpu-validate.stdout.txt");''',
    '''    let qpdf_json = derivative_dir.join("qpdf.json");\n    let qpdf_err = derivative_dir.join("qpdf.stderr.txt");\n    let qpdf_encryption_out = derivative_dir.join("qpdf-show-encryption.stdout.txt");\n    let qpdf_encryption_err = derivative_dir.join("qpdf-show-encryption.stderr.txt");\n    let pdfcpu_out = derivative_dir.join("pdfcpu-validate.stdout.txt");''',
    1,
    "pdf_encryption_control_outputs",
    "Retain a separate derivative for qpdf --show-encryption so password-protected PDFs can still be classified without opening them.",
)

anchor = '''    if let Some(note) = qpdf_json_parse_error.as_deref() {\n        qpdf_status = format!("JSON_PARSE_ERROR:{note}");\n    }\n\n    for (signal, count) in &signals {'''
insert = '''    if let Some(note) = qpdf_json_parse_error.as_deref() {\n        qpdf_status = format!("JSON_PARSE_ERROR:{note}");\n    }\n\n    // qpdf JSON requires a valid password for some encrypted files. Run the\n    // hash-qualified read-only encryption summary independently so encryption\n    // state remains discoverable even when the object JSON path is unavailable.\n    let eargs = vec![\n        OsString::from("--show-encryption"),\n        object_path.as_os_str().to_owned(),\n    ];\n    match external_tools::run_to_files(\n        qpdf,\n        &eargs,\n        &qpdf_encryption_out,\n        &qpdf_encryption_err,\n        policy,\n    ) {\n        Ok(run) => {\n            let status = if run.exit_code == Some(0) { "PASS" } else { "ERROR" };\n            record_tool_run(\n                &tx,\n                source_sha256,\n                qpdf,\n                status,\n                Some("qpdf --show-encryption control"),\n                Some(&run),\n            )?;\n            if run.exit_code == Some(0) {\n                let text = fs::read_to_string(&qpdf_encryption_out).unwrap_or_default();\n                if !text.contains("File is not encrypted")\n                    && (text.contains("R = ")\n                        || text.to_ascii_lowercase().contains("encrypted"))\n                {\n                    bump(&mut signals, "summary:EncryptionPresent");\n                }\n            }\n        }\n        Err(err) => {\n            record_tool_run(\n                &tx,\n                source_sha256,\n                qpdf,\n                "RUNNER_ERROR",\n                Some(&format!("qpdf --show-encryption control: {err}")),\n                None,\n            )?;\n        }\n    }\n\n    for (signal, count) in &signals {'''
replace_exact(
    pdf,
    anchor,
    insert,
    1,
    "pdf_encryption_password_fallback",
    "Use qpdf --show-encryption as a separate read-only control when JSON inventory cannot open a password-protected PDF.",
)

# Expand the integration suite to use the seven already-frozen physical fixtures
# that were present but not directly asserted by the 19-test R2 suite.
tests = src / "tests" / "core_integration.rs"
append = r'''

#[test]
fn declared_windows_1252_mail_fixture_is_exercised() {
    let w = temp_workspace("mail-cp1252");
    let conn = database::open(&w).unwrap();
    let o = store(&w, &conn, "mail_cp1252.eml");
    let parsed = mail::index_eml(&conn, &o.object_path, &o.sha256, o.occurrence_id).unwrap();
    assert_eq!(parsed.subject.as_deref(), Some("Preis €"));
    let (after, _) = util::sha256_file(&o.object_path).unwrap();
    assert_eq!(after, o.sha256);
    fs::remove_dir_all(w).ok();
}

#[test]
fn csv_formula_like_cells_remain_literal_derivative_text() {
    let w = temp_workspace("csv-formula");
    let conn = database::open(&w).unwrap();
    let o = store(&w, &conn, "csv_formula_injection.csv");
    let s = csv_ingest::index_csv(&conn, &o.object_path, &o.sha256, o.occurrence_id).unwrap();
    assert_eq!(s.records, 4);
    let mut stmt = conn
        .prepare("SELECT fields_derivative_json FROM csv_record WHERE source_sha256=? ORDER BY record_index")
        .unwrap();
    let rows: Vec<Vec<String>> = stmt
        .query_map([&o.sha256], |r| r.get::<_, String>(0))
        .unwrap()
        .map(|r| serde_json::from_str::<Vec<String>>(&r.unwrap()).unwrap())
        .collect();
    assert_eq!(rows[1][1], "=2+2");
    assert_eq!(rows[2][1], "+cmd");
    assert_eq!(rows[3][1], "@SUM(A1:A2)");
    let (after, _) = util::sha256_file(&o.object_path).unwrap();
    assert_eq!(after, o.sha256);
    fs::remove_dir_all(w).ok();
}

#[test]
fn remaining_frozen_pdf_state_fixtures_are_exercised_when_tools_are_supplied() {
    let Some(qpdf_exe) = std::env::var_os("MCR_QPDF_EXE") else { return; };
    let Some(qpdf_sha) = std::env::var_os("MCR_QPDF_SHA256") else { return; };
    let Some(pdfcpu_exe) = std::env::var_os("MCR_PDFCPU_EXE") else { return; };
    let Some(pdfcpu_sha) = std::env::var_os("MCR_PDFCPU_SHA256") else { return; };

    let cases: [(&str, &[&str]); 5] = [
        ("pdf_launch_action.pdf", &["action:Launch", "key:OpenAction"]),
        ("pdf_embedded_attachment.pdf", &["key:EmbeddedFiles", "summary:AttachmentSummaryNonEmpty"]),
        ("pdf_acroform.pdf", &["key:AcroForm"]),
        ("pdf_encrypted.pdf", &["summary:EncryptionPresent"]),
        ("pdf_optional_content.pdf", &["key:OptionalContent"]),
    ];

    for (name, expected_signals) in cases {
        let w = temp_workspace("pdf-gap");
        let conn = database::open(&w).unwrap();
        let o = store(&w, &conn, name);
        let qpdf = ToolSpec {
            name: "qpdf".to_owned(),
            version: "12.4.1".to_owned(),
            executable: PathBuf::from(&qpdf_exe),
            expected_sha256: qpdf_sha.to_string_lossy().into_owned(),
        };
        let pdfcpu = ToolSpec {
            name: "pdfcpu".to_owned(),
            version: "0.15.0".to_owned(),
            executable: PathBuf::from(&pdfcpu_exe),
            expected_sha256: pdfcpu_sha.to_string_lossy().into_owned(),
        };
        let _summary = pdf::inventory_pdf(&w, &conn, &o.object_path, &o.sha256, &qpdf, &pdfcpu).unwrap();
        for signal in expected_signals {
            let count: i64 = conn
                .query_row(
                    "SELECT COALESCE(SUM(signal_count),0) FROM pdf_signal WHERE source_sha256=? AND signal=?",
                    rusqlite::params![&o.sha256, signal],
                    |r| r.get(0),
                )
                .unwrap();
            assert!(count > 0, "{name} should expose PDF signal {signal}");
        }
        let (after, _) = util::sha256_file(&o.object_path).unwrap();
        assert_eq!(after, o.sha256);
        fs::remove_dir_all(w).ok();
    }
}
'''

before = tests.read_bytes()
text = before.decode("utf-8")
marker = "fn remaining_frozen_pdf_state_fixtures_are_exercised_when_tools_are_supplied()"
if marker in text:
    raise SystemExit("coverage-expansion tests already present")
tests.write_text(text.rstrip() + append + "\n", encoding="utf-8", newline="\n")
after = tests.read_bytes()
repairs.append({
    "file": "tests/core_integration.rs",
    "kind": "fixture_coverage_expansion",
    "reason": "Directly execute the seven already-frozen matrix fixtures that existed but were not asserted by the original 19-test R2 suite.",
    "occurrences": 7,
    "before_sha256": sha256_bytes(before),
    "after_sha256": sha256_bytes(after),
})

receipt = {
    "schema": "mcr-r2-coverage-expansion-v1",
    "generated_utc": datetime.now(timezone.utc).isoformat(),
    "immutable_source_zip_sha256": "a029571403ee89d42848b90e419384e9d9138534b43733b81483ee2d296d7215",
    "purpose": "Correct PDF encryption classification and directly exercise all seven already-existing physical matrix fixtures omitted from the first runtime suite.",
    "repair_records": len(repairs),
    "repairs": repairs,
    "expected_test_count_after_expansion": 22,
    "expected_direct_matrix_fixture_coverage_after_expansion": "34/57",
}
(out / "COVERAGE_EXPANSION_RECEIPT.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
print(json.dumps(receipt, indent=2))
