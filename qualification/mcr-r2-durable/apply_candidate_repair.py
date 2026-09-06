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

repairs = []

# 1. Upstream dependency repair: rusqlite 0.40.1 omitted its cfg_select! compatibility macro.
cargo = src / "Cargo.toml"
text = cargo.read_text(encoding="utf-8")
old = 'rusqlite = { version = "=0.40.1", features = ["bundled"] }'
new = 'rusqlite = { version = "=0.40.2", features = ["bundled"] }'
count = text.count(old)
if count != 1:
    raise SystemExit(f"expected exactly one rusqlite 0.40.1 pin; found {count}")
before = cargo.read_bytes()
cargo.write_text(text.replace(old, new), encoding="utf-8", newline="\n")
after = cargo.read_bytes()
repairs.append({
    "file": "Cargo.toml",
    "kind": "dependency_pin",
    "old": "rusqlite =0.40.1",
    "new": "rusqlite =0.40.2",
    "reason": "0.40.1 calls cfg_select! but omits the compatibility macro; upstream 0.40.2 adds it.",
    "upstream_old_tag_commit": "6d3c282dc5531a57eb4e22ece3207f00c95d0fb0",
    "upstream_new_tag_commit": "e88f112bef7899234a497baed5cc3c3d553deeb8",
    "occurrences": count,
    "before_sha256": sha256_bytes(before),
    "after_sha256": sha256_bytes(after),
})

# 2. Remove one import that Rust 1.88 proves is unused.
pdf = src / "src" / "pdf.rs"
text = pdf.read_text(encoding="utf-8")
old = "use serde::Deserializer as _;\n"
count = text.count(old)
if count != 1:
    raise SystemExit(f"expected exactly one unused PDF Deserializer import; found {count}")
before = pdf.read_bytes()
pdf.write_text(text.replace(old, ""), encoding="utf-8", newline="\n")
after = pdf.read_bytes()
repairs.append({
    "file": "src/pdf.rs",
    "kind": "compile_cleanup",
    "reason": "Remove the single import rejected by -D warnings as unused; no behavior change.",
    "occurrences": count,
    "before_sha256": sha256_bytes(before),
    "after_sha256": sha256_bytes(after),
})

# 3. Keep quick-xml namespace text alive through scan_element calls.
ooxml = src / "src" / "ooxml.rs"
text = ooxml.read_text(encoding="utf-8")
old = '''                let ns = match resolved {\n                    ResolveResult::Bound(ns) => ns.as_ref(),\n                    _ => "",\n                };\n                signals = signals.saturating_add(scan_element(conn, source_sha256, part, ns, e, version)?);'''
new = '''                let ns = match resolved {\n                    ResolveResult::Bound(ns) => ns.as_ref().to_owned(),\n                    _ => String::new(),\n                };\n                signals = signals.saturating_add(scan_element(conn, source_sha256, part, &ns, e, version)?);'''
count = text.count(old)
if count != 2:
    raise SystemExit(f"expected exactly two OOXML namespace lifetime repair targets; found {count}")
before = ooxml.read_bytes()
ooxml.write_text(text.replace(old, new), encoding="utf-8", newline="\n")
after = ooxml.read_bytes()
repairs.append({
    "file": "src/ooxml.rs",
    "kind": "lifetime_repair",
    "reason": "Own the resolved namespace string through scan_element so quick-xml's temporary Namespace value is not borrowed after drop.",
    "occurrences": count,
    "before_sha256": sha256_bytes(before),
    "after_sha256": sha256_bytes(after),
})

receipt = {
    "schema": "mcr-r2-candidate-repair-set-v2",
    "generated_utc": datetime.now(timezone.utc).isoformat(),
    "purpose": "Bounded compile-repair experiment against the immutable durable R2 source ZIP; no original source bytes are overwritten.",
    "immutable_source_zip_sha256": "a029571403ee89d42848b90e419384e9d9138534b43733b81483ee2d296d7215",
    "repair_count": len(repairs),
    "replacement_occurrences": sum(int(r["occurrences"]) for r in repairs),
    "repairs": repairs,
}
(out / "CANDIDATE_REPAIR_SET.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
print(json.dumps(receipt, indent=2))
