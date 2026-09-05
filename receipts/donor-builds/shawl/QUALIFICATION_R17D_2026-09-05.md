# Shawl qualification receipt R17D — 2026-09-05

**Status:** HOLD  
**Target lane:** Remote Rig Access / Windows service wrapper and recovery  
**Candidate:** `mtkennerly/shawl`  
**Revision:** `51e7ac0910621a4827cfd92cb2a0d5ec5b468af0`  
**Version:** 1.9.0  
**License:** MIT  
**Qualification Rust:** `1.85.0-x86_64-pc-windows-msvc`

## Decision

HOLD. Do not adopt this exact revision yet.

This is not a REJECT because the repeated failing assertion is a test precondition: Shawl's test fails while trying to observe that the PowerShell parent has spawned a grandchild. It fails before the job object is dropped and before the test reaches the code that verifies that parent and grandchild processes were killed. The evidence therefore does **not** prove that Shawl's production process-tree termination is broken.

It is not a PASS because the same process-tree test failed on every independent controlled qualification attempt. Process-tree control is relevant to the service-wrapper/recovery use case, so the failure cannot be waived.

## Independent Windows evidence

Qualification work was performed in PR #35 without importing Shawl source into this repository.

### Run 33971515647 — attempt 1

- Exact Shawl source SHA verification: PASS
- Exact Rust 1.85.0 setup: PASS
- `cargo test --locked -- --test-threads 1`: FAIL
- Result: 90 passed, 1 failed
- Failure: `service::speculate_2::process_job::test_kills_child_and_grandchild_processes_when_job_is_dropped`
- Panic: `Expected parent to spawn at least one grandchild`
- Evidence artifact ID: `9971078137`
- Artifact ZIP SHA-256: `42d3b0e018c615ce9434d230bbd917aa4bc0ca00f0a4bb1a326d932570822978`

### Run 33971515647 — controlled rerun

Fresh Windows Server 2022 runner in a different Azure region.

- Exact source/toolchain setup: PASS
- `cargo test --locked -- --test-threads 1`: FAIL
- Result: 90 passed, 1 failed
- Same test and same panic as attempt 1
- Evidence artifact ID: `9971117294`
- Artifact ZIP SHA-256: `f423cfe20a95b591859f8adedf7f5bb705e7b4ed36aeed02d1313708d1b796a2`

### Run 33971830631 — full-evidence qualification

Harness was changed only so later evidence stages would execute even after a failed test; the final gate still treats any failed underlying outcome as failure.

Manifest outcomes:

- `tests_outcome=failure`
- `build_outcome=success`
- `audit_tool_outcome=success`
- `audit_outcome=failure`

The test failure was again identical: 90 passed, 1 failed, same process-tree test and same `Expected parent to spawn at least one grandchild` panic.

Evidence artifact ID: `9971186305`  
Artifact ZIP SHA-256: `25434c05b5f45845dcc87d920a9334f31a15711870a30a86d4d110a57b549990`

**Observed result across controlled attempts: 3/3 failures of the same process-tree test.**

## Why the process-tree failure is qualified rather than overstated

The exact Shawl test:

1. starts a PowerShell parent;
2. asks it to spawn another PowerShell process;
3. sleeps for only 300 ms;
4. uses `sysinfo` to look for a process whose parent PID equals the spawned parent PID;
5. asserts that at least one such process exists;
6. only after that assertion would it drop the Windows job object and test whether the process tree dies.

All three independent failures occurred at step 5. The kill verification was not reached. A spawn/discovery/timing or hosted-runner interaction therefore remains a plausible explanation, but the repeated result is still enough to block PASS.

## Release build evidence

In the full-evidence run:

- `cargo build --release --locked`: PASS
- `shawl.exe --help`: PASS
- Built EXE SHA-256: `b500552453b5057f4148af262aea9475ccbe916190a490538bf15477afcdfdb0`

No Shawl donor code or binary is adopted by this receipt.

## RustSec audit

Audit tool:

- RustSec `cargo-audit` version: 0.22.2
- Verified release archive SHA-256: `0a7316540862c13d954f648917ceacca593747baed6eec180fafa590be2710ab`
- RustSec database last updated in the retained audit result: `2026-09-02T11:13:32+02:00`
- Lockfile dependency count: 103

Finding:

- `RUSTSEC-2026-0204`
- Package: `crossbeam-epoch 0.9.18`
- Patched: `>=0.9.20`
- Title: invalid pointer dereference in `fmt::Pointer` implementation for `Atomic` and `Shared` when the underlying pointer is invalid

### Runtime-exposure qualification

The exact Shawl `Cargo.toml` places `sysinfo` under `[dev-dependencies]`. The successful locked release-build log did not compile `sysinfo`, `crossbeam-epoch`, `rayon`, or `speculate`. The retained evidence therefore supports treating `RUSTSEC-2026-0204` as a **development/test dependency finding for this revision**, not as a demonstrated vulnerability embedded in the release EXE.

The test/development graph also emitted a future-incompatibility warning for `syn v0.14.9` under Rust 1.85.0.

## Disposition

- **Shawl 1.9.0 / `51e7ac0...`: HOLD**
- **WinSW candidate previously assessed: remains SECURITY HOLD**
- **Remote Rig service-wrapper/recovery donor cell: unresolved**

Requalify Shawl only when a later exact revision or a controlled patch provides evidence that:

1. the process-tree test is made deterministic or an equivalent independent process-tree test passes reliably;
2. the RustSec lock audit is clear, or any remaining dev-only finding is explicitly resolved/contained and documented;
3. the exact locked Windows release build and CLI smoke test still pass;
4. provenance, licence, source pinning and evidence-retention controls remain satisfied.

Until then, do not adopt Shawl for the Remote Rig Access service/recovery layer.