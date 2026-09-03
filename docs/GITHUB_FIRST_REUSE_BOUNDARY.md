# GitHub-first reuse boundary

**Effective:** 2026-09-03

This project uses GitHub as the first place to look for reusable free/open-source software before implementing generic functionality ourselves.

## Default rule

1. Search GitHub first for mature FOSS that already solves the need.
2. Inspect actual source, licence, maintenance state and release/provenance information before reuse.
3. Prefer reuse/adaptation of maintained FOSS over bespoke replacement code.
4. Keep bespoke code to project-specific integration, safety, authority and UX where a suitable FOSS component does not already exist.

## Third-party interaction boundary

Third-party GitHub repositories are **read/research sources by default**, not automation targets.

- Do not automatically create or update third-party issues, issue comments, pull requests, reviews, discussions or other write-side interactions.
- Do not hunt for unrelated third-party bugs merely to create contribution activity.
- Do not create automated integrations with third-party issue trackers.
- Do not ask the user to fork or submit upstream work merely for portfolio/evidence value.
- Upstream contribution work is exceptional: it must directly block or materially improve a project need and requires fresh, explicit user approval before any third-party write-side interaction.
- Reading/searching public repositories, code, releases, licences, issues and pull requests remains allowed for FOSS discovery, compatibility research and defensive engineering.

## Human-work rule

Use the connected GitHub tools to perform as much work as possible inside repositories the user controls. Ask the user to perform a GitHub action only when it is genuinely unavailable through the connection or requires a personal account-level decision.

## Security-testing boundary

GitHub-first reuse does not expand security-testing authority. Vulnerability testing remains limited by the repository's existing authorization and containment controls.
