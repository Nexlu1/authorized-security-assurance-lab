MCR TOOLING — ENGINEERING PREVIEW
6 September 2026

WHAT THIS IS
This is a runnable Windows engineering preview built around the current R2.4 mcr-ingest engine and bundled qualified FOSS specialist tools.

It is intended to let a human use and see the current work instead of interacting only with command-line qualification scripts.

CURRENT ENGINEERING EVIDENCE
- Earlier actual target Windows PC qualification: PASS, 19/19 integration tests, 0 failures.
- Controlled hostile-input matrix: 57/57 behaviours functionally exercised in the engineering programme.
- R2.4 Windows executable is built through the pinned x86_64-pc-windows-gnullvm route and has a reproducible SHA-256 across Windows Server 2022 and 2025.
- Bundled qpdf 12.4.1 and pdfcpu 0.15.0 are FOSS specialist engines.

IMPORTANT STATUS
THIS IS AN ENGINEERING PREVIEW, NOT THE FINAL PRODUCTION-CERTIFIED RELEASE.
Remaining release/acceptance work includes final consolidated full-suite fixture qualification, final target-PC acceptance/calibration, and final promotion review.

HOW TO RUN
1. Extract the entire ZIP to a normal local folder.
2. Double-click MCR_TOOLING_ENGINEERING_PREVIEW.exe.
3. Choose a workspace folder.
4. Choose a file.
5. Use Quick Analyse, or choose the specific operation.

SUPPORTED CURRENT OPERATIONS
- Generic file ingestion into the SHA-256 content-addressed workspace.
- ZIP inventory.
- EML indexing.
- MBOX indexing.
- CSV indexing with byte-position provenance.
- Office Open XML inventory for DOCX/XLSX/PPTX.
- PDF state inventory using bundled qpdf/pdfcpu.
- Bundled-package hash verification.

LOCAL / PRIVACY BOUNDARY
The preview itself performs local processing. It does not upload evidence or make network calls. The bundled executable and specialists are already present in the extracted package.

SOURCE HANDLING
The engine is provenance-first and does not intentionally mutate source evidence. It writes the controlled object store, SQLite state, audit records and derivatives into the workspace you select.

For an engineering preview, use a fresh workspace and preferably begin with non-critical copies or synthetic/sample files while final release acceptance is still open.

FROZEN PRODUCTION MCR
The existing frozen MCR R59 is outside this future-tooling preview and is not modified by the package.
