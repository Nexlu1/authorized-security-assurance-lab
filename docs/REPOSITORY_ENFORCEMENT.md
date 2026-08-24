# Repository Enforcement Baseline

This repository is designed to use GitHub-enforced branch controls on its public `main` branch. The ruleset is a platform control, not an OpenAI requirement or certification.

## Bootstrap exception

The initial sanitized repository seed is the one-time pre-enforcement bootstrap needed to install the trusted workflows. It must contain no operational approvals and must leave all gates closed with the activation hold active.

After the bootstrap reaches `main`, create one non-authority probe pull request so GitHub records the actual `governance-integrity` and `trusted-authority-guardian` check identities. Do not merge the probe.

No authority-changing pull request may be opened until the ruleset below is observed as active and enforced.

## Required `main` ruleset

Configure one active branch ruleset targeting `main` with:

- bypass list empty;
- restrict deletions enabled;
- require a pull request before merging enabled;
- required approvals set to `0`;
- require conversation resolution before merging enabled;
- require status checks to pass enabled;
- required check `trusted-authority-guardian`, with the GitHub Actions source selected where GitHub exposes source binding;
- required check `governance-integrity`, with the GitHub Actions source selected where GitHub exposes source binding;
- **Require branches to be up to date before merging** enabled;
- block force pushes enabled.

Leave these controls disabled unless a later, separately reviewed control change justifies them:

- restrict creations;
- restrict updates;
- require linear history;
- require deployments to succeed;
- require signed commits;
- require review from specific teams;
- require approval of the most recent reviewable push;
- additional Copilot-specific approval rules;
- code-scanning, code-quality, or code-coverage merge rules not already defined by this control plane.

Allowed merge methods may remain at the repository defaults. The trusted transition model validates semantic state and current-base chronology rather than relying on a particular merge-commit shape.

## Strict current-base rule

A previously green guardian result is insufficient after `main` advances. Strict/up-to-date enforcement must make the pull request ineligible until it incorporates the new base and both required checks rerun.

If GitHub cannot enforce the required controls, stop before authority changes rather than substituting convention for platform enforcement.

## Acceptance evidence

Before the first authority-changing pull request, observe all of the following in GitHub:

1. ruleset enforcement is active for `main`;
2. bypass list is empty;
3. pull requests are required;
4. conversation resolution is required;
5. `trusted-authority-guardian` is a required GitHub Actions check;
6. `governance-integrity` is a required GitHub Actions check;
7. branch-up-to-date/strict checking is enabled;
8. force pushes are blocked;
9. deletion is restricted.

Record the ruleset observation as public administrative evidence only after those properties are actually visible in GitHub.
