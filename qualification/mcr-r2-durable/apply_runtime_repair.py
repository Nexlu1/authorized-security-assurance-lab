from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from datetime import datetime, timezone

src = Path(os.environ["MCR_R2_SRC"])
path = src / "src" / "object_store.rs"
text = path.read_text(encoding="utf-8")
old = "    let mut buf = [0u8; 1024 * 1024];"
new = "    let mut buf = vec![0u8; 1024 * 1024];"
count = text.count(old)
if count != 1:
    raise SystemExit(f"expected exactly one 1 MiB stack-buffer target; found {count}")

def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

before = path.read_bytes()
path.write_text(text.replace(old, new), encoding="utf-8", newline="\n")
after = path.read_bytes()
out = Path(os.environ["RUNNER_TEMP"]) / "mcr-r2-compile-evidence"
out.mkdir(parents=True, exist_ok=True)
receipt = {
    "schema": "mcr-r2-runtime-repair-v1",
    "generated_utc": datetime.now(timezone.utc).isoformat(),
    "file": "src/object_store.rs",
    "kind": "stack_safety_repair",
    "reason": "The first real fixture execution overflowed the test thread stack at object-store capture. Move the fixed 1 MiB ingest buffer from stack storage to heap storage without changing read chunk size or hashing semantics.",
    "occurrences": count,
    "before_sha256": sha256_bytes(before),
    "after_sha256": sha256_bytes(after),
}
(out / "RUNTIME_REPAIR.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
print(json.dumps(receipt, indent=2))
