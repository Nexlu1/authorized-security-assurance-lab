from __future__ import annotations

import hashlib
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

src = Path(os.environ["MCR_R2_SRC"])
out = Path(os.environ["RUNNER_TEMP"]) / "mcr-r2-promotable-source"
if out.exists():
    shutil.rmtree(out)
out.mkdir(parents=True)

# Copy the repaired/qualified source tree, never build products or temporary state.
for p in src.rglob("*"):
    rel = p.relative_to(src)
    if rel.parts and rel.parts[0] == "target":
        continue
    dst = out / rel
    if p.is_dir():
        dst.mkdir(parents=True, exist_ok=True)
    elif p.is_file():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, dst)

control = out / "CONTROL"
control.mkdir(exist_ok=True)
compile_evidence = Path(os.environ["RUNNER_TEMP"]) / "mcr-r2-compile-evidence"
for name in (
    "CANDIDATE_REPAIR_SET.json",
    "RUNTIME_REPAIR.json",
    "COVERAGE_EXPANSION_RECEIPT.json",
    "FIXTURE_R2_1_TEST_EXPANSION_RECEIPT.json",
    "R2_2_EXPANSION_RECEIPT.json",
    "R2_3_EXPANSION_RECEIPT.json",
    "COMPILE_RECEIPT.json",
):
    p = compile_evidence / name
    if p.is_file():
        shutil.copy2(p, control / name)

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()

rows = []
for p in sorted(x for x in out.rglob("*") if x.is_file() and x.name != "PROMOTION_MANIFEST.json"):
    rows.append({
        "path": p.relative_to(out).as_posix(),
        "bytes": p.stat().st_size,
        "sha256": sha256(p),
    })

manifest = {
    "schema": "mcr-r2-promotable-source-v1",
    "generated_utc": datetime.now(timezone.utc).isoformat(),
    "github_sha": os.environ.get("GITHUB_SHA"),
    "source_zip_sha256": "a029571403ee89d42848b90e419384e9d9138534b43733b81483ee2d296d7215",
    "status": "PROMOTABLE_SOURCE_AFTER_54_OF_57_COMPILE_GATE",
    "matrix_coverage": "54/57",
    "remaining_matrix_cases": ["ARC-008", "ARC-009", "ARC-011"],
    "file_count": len(rows),
    "files": rows,
    "authority_boundary": "future tooling only; frozen MCR R59 unchanged",
}
(control / "PROMOTION_MANIFEST.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
print(json.dumps({"status": manifest["status"], "file_count": len(rows)}, indent=2))
