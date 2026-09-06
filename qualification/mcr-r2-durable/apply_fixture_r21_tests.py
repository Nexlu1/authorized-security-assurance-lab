from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from datetime import datetime, timezone

src = Path(os.environ["MCR_R2_SRC"])
out = Path(os.environ["RUNNER_TEMP"]) / "mcr-r2-compile-evidence"
out.mkdir(parents=True, exist_ok=True)
tests = src / "tests" / "core_integration.rs"
before = tests.read_bytes()
text = before.decode("utf-8")
marker = "fn ooxml_r21_webhidden_comments_customxml_embedded_and_clean_baseline()"
if marker in text:
    raise SystemExit("R2.1 fixture tests already present")

append = r'''

#[test]
fn ooxml_r21_webhidden_comments_customxml_embedded_and_clean_baseline() {
    let w = temp_workspace("oox-r21-clean");
    let conn = database::open(&w).unwrap();
    let clean = store(&w, &conn, "oox_clean.docx");
    archive::inventory_zip(&conn, &clean.object_path, &clean.sha256).unwrap();
    let summary = ooxml::inventory_ooxml(
        &conn,
        &clean.object_path,
        &clean.sha256,
        ooxml::OoxmlPolicy::default(),
    )
    .unwrap();
    assert_eq!(summary.signals, 0, "corrected clean OOXML baseline must have zero policy signals");
    fs::remove_dir_all(w).ok();

    assert!(ooxml_signal_count("oox_webhidden.docx", "word:hidden_text_webhidden") > 0);
    assert!(ooxml_signal_count("oox_comments.docx", "package:comments_part") > 0);
    assert!(ooxml_signal_count("oox_comments.docx", "word:comment_state") > 0);
    assert!(ooxml_signal_count("oox_custom_xml_binding.docx", "package:custom_xml") > 0);
    assert!(ooxml_signal_count("oox_custom_xml_binding.docx", "word:data_binding") > 0);
    assert!(ooxml_signal_count("oox_embedded_package.docx", "package:embedded_object_or_package") > 0);
}

#[test]
fn unlabelled_legacy_text_is_only_a_provenanced_guess() {
    let bytes = fs::read(fixture("text_unlabelled_cp1252.txt")).unwrap();
    let decoded = text_decode::decode(&bytes, None);
    assert_eq!(decoded.provenance["method"], "guessed_fallback");
    assert!(decoded.provenance["warning"].as_str().is_some_and(|v| v.contains("derivative heuristic")));
    assert_ne!(decoded.text.as_bytes(), bytes.as_slice(), "decoded derivative must not be confused with raw source bytes");
}
'''

tests.write_text(text.rstrip() + append + "\n", encoding="utf-8", newline="\n")
after = tests.read_bytes()
receipt = {
    "schema": "mcr-r2-fixture-r2-1-test-expansion-v1",
    "generated_utc": datetime.now(timezone.utc).isoformat(),
    "purpose": "Exercise the corrected clean OOXML baseline plus OOX-004, OOX-007, OOX-008, OOX-011 and TXT-003 from the synthetic R2.1 successor fixture corpus.",
    "source_file": "tests/core_integration.rs",
    "before_sha256": hashlib.sha256(before).hexdigest(),
    "after_sha256": hashlib.sha256(after).hexdigest(),
    "expected_test_count_after_expansion": 24,
    "expected_direct_matrix_fixture_coverage_after_expansion": "39/57",
}
(out / "FIXTURE_R2_1_TEST_EXPANSION_RECEIPT.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
print(json.dumps(receipt, indent=2))
