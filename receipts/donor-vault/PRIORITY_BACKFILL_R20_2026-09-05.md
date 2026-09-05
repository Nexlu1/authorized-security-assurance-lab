# Priority exact-source donor-vault backfill R20 — 2026-09-05

**Lane:** GitHub/FOSS reconnaissance → provenance / supply-chain control  
**Status:** **PASS for the four historical priority source-byte packages**

## Mission boundary

This is post-freeze preservation work. `Initial Comprehensive GitHub/FOSS Reconnaissance v1` was already frozen on 2026-09-05; R20 does not restart or replace that discovery baseline.

R20 closes the previously controlled source-byte acquisition/package backlog for the four historical priority donors. It does **not** claim that the user's separate local `E:` working-vault copy and independent restic/cold-storage copy have been physically written from this chat; those remain storage-redundancy/operator tasks outside this chat's machine access.

## Final controlled run

- Temporary operational PR: **#41** — do not merge the harness.
- Final temporary workflow head: `53aa79493cd8349c1cfadb18deeee98d3dab0352`
- Final donor-vault run: `33977293449`
- Result: **4 / 4 donor jobs PASS**
- Repository controls on the same head:
  - Governance integrity: PASS
  - Workflow assurance: PASS
  - Python SAST: PASS
  - Repository assurance: PASS

The final harness also uses `persist-credentials: false`; an earlier `zizmor` finding correctly prevented a checkout token from remaining in repository Git configuration before artifact upload.

## Preservation controls actually exercised

Each final package passed all of the following in GitHub Actions:

1. acquire and verify the exact pinned commit;
2. record the exact original Git tree and original commit object;
3. export every tracked file from the Git index using `git checkout-index` rather than `git archive`, avoiding `.gitattributes export-ignore` loss;
4. reconstruct a new Git tree from the source tar and require exact equality with the original pinned Git tree;
5. create and verify a reconstructable Git bundle;
6. preserve root licence/notice material and hashes;
7. clone/restore from the bundle, compare restored Git tree and `ls-tree` manifest with the original, and run `git fsck --full`;
8. generate portable relative-path SHA-256 manifests and self-verify them before upload.

The stricter controls caught and corrected three real harness defects before canonisation: bundle restore without an explicit preserved ref, non-portable checksum paths, and source archives affected by `export-ignore` / tracked-but-gitignored files. None was waived.

## Independent downloaded-artifact verification

After the final Actions run, all four artifact ZIPs were downloaded into a separate working environment and independently reverified without relying on the workflow result.

Independent local checks included:

- outer artifact ZIP SHA-256 equals the GitHub artifact digest;
- every internal portable SHA-256 manifest verifies;
- the preserved raw commit object hashes back to the recorded pinned commit;
- `git bundle verify` passes;
- cloning the preserved bundle ref succeeds;
- restored Git tree equals the original tree;
- `git fsck --full` passes;
- restored `ls-tree` manifest equals the original manifest byte-for-byte;
- exact-history packages restore the original pinned commit;
- extracting the tracked source tar, force-indexing every archived tracked file, and running `git write-tree` reproduces the exact original Git tree.

Result: **4 / 4 PASS**.  
Independent result-manifest SHA-256: `024664a8b8a0cafc6d9c4fb4e3e824e03583f3a2d47095a4d5dcf93df69b6ee8`.

## Final priority entries

### 1. `ggml-org/llama.cpp`

- Pinned commit: `0ef4d560e12c1a46470265c1abd31dd47c777d23`
- Original Git tree: `abeb6d5e222529f849ce13a3e8e33345ff5c3a55`
- Licence: MIT
- Existing qualification state: `USE_INTEGRATED`
- Target lane: Rig Worker
- Source tar SHA-256: `79ada0ebb29b9194bc6fc8a50bba39dd5cb8f8e98d78724ed7823a0a5aa854f8`
- Git bundle SHA-256: `b39d3db00b1037d558d13fd6e1c5e08b63d1930f1b740bbde48b730f970ec2af`
- Final artifact ID: `9972690049`
- Final artifact ZIP SHA-256: `1cfdbe042acedc32b49e84ee3eb4a1d3ac861612e11c76ffecf6a6b6f2689582`
- Bundle mode: `source_snapshot`
- Snapshot commit: `facc4f563a1ec99266ee1758cab88145d619131f`

