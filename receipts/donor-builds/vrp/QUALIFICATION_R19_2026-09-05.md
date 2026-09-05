# VRP near-duplicate video-similarity qualification R19 — 2026-09-05

**Lane:** GitHub/FOSS reconnaissance → Video Research Programme (VRP)  
**Purpose:** close the remaining near-duplicate-video PARTIAL cell using independently qualified existing FOSS rather than bespoke implementation.

## Overall decision

| Capability | Donor | Exact revision | Licence | Decision |
|---|---|---|---|---|
| Whole-video / same-length near-duplicate detection | `facebook/ThreatExchange` TMK+PDQF | `73a742c45c35d711e94c8bf92254df1a2d9c9f01` | BSD-3-Clause-style root licence | **PASS / USE** |
| Partial-video / clip / subsequence matching | `facebook/ThreatExchange` vPDQ | `73a742c45c35d711e94c8bf92254df1a2d9c9f01` | BSD-3-Clause-style root licence | **PASS / USE** |
| Simple Python whole-video perceptual hash | `akamhy/videohash` | `e407bb0b26de625a846c2700072efccd9eb44e9a` | MIT | **HOLD / legacy study only** |

**Recommended VRP architecture:** use TMK as the primary whole-video near-duplicate index and vPDQ as the complementary partial/clip matcher. Do not make `videohash` a core dependency.

## 1. Meta ThreatExchange source boundary

- Repository: `facebook/ThreatExchange`
- Exact qualified SHA: `73a742c45c35d711e94c8bf92254df1a2d9c9f01`
- The inspected mainline was active in 2026 rather than an abandoned historical repository.
- Root licence permits source/binary redistribution and modification subject to the stated BSD-style notice/conditions/disclaimer requirements.
- The older research repository `facebookresearch/videoalignment` was also inspected but is archived; it was not preferred over the maintained production implementations in ThreatExchange.

No ThreatExchange source or binary is imported by this receipt.

## 2. TMK+PDQF — PASS / USE

### Role

TMK produces a fixed-length video fingerprint using PDQ-derived frame features plus a temporal component. It is well suited to whole-video near-duplicate matching, particularly videos representing substantially the same content/length with transformations such as quality/resolution/logo/bar changes.

It is not the preferred tool for arbitrary short excerpts cut from longer videos; vPDQ fills that separate role.

### Independent qualification

Experimental qualification PR: #39  
Workflow run: `33973310185`  
Artifact: `vrp-tmk-r19`  
Artifact ID: `9971570081`  
Artifact digest: `sha256:887266e69dc8ab37bd0a63f4ae5a0a571664dbe4250980ae79e555c4717b7ce9`

Results:

- exact source SHA verification: PASS
- native C++ build: PASS
- upstream TMK regression hashing against committed reference hashes: PASS
- independent known-similar / known-different scoring smoke: PASS

Independent score evidence:

- known near-duplicate pair `chair-19-sd-bar` vs `chair-20-sd-bar`: `0.989083 / 0.991138`
- unrelated pair `chair-19-sd-bar` vs `doorknob-hd-no-bar`: `0.199326 / 0.281832`

The qualified run therefore demonstrated strong separation between the selected near-duplicate and unrelated sample rather than merely proving that the code compiled.

Qualified binary SHA-256 receipts from that Linux build:

- `tmk-hash-video`: `397385f22881cb696b60b68366364f5a95f62ea79cd5ed68f4578e491ea5cdb3`
- `tmk-compare-two-tmks`: `85b9f82ab4fadb6f4c6c4a6a1aad55ddc45c717d726e39bca755034b152ae284`
- `tmk-two-level-score`: `4671e4ffbadb698f627ba0acc6049db3126dc2cba5e5a77c1480e5a0a554a48c`
- `tmk-clusterize`: `fba39d9c1502df1a0d0b959a83f3fbf997db55d920c2eeb8d2a806e535bf53af`

These executable hashes are evidence for this qualification run, not a substitute for reproducible source pinning on another platform/build environment.

### Adoption rule

Use/pin the exact source revision or independently requalify a later revision. Preserve licence/NOTICE requirements. Treat matching thresholds as application policy that must be calibrated on VRP's own representative corpus rather than assuming the regression smoke values are universal production thresholds.

## 3. vPDQ — PASS / USE

### Role

vPDQ creates PDQ hashes for selected video frames and supports matching at frame/segment level. It is the complementary donor for identifying a clip/subsequence inside a longer source video where a fixed-length whole-video fingerprint is insufficient.

### Independent qualification

Experimental qualification PR: #39  
Workflow run: `33973310185`  
Artifact: `vrp-vpdq-r19`  
Artifact ID: `9971584857`  
Artifact digest: `sha256:bc2225a53afb842cdbdffce3181e7fa5bbd920f4a18d77fef07ccc03539eeae9`

Results:

- exact source SHA verification: PASS
- CMake/native build: PASS
- complete upstream vPDQ regression exercise on committed samples: PASS
- auto-thread and single-thread hashing both matched committed reference hashes: PASS
- feature-frame ordering validation: PASS
- independent actual clip→full-video smoke: PASS

The independent smoke used the qualified sample source `chair-orig-22-sd-bar.mp4`:

