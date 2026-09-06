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

mail = src / "src" / "mail.rs"

# Add bounded raw-byte preflight notes before the MIME parser. These notes do
# not replace parser output; they explain potentially lossy/ambiguous derivative
# behavior while the raw object remains authority.
anchor = '''pub struct ParsedMail {\n    pub message_id: Option<String>,\n    pub subject: Option<String>,\n    pub date_text: Option<String>,\n    pub in_reply_to: Vec<String>,\n    pub references: Vec<String>,\n    pub status: String,\n    pub note: Option<String>,\n}\n\npub fn parse_message_bytes(bytes: &[u8]) -> ParsedMail {\n    match MessageParser::default().parse(bytes) {'''
replacement = '''pub struct ParsedMail {\n    pub message_id: Option<String>,\n    pub subject: Option<String>,\n    pub date_text: Option<String>,\n    pub in_reply_to: Vec<String>,\n    pub references: Vec<String>,\n    pub status: String,\n    pub note: Option<String>,\n}\n\nfn append_note(note: &mut Option<String>, value: &str) {\n    *note = Some(match note.take() {\n        Some(existing) => format!("{existing}; {value}"),\n        None => value.to_owned(),\n    });\n}\n\nfn raw_preflight_notes(bytes: &[u8]) -> Vec<&'static str> {\n    let header_end = bytes\n        .windows(4)\n        .position(|w| w == b"\\r\\n\\r\\n")\n        .map(|i| i + 4)\n        .or_else(|| bytes.windows(2).position(|w| w == b"\\n\\n").map(|i| i + 2));\n    let split = header_end.unwrap_or(bytes.len());\n    let header = &bytes[..split];\n    let body = &bytes[split..];\n    let mut notes = Vec::new();\n\n    if header.windows(2).any(|w| w == b"=?") && header.windows(2).any(|w| w == b"?=") {\n        notes.push("RFC2047 encoded-word header decoded only into derivative fields by mail-parser; raw source bytes retained");\n    }\n\n    let malformed_header = header.split(|b| *b == b'\\n').any(|line| {\n        let line = line.strip_suffix(b"\\r").unwrap_or(line);\n        !line.is_empty()\n            && !matches!(line.first(), Some(b' ' | b'\\t'))\n            && !line.contains(&b':')\n    });\n    if malformed_header {\n        notes.push("malformed header line without colon observed; parser result is derivative and raw source remains authoritative");\n    }\n    if header.iter().any(|b| *b < 0x20 && !matches!(*b, b'\\r' | b'\\n' | b'\\t')) {\n        notes.push("control byte observed in message header; parser result is derivative and raw source remains authoritative");\n    }\n\n    let header_text = String::from_utf8_lossy(header).to_ascii_lowercase();\n    if header_text.contains("content-transfer-encoding: base64") {\n        let compact: Vec<u8> = body.iter().copied().filter(|b| !b.is_ascii_whitespace()).collect();\n        let alphabet_ok = compact.iter().all(|b| b.is_ascii_alphanumeric() || matches!(*b, b'+' | b'/' | b'='));\n        let padding_pos = compact.iter().position(|b| *b == b'=');\n        let padding_ok = padding_pos.is_none_or(|i| compact[i..].iter().all(|b| *b == b'=') && compact.len() - i <= 2);\n        if !alphabet_ok || !padding_ok || compact.len() % 4 != 0 {\n            notes.push("invalid base64 transfer-encoding syntax observed; decoded derivative must not replace raw body bytes");\n        }\n    } else if header_text.contains("content-transfer-encoding: quoted-printable") {\n        let mut invalid = false;\n        let mut i = 0usize;\n        while i < body.len() {\n            if body[i] == b'=' {\n                let valid = if i + 1 < body.len() && body[i + 1] == b'\\n' {\n                    true\n                } else if i + 2 < body.len() && body[i + 1] == b'\\r' && body[i + 2] == b'\\n' {\n                    true\n                } else if i + 2 < body.len() {\n                    body[i + 1].is_ascii_hexdigit() && body[i + 2].is_ascii_hexdigit()\n                } else {\n                    false\n                };\n                if !valid { invalid = true; break; }\n            }\n            i += 1;\n        }\n        if invalid {\n            notes.push("invalid quoted-printable transfer-encoding syntax observed; decoded derivative must not replace raw body bytes");\n        }\n    }\n    notes\n}\n\npub fn parse_message_bytes(bytes: &[u8]) -> ParsedMail {\n    let preflight = raw_preflight_notes(bytes);\n    let mut parsed = match MessageParser::default().parse(bytes) {'''
replace_exact(mail, anchor, replacement, 1, "mail_raw_preflight", "Add bounded provenance/warning checks for RFC2047, malformed headers/control bytes and invalid transfer-encoding syntax.")

