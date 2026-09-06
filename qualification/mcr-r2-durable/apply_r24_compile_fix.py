from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

src = Path(os.environ["MCR_R2_SRC"])
out = Path(os.environ["RUNNER_TEMP"]) / "mcr-r2-compile-evidence"
out.mkdir(parents=True, exist_ok=True)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def replace_exact(path: Path, old: str, new: str, expected: int, reason: str):
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != expected:
        raise SystemExit(
            f"expected exactly {expected} R2.4 compile-fix target(s) in {path.relative_to(src)}; found {count}: {reason}"
        )
    before = path.read_bytes()
    path.write_text(text.replace(old, new), encoding="utf-8", newline="\n")
    after = path.read_bytes()
    fixes.append({
        "file": path.relative_to(src).as_posix(),
        "reason": reason,
        "occurrences": count,
        "before_sha256": sha256_bytes(before),
        "after_sha256": sha256_bytes(after),
    })


fixes = []
archive = src / "src" / "archive.rs"
main = src / "src" / "main.rs"
tests = src / "tests" / "core_integration.rs"

replace_exact(
    archive,
    '#[derive(Debug, Clone, Copy, PartialEq, Eq, serde::Serialize)]\n#[serde(rename_all = "snake_case")]\npub enum ArchiveResourceLimitKind {',
    '#[derive(Debug, Clone, Copy, PartialEq, Eq)]\npub enum ArchiveResourceLimitKind {',
    1,
    "Keep the core resource-limit enum independent of Serde derive macros.",
)
replace_exact(
    archive,
    '#[derive(Debug, Clone, serde::Serialize)]\npub struct ArchiveResourceSummary {',
    '#[derive(Debug, Clone)]\npub struct ArchiveResourceSummary {',
    1,
    "Keep the core summary independent of Serde derive macros; CLI JSON is explicit.",
)

old = '''            println!("{}", serde_json::to_string_pretty(&summary)?);'''
new = '''            let limit_hit = summary.limit_hit.map(|kind| match kind {
                archive::ArchiveResourceLimitKind::Member => "member",
                archive::ArchiveResourceLimitKind::Aggregate => "aggregate",
            });
            let output = json!({
                "members_seen": summary.members_seen,
                "members_completed": summary.members_completed,
                "fully_verified_members": summary.fully_verified_members,
                "accepted_uncompressed_bytes": summary.accepted_uncompressed_bytes,
                "probed_uncompressed_bytes": summary.probed_uncompressed_bytes,
                "max_member_accepted_bytes": summary.max_member_accepted_bytes,
                "metadata_size_mismatch_members": summary.metadata_size_mismatch_members,
                "metadata_understatement_members": summary.metadata_understatement_members,
                "limit_hit": limit_hit,
                "limit_member_index": summary.limit_member_index,
                "limit_member_name": summary.limit_member_name,
                "elapsed_ms": summary.elapsed_ms,
                "materialisation_performed": summary.materialisation_performed,
            });
            println!("{}", serde_json::to_string_pretty(&output)?);'''
replace_exact(
    main,
    old,
    new,
    1,
    "Emit archive-resource-check JSON explicitly without enabling Serde derive.",
)

replace_exact(
    tests,
    "    assert!(summary.probed_uncompressed_bytes >= total_limit + 1);",
    "    assert!(summary.probed_uncompressed_bytes > total_limit);",
    1,
    "Use the Clippy-preferred equivalent aggregate-overrun assertion.",
)

receipt = {
    "schema": "mcr-r2-4-compile-fix-v2",
    "generated_utc": datetime.now(timezone.utc).isoformat(),
    "purpose": "Remove an unnecessary Serde-derive dependency requirement and keep the R2.4 tests strict-Clippy clean.",
    "fixes": fixes,
    "dependency_surface_change": "none"
}
(out / "R2_4_COMPILE_FIX_RECEIPT.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
print(json.dumps(receipt, indent=2))
