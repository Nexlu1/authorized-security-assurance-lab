# MCR outward procedural rehearsal — synthetic only

This directory is the public/synthetic GitHub control point for MCR outward procedural tooling.

## Purpose

Reuse proven open-source components and official HMCTS implementation patterns before writing custom code.

## Donors

- HMCTS `em-stitching-api` — behaviour reference for bundle/stitching controls.
- HMCTS `sscs-case-loader` — SSCS case/document-flow reference.
- `J-F-Liu/lopdf` — pinned Rust PDF manipulation layer already qualified in the synthetic court-bundle builder.
- `typst/typst` — pinned document-generation layer for synthetic procedural documents.
- `qpdf/qpdf` — independent PDF structural validator.
- `pdfcpu/pdfcpu` — independent strict PDF validator.

Exact versions, commits, licences and hashes are in `GITHUB_DONOR_MANIFEST_R1.json`.

## Privacy boundary

This public directory must never contain R59 PDFs, claimant evidence, private correspondence, medical/financial material or live case identifiers.

## Local execution

Use OpenCode + GPT-5.6 Sol on the Windows rig with `OPENCODE_GITHUB_FREEZE_AND_REHEARSAL_MISSION.txt`.

Storage policy:
- C: no intentional project writes.
- E: tools/repos/donor assets.
- F: workspace/build/cache/temp.
- G: result archive when available.

## Success gates

1. GitHub contains and re-serves the exact qualified court-builder source bytes.
2. Synthetic procedural Typst document generation passes.
3. qpdf passes.
4. pdfcpu strict validation passes.
5. No R59/private evidence access.
6. No intentional project writes to C:.
