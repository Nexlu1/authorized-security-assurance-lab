from __future__ import annotations

import hashlib
import json
import os
import struct
import zipfile
from pathlib import Path

out = Path(os.environ.get("MCR_R24_FIXTURE_DIR", Path(os.environ.get("RUNNER_TEMP", ".")) / "mcr-r24-resource-fixtures"))
out.mkdir(parents=True, exist_ok=True)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def stored_zip(path: Path, members: list[tuple[str, bytes]]) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as zf:
        for name, data in members:
            info = zipfile.ZipInfo(name)
            info.compress_type = zipfile.ZIP_STORED
            info.external_attr = 0o600 << 16
            zf.writestr(info, data)


# ARC-008: actual and declared single-member size are above the small functional-test limit.
stored_zip(out / "arc_single_member_oversize.zip", [("oversize.bin", b"A" * (2 * 1024 * 1024))])

# ARC-009: each member is below the member limit, but total actual bytes cross the aggregate limit.
stored_zip(
    out / "arc_aggregate_oversize.zip",
    [(f"part-{i}.bin", bytes([65 + i]) * (400 * 1024)) for i in range(4)],
)

# ARC-011: create one stored member with 1 MiB of real data, then lie in both local and central
# uncompressed-size fields. Compressed size remains truthful so rawzip can still locate the data.
lie = out / "arc_header_size_lies.zip"
stored_zip(lie, [("lying-size.bin", b"Z" * (1024 * 1024))])
data = bytearray(lie.read_bytes())
local_sig = b"PK\x03\x04"
central_sig = b"PK\x01\x02"
li = data.find(local_sig)
ci = data.find(central_sig)
if li < 0 or ci < 0:
    raise SystemExit("failed to locate ZIP headers for ARC-011 fixture")
# Local file header uncompressed-size offset is signature + 22 bytes.
struct.pack_into("<I", data, li + 22, 16)
# Central-directory uncompressed-size offset is signature + 24 bytes.
struct.pack_into("<I", data, ci + 24, 16)
lie.write_bytes(data)

rows = []
for p in sorted(out.glob("*.zip")):
    rows.append({"name": p.name, "bytes": p.stat().st_size, "sha256": sha256(p)})
manifest = {
    "schema": "mcr-r2-4-resource-fixtures-v1",
    "matrix_cases": ["ARC-008", "ARC-009", "ARC-011"],
    "fixtures": rows,
    "notes": {
        "ARC-008": "2 MiB stored member; functional-test member limit is 512 KiB",
        "ARC-009": "four 400 KiB stored members; functional-test aggregate limit is 900 KiB",
        "ARC-011": "1 MiB actual stored member with local+central uncompressed-size fields tampered to 16 bytes"
    }
}
(out / "R24_RESOURCE_FIXTURE_MANIFEST.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
print(json.dumps(manifest, indent=2))
