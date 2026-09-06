from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from datetime import datetime, timezone

src = Path(os.environ["MCR_R2_SRC"])
cargo = src / "Cargo.toml"
text = cargo.read_text(encoding="utf-8")
old = 'rusqlite = { version = "=0.40.1", features = ["bundled"] }'
new = 'rusqlite = { version = "=0.40.2", features = ["bundled"] }'
count = text.count(old)
if count != 1:
    raise SystemExit(f"expected exactly one rusqlite 0.40.1 pin; found {count}")

def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

before = cargo.read_bytes()
cargo.write_text(text.replace(old, new), encoding="utf-8", newline="\n")
after = cargo.read_bytes()
receipt = {
    "schema": "mcr-r2-candidate-dependency-repair-v1",
    "generated_utc": datetime.now(timezone.utc).isoformat(),
    "purpose": "Controlled experiment: replace defective rusqlite 0.40.1 release with upstream 0.40.2 only; immutable R2 source ZIP is unchanged.",
    "upstream": "rusqlite/rusqlite",
    "old_version": "0.40.1",
    "old_tag_commit": "6d3c282dc5531a57eb4e22ece3207f00c95d0fb0",
    "new_version": "0.40.2",
    "new_tag_commit": "e88f112bef7899234a497baed5cc3c3d553deeb8",
    "reason": "0.40.1 calls cfg_select! but does not define the compatibility macro; 0.40.2 adds that macro.",
    "cargo_toml_before_sha256": sha256_bytes(before),
    "cargo_toml_after_sha256": sha256_bytes(after),
    "replacement_count": count,
}
out = Path(os.environ["RUNNER_TEMP"]) / "mcr-r2-compile-evidence"
out.mkdir(parents=True, exist_ok=True)
(out / "CANDIDATE_DEPENDENCY_REPAIR.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
print(json.dumps(receipt, indent=2))
