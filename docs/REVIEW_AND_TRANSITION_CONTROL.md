# Review and Transition Control

This repository uses two independent GitHub Actions checks once public branch enforcement is enabled:

- `governance-integrity` validates the candidate's current canonical state and runs the adversarial test suite.
- `trusted-authority-guardian` is triggered by `pull_request_target`, checks out only the trusted base branch, fetches the proposed head as Git data, and evaluates the candidate with trusted prior-state code.

## Owner authorization artifact

Opening a gate requires one unedited GitHub issue or pull-request comment in this same repository from the repository owner. The comment is independently fetched through GitHub's API and must have `OWNER` association with `created_at == updated_at`.

The approval text is deterministic and contains:

1. an `Authorization digest` calculated from the exact semantic result being approved;
2. the exact list of gates being opened;
3. the exact `authorized_scope` for every opened gate; and
4. a statement that no other gate is approved by that comment.

The digest deliberately excludes the comment URL/timestamp and evidence-record metadata, avoiding a circular dependency: the owner can approve the intended semantic state first, and the later candidate can record the resulting GitHub artifact without changing what was approved.

A single owner comment may approve more than one gate where every dependency and every exact scope is expressed in the digest-bound state. Higher gates are never inferred from lower ones.

## Gate relationships

G1 depends on G0. G2 depends on G0/G1 and may open only after the activation hold was already released in trusted prior state. G3 depends on G2. G4 governs future publication/disclosure of lab findings or evidence beyond the sanitized governance bootstrap and is independent after G0. G5 scope expansion is intentionally unavailable in control version 1 until a separate reviewed scope-migration control exists.

## Self-amendment protection

An authority-changing pull request may not modify:

- `.github/workflows/governance-integrity.yml`;
- `.github/workflows/trusted-authority-guardian.yml`;
- `scripts/check_governance.py`;
- `scripts/check_transition.py`.

Control maintenance must therefore be merged separately while authority remains unchanged. The new control becomes trusted only after it reaches `main` and may govern a later authority transition.

## Evidence

`evidence/EVIDENCE_REGISTER.json` is append-only. Existing entries cannot be edited, reordered, deleted, or reclassified. Authority changes must append the exact transition artifact required by the trusted checker. Evidence IDs are sequential and timestamps are monotonic.

## Strict merge-base rule

The public `main` branch must be configured with GitHub enforcement requiring both checks and **Require branches to be up to date before merging**. If `main` advances, a stale pull request must update and rerun against the new base before it can merge.

## `pull_request_target` safety model

The guardian never checks out or executes pull-request-controlled code. It checks out the trusted base SHA, fetches the proposed commit only as Git data, reads candidate JSON with `git show`, and runs only checker code already present on the trusted base. Its token permissions are read-only.

## Bootstrap

The initial public repository bootstrap contains no approvals and no technical-testing authority. It is the one-time pre-enforcement seed needed to install the trusted workflows. A non-authority probe pull request should then exercise both check identities. Only after GitHub enforcement is observed live may the first authority-changing pull request be opened.