old = '''        None => ParsedMail {\n            message_id: None,\n            subject: None,\n            date_text: None,\n            in_reply_to: Vec::new(),\n            references: Vec::new(),\n            status: "UNPARSED".to_owned(),\n            note: Some("mail-parser returned None; raw bytes remain authoritative".to_owned()),\n        },\n    }\n}'''
new = '''        None => ParsedMail {\n            message_id: None,\n            subject: None,\n            date_text: None,\n            in_reply_to: Vec::new(),\n            references: Vec::new(),\n            status: "UNPARSED".to_owned(),\n            note: Some("mail-parser returned None; raw bytes remain authoritative".to_owned()),\n        },\n    };\n    for value in preflight {\n        append_note(&mut parsed.note, value);\n    }\n    parsed\n}'''
replace_exact(mail, old, new, 1, "mail_preflight_note_merge", "Merge bounded raw preflight warnings into parser provenance without altering raw bytes.")

mbox = src / "src" / "mbox.rs"
old = '''        if prefix_incomplete {\n            parsed.note = Some(match parsed.note {\n                Some(n) => format!("{n}; header-prefix candidate ceiling reached or header terminator absent"),\n                None => "header-prefix candidate ceiling reached or header terminator absent".to_owned(),\n            });\n        }\n        mail::insert_mail_row(&tx, source_sha256, occurrence_id, ordinal, Some((start,end)), &raw_hash, &parsed)?;'''
new = '''        if prefix_incomplete {\n            parsed.note = Some(match parsed.note {\n                Some(n) => format!("{n}; header-prefix candidate ceiling reached or header terminator absent"),\n                None => "header-prefix candidate ceiling reached or header terminator absent".to_owned(),\n            });\n        }\n        if ranges.len() > 1 {\n            let warning = "MBOX From_ boundary matched deterministic envelope grammar; the format cannot prove whether an unescaped body line was intended, so the full MBOX bytes and source SHA remain authority";\n            parsed.note = Some(match parsed.note {\n                Some(n) => format!("{n}; {warning}"),\n                None => warning.to_owned(),\n            });\n        }\n        mail::insert_mail_row(&tx, source_sha256, occurrence_id, ordinal, Some((start,end)), &raw_hash, &parsed)?;'''
replace_exact(mbox, old, new, 1, "mbox_boundary_ambiguity_provenance", "Record deterministic From_ boundary ambiguity on multi-message MBOX derivatives while preserving full source authority.")

# Add direct tests for the final non-resource synthetic cases.
tests = src / "tests" / "core_integration.rs"
before = tests.read_bytes()
text = before.decode("utf-8")
marker = "fn r23_mail_warning_provenance_cases_are_explicit()"
if marker in text:
    raise SystemExit("R2.3 tests already present")
