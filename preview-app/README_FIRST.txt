MCR ENGINEERING PREVIEW — 7 SEPTEMBER 2026

This is a runnable engineering checkpoint, not the final production-certified MCR tooling release.

HOW TO START
1. Keep this entire extracted folder together.
2. Double-click: MCR Engineering Preview.exe
3. Use Import & inspect -> Browse to choose a file.
4. The default workspace is your Documents\MCR Engineering Preview Workspace folder.

WHAT IT DOES NOW
- SHA-256 content-addressed capture with separate occurrence provenance
- ZIP/archive inventory and hostile path controls
- EML and MBOX indexing with provenance warnings
- CSV byte-position / text decoding provenance
- DOCX/XLSX/PPTX OOXML state inspection
- PDF inspection using bundled qpdf 12.4.1 + pdfcpu 0.15.0

SAFETY / SCOPE
- Local workflow; no cloud upload is part of this preview.
- The engine preserves original source bytes in the workspace object store.
- This preview does not retroactively certify or modify frozen production MCR R59.
- 57/57 functional hostile behaviours have been reached in engineering qualification, but target resource calibration and final release/promotion controls are still open.

FOSS SHELL
- egui/eframe 0.36.1 — Apache-2.0 — GitHub: emilk/egui
- rfd 0.17.2 — MIT — GitHub: PolyMeilex/rfd
- qpdf 12.4.1 — Apache-2.0 — GitHub: qpdf/qpdf
- pdfcpu 0.15.0 — Apache-2.0 — GitHub: pdfcpu/pdfcpu

If the app shows an error, take a screenshot and send it back to the development chat. Do not repeatedly rerun a failing operation.
