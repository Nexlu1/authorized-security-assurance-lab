# Scope and Authorization

This document is explanatory. `governance/AUTHORITY_STATE.json` is the only operational authority source.

## Bootstrap scope

At bootstrap, no target activation or technical testing is authorized and all operational gates are closed.

The only planned training target is:

- OWASP WebGoat `v2025.3`;
- official image `webgoat/webgoat:v2025.3`;
- owned/local computer only;
- loopback-only WebGoat/WebWolf bindings;
- synthetic data only.

Planning a target does not authorize activation or technical testing.

## Always out of scope unless separately authorized

- public Internet targets not owned by the operator;
- third-party production systems, accounts, APIs, networks, cloud tenants, or data;
- real credentials or sensitive third-party data;
- denial of service, destructive activity, uncontrolled scanning, propagation, or persistence.

## Gate dependencies

- G0 establishes the governance baseline.
- G1 local target activation requires G0.
- G2 technical security testing requires G0, G1, and a previously released activation hold.
- G3 higher-impact validation requires G2.
- G4 future publication/disclosure of lab findings or evidence beyond the sanitized governance bootstrap requires G0 but is otherwise independent of G1-G3.
- G5 scope expansion is fail-closed in control version 1 and requires a separately reviewed scope-migration control before it can be used.

## Transition rule

A gate may open only through a reviewed pull request after repository enforcement is active. The trusted base guardian authenticates an unedited GitHub issue/PR comment from the repository owner. The comment contains a SHA-256 digest of the exact semantic authorization result and the exact scope for every gate it approves. The digest is recomputed from the candidate canonical state, so later scope or gate changes invalidate the approval artifact.

## Runtime evidence boundary

The canonical target object records the planned bounded target, not live runtime telemetry. Actual image acquisition, start, containment validation, stop, remediation, and retest events are recorded separately as evidence when observed. GitHub state must not claim that a local service is currently running unless an appropriate evidence mechanism is introduced and validated.
