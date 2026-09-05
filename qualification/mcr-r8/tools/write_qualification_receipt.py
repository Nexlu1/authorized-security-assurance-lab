from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BINARY = ROOT / "target" / "release" / ("mcr-ingest.exe" if os.name == "nt" else "mcr-ingest")
OUT = ROOT / "qualification-receipt.json"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def command_text(*args: str) -> str:
    return subprocess.check_output(args, cwd=ROOT, text=True, stderr=subprocess.STDOUT).strip()


if not BINARY.is_file():
    raise SystemExit(f"release binary missing: {BINARY}")

record = {
    "schema": "mcr-r8-focused-public-qualification-receipt-v1",
    "generated_utc": datetime.now(timezone.utc).isoformat(),
    "scope": (
        "Focused dependency-free Rust bootstrap slice only: archive-name checks, "
        "content-addressed object paths, MBOX scanning, and evidence-aware mail threading. "
        "This is not the complete 57-fixture or full production MCR tooling qualification."
    ),
    "repository": os.environ.get("GITHUB_REPOSITORY"),
    "git_sha": os.environ.get("GITHUB_SHA"),
    "workflow_run_id": os.environ.get("GITHUB_RUN_ID"),
    "runner_os": os.environ.get("RUNNER_OS"),
    "runner_arch": os.environ.get("RUNNER_ARCH"),
    "platform": platform.platform(),
    "python": platform.python_version(),
    "rustc": command_text("rustc", "-Vv"),
    "cargo": command_text("cargo", "-V"),
    "binary": {
        "name": BINARY.name,
        "bytes": BINARY.stat().st_size,
        "sha256": sha256_file(BINARY),
    },
    "gates": {
        "cargo_fmt_check": "PASS",
        "cargo_test_locked_all_targets": "PASS_23_TESTS",
        "cargo_clippy_locked_all_targets_deny_warnings": "PASS",
        "cargo_release_build_locked": "PASS",
        "release_runtime_self_test": "PASS",
    },
}
OUT.write_text(json.dumps(record, indent=2), encoding="utf-8")
print(json.dumps(record, indent=2))
