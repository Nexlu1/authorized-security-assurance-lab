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
            f"expected exactly {expected} R2.4 target(s) in {path.relative_to(src)}; found {count}: {reason}"
        )
    before = path.read_bytes()
    path.write_text(text.replace(old, new), encoding="utf-8", newline="\n")
    after = path.read_bytes()
    repairs.append({
        "file": path.relative_to(src).as_posix(),
        "reason": reason,
        "occurrences": count,
        "before_sha256": sha256_bytes(before),
        "after_sha256": sha256_bytes(after),
    })


repairs = []
archive = src / "src" / "archive.rs"
main = src / "src" / "main.rs"
tests = src / "tests" / "core_integration.rs"

replace_exact(
    archive,
    "use std::fs::File;\nuse std::path::Path;",
    "use std::fs::File;\nuse std::io::Read;\nuse std::path::Path;\nuse std::time::Instant;",
    1,
    "Import streaming Read and timing support for hard archive-resource limits.",
)

resource_code = r'''
#[derive(Debug, Clone, Copy, PartialEq, Eq, serde::Serialize)]
#[serde(rename_all = "snake_case")]
pub enum ArchiveResourceLimitKind {
    Member,
    Aggregate,
}

#[derive(Debug, Clone, Copy)]
pub struct ArchiveResourceLimits {
    pub max_member_bytes: u64,
    pub max_total_bytes: u64,
}

#[derive(Debug, Clone, serde::Serialize)]
pub struct ArchiveResourceSummary {
    pub members_seen: u64,
    pub members_completed: u64,
    pub fully_verified_members: u64,
    pub accepted_uncompressed_bytes: u64,
    pub probed_uncompressed_bytes: u64,
    pub max_member_accepted_bytes: u64,
    pub metadata_size_mismatch_members: u64,
    pub metadata_understatement_members: u64,
    pub limit_hit: Option<ArchiveResourceLimitKind>,
    pub limit_member_index: Option<u64>,
    pub limit_member_name: Option<String>,
    pub elapsed_ms: u128,
    pub materialisation_performed: bool,
}

#[derive(Debug)]
struct StreamProbe {
    accepted: u64,
    probed: u64,
    complete: bool,
    metadata_understates: bool,
}

fn probe_uncompressed_reader<R: Read>(
    mut reader: R,
    declared_uncompressed: u64,
    accepted_limit: u64,
) -> Result<StreamProbe> {
    // One sentinel byte may be decoded to prove more data exists, but bytes
    // accepted by policy never exceed accepted_limit and nothing is materialised.
    let probe_cap = accepted_limit.saturating_add(1);
    let mut buf = [0u8; 64 * 1024];
    let mut probed = 0u64;
    loop {
        let remaining = probe_cap.saturating_sub(probed);
        if remaining == 0 {
            return Ok(StreamProbe {
                accepted: accepted_limit,
                probed,
                complete: false,
                metadata_understates: probed > declared_uncompressed,
            });
        }
        let want = usize::try_from(remaining.min(buf.len() as u64))?;
        let n = reader.read(&mut buf[..want])?;
        if n == 0 {
            return Ok(StreamProbe {
                accepted: probed,
                probed,
                complete: true,
                metadata_understates: probed > declared_uncompressed,
            });
        }
        probed = probed
            .checked_add(u64::try_from(n)?)
            .ok_or("archive resource probe byte counter overflow")?;
        if probed > accepted_limit {
            return Ok(StreamProbe {
                accepted: accepted_limit,
                probed,
                complete: false,
                metadata_understates: probed > declared_uncompressed,
            });
        }
    }
}

/// Streams allowed ZIP members to a counting sink without filesystem
/// materialisation and enforces hard limits against bytes actually returned by
/// the decompressor. Central-directory uncompressed-size fields are treated as
/// untrusted hints only.
pub fn check_archive_resource_limits(
    object_path: &Path,
    limits: ArchiveResourceLimits,
) -> Result<ArchiveResourceSummary> {
    if limits.max_member_bytes == 0 || limits.max_total_bytes == 0 {
        return Err("archive resource limits must both be greater than zero".into());
    }

    let started = Instant::now();
    let file = File::open(object_path)?;
    let mut buffer = vec![0u8; rawzip::RECOMMENDED_BUFFER_SIZE];
    let archive = rawzip::ZipArchive::from_file(file, &mut buffer)?;
    let mut entries = archive.entries(&mut buffer);
    let mut summary = ArchiveResourceSummary {
        members_seen: 0,
        members_completed: 0,
        fully_verified_members: 0,
        accepted_uncompressed_bytes: 0,
        probed_uncompressed_bytes: 0,
        max_member_accepted_bytes: 0,
        metadata_size_mismatch_members: 0,
        metadata_understatement_members: 0,
        limit_hit: None,
        limit_member_index: None,
        limit_member_name: None,
        elapsed_ms: 0,
        materialisation_performed: false,
    };

    while let Some(entry) = entries.next_entry()? {
        let member_index = summary.members_seen;
        summary.members_seen = summary
            .members_seen
            .checked_add(1)
            .ok_or("archive resource member counter overflow")?;
        if entry.is_dir() {
            summary.members_completed = summary.members_completed.saturating_add(1);
            continue;
        }
        if entry.flags().is_encrypted() {
            return Err("archive resource probe refuses encrypted members".into());
        }
        let method = entry.compression_method();
        if method != rawzip::CompressionMethod::STORE
            && method != rawzip::CompressionMethod::DEFLATE
        {
            return Err(format!(
                "archive resource probe refuses unsupported compression method {}",
                method.as_u16()
            )
            .into());
        }

        let remaining_total = limits
            .max_total_bytes
            .saturating_sub(summary.accepted_uncompressed_bytes);
        let accepted_limit = limits.max_member_bytes.min(remaining_total);
        let hit_kind = if limits.max_member_bytes <= remaining_total {
            ArchiveResourceLimitKind::Member
        } else {
            ArchiveResourceLimitKind::Aggregate
        };
        let declared = entry.uncompressed_size_hint();
        let member_name = String::from_utf8_lossy(entry.file_path().as_ref()).into_owned();
        let zip_entry = archive.get_entry(entry.wayfinder())?;

        let probe = match method {
            rawzip::CompressionMethod::STORE => {
                probe_uncompressed_reader(zip_entry.reader(), declared, accepted_limit)?
            }
            rawzip::CompressionMethod::DEFLATE => {
                let decoder = flate2::read::DeflateDecoder::new(zip_entry.reader());
                probe_uncompressed_reader(decoder, declared, accepted_limit)?
            }
            _ => unreachable!(),
        };

        summary.accepted_uncompressed_bytes = summary
            .accepted_uncompressed_bytes
            .checked_add(probe.accepted)
            .ok_or("archive aggregate accepted-byte counter overflow")?;
        summary.probed_uncompressed_bytes = summary
            .probed_uncompressed_bytes
            .checked_add(probe.probed)
            .ok_or("archive aggregate probe-byte counter overflow")?;
        summary.max_member_accepted_bytes = summary.max_member_accepted_bytes.max(probe.accepted);

        let mismatch = probe.metadata_understates || (probe.complete && probe.accepted != declared);
        if mismatch {
            summary.metadata_size_mismatch_members = summary
                .metadata_size_mismatch_members
                .saturating_add(1);
        }
        if probe.metadata_understates {
            summary.metadata_understatement_members = summary
                .metadata_understatement_members
                .saturating_add(1);
        }

        if !probe.complete {
            summary.limit_hit = Some(hit_kind);
            summary.limit_member_index = Some(member_index);
            summary.limit_member_name = Some(member_name);
            summary.elapsed_ms = started.elapsed().as_millis();
            return Ok(summary);
        }

        summary.members_completed = summary.members_completed.saturating_add(1);

        // Only use rawzip's CRC/size verifier when the first independent pass
        // proved that actual decoded length agrees with the untrusted hint.
        // If metadata lies, the mismatch itself is preserved instead of letting
        // the hint prematurely terminate the hard-limit probe.
        if probe.accepted == declared {
            match method {
                rawzip::CompressionMethod::STORE => {
                    let reader = zip_entry.reader();
                    let mut verifier = zip_entry.verifying_reader(reader);
                    std::io::copy(&mut verifier, &mut std::io::sink())?;
                }
                rawzip::CompressionMethod::DEFLATE => {
                    let decoder = flate2::read::DeflateDecoder::new(zip_entry.reader());
                    let mut verifier = zip_entry.verifying_reader(decoder);
                    std::io::copy(&mut verifier, &mut std::io::sink())?;
                }
                _ => unreachable!(),
            }
            summary.fully_verified_members = summary.fully_verified_members.saturating_add(1);
        }
    }

    summary.elapsed_ms = started.elapsed().as_millis();
    Ok(summary)
}

'''

