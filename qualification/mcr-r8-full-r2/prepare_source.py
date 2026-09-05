from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path

EXPECTED_SOURCE_ZIP_SHA256 = "2bf606cbc6734ce02c01bf57128129bb36fa09d5ca596f79ca69e050c27f8bd7"
EXPECTED_FIXTURE_SHA256 = "b9199cbe9c4627f4445167e82c0997edaad9e7b8ed98ec176f27641f317725dd"
EXPECTED_MANIFEST_ROWS = 37


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def safe_extract(zf: zipfile.ZipFile, destination: Path) -> None:
    base = destination.resolve()
    for info in zf.infolist():
        target = (destination / info.filename).resolve()
        if target != base and base not in target.parents:
            raise RuntimeError(f"unsafe ZIP member path: {info.filename!r}")
    zf.extractall(destination)


def append_github_env(name: str, value: str) -> None:
    env_path = os.environ.get("GITHUB_ENV")
    if env_path:
        with Path(env_path).open("a", encoding="utf-8") as stream:
            stream.write(f"{name}={value}\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-zip", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()

    source_zip = args.source_zip.resolve()
    out = args.out.resolve()
    actual_source_sha = sha256_file(source_zip)
    if actual_source_sha != EXPECTED_SOURCE_ZIP_SHA256:
        raise SystemExit(
            f"source ZIP SHA-256 mismatch: expected={EXPECTED_SOURCE_ZIP_SHA256} actual={actual_source_sha}"
        )

    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    with zipfile.ZipFile(source_zip, "r") as zf:
        bad = zf.testzip()
        if bad is not None:
            raise SystemExit(f"source ZIP CRC/read failure at member: {bad}")
        safe_extract(zf, out)

    manifest_path = out / "MCR_INGEST_R2_SOURCE_MANIFEST_SHA256.csv"
    with manifest_path.open(newline="", encoding="utf-8-sig") as stream:
        rows = list(csv.DictReader(stream))
    if len(rows) != EXPECTED_MANIFEST_ROWS:
        raise SystemExit(f"source manifest row count mismatch: {len(rows)}")

    errors: list[str] = []
    listed: set[str] = set()
    for row in rows:
        rel = row["path"]
        listed.add(rel)
        path = out / Path(rel)
        if not path.is_file():
            errors.append(f"missing:{rel}")
            continue
        actual_size = path.stat().st_size
        expected_size = int(row["bytes"])
        if actual_size != expected_size:
            errors.append(f"size:{rel}:{expected_size}:{actual_size}")
        actual_sha = sha256_file(path)
        if actual_sha != row["sha256"]:
            errors.append(f"sha256:{rel}:{row['sha256']}:{actual_sha}")

    actual = {
        path.relative_to(out).as_posix()
        for path in out.rglob("*")
        if path.is_file() and path != manifest_path
    }
    if listed != actual:
        for rel in sorted(listed - actual):
            errors.append(f"listed-but-absent:{rel}")
        for rel in sorted(actual - listed):
            errors.append(f"unlisted-file:{rel}")
    if errors:
        raise SystemExit("source manifest verification failed:\n" + "\n".join(errors))

    fixture_zip = out / "qualification" / "MCR_TOOLING_SYNTHETIC_INGEST_FIXTURE_SEED_CORPUS_R1_2026-09-03.zip"
    actual_fixture_sha = sha256_file(fixture_zip)
    if actual_fixture_sha != EXPECTED_FIXTURE_SHA256:
        raise SystemExit(
            f"fixture ZIP SHA-256 mismatch: expected={EXPECTED_FIXTURE_SHA256} actual={actual_fixture_sha}"
        )
    fixtures = out / "qualification_out" / "fixtures"
    fixtures.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(fixture_zip, "r") as zf:
        bad = zf.testzip()
        if bad is not None:
            raise SystemExit(f"fixture ZIP CRC/read failure at member: {bad}")
        safe_extract(zf, fixtures)

    receipt = {
        "schema": "mcr-ingest-r2-public-source-prepare-receipt-v1",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "source_zip": source_zip.name,
        "source_zip_bytes": source_zip.stat().st_size,
        "source_zip_sha256": actual_source_sha,
        "source_manifest_rows": len(rows),
        "source_manifest_files_verified": len(listed),
        "fixture_zip_sha256": actual_fixture_sha,
        "fixture_member_count": len(list(fixtures.iterdir())),
        "real_case_material": False,
        "status": "PASS",
    }
    receipt_path = out / "qualification_out" / "source-prepare-receipt.json"
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")

    append_github_env("MCR_FIXTURE_DIR", str(fixtures))
    append_github_env("MCR_R2_PROJECT_ROOT", str(out))
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
