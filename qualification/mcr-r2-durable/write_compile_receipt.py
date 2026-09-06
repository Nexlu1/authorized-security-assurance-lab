from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
from datetime import datetime, timezone

src = Path(os.environ["MCR_R2_SRC"])
out = Path(os.environ["RUNNER_TEMP"]) / "mcr-r2-compile-evidence"
out.mkdir(parents=True, exist_ok=True)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def capture(*cmd: str) -> str:
    return subprocess.check_output(cmd, cwd=src, text=True, stderr=subprocess.STDOUT).strip()


lock = src / "Cargo.lock"
binary = src / "target" / "release" / ("mcr-ingest.exe" if os.name == "nt" else "mcr-ingest")

deps = src / "target" / "debug" / "deps"
if os.name == "nt":
    tests = sorted(deps.glob("core_integration-*.exe"))
else:
    tests = sorted(
        p for p in deps.glob("core_integration-*")
        if p.is_file() and not p.name.endswith(".d") and os.access(p, os.X_OK)
    )
if len(tests) != 1:
    raise SystemExit(f"expected exactly one compiled core_integration test executable; found {len(tests)}: {tests}")
test_binary = tests[0]

receipt = {
    "schema": "mcr-r2-durable-compile-receipt-v2",
    "generated_utc": datetime.now(timezone.utc).isoformat(),
    "github_sha": os.environ.get("GITHUB_SHA"),
    "runner_os": os.environ.get("RUNNER_OS"),
    "runner_arch": os.environ.get("RUNNER_ARCH"),
    "platform": platform.platform(),
    "source_zip_sha256": "a029571403ee89d42848b90e419384e9d9138534b43733b81483ee2d296d7215",
    "rustc": capture("rustc", "-Vv"),
    "cargo": capture("cargo", "-V"),
    "cargo_lock_bytes": lock.stat().st_size,
    "cargo_lock_sha256": sha256(lock),
    "release_binary": {
        "name": binary.name,
        "bytes": binary.stat().st_size,
        "sha256": sha256(binary),
    },
    "core_integration_test_binary": {
        "name": test_binary.name,
        "bytes": test_binary.stat().st_size,
        "sha256": sha256(test_binary),
    },
    "gates": {
        "cargo_fmt_check": "PASS",
        "cargo_clippy_deny_warnings": "PASS",
        "cargo_test_all_targets_no_run": "PASS",
        "cargo_release_build": "PASS",
    },
}
(out / "COMPILE_RECEIPT.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
shutil.copy2(lock, out / "Cargo.lock")
shutil.copy2(binary, out / binary.name)
shutil.copy2(test_binary, out / test_binary.name)
print(json.dumps(receipt, indent=2))
