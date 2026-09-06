from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

src = Path(os.environ["MCR_R2_SRC"])
path = src / "src" / "util.rs"
text = path.read_text(encoding="utf-8")
old = "    let mut buf = [0u8; 1024 * 1024];"
new = "    let mut buf = vec![0u8; 1024 * 1024];"
count = text.count(old)
if count != 1:
    raise SystemExit(f"expected exactly one shared 1 MiB stack hash buffer; found {count}")

before = path.read_bytes()
path.write_text(text.replace(old, new), encoding="utf-8", newline="\n")
after = path.read_bytes()

def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

out = Path(os.environ["RUNNER_TEMP"]) / "mcr-r2-compile-evidence"
out.mkdir(parents=True, exist_ok=True)
receipt = {
    "schema": "mcr-r2-stack-safety-v2",
    "generated_utc": datetime.now(timezone.utc).isoformat(),
    "file": "src/util.rs",
    "kind": "stack_safety_repair",
    "reason": "Windows runtime smoke returned 0xC00000FD STATUS_STACK_OVERFLOW during ingest-file after the object-store buffer had already been moved to the heap. sha256_reader still allocated a separate fixed 1 MiB buffer on the thread stack and is called during source re-open verification. Move only that buffer to heap storage; hashing/read semantics and chunk size remain unchanged.",
    "occurrences": count,
    "before_sha256": sha256(before),
    "after_sha256": sha256(after),
}
(out / "STACK_SAFETY_V2.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
print(json.dumps(receipt, indent=2))
