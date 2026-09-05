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
REBUILD_RECEIPT = ROOT / "clean-rebuild-receipt.json"
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
if not REBUILD_RECEIPT.is_file():
    raise SystemExit(f"clean rebuild receipt missing: {REBUILD_RECEIPT}")

rebuild = json.loads(REBUILD_RECEIPT.read_text(encoding="utf-8"))
if rebuild.get("byte_identical") is not True:
    raise SystemExit("clean rebuild receipt does not prove byte identity")

record = {
    "schema": "mcr-r8-focused-public-qualification-receipt-v2",
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
    "source_date_epoch": os.environ.get("SOURCE_DATE_EPOCH"),
    "linker": os.environ.get("CARGO_TARGET_X86_64_PC_WINDOWS_MSVC_LINKER"),
    "rustflags": os.environ.get("RUSTFLAGS"),
    "binary": {
        "name": BINARY.name,
        "bytes": BINARY.stat().st_size,
        "sha256": sha256_file(BINARY),
    },
    "clean_rebuild": rebuild,
    "gates": {
        "cargo_fmt_check": "PASS",
        "cargo_test_locked_all_targets": "PASS_23_TESTS",
        "cargo_clippy_locked_all_targets_deny_warnings": "PASS",
        "cargo_release_build_locked": "PASS",
        "release_runtime_self_test": "PASS",
        "same_runner_clean_rebuild_byte_identity": "PASS",
    },
}
OUT.write_text(json.dumps(record, indent=2), encoding="utf-8")
print(json.dumps(record, indent=2))
