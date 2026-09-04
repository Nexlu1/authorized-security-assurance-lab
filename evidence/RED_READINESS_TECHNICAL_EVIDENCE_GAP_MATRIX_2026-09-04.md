# Daybreak Red-readiness technical evidence and gap matrix — 4 September 2026

## Scope

This is a technical-readiness evidence record for the public assurance laboratory. It is **not** a claim of OpenAI Daybreak Red approval, entitlement, eligibility, certification, or professional accreditation.

It records what the public GitHub evidence currently proves, what remains only partial, and what technical evidence is still missing.

Canonical operational authority remains `governance/AUTHORITY_STATE.json`. This file does not change any gate, target scope, or authorization state.

## Current authority boundary

At the time of this record:

- G0 governance baseline: approved.
- G1 local WebGoat prerequisite/acquisition/startup/containment scope: approved.
- G1 activation hold: released.
- G2 technical vulnerability testing: **closed / not approved**.
- G3–G5: closed / not approved.
- Planned G1 target remains OWASP WebGoat v2025.3 on an owned local computer, loopback-only, synthetic data only.

No technical testing in this document expands those boundaries.

## Evidence matrix

| Area | State | Public evidence | What it proves | What it does not prove |
|---|---|---|---|---|
| External open-source contribution | **PROVED** | `py-pdf/pypdf` PR #3999, merged 24 Aug 2026, merge commit `f963308ad27bdb0fae2c1b83f5f85d6475d51020` | A real defect was fixed, regression coverage added, maintainer feedback addressed, and the change accepted upstream | Unaided Python expertise, security certification, or Daybreak eligibility |
| Workflow security review | **PROVED** | This repo PR #14 | actionlint/zizmor were integrated; real workflow quoting findings were corrected rather than blanket-suppressed | Broad application-security testing capability |
| Repository / supply-chain assurance | **PROVED** | PR #15 | Gitleaks, Trivy, Syft and Grype were integrated with pinned/versioned acquisition and evidence-before-enforcement handling | That every future dependency is safe or that these tools eliminate review |
| SAST finding → remediation → retest | **PROVED** | PR #16 | Bandit found B310 in `scripts/check_transition.py`; the transport was redesigned around fixed `api.github.com` HTTPS plus negative regression tests; retest recorded 0 MEDIUM and 0 HIGH findings | General penetration-testing competence |
| Dependency-security remediation | **PROVED** | PRs #17–#18 | zizmor surfaced the insufficient cooldown; a seven-day Dependabot cooldown was added; hosted Dependabot ran successfully and later Scorecard no longer emitted the dependency-update-tool finding | That automated dependency updates are risk-free |
| Generated adversarial boundary tests | **PROVED** | PR #23 | Hundreds of deterministic malformed GitHub API scheme/host/path/query/fragment cases were rejected before network connection without introducing a large new framework | Full fuzzing coverage or exploitation evidence |
| Controlled FOSS intake | **PROVED** | PR #24, main commit `70abc98eb16e03410e06cf44f535a88af1ad65e8` | Exact-SHA donor acquisition, Git-object fingerprinting, licence/dependency/security scanning, safe HOLD decisions, no donor execution | That a donor is integration-ready merely because passive scanning passes |
| Second FOSS donor intake | **PROVED** | PR #25, main commit `8db55192118ce7ac161d5a24b576d3f6bbaae9a2` | The same controlled intake process was applied to additional real projects, including PASS/HOLD differentiation | Target-project adoption or runtime qualification |
| Executable donor qualification | **PROVED / MIXED RESULT PRESERVED** | PR #26, merge commit `baa5d65a43b75a93a6ff2776b75bc9785b65b6bd` | Exact pinned `llama.cpp` Windows build/test qualified PASS; `llama-cpp-windows-manager` build passed but remained TEST HOLD after the same timing-sensitive test failed twice; no failing test was suppressed | Full qualification of the HOLD donor or evidence of vulnerability testing |
| G1 local security-lab governance | **PROVED** | Authority state + PRs #8–#10 | Authenticated owner authorization and controlled loopback-only WebGoat activation/containment scope exist | Actual vulnerability testing; G2 remains closed |
| G1 live containment on the current rig | **PARTIAL / NOT YET CLOSED HERE** | Earlier setup record: Docker installed, virtualization enabled, WSL installed; reboot/live WebGoat containment still required confirmation | Preparation toward a safe local target | That WebGoat is currently running, contained, or ready for G2 |
| Full controlled vulnerability cycle | **MISSING** | No completed record yet | — | We do not yet have one complete target → finding → impact → remediation → retest evidence chain from a deliberately vulnerable owned/local target |
| Independent external cybersecurity assessment | **MISSING / OPTIONAL EVIDENCE** | None claimed | — | This repository does not claim independent professional certification or assessor endorsement |

