from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from datetime import datetime, timezone

src = Path(os.environ["MCR_R2_SRC"])
out = Path(os.environ["RUNNER_TEMP"]) / "mcr-r2-compile-evidence"
out.mkdir(parents=True, exist_ok=True)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def replace_exact(path: Path, old: str, new: str, expected: int, kind: str, reason: str, **extra):
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != expected:
        raise SystemExit(
            f"expected exactly {expected} repair target(s) in {path.relative_to(src)}; found {count}: {reason}"
        )
    before = path.read_bytes()
    path.write_text(text.replace(old, new), encoding="utf-8", newline="\n")
    after = path.read_bytes()
    row = {
        "file": path.relative_to(src).as_posix(),
        "kind": kind,
        "reason": reason,
        "occurrences": count,
        "before_sha256": sha256_bytes(before),
        "after_sha256": sha256_bytes(after),
    }
    row.update(extra)
    repairs.append(row)


repairs = []

# 1. Upstream dependency repair: rusqlite 0.40.1 omitted its cfg_select! compatibility macro.
replace_exact(
    src / "Cargo.toml",
    'rusqlite = { version = "=0.40.1", features = ["bundled"] }',
    'rusqlite = { version = "=0.40.2", features = ["bundled"] }',
    1,
    "dependency_pin",
    "0.40.1 calls cfg_select! but omits the compatibility macro; upstream 0.40.2 adds it.",
    dependency_old="rusqlite =0.40.1",
    dependency_new="rusqlite =0.40.2",
    upstream_old_tag_commit="6d3c282dc5531a57eb4e22ece3207f00c95d0fb0",
    upstream_new_tag_commit="e88f112bef7899234a497baed5cc3c3d553deeb8",
)

# 2. Remove one import that Rust 1.88 proves is unused.
replace_exact(
    src / "src" / "pdf.rs",
    "use serde::Deserializer as _;\n",
    "",
    1,
    "compile_cleanup",
    "Remove the single import rejected by -D warnings as unused; no behavior change.",
)

# 3. Keep quick-xml namespace text alive through scan_element calls.
replace_exact(
    src / "src" / "ooxml.rs",
    '''                let ns = match resolved {\n                    ResolveResult::Bound(ns) => ns.as_ref(),\n                    _ => "",\n                };\n                signals = signals.saturating_add(scan_element(conn, source_sha256, part, ns, e, version)?);''',
    '''                let ns = match resolved {\n                    ResolveResult::Bound(ns) => ns.as_ref().to_owned(),\n                    _ => String::new(),\n                };\n                signals = signals.saturating_add(scan_element(conn, source_sha256, part, &ns, e, version)?);''',
    2,
    "lifetime_repair",
    "Own the resolved namespace string through scan_element so quick-xml's temporary Namespace value is not borrowed after drop.",
)

# 4. Let rawzip entry iteration end naturally at its last use instead of explicitly dropping a non-Drop iterator.
replace_exact(
    src / "src" / "archive.rs",
    "    drop(entries);\n\n",
    "\n",
    1,
    "lifetime_cleanup",
    "Remove explicit drop(entries); NLL ends the iterator borrow at its final use and Clippy rejects drop on this non-Drop type.",
)

# 5. Lock files are intentionally retained; make non-truncation explicit.
for rel in ("src/audit.rs", "src/workspace_lock.rs"):
    replace_exact(
        src / rel,
        "            .create(true)\n            .read(true)\n",
        "            .create(true)\n            .truncate(false)\n            .read(true)\n",
        1,
        "open_options_intent",
        "Make the lock-file non-truncation policy explicit; lock files must not be truncated when reopened.",
    )

# 6. Apply only the Clippy format-argument modernizations surfaced by the strict gate.
replace_exact(
    src / "src" / "audit.rs",
    '''            return Err(format!(\n                "audit recovery refused: JSONL head {:?} does not match pending event predecessor {:?}",\n                file_head, previous\n            ).into());''',
    '''            return Err(format!(\n                "audit recovery refused: JSONL head {file_head:?} does not match pending event predecessor {previous:?}"\n            ).into());''',
    1,
    "format_cleanup",
    "Use captured format arguments; message and values are unchanged.",
)

replace_exact(
    src / "src" / "mbox.rs",
    'Some(n) => format!("{}; header-prefix candidate ceiling reached or header terminator absent", n),',
    'Some(n) => format!("{n}; header-prefix candidate ceiling reached or header terminator absent"),',
    1,
    "format_cleanup",
    "Use captured format argument; emitted parser note is unchanged.",
)

replace_exact(
    src / "src" / "main.rs",
    'println!("PASS sha256={} size={}", actual, size);',
    'println!("PASS sha256={actual} size={size}");',
    1,
    "format_cleanup",
    "Use captured format arguments; CLI PASS output is unchanged.",
)

# 7. The duplicate-message integration test must borrow the digest for repeated SQL queries instead of moving it.
replace_exact(
    src / "tests" / "core_integration.rs",
    "[d.sha256]",
    "[&d.sha256]",
    2,
    "test_ownership_repair",
    "Borrow the same captured SHA-256 in two duplicate-message queries; preserves the test value for the second assertion.",
)

receipt = {
    "schema": "mcr-r2-candidate-repair-set-v4",
    "generated_utc": datetime.now(timezone.utc).isoformat(),
    "purpose": "Bounded compile-repair experiment against the immutable durable R2 source ZIP; no original source bytes are overwritten.",
    "immutable_source_zip_sha256": "a029571403ee89d42848b90e419384e9d9138534b43733b81483ee2d296d7215",
    "repair_count": len(repairs),
    "replacement_occurrences": sum(int(r["occurrences"]) for r in repairs),
    "repairs": repairs,
}
(out / "CANDIDATE_REPAIR_SET.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
print(json.dumps(receipt, indent=2))