- source duration: `22.464` seconds
- generated/re-encoded query clip: `4.0` seconds from the beginning
- vPDQ query-video match reported: **100.00%**
- target-video coverage reported: **17.39%**

That is the expected shape for a short query contained inside a longer target and directly demonstrates the capability that the old `videohash` donor lacks.

Qualified binary SHA-256 receipts from that Linux build:

- `vpdq-hash-video`: `9b559c508f0e246ed44e17ca89931e6efdc002170e3865f46053568a45e37cc0`
- `match-hashes-byline`: `12c5b86481e804fc71d13eadbc53182c7dbd7da25b8098f16be0200ac98a7276`
- `match-hashes-brute`: `ac29a623c106655b8f8fa7d99b1e9fd95fe38e7391246041b964091ad1951e72`

### Adoption rule

Use vPDQ for partial/segment matching where TMK's fixed-length whole-video approach is unsuitable. Search/index strategy and distance/quality thresholds must be calibrated for VRP scale and error tolerance rather than copied blindly from the smoke test.

## 4. `akamhy/videohash` — HOLD / legacy study only

### Donor

- Repository: `akamhy/videohash`
- Exact inspected SHA: `e407bb0b26de625a846c2700072efccd9eb44e9a`
- Package version: `3.0.1`
- Licence: MIT
- Last commit on inspected mainline: 2022-05-29

The package is a small Python whole-video perceptual-hashing implementation and its README explicitly states that it cannot determine that one video is part of another. This means it does not cover the key clip/subsequence capability solved by vPDQ.

### Exact-source current-environment qualification

Workflow run: `33973310185`  
Artifact: `vrp-videohash-r19`  
Artifact ID: `9971574998`  
Artifact digest: `sha256:57b916b651b734d6bcf2333c0f53fb86dd349141c55a1dedf1bd95be74e45bd5`

Results on Python 3.12/current dependencies:

- install: PASS
- `pip check`: PASS
- dependency audit (`pip-audit 2.10.1`): PASS / no known vulnerabilities in the resolved environment
- upstream tests: qualification could not initially run correctly because the repository's `pytest.ini` requires `pytest-cov` while the bounded harness had not installed that upstream test plugin; this was a harness defect and is **not** counted against the donor
- local generated behavior smoke: FAIL on current Pillow because the donor calls removed API `PIL.Image.ANTIALIAS`

Exact source therefore does not qualify cleanly on the current Python/Pillow stack.

### Minimal remediation trial

A second bounded trial corrected the harness by installing `pytest-cov` and changed only the single `Image.ANTIALIAS` occurrence inside `videohash/collagemaker.py` to `Image.Resampling.LANCZOS`.

Workflow run: `33973551643`  
Artifact: `vrp-videohash-remediation-r19`  
Artifact ID: `9971640891`  
Artifact digest: `sha256:af1a2f83c01c7f90e57f63c4c3d48095338b120d51428cce8eaec9ad1140e1a8`

Retained one-line trial patch SHA-256 in the artifact: `5409e9d35ca156425a76bab6c112f71a8e195677e9b9962251abb363f48cffaf`.

The trial did **not** clear the donor:

- complete upstream suite: 3 passed / 2 failed
- one failure is external-test brittleness: a live YouTube download received HTTP 429 / bot-authentication rejection
- the other is a deeper compatibility problem: dependency `imagedominantcolor 1.0.1` itself also calls removed `PIL.Image.ANTIALIAS`
- the local behavior smoke consequently remained blocked by the transitive dependency compatibility break
- dependency audit remained clean

This means a genuine current-environment adoption would require more than a one-line donor fix: either a dependency repair/replacement/compatibility shim or an intentionally older Pillow stack, plus removal/isolation of live-network assumptions from deterministic tests.

### Disposition

Do **not** spend VRP engineering effort rescuing this donor as a core dependency when the maintained ThreatExchange stack already passed stronger behavioral qualification and covers both whole-video and clip/subsequence use cases.

Keep `videohash` only as a legacy/reference donor if its simple 64-bit Python approach is useful for later study. Any future adoption must be freshly qualified and must not silently pin an old Pillow merely to restore `ANTIALIAS` without a security/maintenance assessment.

## 5. VRP architecture handoff

For the specialist VRP lane:

1. **Primary whole-video near-duplicate index:** ThreatExchange TMK+PDQF.
2. **Partial clip/subsequence detection:** ThreatExchange vPDQ.
3. **Do not implement a new perceptual-video hashing algorithm from scratch.**
4. **Do not make `akamhy/videohash` a core dependency** unless a later need justifies repairing and requalifying it.
5. Keep existing VRP donors for acquisition/transcription/scene/visual-search work separate; this receipt closes only the remaining near-duplicate-video cell.
6. Before production-scale use, calibrate thresholds, indexing strategy, false-positive/false-negative tolerances and performance using representative VRP material.

## 6. Reconnaissance disposition

**VRP near-duplicate video similarity PARTIAL cell: CLOSED at reconnaissance level.**

The remaining initial reconnaissance cursor is now:

1. build/backfill the **permanent donor vault** with exact-source/provenance snapshots for the important qualified donors already selected;
2. perform the **adversarial whole-estate omission sweep**;
3. if no material capability gap remains, freeze **Initial Comprehensive GitHub/FOSS Reconnaissance v1** and switch this chat to continuous GitHub-first radar mode.
