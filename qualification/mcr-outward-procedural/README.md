# MCR outward procedural rehearsal — synthetic only

This directory is the synthetic integration checkpoint for MCR outward procedural tooling.

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

## Operating model

- Work local-first and batch-first.
- Perform substantive engineering with OpenCode and local Git before GitHub administration.
- Use `Invoke-OutwardProceduralTrancheR2.ps1` as the local executable gate.
- Use GitHub as a donor, provenance and integration checkpoint.
- Treat hosted Actions as optional supporting evidence, not current authority.
- Do not use paid hosted CI.
- Create one meaningful integration PR only after a coherent local PASS.
- Do not create issues, branches or PRs for ordinary next steps.

## Local execution

Run `Invoke-OutwardProceduralTrancheR2.ps1` from a local-only `local/*` Git branch.

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

The R2 gate builds the synthetic procedural set and qualified hearing/core derivatives, validates every PDF with qpdf and pdfcpu strict mode with configuration disabled, and writes the final receipt and ZIP to G: when available.