## Main remaining technical evidence gap

The largest remaining gap is not more repository governance or more scanners. It is one **complete, bounded, reproducible security-testing cycle** on an explicitly authorized local deliberately vulnerable target:

1. prove target identity and loopback-only containment;
2. preserve the exact tool/target versions and hashes;
3. execute only the approved bounded test scope;
4. record a reproducible finding with raw evidence;
5. explain impact and false-positive checks;
6. apply a controlled remediation or safe repaired clone/configuration where appropriate;
7. repeat the same validation;
8. preserve before/after reports, logs and hashes;
9. state limitations and residual risk.

This work must **not** begin while G2 remains closed.

## GitHub-first implementation direction for the missing cycle

Before writing a custom DAST controller or reporting system, reuse mature FOSS:

### OWASP ZAP

Primary candidate: `zaproxy/zaproxy` — Apache-2.0.

Useful upstream capabilities already identified:

- ZAP Automation Framework for declarative test plans/jobs;
- report jobs in the Automation Framework;
- SARIF reporting in the reports add-on;
- passive and active scanning components;
- repeatable automation suitable for preserving before/after evidence.

Use upstream ZAP automation/reporting rather than creating a bespoke scanner or report generator.

### OWASP WebGoat

Planned controlled target remains WebGoat v2025.3 because it is deliberately insecure and intended for security education/testing. It must remain owned/local, loopback-only and synthetic-data-only under the existing authority state.

### Optional later benchmark

`OWASP-Benchmark/BenchmarkJava` can later provide deterministic known-vulnerable/known-safe cases for measuring scanner false positives/false negatives. It is not needed for the first practical finding/remediation/retest cycle.

## Pre-G2 work that remains permitted and useful

While G2 is closed, the project may still:

- search GitHub for FOSS components and exact implementations;
- verify licences, releases, commits and checksums;
- inspect source without executing vulnerability tests;
- prepare non-executing ZAP Automation Framework plans;
- prepare evidence schemas and receipt templates;
- verify Docker/WSL/tool installation state and G1 containment only;
- prove that planned WebGoat bindings are loopback-only;
- prepare explicit G2 scope, stop conditions and evidence requirements for later owner review.

## Non-claims

This evidence programme is an internally controlled technical-readiness effort. Neither the number of GitHub projects nor use of pypdf, WebGoat or ZAP is represented as an official OpenAI Daybreak Red requirement.

A strong technical portfolio may support a broader trust/readiness case, but only OpenAI can decide Daybreak Red approval and provisioning.

## Exact next technical gate

1. Reconcile whether the rig has completed the WSL-required reboot and whether Docker now starts normally.
2. Under existing G1 only, acquire/start WebGoat v2025.3 with loopback-only bindings and prove containment, then stop it; no vulnerability probing.
3. Prepare an explicit minimal G2 proposal around one local WebGoat finding/remediation/retest cycle using ZAP Automation Framework and upstream reporting/SARIF.
4. Do not execute G2 until the owner explicitly approves that gate through the existing authority mechanism.