Because GitHub reported this repository at roughly 438 MB, R20 deliberately did not mirror its entire historical object graph. The bundle is a self-contained snapshot commit whose Git tree is exactly the pinned source tree; the original pinned commit object is also preserved separately. This is source-complete for the controlled revision, not history-complete.

### 2. `alekk89/llama-cpp-windows-manager`

- Pinned commit: `a48a8b9dca99736792096de66446fdf7d28bf585`
- Original Git tree: `1af146aaad927ff10e39ac3219fe7454fee87711`
- Licence: MIT
- Existing qualification state: `HOLD_SECURITY`
- Target lane: Rig Worker
- Source tar SHA-256: `f09466c5b5f2e5edafbc95722c4bd9ecfcac2ae9ed018ecba4c34ffce58183f6`
- Git bundle SHA-256: `61f0eadabed7ba2a3d433ad3c39be62d9ddb04fa7883ab6ff1c018f039790a88`
- Final artifact ID: `9972686418`
- Final artifact ZIP SHA-256: `ee8fe00ea6e465fd68d6125c957e9b5558a7c935a593d04508ed7e2c4ed41f9f`
- Bundle mode: `exact_history_to_commit`

The bundle restores the exact original pinned commit and its reachable ancestry to that commit. Preservation does not change the existing security HOLD.

### 3. `winsw/winsw`

- Pinned commit: `1d0ee4a91bad596d5e7e9c360f2b39ef54674674`
- Original Git tree: `66bdc63b630f98eb4bbf81e11bb29391bc42bec5`
- Licence: MIT
- Existing qualification state: `TEST_PASS_SECURITY_HOLD`
- Target lanes: Remote Rig Access / Windows supervision
- Source tar SHA-256: `c3db838bf19138527ef965be9bea48c2e372d5753d21baffebd6d6afb4c51192`
- Git bundle SHA-256: `c3ed55676df8d9ca9f4aa18ab57954b3a4047a40468830203d5d7525508c9938`
- Final artifact ID: `9972686398`
- Final artifact ZIP SHA-256: `f9b8a2a93f4b27dab7234bfbf9d792482c8d18f85e7b8547e532ded4153463d5`
- Bundle mode: `exact_history_to_commit`

The bundle restores the exact original pinned commit and its reachable ancestry to that commit. Preservation does not clear the existing vulnerable-dependency security HOLD.

### 4. `Sh3n0bi/NetForensicAI`

- Pinned commit: `70cd1b98a4433ab6fe2db6280799d33673acea9e`
- Original Git tree: `6a72dd0c0798836647f77c828321425dc9921d26`
- Licence: MIT
- Existing qualification state: `ADAPT_HOLD`
- Target lanes: ECO / Dossier / MCR
- Source tar SHA-256: `cc55f946d0a3da231bc404c421e33fabd6ca6f24bd549f78a34e7d351da66af1`
- Git bundle SHA-256: `37ba1396a55c8f7d12a0736c4638d1c222bce27b0698653063f6749c57a485aa`
- Final artifact ID: `9972685664`
- Final artifact ZIP SHA-256: `a8e185d5e024205c77b59cdb672777ca9ed3bbd9659121b9244811f4b8026f70`
- Bundle mode: `exact_history_to_commit`

The bundle restores the exact original pinned commit and its reachable ancestry to that commit. Preservation does not change the existing ADAPT/HOLD decision.

## Disposition

**Historical priority donor source-byte backfill: CLOSED for the four controlled priority entries.**

This closes the source acquisition/restorable-packaging backlog that the v1 freeze carried forward. It does not alter any donor's USE/HOLD/ADAPT status and does not replace the planned separate physical redundancy model (local fast-storage vault plus independent cold/restic copy).

After this receipt is merged and the temporary PR #41 is closed unmerged, this chat returns to its permanent mission: **continuous GitHub-first radar, donor control, and affected-project handoff only. Do not restart the already-frozen whole-estate reconnaissance without a material estate change.**
