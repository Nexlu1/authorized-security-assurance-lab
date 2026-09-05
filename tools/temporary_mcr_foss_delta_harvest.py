#!/usr/bin/env python3
from __future__ import annotations

import csv
import hashlib
import json
import os
import pathlib
import re
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime, timezone
from typing import Any

ROOT = pathlib.Path("harvest-work")
PAYLOAD = ROOT / "MCR_GITHUB_FOSS_DELTA_R1_2026-09-05"
DOWNLOADS = ROOT / "downloads"
CHUNKS = ROOT / "chunks"
OUTPUT = pathlib.Path("harvest-output")
MANIFEST_PATH = pathlib.Path("controls/mcr_foss_delta_manifest.json")
TOKEN = os.environ.get("GH_TOKEN", "")
API = "https://api.github.com"
USER_AGENT = "mcr-foss-delta-harvest/1.0"
FIXED_ZIP_TIME = (2026, 9, 5, 0, 0, 0)
SOURCE_CHUNK_BYTES = 250 * 1024 * 1024
PART_TARGET_BYTES = 350 * 1024 * 1024
MAX_PARTS = 16
MAX_LICENSE_BYTES = 5 * 1024 * 1024
MAX_SOURCE_MEMBERS = 1_000_000
MAX_DECLARED_UNCOMPRESSED_BYTES = 20 * 1024 * 1024 * 1024

source_records: list[dict[str, Any]] = []
license_records: list[dict[str, Any]] = []
failures: list[dict[str, Any]] = []
payload_items: list[tuple[pathlib.Path, str]] = []


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def safe_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("_")
    return cleaned or "unnamed"


def request(url: str, accept: str = "application/vnd.github+json") -> urllib.request.Request:
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": accept,
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if TOKEN:
        headers["Authorization"] = "Bearer " + TOKEN
    return urllib.request.Request(url, headers=headers)


def api_json(path: str) -> Any:
    with urllib.request.urlopen(request(API + path), timeout=120) as response:
        return json.load(response)


def download(url: str, destination: pathlib.Path, attempts: int = 5) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(
                request(url, "application/octet-stream"), timeout=300
            ) as response, destination.open("wb") as output:
                shutil.copyfileobj(response, output, 1024 * 1024)
            if destination.stat().st_size == 0:
                raise RuntimeError("downloaded file is empty")
            return
        except Exception as error:  # noqa: BLE001 - receipt preserves exact exception
            last_error = error
            destination.unlink(missing_ok=True)
            if attempt + 1 < attempts:
                time.sleep(2**attempt)
    assert last_error is not None
    raise last_error


def verify_commit(repository: str, expected: str) -> dict[str, Any]:
    encoded = urllib.parse.quote(expected, safe="")
    result = api_json(f"/repos/{repository}/commits/{encoded}")
    actual = str(result.get("sha", "")).lower()
    if actual != expected.lower():
        raise RuntimeError(f"commit resolution mismatch: expected {expected}, got {actual}")
    verification = result.get("commit", {}).get("verification", {})
    return {
        "resolved_commit": actual,
        "commit_html_url": result.get("html_url"),
        "commit_date": result.get("commit", {}).get("committer", {}).get("date"),
        "commit_verification_verified": verification.get("verified"),
        "commit_verification_reason": verification.get("reason"),
    }


LICENSE_BASENAME = re.compile(
    r"^(?:license|licence|copying|notice|copyright|unlicense|artistic)(?:[._-].*)?$",
    re.IGNORECASE,
)
README_BASENAME = re.compile(r"^readme(?:[._-].*)?$", re.IGNORECASE)
LICENSE_TEXT_MARKERS = (
    b"mit license",
    b"apache license",
    b"gnu general public license",
    b"gnu lesser general public license",
    b"mozilla public license",
    b"bsd license",
    b"public domain",
    b"open government licence",
    b"artistic license",
    b"creative commons",
)


