from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def run(command: list[str], cwd: Path) -> dict[str, object]:
    completed = subprocess.run(command, cwd=cwd, text=True, capture_output=True)
    if completed.returncode != 0:
        raise SystemExit(
            f"command failed ({completed.returncode}): {command}\nSTDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}"
        )
    return {
        "command": command,
        "return_code": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True, type=Path)
    args = parser.parse_args()
    project = args.project.resolve()
    exe = project / "target" / "release" / ("mcr-ingest.exe" if os.name == "nt" else "mcr-ingest")
    fixtures = Path(os.environ["MCR_FIXTURE_DIR"]).resolve()
    if not exe.is_file():
        raise SystemExit(f"release executable missing: {exe}")

    workspace = Path(tempfile.mkdtemp(prefix="mcr-r2-smoke-"))
    try:
        commands = [
            [str(exe), "init", str(workspace)],
            [str(exe), "inventory-zip", str(workspace), str(fixtures / "arc_parent_traversal.zip")],
            [str(exe), "index-mbox", str(workspace), str(fixtures / "mail_thread_cycle.mbox")],
            [str(exe), "index-eml", str(workspace), str(fixtures / "mail_malformed_mime.eml")],
            [str(exe), "index-csv", str(workspace), str(fixtures / "csv_multiline.csv")],
            [str(exe), "inventory-ooxml", str(workspace), str(fixtures / "oox_hidden_text.docx")],
            [str(exe), "verify-object", str(workspace), sha256_file(fixtures / "oox_hidden_text.docx")],
        ]
        results = [run(command, project) for command in commands]
    finally:
        shutil.rmtree(workspace, ignore_errors=True)

    receipt = {
        "schema": "mcr-ingest-r2-portable-smoke-receipt-v1",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "runner_os": os.environ.get("RUNNER_OS"),
        "runner_arch": os.environ.get("RUNNER_ARCH"),
        "git_sha": os.environ.get("GITHUB_SHA"),
        "binary": {
            "name": exe.name,
            "bytes": exe.stat().st_size,
            "sha256": sha256_file(exe),
        },
        "commands": results,
        "status": "PASS",
    }
    out = project / "qualification_out" / "portable-smoke-receipt.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
