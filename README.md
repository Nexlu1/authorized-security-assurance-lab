# mcr-ingest 0.8.0 — recovery candidate

This is a compile-ready, read-only Rust CLI created to continue the Master Case Record tooling engineering lane after the previous chat ended before R8 was safely persisted.

It inventories a directory without following symlinks, hashes bounded regular files with SHA-256, compares common file signatures with extensions, examines ZIP metadata without extracting it, flags hostile paths and archive-bomb indicators, and writes an atomic JSON manifest plus an optional Markdown report.

## Build and test

```powershell
cargo fmt --check
cargo test --all-targets
cargo clippy --all-targets -- -D warnings
cargo build --release
```

## Scan

```powershell
.\target\release\mcr-ingest.exe scan "D:\Evidence" `
  --output "D:\Results\manifest.json" `
  --report "D:\Results\report.md"
```

Exit codes: `0` no high/critical finding or scan error; `2` high finding or recoverable scan error; `3` critical finding; `4` invalid manifest hash.

## Non-negotiable limits

This candidate is not a forensic disk imager, malware sandbox, antivirus engine, OCR system, evidential authenticity opinion, or replacement for a human review. It never extracts ZIP contents and never executes an ingested file. R7 source files were not silently reconstructed or claimed to be present; the recovery gap is recorded in `../CONTROL/R7_R8_RECOVERY_GAP.md`.
