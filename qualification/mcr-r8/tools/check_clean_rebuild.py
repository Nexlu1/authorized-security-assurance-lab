from __future__ import annotations

import hashlib
import json
import os
import shutil
import struct
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BINARY = ROOT / "target" / "release" / ("mcr-ingest.exe" if os.name == "nt" else "mcr-ingest")
FIRST_COPY = ROOT / ("repro-first-mcr-ingest.exe" if os.name == "nt" else "repro-first-mcr-ingest")
SECOND_COPY = ROOT / ("repro-second-mcr-ingest.exe" if os.name == "nt" else "repro-second-mcr-ingest")
OUT = ROOT / "clean-rebuild-receipt.json"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def binary_summary(path: Path) -> dict[str, object]:
    data = path.read_bytes()
    result: dict[str, object] = {
        "bytes": len(data),
        "sha256": sha256_bytes(data),
    }
    if len(data) >= 256 and data[:2] == b"MZ":
        pe_offset = struct.unpack_from("<I", data, 0x3C)[0]
        if data[pe_offset : pe_offset + 4] == b"PE\0\0":
            machine, section_count, timestamp, _, _, optional_size, _ = struct.unpack_from(
                "<HHIIIHH", data, pe_offset + 4
            )
            result["pe"] = {
                "machine": machine,
                "section_count": section_count,
                "coff_timestamp": timestamp,
            }
            section_table = pe_offset + 4 + 20 + optional_size
            sections = []
            for index in range(section_count):
                offset = section_table + index * 40
                name = data[offset : offset + 8].split(b"\0", 1)[0].decode("ascii", "replace")
                raw_size, raw_pointer = struct.unpack_from("<II", data, offset + 16)
                raw = data[raw_pointer : raw_pointer + raw_size]
                sections.append(
                    {
                        "name": name,
                        "raw_size": raw_size,
                        "raw_pointer": raw_pointer,
                        "raw_sha256": sha256_bytes(raw),
                    }
                )
            result["pe"]["sections"] = sections  # type: ignore[index]
    return result


def diff_summary(first: bytes, second: bytes) -> dict[str, object]:
    limit = min(len(first), len(second))
    differing = [index for index in range(limit) if first[index] != second[index]]
    differing.extend(range(limit, max(len(first), len(second))))
    runs = []
    if differing:
        start = previous = differing[0]
        for index in differing[1:]:
            if index == previous + 1:
                previous = index
            else:
                runs.append([start, previous])
                start = previous = index
        runs.append([start, previous])
    return {
        "differing_bytes": len(differing),
        "difference_runs": len(runs),
        "first_difference": differing[0] if differing else None,
        "last_difference": differing[-1] if differing else None,
        "first_100_runs": runs[:100],
    }


if not BINARY.is_file():
    raise SystemExit(f"first release binary missing: {BINARY}")

shutil.copy2(BINARY, FIRST_COPY)
first = binary_summary(FIRST_COPY)

subprocess.run(["cargo", "clean"], cwd=ROOT, check=True)
subprocess.run(["cargo", "build", "--locked", "--release", "--verbose"], cwd=ROOT, check=True)
subprocess.run([str(BINARY), "self-test"], cwd=ROOT, check=True)

shutil.copy2(BINARY, SECOND_COPY)
second = binary_summary(SECOND_COPY)
first_data = FIRST_COPY.read_bytes()
second_data = SECOND_COPY.read_bytes()

record = {
    "schema": "mcr-r8-clean-rebuild-receipt-v2",
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
    "byte_identical": first_data == second_data,
    "difference": diff_summary(first_data, second_data),
    "second_binary_self_test": "PASS",
}
OUT.write_text(json.dumps(record, indent=2), encoding="utf-8")
print(json.dumps(record, indent=2))
