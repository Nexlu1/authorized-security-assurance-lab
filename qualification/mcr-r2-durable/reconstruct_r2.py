from __future__ import annotations

import base64
import hashlib
import os
from pathlib import Path
import shutil
import zipfile

HERE = Path(__file__).resolve().parent
EXPECTED_SHA256 = "a029571403ee89d42848b90e419384e9d9138534b43733b81483ee2d296d7215"
EXPECTED_PARTS = [HERE / f"source-payload.part{i:02d}" for i in range(16)]

missing = [str(p) for p in EXPECTED_PARTS if not p.is_file()]
if missing:
    raise SystemExit(f"missing exact source payload part(s): {missing}")

encoded = "".join(p.read_text(encoding="utf-8").strip() for p in EXPECTED_PARTS)
raw = base64.b64decode(encoded, validate=True)
actual = hashlib.sha256(raw).hexdigest()
if actual != EXPECTED_SHA256:
    raise SystemExit(f"source ZIP SHA-256 mismatch: expected {EXPECTED_SHA256}, got {actual}")

runner_temp = Path(os.environ["RUNNER_TEMP"])
zip_path = runner_temp / "mcr-r2-durable-source.zip"
src = runner_temp / "mcr-r2-durable-src"
zip_path.write_bytes(raw)
if src.exists():
    shutil.rmtree(src)
src.mkdir(parents=True)
with zipfile.ZipFile(zip_path, "r") as zf:
    bad = zf.testzip()
    if bad is not None:
        raise SystemExit(f"source ZIP CRC/read failure at {bad}")
    zf.extractall(src)

required = ["Cargo.toml", "rust-toolchain.toml", "src/lib.rs", "src/pdf.rs", "src/ooxml.rs", "src/mbox.rs", "tests/core_integration.rs"]
absent = [name for name in required if not (src / name).is_file()]
if absent:
    raise SystemExit(f"reconstructed R2 source missing required files: {absent}")

with Path(os.environ["GITHUB_ENV"]).open("a", encoding="utf-8") as f:
    f.write(f"MCR_R2_SRC={src}\n")
print(f"PASS exact R2 source: {len(raw)} bytes, SHA-256 {actual}, extracted to {src}")