def is_license_candidate(member_name: str) -> bool:
    parts = pathlib.PurePosixPath(member_name).parts
    if not parts:
        return False
    basename = parts[-1]
    lowered_parts = {part.lower() for part in parts[:-1]}
    return bool(LICENSE_BASENAME.match(basename)) or bool(
        lowered_parts.intersection({"license", "licenses", "licence", "licences"})
    )


def safe_member_filename(member_name: str, ordinal: int) -> str:
    parts = pathlib.PurePosixPath(member_name).parts
    tail = "__".join(parts[-4:]) if parts else f"member-{ordinal}"
    return f"{ordinal:04d}__{safe_name(tail)}"


def inspect_source_archive(
    component: str, repository: str, archive_path: pathlib.Path
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    extracted: list[dict[str, Any]] = []
    source_stats: dict[str, Any] = {}
    with zipfile.ZipFile(archive_path, "r") as archive:
        members = archive.infolist()
        if len(members) > MAX_SOURCE_MEMBERS:
            raise RuntimeError(f"source archive member ceiling exceeded: {len(members)}")
        declared_total = sum(member.file_size for member in members)
        if declared_total > MAX_DECLARED_UNCOMPRESSED_BYTES:
            raise RuntimeError(
                f"source archive declared-size ceiling exceeded: {declared_total}"
            )
        corrupt = archive.testzip()
        if corrupt is not None:
            raise RuntimeError(f"source archive CRC/read failure: {corrupt}")

        candidate_infos = [
            member
            for member in members
            if not member.is_dir()
            and 0 <= member.file_size <= MAX_LICENSE_BYTES
            and is_license_candidate(member.filename)
        ]

        # Some public-domain/data repositories carry the grant only in README.
        # Use README merely as evidence-to-review, never as an automatic licence conclusion.
        if not candidate_infos:
            for member in members:
                if (
                    member.is_dir()
                    or member.file_size < 1
                    or member.file_size > MAX_LICENSE_BYTES
                    or not README_BASENAME.match(pathlib.PurePosixPath(member.filename).name)
                ):
                    continue
                try:
                    sample = archive.read(member)[:MAX_LICENSE_BYTES].lower()
                except Exception:  # noqa: BLE001
                    continue
                if any(marker in sample for marker in LICENSE_TEXT_MARKERS):
                    candidate_infos.append(member)
                    break

        destination_root = PAYLOAD / "licenses" / safe_name(component)
        seen_hashes: set[str] = set()
        for ordinal, member in enumerate(candidate_infos):
            data = archive.read(member)
            digest = hashlib.sha256(data).hexdigest()
            if digest in seen_hashes:
                continue
            seen_hashes.add(digest)
            destination_root.mkdir(parents=True, exist_ok=True)
            destination = destination_root / safe_member_filename(member.filename, ordinal)
            destination.write_bytes(data)
            arcname = destination.relative_to(PAYLOAD).as_posix()
            record = {
                "component": component,
                "repository": repository,
                "source_member": member.filename,
                "file": arcname,
                "bytes": len(data),
                "sha256": digest,
                "evidence_only": True,
            }
            extracted.append(record)
            license_records.append(record)
            payload_items.append((destination, arcname))

        source_stats = {
            "zip_member_count": len(members),
            "zip_declared_uncompressed_bytes": declared_total,
            "zip_crc_and_read": "PASS",
            "license_evidence_count": len(extracted),
        }
    return extracted, source_stats


def add_archive_or_chunks(
    component: str, archive_path: pathlib.Path, archive_name: str
) -> list[dict[str, Any]]:
    storage: list[dict[str, Any]] = []
    if archive_path.stat().st_size <= SOURCE_CHUNK_BYTES:
        arcname = f"sources/{archive_name}"
        payload_items.append((archive_path, arcname))
        storage.append(
            {
                "path": arcname,
                "bytes": archive_path.stat().st_size,
                "sha256": sha256_file(archive_path),
                "chunk_index": 0,
                "chunk_count": 1,
            }
        )
        return storage

    chunk_root = CHUNKS / safe_name(component)
    chunk_root.mkdir(parents=True, exist_ok=True)
    chunk_paths: list[pathlib.Path] = []
    with archive_path.open("rb") as source:
        index = 0
        while True:
            data = source.read(SOURCE_CHUNK_BYTES)
            if not data:
                break
            chunk = chunk_root / f"{archive_name}.part{index:03d}"
            chunk.write_bytes(data)
            chunk_paths.append(chunk)
            index += 1
    count = len(chunk_paths)
    for index, chunk in enumerate(chunk_paths):
        arcname = f"source-chunks/{safe_name(component)}/{chunk.name}"
        payload_items.append((chunk, arcname))
        storage.append(
            {
                "path": arcname,
                "bytes": chunk.stat().st_size,
                "sha256": sha256_file(chunk),
                "chunk_index": index,
                "chunk_count": count,
                "reconstruct_as": f"sources/{archive_name}",
            }
        )
    archive_path.unlink()
    return storage


def harvest_source(item: dict[str, Any], ordinal: int, total: int) -> None:
    component = str(item["id"])
    repository = str(item["repo"])
    expected_commit = str(item["commit"]).lower()
    required = bool(item.get("required", True))
    record: dict[str, Any] = {
        **item,
        "status": "STARTED",
        "started_utc": now(),
    }
    print(f"[source {ordinal}/{total}] {repository}@{expected_commit}", flush=True)
    try:
        commit_record = verify_commit(repository, expected_commit)
        archive_name = (
            f"{safe_name(component)}__{safe_name(repository)}__{expected_commit}.zip"
        )
        archive_path = DOWNLOADS / archive_name
        download(
            f"https://codeload.github.com/{repository}/zip/{expected_commit}",
            archive_path,
        )
        archive_bytes = archive_path.stat().st_size
        archive_sha256 = sha256_file(archive_path)
        evidence, source_stats = inspect_source_archive(
            component, repository, archive_path
        )
        storage = add_archive_or_chunks(component, archive_path, archive_name)
        licence_status = "EVIDENCE_FOUND" if evidence else "EVIDENCE_OPEN_REVIEW_REQUIRED"
        record.update(
            commit_record,
            status="DOWNLOADED_HASHED_AND_ZIP_VERIFIED",
            archive_name=archive_name,
            archive_bytes=archive_bytes,
            archive_sha256=archive_sha256,
            source_stats=source_stats,
            license_evidence_status=licence_status,
            license_evidence=[entry["file"] for entry in evidence],
            storage_items=storage,
            completed_utc=now(),
        )
    except Exception as error:  # noqa: BLE001 - preserve exact failure in receipt
        record.update(
            status="FAILED",
            error=f"{type(error).__name__}: {error}",
            completed_utc=now(),
        )
        failures.append(
            {
                "component": component,
                "repository": repository,
                "required": required,
                "error": record["error"],
            }
        )
    source_records.append(record)


def write_csv(path: pathlib.Path, records: list[dict[str, Any]]) -> None:
    fields = [
        "category",
        "id",
        "repo",
        "commit",
        "resolved_commit",
        "license",
        "use",
        "status",
        "archive_name",
        "archive_bytes",
        "archive_sha256",
        "license_evidence_status",
        "error",
    ]
    with path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()
        for record in records:
            writer.writerow({field: record.get(field, "") for field in fields})


def stream_zip_member(
    archive: zipfile.ZipFile, source: pathlib.Path, arcname: str
) -> None:
    info = zipfile.ZipInfo(arcname, FIXED_ZIP_TIME)
    info.compress_type = zipfile.ZIP_STORED
    info.external_attr = 0o100644 << 16
    info.file_size = source.stat().st_size
    with source.open("rb") as input_stream, archive.open(
        info, "w", force_zip64=True
    ) as output_stream:
        shutil.copyfileobj(input_stream, output_stream, 1024 * 1024)


def deterministic_zip(path: pathlib.Path, items: list[tuple[pathlib.Path, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.unlink(missing_ok=True)
    with zipfile.ZipFile(path, "w", allowZip64=True) as archive:
        for source, arcname in sorted(items, key=lambda item: item[1].lower()):
            stream_zip_member(archive, source, arcname)
    with zipfile.ZipFile(path, "r") as archive:
        corrupt = archive.testzip()
        if corrupt is not None:
            raise RuntimeError(f"output ZIP CRC/read failure: {path.name}: {corrupt}")


def assign_bins(
    items: list[tuple[pathlib.Path, str]], target_bytes: int
) -> list[list[tuple[pathlib.Path, str]]]:
    bins: list[list[tuple[pathlib.Path, str]]] = []
    totals: list[int] = []
    for item in sorted(items, key=lambda value: value[0].stat().st_size, reverse=True):
        size = item[0].stat().st_size
        placed = False
        for index, total in enumerate(totals):
            if total + size <= target_bytes:
                bins[index].append(item)
                totals[index] += size
                placed = True
                break
        if not placed:
            bins.append([item])
            totals.append(size)
    return bins


def build_controls(plan: dict[str, Any]) -> dict[str, Any]:
    control = PAYLOAD / "CONTROL"
    control.mkdir(parents=True, exist_ok=True)
    required_failures = [failure for failure in failures if failure["required"]]
    license_open = [
        record
        for record in source_records
        if record.get("license_evidence_status") == "EVIDENCE_OPEN_REVIEW_REQUIRED"
    ]
    result = {
        "schema": "mcr-github-foss-delta-harvest-result-v1",
        "generated_utc": now(),
        "requested_sources": len(plan["sources"]),
        "downloaded_sources": sum(
            record["status"] == "DOWNLOADED_HASHED_AND_ZIP_VERIFIED"
            for record in source_records
        ),
        "required_failures": required_failures,
        "all_failures": failures,
        "license_evidence_open_count": len(license_open),
        "license_evidence_open_components": [record["id"] for record in license_open],
        "sources": source_records,
        "license_evidence": license_records,
        "authority_boundary": plan["authority_boundary"],
    }
    (control / "DELTA_PLAN.json").write_text(
        json.dumps(plan, indent=2, sort_keys=True), encoding="utf-8"
    )
    (control / "HARVEST_RESULT.json").write_text(
        json.dumps(result, indent=2, sort_keys=True), encoding="utf-8"
    )
    (control / "LICENSE_EVIDENCE_REGISTER.json").write_text(
        json.dumps(license_records, indent=2, sort_keys=True), encoding="utf-8"
    )
    write_csv(control / "SOURCE_REGISTER.csv", source_records)
    (control / "EXECUTION_RECEIPT.json").write_text(
        json.dumps(
            {
                "generated_utc": now(),
                "github_repository": os.environ.get("GITHUB_REPOSITORY"),
                "github_ref": os.environ.get("GITHUB_REF"),
                "github_sha": os.environ.get("GITHUB_SHA"),
                "github_run_id": os.environ.get("GITHUB_RUN_ID"),
                "runner_os": os.environ.get("RUNNER_OS"),
                "runner_arch": os.environ.get("RUNNER_ARCH"),
                "python": sys.version,
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    (control / "README.md").write_text(
        "# MCR GitHub/FOSS Delta Harvest R1\n\n"
        "Exact public source snapshots absent from the previously verified 41-source "
        "local harvest. Source acquisition does not make a component trusted or "
        "authorise integration. Licence evidence remains reviewable per source. "
        "No live case evidence, credentials or frozen R59 bytes are included.\n\n"
        f"- Requested: {result['requested_sources']}\n"
        f"- Downloaded and ZIP-verified: {result['downloaded_sources']}\n"
        f"- Required failures: {len(required_failures)}\n"
        f"- Licence-evidence reviews still open: {len(license_open)}\n",
        encoding="utf-8",
    )
    return result


def build_payload_manifest() -> list[dict[str, Any]]:
    manifest: list[dict[str, Any]] = []
    for path, arcname in sorted(payload_items, key=lambda item: item[1].lower()):
        manifest.append(
            {
                "path": arcname,
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    control = PAYLOAD / "CONTROL"
    (control / "PAYLOAD_FILE_MANIFEST.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
    )
    (control / "PAYLOAD_SHA256SUMS.txt").write_text(
        "".join(f"{entry['sha256']}  {entry['path']}\n" for entry in manifest),
        encoding="utf-8",
    )
    return manifest


def package_outputs(result: dict[str, Any]) -> list[dict[str, Any]]:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    bins = assign_bins(payload_items, PART_TARGET_BYTES)
    if len(bins) > MAX_PARTS:
        raise RuntimeError(f"connector-safe part ceiling exceeded: {len(bins)} > {MAX_PARTS}")

    part_records: list[dict[str, Any]] = []
    for index, items in enumerate(bins):
        path = OUTPUT / f"MCR_FOSS_DELTA_R1_PART_{index:02d}.zip"
        deterministic_zip(path, items)
        part_records.append(
            {
                "part": index,
                "file": path.name,
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
                "payload_items": len(items),
                "payload_bytes": sum(item[0].stat().st_size for item in items),
            }
        )

    control = PAYLOAD / "CONTROL"
    split_manifest = {
        "schema": "mcr-foss-delta-split-manifest-v1",
        "generated_utc": now(),
        "source_archive_count": result["downloaded_sources"],
        "parts": part_records,
    }
    (control / "SPLIT_MANIFEST.json").write_text(
        json.dumps(split_manifest, indent=2, sort_keys=True), encoding="utf-8"
    )

    control_items = [
        (path, f"CONTROL/{path.name}")
        for path in sorted(control.iterdir(), key=lambda item: item.name.lower())
        if path.is_file()
    ]
    controls_zip = OUTPUT / "MCR_FOSS_DELTA_R1_CONTROLS.zip"
    deterministic_zip(controls_zip, control_items)

    output_hashes = [
        {
            "file": controls_zip.name,
            "bytes": controls_zip.stat().st_size,
            "sha256": sha256_file(controls_zip),
        },
        *part_records,
    ]
    (OUTPUT / "OUTPUT_SHA256.json").write_text(
        json.dumps(output_hashes, indent=2, sort_keys=True), encoding="utf-8"
    )
    (OUTPUT / "OUTPUT_SHA256.txt").write_text(
        "".join(
            f"{record['sha256']}  {record['file']}\n" for record in output_hashes
        ),
        encoding="utf-8",
    )
    return part_records


def main() -> None:
    if ROOT.exists():
        shutil.rmtree(ROOT)
    if OUTPUT.exists():
        shutil.rmtree(OUTPUT)
    PAYLOAD.mkdir(parents=True, exist_ok=True)
    DOWNLOADS.mkdir(parents=True, exist_ok=True)
    CHUNKS.mkdir(parents=True, exist_ok=True)

    plan = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    sources = plan["sources"]
    for ordinal, item in enumerate(sources, start=1):
        harvest_source(item, ordinal, len(sources))

    result = build_controls(plan)
    build_payload_manifest()
    part_records = package_outputs(result)
    print(
        json.dumps(
            {
                "requested_sources": result["requested_sources"],
                "downloaded_sources": result["downloaded_sources"],
                "required_failures": len(result["required_failures"]),
                "license_evidence_open_count": result["license_evidence_open_count"],
                "connector_safe_parts": len(part_records),
            },
            indent=2,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
