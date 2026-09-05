from __future__ import annotations

import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BINARY = ROOT / "target" / "release" / ("mcr-ingest.exe" if os.name == "nt" else "mcr-ingest")
OUT = ROOT / "clean-rebuild-receipt.json"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


if not BINARY.is_file():
    raise SystemExit(f"first release binary missing: {BINARY}")

first = {
    "bytes": BINARY.stat().st_size,
    "sha256": sha256_file(BINARY),
}

subprocess.run(["cargo", "clean"], cwd=ROOT, check=True)
subprocess.run(["cargo", "build", "--locked", "--release", "--verbose"], cwd=ROOT, check=True)
subprocess.run([str(BINARY), "self-test"], cwd=ROOT, check=True)

second = {
    "bytes": BINARY.stat().st_size,
    "sha256": sha256_file(BINARY),
}

record = {
    "schema": "mcr-r8-clean-rebuild-receipt-v1",
    "generated_utc": datetime.now(timezone.utc).isoformat(),
    "repository": os.environ.get("GITHUB_REPOSITORY"),
    "git_sha": os.environ.get("GITHUB_SHA"),
    "workflow_run_id": os.environ.get("GITHUB_RUN_ID"),
    "runner_os": os.environ.get("RUNNER_OS"),
    "runner_arch": os.environ.get("RUNNER_ARCH"),
    "source_date_epoch": os.environ.get("SOURCE_DATE_EPOCH"),
    "linker": os.environ.get("CARGO_TARGET_X86_64_PC_WINDOWS_MSVC_LINKER"),
    "rustflags": os.environ.get("RUSTFLAGS"),
    "first_build": first,
    "second_clean_build": second,
    "byte_identical": first == second,
    "second_binary_self_test": "PASS",
}
OUT.write_text(json.dumps(record, indent=2), encoding="utf-8")
print(json.dumps(record, indent=2))

if first != second:
    raise SystemExit(
        "clean rebuild was not byte-identical: "
        f"first={first['sha256']} second={second['sha256']}"
    )
