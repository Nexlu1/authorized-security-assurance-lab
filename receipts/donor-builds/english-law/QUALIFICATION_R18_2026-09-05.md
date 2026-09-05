# English Law source-verification donor receipt R18 — 2026-09-05

**Lane:** GitHub/FOSS reconnaissance → English Law case-law/source verification  
**Purpose:** identify and independently qualify reusable free/open-source components before any bespoke implementation.

## Overall decision

The reconnaissance cell is sufficiently resolved for handoff.

| Capability | Donor | Exact revision | Licence | Decision |
|---|---|---|---|---|
| UK courts / neutral-citation recognition and canonical Find Case Law routing | `nationalarchives/ds-caselaw-utils` | `b37f1bb1bba3e1cfbb0f4d9bd588b7a828d8b850` | MIT | **PASS** |
| UK legislation.gov.uk search/retrieval/effects MCP | `legislation/legislation-mcp-ts` | `8261b2aada185aa846d34288790d1321ac79c8dc` | OGL-UK-3.0 | **HOLD as published; PASS with the qualified lock-only remediation below** |
| Judgment citation/legislation enrichment logic | `nationalarchives/ds-caselaw-data-enrichment-service` | `fe2d1d83572fbe2a21866996f730e40bed139a41` | MIT | **SELECTIVE DONOR** — reuse/adapt rules and concepts; do not adopt the whole AWS/serverless service by default |
| Find Case Law public API specification | `nationalarchives/ds-find-caselaw-docs` | official National Archives repository | published documentation | **AUTHORITATIVE INTERFACE REFERENCE** |
| CLML schema repository | `legislation/clml-schema` | official legislation repository | explicit repository licence not established during this pass | **LICENCE HOLD** |
| Third-party public-API downloader | `pw9876/caselaw-downloader` | repository inspected 2026-09-05 | no software licence established | **REJECT FOR CODE REUSE** |

## 1. Case-law utility donor — PASS

### Donor

- Repository: `nationalarchives/ds-caselaw-utils`
- Exact SHA: `b37f1bb1bba3e1cfbb0f4d9bd588b7a828d8b850`
- Qualified package version: `4.10.0`
- Licence: MIT
- Runtime used: Python 3.12

This is The National Archives' own reusable utility package for Find Case Law. It includes the court catalogue, neutral-citation matching/validation and conversion of supported neutral citations into canonical Find Case Law routes.

### Independent evidence

Qualification run: `33972514930`  
Artifact: `english-law-caselaw-utils-r18`  
Artifact ID: `9971341334`  
Artifact digest: `sha256:5556b022c02512a7c8ad9e9367a378ca1bff54adb4618d3209251358e49a5946`

Results:

- exact donor SHA verification: PASS
- package install: PASS
- `pip check`: PASS — no broken requirements
- complete upstream pytest suite: **80 passed / 0 failed**
- independent neutral-citation smoke: PASS
- invalid-court smoke: PASS

### Adoption rule

Use this donor rather than writing a fresh UK-court/neutral-citation regex catalogue. Pin the exact adopted revision and preserve attribution/licence material.

## 2. legislation.gov.uk MCP — published revision HOLD

### Donor

- Repository: `legislation/legislation-mcp-ts`
- Exact SHA: `8261b2aada185aa846d34288790d1321ac79c8dc`
- Version: `0.1.0`
- Author: The National Archives
- Licence: OGL-UK-3.0
- Required Node: `>=22.16.0`
- Qualification runtime: Node `22.16.0`

The public/core toolset is unusually well aligned with the English Law Master source-verification problem. It provides legislation search, full document retrieval, fragment retrieval, metadata, table of contents, legislative-effects search and resource retrieval, including point-in-time/version and outstanding/unapplied-effects capabilities.

### Exact published-source evidence

Qualification run: `33972514930`  
Artifact: `english-law-legislation-mcp-r18`  
Artifact ID: `9971343789`  
Artifact digest: `sha256:e11d9b77e0bc163c52f61bfc6b6a283a0199a52f0a3b49cc8cebfdf43d385952`

Results before security gate:

- exact donor SHA verification: PASS
- exact Node setup: PASS
- locked `npm ci`: PASS
- TypeScript check: PASS
- build: PASS
- complete upstream tests: **434 passed / 0 failed**
- production dependency audit: **FAIL**

Production-only npm audit at that exact published lockfile found:

- critical: 0
- high: 4
- moderate: 3
- low: 1
- total: 8

Affected production packages included direct dependencies `hono`, `@xmldom/xmldom` and `@hono/node-server`, plus transitive `fast-uri`, `ip-address`, `body-parser`, `express-rate-limit` and `qs`. npm reported fixes available.

Therefore the exact repository revision **as published/locked is HOLD** and must not be represented as a clean PASS.

## 3. Qualified lock-only remediation — PASS

A controlled remediation was then tested against the same exact source SHA. The remediation used npm's non-force package-lock-only audit repair. It was required to alter only `package-lock.json`; any application/source change would have failed the qualification.

Qualification run: `33972672091`  
Artifact: `english-law-legislation-mcp-remediation-r18`  
Artifact ID: `9971393907`  
Artifact digest: `sha256:4152462d82eee62183c2edc96e8fb0d4e3c0866ef3c0515be1fb6051529cb21b`

The exact tested remediation is preserved durably in this repository as:

- `receipts/donor-builds/english-law/legislation-mcp/package-lock-remediation-8261b2a.patch`
- patch SHA-256: `afa2d7122dc296a447c20b8f6ea546ed2a4e5b39e900744845e3f1b486527e29`
- patch base: exact upstream source SHA `8261b2aada185aa846d34288790d1321ac79c8dc`

