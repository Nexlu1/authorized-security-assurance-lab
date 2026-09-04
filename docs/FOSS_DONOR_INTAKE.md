# Controlled FOSS donor intake

## Purpose

This is the bridge between GitHub reconnaissance and product integration.

We do not treat a useful-looking repository as code we can simply paste into a project. We first acquire and inspect an exact source revision, preserve its provenance, scan it, decide what is actually useful, then integrate only the minimum justified code or pattern into the correct project.

## Intake sequence

1. **Need** — identify a real project problem first.
2. **Search GitHub** — prefer maintained free/open-source projects over bespoke replacements.
3. **Pin** — record the exact repository and full commit SHA.
4. **Licence check** — read the actual upstream LICENSE/NOTICE and record the expected licence.
5. **Acquire** — download only that exact GitHub commit into an isolated intake workspace.
6. **Fingerprint** — record the exact commit and source-tree hashes.
7. **Scan** — run source secret scanning, vulnerability/misconfiguration/licence scanning, SBOM generation and vulnerability review.
8. **Inspect** — read the actual relevant code and dependency files; do not rely on README claims alone.
9. **Build/test qualification** — only after the passive intake review, use a separate no-secrets/no-write isolated job if executing upstream build/tests is justified.
10. **Decision** — classify as USE, ADAPT, STUDY, HOLD or REJECT with reasons.
11. **Integrate in the target repository** — copy/adapt only the needed portion or use the dependency normally; preserve copyright/licence/NOTICE obligations and provenance.
12. **Test our integration** — the target project must pass its own tests and security controls. Upstream tests do not prove our integration is correct.

## Hard boundaries

- Third-party repositories are read-only research/source donors by default.
- The intake workflow does not comment, open issues, create pull requests, or push to donor repositories.
- The passive intake workflow does **not execute donor code**.
- No donor is automatically approved because scanners are green.
- No source is copied into a target product merely because its licence is permissive.
- Licence, dependency and security findings are evidence to review, not results to suppress.
- Exact upstream provenance must remain traceable after adaptation.

## Why source is not bulk-committed here

This repository is the intake/control bench, not a warehouse of copied third-party applications. GitHub Actions obtains exact pinned revisions in disposable workspaces and preserves scan/fingerprint evidence. Approved code belongs in the relevant target repository, with its attribution and provenance, rather than mixing every donor codebase into one giant repository.

## First pilot

The initial pilot qualifies three Go-native candidates relevant to current work:

- `maragudk/goqite` — persistent SQLite queue/job patterns for ECO.
- `shirou/gopsutil` — real resource/process metrics for ECO/Rig tooling.
- `schollz/progressbar` — engineering/support CLI progress reporting.

The pilot deliberately replaces the earlier assumption that Python queue/monitoring libraries should automatically be used in ECO. ECO is predominantly Go, so direct-code candidates must be architecture/language compatible unless there is a specific cross-language boundary.
