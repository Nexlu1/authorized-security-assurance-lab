# Authorized Security Assurance Lab

A public, sanitized governance and evidence-control reference for lawful, explicitly authorized cybersecurity research.

This repository is an independent personal project. It is **not** an OpenAI repository, does not imply OpenAI endorsement or Daybreak approval, and does not grant permission to test any third-party system.

## Safety boundary

No technical security testing is authorized by this repository's bootstrap state. Future testing may occur only after the canonical authority state records an explicit owner approval for a named, bounded target and objective, and the protected review/transition checks pass.

The planned training target is OWASP WebGoat in a local, loopback-only configuration using synthetic data. Public or third-party targets are outside scope unless separately and explicitly authorized.

## Why this repository is public

The repository contains only sanitized governance, controls, test code, and public evidence. Private conversation records, secrets, personal data, private infrastructure details, and historical internal evidence are intentionally excluded.

## Canonical records

- `governance/AUTHORITY_STATE.json` — operational gate state.
- `evidence/EVIDENCE_REGISTER.json` — append-only public evidence register.

Markdown is explanatory only and cannot grant or expand authorization.

Key public control documents:

- `docs/SCOPE_AND_AUTHORIZATION.md`
- `docs/RULES_OF_ENGAGEMENT.md`
- `docs/REVIEW_AND_TRANSITION_CONTROL.md`
- `docs/PUBLIC_EVIDENCE_MODEL.md`
- `docs/STANDARDS_BASELINE.md`
- `docs/CONTAINMENT_BASELINE.md`
- `docs/REPOSITORY_ENFORCEMENT.md`

## Controls

- PR-before-merge governance.
- Strict required status checks.
- A base-controlled `pull_request_target` guardian that evaluates candidate authority using trusted prior code.
- Append-only evidence.
- Owner-authenticated, unedited GitHub approval comments for authority transitions.
- Self-amendment protection for trusted control code.
- Explicit stop/fail-closed behavior.

## Bootstrap and current state

The initial public bootstrap deliberately starts with every operational gate closed and grants **no** technical-testing authority. Current operational status is always read from `governance/AUTHORITY_STATE.json`; this README cannot promote or override that state.
