from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

src = Path(os.environ["MCR_R2_SRC"])
path = src / "src" / "util.rs"
old = path.read_bytes()
old_text = old.decode("utf-8")
needle = "let mut buf = [0u8; 1024 * 1024];"
replacement = "let mut buf = vec![0u8; 1024 * 1024];"
count = old_text.count(needle)
if count != 1:
    raise SystemExit(f"expected exactly one SHA-256 stack buffer, found {count}")
new_text = old_text.replace(needle, replacement, 1)
path.write_text(new_text, encoding="utf-8")
new = path.read_bytes()
receipt = {
    "schema": "mcr-r2-sha256-stack-repair-v1",
    "generated_utc": datetime.now(timezone.utc).isoformat(),
    "file": "src/util.rs",
    "kind": "stack_safety_repair",
    "reason": "sha256_reader retained a 1 MiB fixed array on the caller thread stack; store_file invokes sha256_file for its second-read verification, so Windows ingest still overflowed after the object_store buffer was moved to the heap. Preserve the 1 MiB chunk size but allocate the verifier buffer on the heap.",
    "occurrences": 1,
    "before_sha256": hashlib.sha256(old).hexdigest(),
    "after_sha256": hashlib.sha256(new).hexdigest(),
}
out = Path(os.environ.get("RUNNER_TEMP", ".")) / "MCR_SHA256_STACK_REPAIR_RECEIPT.json"
out.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
print(json.dumps(receipt, indent=2))
