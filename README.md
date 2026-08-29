# Authorized Security Assurance Lab

A public, sanitized governance and evidence-control reference for lawful, explicitly authorized cybersecurity research.

This repository is an independent personal project. It is **not** an OpenAI repository, does not imply OpenAI endorsement or Daybreak approval, and does not grant permission to test any third-party system.

## Safety boundary

Technical security testing is authorized only when the canonical authority state permits it. The current canonical state keeps G2 technical security testing closed; narrative files cannot override that state.

The currently planned G1 setup/activation route uses OWASP WebGoat in a local, loopback-only configuration with synthetic data. G1 permits only prerequisites, image acquisition, startup, and containment validation; it does **not** authorize WebGoat lesson solving or other technical security testing. This route is optional evidence-building setup work, not a requirement to obtain OpenAI Daybreak access. Public or third-party targets remain outside scope unless separately and explicitly authorized.

## Daybreak positioning

OpenAI's current Daybreak Access guidance distinguishes Daybreak Blue from separately approved Daybreak Red. Daybreak Red is intended for advanced, authorized workflows and is subject to additional approval, stronger verification, monitoring, access controls, and human oversight.

This repository is an evidence-building and governance exercise, **not an official OpenAI qualification checklist**. Open-source contributions, WebGoat exercises, GitHub controls, project counts, or other portfolio artifacts must not be described as formal Daybreak Red requirements or as proof of approval. Any eligibility or access claim must be checked against current first-party OpenAI guidance and the actual account/workspace entitlement.

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

## Current state

The repository began with every operational gate closed. Current operational status is always read from `governance/AUTHORITY_STATE.json`; this README cannot promote or override that state.