This patch contains the complete tested lockfile delta, including resolved package URLs and integrity fields; it is not merely a version summary. If the patch does not apply cleanly to that exact base or its resulting lockfile hash differs from the qualified hash below, the remediation must be requalified rather than reconstructed heuristically.

Lockfile hashes:

- original exact upstream `package-lock.json`: `e5c06d6416c0cda3f4de9a20134581f179941ba2acf075b893df66b6859c57a2`
- qualified remediated `package-lock.json`: `46c8af715985a901855f92a9874eb76982aa4a5cb8d91c4738cb5b8553710931`

Security-relevant resolved versions after the lock-only refresh:

- `@hono/node-server`: `1.19.12` → `1.19.17`
- `@xmldom/xmldom`: `0.9.9` → `0.9.12`
- `hono`: `4.12.11` → `4.13.7`
- `fast-uri`: `3.1.0` → `3.1.7`
- `ip-address`: `10.1.0` → `10.7.0`
- `body-parser`: `2.2.2` → `2.3.0`
- `express-rate-limit`: `8.3.0` → `8.7.0`
- `qs`: `6.15.0` → `6.16.0`

Post-remediation results:

- changed-file assertion: **only `package-lock.json` changed**
- clean reinstall from remediated lockfile: PASS
- production npm audit: **0 vulnerabilities total**
- TypeScript check: PASS
- build: PASS
- complete upstream tests: **434 passed / 0 failed**
- final source-integrity assertion: PASS — no donor source/application file changed

### Adoption rule

The exact upstream source is acceptable only when paired with either:

1. an upstream revision whose committed dependency lock independently requalifies cleanly; or
2. the exact preserved remediation patch above applied to exact source SHA `8261b2aada185aa846d34288790d1321ac79c8dc`, with the resulting `package-lock.json` verified as SHA-256 `46c8af715985a901855f92a9874eb76982aa4a5cb8d91c4738cb5b8553710931`; or
3. a later independently qualified equivalent.

Do not rerun `npm audit fix` and assume it reproduces the qualified graph. Do not silently use the vulnerable published lockfile.

## 4. Judgment enrichment donor — selective reuse

- Repository: `nationalarchives/ds-caselaw-data-enrichment-service`
- Inspected/pinned SHA: `fe2d1d83572fbe2a21866996f730e40bed139a41`
- Licence at that exact SHA: MIT, Crown Copyright (The National Archives)

This official Judgment Enrichment Pipeline already contains logic/concepts for identifying and enriching:

- UK case citations;
- primary legislation references;
- abbreviations;
- indirect references such as “the Act”;
- provision references such as “section 6”;
- LegalDocML citation metadata.

It is useful evidence that we should not invent the English-law citation/enrichment rules from zero. However, the complete repository is an AWS/serverless service with deployment/environment assumptions, so it is a **selective donor/reference**, not a default whole-service dependency for an offline/local English Law Master. Any later reuse must remain pinned to an inspected revision and independently requalify any materially different revision.

## 5. Public Find Case Law API and data-licence boundary

The authoritative public Find Case Law API specification is maintained by The National Archives in `nationalarchives/ds-find-caselaw-docs`.

Important boundary: software-code licensing and judgment-data licensing are separate. The National Archives' Find Case Law documentation states that judgment records are governed by the Open Justice Licence and that computational analysis of the records requires applying for permission.

Therefore:

- using the official public API for permitted lookup/source-verification workflows is an interface decision;
- an MIT/OGL software donor does **not** give unrestricted rights to bulk computationally analyse the judgment corpus;
- do not build a bulk case-law mining/training pipeline on the assumption that GitHub software licensing overrides the judgment-data terms;
- obtain/record the required permission before any workflow that falls within the restricted computational-analysis use.

## 6. Rejected / held candidates

### `pw9876/caselaw-downloader` — REJECT FOR CODE REUSE

The repository demonstrates that the public Find Case Law Atom/API workflow is technically straightforward, but no software licence was established in the repository during this pass. References to the judgment-data licence do not license the downloader's source code. Under the GitHub/FOSS-first rule, unlicensed code is not a reusable donor.

### `legislation/clml-schema` — LICENCE HOLD

The official CLML schema is technically relevant to legislation XML validation, but this pass did not establish an explicit repository software/schema licence. Public readability on GitHub is not treated as permission to reuse. Revisit only when the licence is independently established.

## 7. Recommended English Law source stack

For the specialist English Law lane, the practical architecture is now:

1. **Neutral citations / court identity:** adopt the qualified `nationalarchives/ds-caselaw-utils` donor.
2. **Judgment source lookup:** use the authoritative Find Case Law public API specification, respecting Open Justice data-use restrictions.
3. **Citation/enrichment logic:** selectively reuse/adapt the pinned MIT-licensed National Archives enrichment patterns rather than writing a fresh recogniser.
4. **Legislation source/version/effects retrieval:** prefer the official `legislation/legislation-mcp-ts` core public tools, but only with a clean independently qualified dependency lock; the published `8261b2a...` lock is HOLD, while the exact source plus the durably preserved qualified remediation patch above passed all gates.
5. **CLML validation:** remain on licence HOLD until explicit reuse terms are verified.
6. Preserve exact source SHA, licence, dependency-lock hash and qualification evidence for every adopted donor.

## 8. Reconnaissance disposition

**English Law case-law/source-verification PARTIAL cell: CLOSED at reconnaissance level.**

This does not mean the English Law Master itself is complete. It means the reusable GitHub/FOSS source-verification architecture has been identified with explicit PASS/HOLD/REJECT boundaries and independent evidence, so the specialist lane can integrate instead of reinventing these components.

Next GitHub/FOSS reconnaissance cursor after this receipt is merged: **VRP — finish validating near-duplicate video detection donors.**