replace_exact(
    archive,
    "pub fn policy_reasons(\n",
    resource_code + "pub fn policy_reasons(\n",
    1,
    "Add metadata-independent member/aggregate streaming limit engine for ARC-008/009/011.",
)

replace_exact(
    main,
    "  inventory-ooxml <workspace> <file>\\n  inventory-pdf <workspace> <file> <qpdf-exe> <qpdf-sha256> <pdfcpu-exe> <pdfcpu-sha256>\\n  verify-object <workspace> <sha256>\\n",
    "  inventory-ooxml <workspace> <file>\\n  inventory-pdf <workspace> <file> <qpdf-exe> <qpdf-sha256> <pdfcpu-exe> <pdfcpu-sha256>\\n  archive-resource-check <file> <max-member-bytes> <max-total-bytes>\\n  verify-object <workspace> <sha256>\\n",
    1,
    "Expose the bounded archive stream checker for qualification and later policy enforcement.",
)

resource_arm = r'''        "archive-resource-check" => {
            let source = arg_path(args.next(), "file")?;
            let member_limit: u64 = args
                .next()
                .ok_or("missing max-member-bytes")?
                .parse()?;
            let total_limit: u64 = args
                .next()
                .ok_or("missing max-total-bytes")?
                .parse()?;
            let summary = archive::check_archive_resource_limits(
                &source,
                archive::ArchiveResourceLimits {
                    max_member_bytes: member_limit,
                    max_total_bytes: total_limit,
                },
            )?;
            println!("{}", serde_json::to_string_pretty(&summary)?);
        }
'''
replace_exact(
    main,
    '        "verify-object" => {\n',
    resource_arm + '        "verify-object" => {\n',
    1,
    "Add JSON-emitting archive-resource-check CLI command.",
)