append = r'''

#[test]
fn r23_mbox_unescaped_from_ambiguity_is_explicit_and_no_bytes_are_dropped() {
    let source = fixture("mail_unescaped_from_ambiguity.mbox");
    let ranges = mbox::scan_ranges(&source).unwrap();
    assert_eq!(ranges.len(), 2, "deterministic envelope grammar should classify the ambiguous From_ line as a boundary");
    assert_eq!(ranges[0].0, 0);
    assert_eq!(ranges[0].1, ranges[1].0);
    assert_eq!(ranges[1].1, fs::metadata(&source).unwrap().len());

    let w = temp_workspace("mbox-ambiguity");
    let conn = database::open(&w).unwrap();
    let o = store(&w, &conn, "mail_unescaped_from_ambiguity.mbox");
    assert_eq!(mbox::index_mbox(&conn, &o.object_path, &o.sha256, o.occurrence_id).unwrap(), 2);
    let warning_rows: i64 = conn.query_row(
        "SELECT COUNT(*) FROM mail_message WHERE source_sha256=? AND parser_note LIKE '%From_ boundary matched deterministic envelope grammar%'",
        [&o.sha256], |r| r.get(0),
    ).unwrap();
    assert_eq!(warning_rows, 2);
    let (after, _) = util::sha256_file(&o.object_path).unwrap();
    assert_eq!(after, o.sha256);
    fs::remove_dir_all(w).ok();
}

#[test]
fn r23_mail_warning_provenance_cases_are_explicit() {
    let cases = [
        ("mail_rfc2047.eml", "RFC2047 encoded-word", Some("Synthetic € Header")),
        ("mail_arbitrary_bytes.eml", "control byte observed", None),
        ("mail_malformed_rfc822.eml", "malformed header line without colon", None),
        ("mail_invalid_base64.eml", "invalid base64 transfer-encoding syntax", Some("Invalid transfer encoding")),
    ];
    for (name, warning, expected_subject) in cases {
        let w = temp_workspace("mail-r23");
        let conn = database::open(&w).unwrap();
        let o = store(&w, &conn, name);
        let parsed = mail::index_eml(&conn, &o.object_path, &o.sha256, o.occurrence_id).unwrap();
        if let Some(subject) = expected_subject { assert_eq!(parsed.subject.as_deref(), Some(subject)); }
        let note = parsed.note.as_deref().unwrap_or("");
        assert!(note.contains(warning), "{name} should record warning/provenance containing {warning:?}; got {note:?}");
        let (after, _) = util::sha256_file(&o.object_path).unwrap();
        assert_eq!(after, o.sha256);
        fs::remove_dir_all(w).ok();
    }
}

#[test]
fn r23_damaged_pdf_xref_terminates_with_controlled_recovery_status() {
    let Some(qpdf_exe) = std::env::var_os("MCR_QPDF_EXE") else { return; };
    let Some(qpdf_sha) = std::env::var_os("MCR_QPDF_SHA256") else { return; };
    let Some(pdfcpu_exe) = std::env::var_os("MCR_PDFCPU_EXE") else { return; };
    let Some(pdfcpu_sha) = std::env::var_os("MCR_PDFCPU_SHA256") else { return; };
    let w = temp_workspace("pdf-damaged-xref");
    let conn = database::open(&w).unwrap();
    let o = store(&w, &conn, "pdf_damaged_xref.pdf");
    let qpdf = ToolSpec { name: "qpdf".to_owned(), version: "12.4.1".to_owned(), executable: PathBuf::from(qpdf_exe), expected_sha256: qpdf_sha.to_string_lossy().into_owned() };
    let pdfcpu = ToolSpec { name: "pdfcpu".to_owned(), version: "0.15.0".to_owned(), executable: PathBuf::from(pdfcpu_exe), expected_sha256: pdfcpu_sha.to_string_lossy().into_owned() };
    let summary = pdf::inventory_pdf(&w, &conn, &o.object_path, &o.sha256, &qpdf, &pdfcpu).unwrap();
    assert_eq!(summary.qpdf_status, "PASS_WITH_WARNINGS");
    assert_eq!(summary.pdfcpu_status, "STRICT_INVALID_OR_ERROR");
    let (after, _) = util::sha256_file(&o.object_path).unwrap();
    assert_eq!(after, o.sha256);
    fs::remove_dir_all(w).ok();
}
'''
tests.write_text(text.rstrip() + append + "\n", encoding="utf-8", newline="\n")
after = tests.read_bytes()
repairs.append({
    "file": "tests/core_integration.rs",
    "kind": "fixture_r2_3_coverage_expansion",
    "reason": "Directly exercise MAIL-002/005/007/008/010 and PDF-014 from the R2.3 synthetic successor corpus.",
    "occurrences": 6,
    "before_sha256": sha256_bytes(before),
    "after_sha256": sha256_bytes(after),
})

receipt = {
    "schema": "mcr-r2-r2-3-expansion-v1",
    "generated_utc": datetime.now(timezone.utc).isoformat(),
    "immutable_source_zip_sha256": "a029571403ee89d42848b90e419384e9d9138534b43733b81483ee2d296d7215",
    "purpose": "Expand all currently non-resource synthetic cases to 54/57 with explicit mail warning provenance and damaged-PDF controlled recovery.",
    "repair_records": len(repairs),
    "repairs": repairs,
    "expected_test_count_after_expansion": 29,
    "expected_direct_matrix_fixture_coverage_after_expansion": "54/57",
    "remaining_cases": ["ARC-008", "ARC-009", "ARC-011"],
}
(out / "R2_3_EXPANSION_RECEIPT.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
print(json.dumps(receipt, indent=2))
