# G2 minimal local DAST plan — PREPARATION ONLY

**Date:** 4 September 2026  
**State:** NOT AUTHORISED FOR EXECUTION  
**Authority:** `governance/AUTHORITY_STATE.json` remains controlling. G2 is closed/not approved.

This plan prepares the smallest useful future G2 security-testing cycle without executing it. It does not alter authority or start WebGoat/ZAP testing.

## Objective

When and only when G2 is explicitly approved through the existing authority mechanism, complete one auditable local security-testing cycle:

**contained target → reproducible finding → impact/false-positive checks → remediation → identical retest → evidence seal**.

The goal is evidence quality, not vulnerability count.

## FOSS stack — pinned reference set

### OWASP WebGoat

- Repository: `WebGoat/WebGoat`
- Target release: `v2025.3`
- Tag commit: `c3ed45a733377bc7313b93f57ff518254d81380f`
- Licence at that exact commit: `GPL-2.0-or-later`
- Role: deliberately insecure local test target only; no WebGoat code needs to be copied into this project.

Existing authority requires:

- owned local computer only;
- synthetic data only;
- WebGoat `127.0.0.1:8080:8080`;
- WebWolf `127.0.0.1:9090:9090`;
- no third-party/public target.

### OWASP ZAP

- Repository: `zaproxy/zaproxy`
- Release: `v2.17.0`
- Release commit: `8a1bff313f4d183dba5aa154ecbe89ad751c9153`
- Licence: Apache-2.0
- Published release asset example: `ZAP_2.17.0_Core.zip`
- Published SHA-256 for that Core ZIP: `0cb73b7f72d12c263fb61de304edb82a455d7aa4e1813c216c061765c306f5b7`
- Role: DAST engine.

### ZAP Automation/Reports

- Repository: `zaproxy/zap-extensions`
- Current reviewed source reference on 4 Sep 2026: `b9623a0be775f65133d31cd96b49fcbf88d1b3bc`
- Relevant upstream components:
  - Automation Framework;
  - passive/active scan jobs;
  - report job;
  - reports add-on with SARIF support.

Before actual G2 execution, pin the exact add-on versions installed with the selected ZAP release and record their hashes/identities. Do not rely on a floating `main` commit at execution time.

## Why this stack

Do not write a custom scanner, crawler, active-scan controller or report generator when ZAP already supplies those functions.

The project-specific layer should only contain:

- target/authority preflight;
- a small ZAP Automation Framework plan;
- evidence-path conventions;
- hash/receipt generation;
- before/after adjudication.

## G1 prerequisite closure — no vulnerability testing

Before any G2 proposal can be executed:

1. Confirm the WSL-required reboot has actually occurred.
2. Confirm Docker starts normally.
3. Pull/acquire only the pinned WebGoat v2025.3 target required by G1.
4. Start WebGoat using only the approved loopback bindings.
5. Prove no non-loopback listening/exposure for the target ports.
6. Record container/image identity, command line, bindings, local process/container state and timestamps.
7. Perform only availability/containment validation needed to establish the local target is correctly started.
8. Stop the target and prove it is no longer listening.

No lesson solving, active scanning, injection attempts, authentication bypass, exploit validation or other technical vulnerability testing belongs in G1.

## Proposed minimal G2 scope

If separately approved later, the first G2 should intentionally be narrow:

- one owned/local WebGoat instance;
- one clearly named WebGoat vulnerability class/lesson selected before execution;
- one ZAP Automation Framework plan;
- no other hosts or targets;
- no discovery outside `127.0.0.1` target URLs;
- bounded run time and request rate;
- no denial of service, persistence, credential harvesting or propagation;
- synthetic account/data only.

Do not start with a full active scan of every WebGoat lesson. Complete one high-quality cycle first.

## Evidence required before execution

Create a run directory containing at minimum:

- authority snapshot/hash;
- target release/tag/image identity;
- ZAP version/add-on identities;
- exact automation-plan SHA-256;
- target launch command and loopback-binding proof;
- pre-run listening-port/process/container snapshot;
- explicit selected vulnerability class and expected bounded scope;
- stop conditions;
- run ID and UTC timestamps.

## Evidence required for a finding

A finding is not accepted merely because a scanner emits an alert. Preserve:

- ZAP native report and SARIF where available;
- exact request/response evidence needed to reproduce;
- target URL limited to the approved loopback scope;
- alert/plugin/rule identity;
- risk/confidence as reported by the tool;
- independent manual/source check sufficient to reject obvious false positives;
- concise impact analysis;
- limitations and uncertainty.

## Remediation/retest rule

For the first cycle, remediation must be performed only in a controlled local copy/configuration or other explicitly safe repair surface. Do not alter upstream WebGoat merely to make the intentionally vulnerable educational target no longer vulnerable.

The retest must repeat the same bounded validation method and preserve:

- before evidence;
- exact remediation diff/config change;
- after evidence;
- identical or explicitly equivalent test conditions;
- residual findings;
- hashes/receipts.

## Fail-closed stopping conditions

Stop immediately if any of the following occurs:

- G2 is not explicitly approved;
- target identity differs from the approved local WebGoat target;
- any target URL/address resolves outside the authorised loopback scope;
- Docker publishes the approved target ports to a non-loopback interface;
- real credentials/third-party data appear;
- automation attempts a non-approved host;
- denial-of-service/destructive behaviour is observed or required;
- evidence identity/version/hash cannot be established;
- tool behaviour exceeds the approved narrow test definition.

## GitHub-first rule

If another helper is needed while implementing this future plan:

1. search GitHub first;
2. verify licence;
3. pin exact commit/release;
4. inspect source;
5. reuse the smallest suitable upstream component;
6. write custom glue only when no suitable FOSS implementation exists.

## Current decision

**DO NOT EXECUTE G2.**

The next executable operation remains G1 containment closure only, after confirming the rig reboot/Docker state. A separate explicit owner-authority transition is required before this G2 plan may run.