resource_tests = r'''

#[test]
fn zip_resource_single_member_limit_is_enforced_from_stream_bytes() {
    let member_limit = 512 * 1024u64;
    let summary = archive::check_archive_resource_limits(
        &fixture("arc_single_member_oversize.zip"),
        archive::ArchiveResourceLimits {
            max_member_bytes: member_limit,
            max_total_bytes: 8 * 1024 * 1024,
        },
    )
    .unwrap();
    assert_eq!(
        summary.limit_hit,
        Some(archive::ArchiveResourceLimitKind::Member)
    );
    assert_eq!(summary.accepted_uncompressed_bytes, member_limit);
    assert_eq!(summary.max_member_accepted_bytes, member_limit);
    assert_eq!(summary.probed_uncompressed_bytes, member_limit + 1);
    assert!(!summary.materialisation_performed);
}

#[test]
fn zip_resource_aggregate_limit_is_exact_across_members() {
    let total_limit = 900 * 1024u64;
    let summary = archive::check_archive_resource_limits(
        &fixture("arc_aggregate_oversize.zip"),
        archive::ArchiveResourceLimits {
            max_member_bytes: 1024 * 1024,
            max_total_bytes: total_limit,
        },
    )
    .unwrap();
    assert_eq!(
        summary.limit_hit,
        Some(archive::ArchiveResourceLimitKind::Aggregate)
    );
    assert_eq!(summary.accepted_uncompressed_bytes, total_limit);
    assert!(summary.max_member_accepted_bytes <= 1024 * 1024);
    assert!(summary.probed_uncompressed_bytes >= total_limit + 1);
    assert!(!summary.materialisation_performed);
}

#[test]
fn zip_resource_header_lie_cannot_bypass_actual_stream_limit() {
    let member_limit = 256 * 1024u64;
    let summary = archive::check_archive_resource_limits(
        &fixture("arc_header_size_lies.zip"),
        archive::ArchiveResourceLimits {
            max_member_bytes: member_limit,
            max_total_bytes: 4 * 1024 * 1024,
        },
    )
    .unwrap();
    assert_eq!(
        summary.limit_hit,
        Some(archive::ArchiveResourceLimitKind::Member)
    );
    assert_eq!(summary.accepted_uncompressed_bytes, member_limit);
    assert_eq!(summary.probed_uncompressed_bytes, member_limit + 1);
    assert_eq!(summary.metadata_understatement_members, 1);
    assert_eq!(summary.metadata_size_mismatch_members, 1);
    assert!(!summary.materialisation_performed);
}
'''

before = tests.read_bytes()
text = before.decode("utf-8")
if "zip_resource_single_member_limit_is_enforced_from_stream_bytes" in text:
    raise SystemExit("R2.4 resource tests already present")
tests.write_text(text.rstrip() + resource_tests + "\n", encoding="utf-8", newline="\n")
after = tests.read_bytes()
repairs.append({
    "file": "tests/core_integration.rs",
    "reason": "Add direct ARC-008/009/011 hard-streaming-limit regression tests.",
    "occurrences": 1,
    "before_sha256": sha256_bytes(before),
    "after_sha256": sha256_bytes(after),
})

receipt = {
    "schema": "mcr-r2-4-resource-limit-expansion-v1",
    "generated_utc": datetime.now(timezone.utc).isoformat(),
    "purpose": "Implement the final three controlled hostile-matrix cases using actual decoded stream bytes rather than trusting ZIP size metadata.",
    "matrix_cases": ["ARC-008", "ARC-009", "ARC-011"],
    "expected_matrix_coverage_after_runtime_pass": "57/57",
    "repairs": repairs,
    "resource_policy": {
        "materialisation": "none",
        "member_limit": "configured hard accepted-byte limit",
        "aggregate_limit": "configured hard accepted-byte limit across members",
        "metadata": "untrusted hint only",
        "sentinel": "at most one extra decoded byte may be probed to prove overrun; it is never accepted/materialised",
        "production_numeric_limits": "still pending target-Windows pressure measurement"
    }
}
(out / "R2_4_RESOURCE_LIMIT_EXPANSION_RECEIPT.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
print(json.dumps(receipt, indent=2))
