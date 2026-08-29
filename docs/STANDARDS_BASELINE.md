# Standards Baseline

Rechecked: **2026-08-29**.

This is a working benchmark, not a claim of certification, professional status, OpenAI endorsement, Daybreak eligibility, NCSC assurance, or CHECK status.

## OpenAI Daybreak / Trusted Access for Cyber

Current first-party OpenAI guidance states that Daybreak Access is the Trusted Access for Cyber program and distinguishes Daybreak Blue from Daybreak Red.

- Daybreak Blue is the recommended starting point for most security teams and supports authorized defensive workflows.
- Daybreak Red uses specialized capabilities for advanced, authorized workflows such as penetration testing, red teaming, exploit validation/development, and controlled vulnerability research.
- Daybreak Red requires separate approval and is subject to stronger verification, monitoring, access controls, and human oversight.
- Existing Trusted Access or other cyber access does not automatically grant Daybreak Red.
- OpenAI states that review factors can include identity/trust verification, risk considerations, intended use, and the applicant's ability to strengthen the broader cybersecurity ecosystem.

Sources rechecked 2026-08-29:

- https://help.openai.com/en/articles/20001258-openai-daybreak-trusted-access-for-cyber-overview
- https://openai.com/daybreak/
- https://openai.com/index/expanding-daybreak-as-the-cyber-defense-window-narrows/

Controls adopted here: explicit scope, owner authorization, stronger gates for higher-impact work, fail-closed uncertainty handling, no inference of authorization from technical reachability, and exact outcome-state wording.

### Evidence-building non-claim

OpenAI's current guidance does **not** state that a pypdf contribution, WebGoat exercise, GitHub repository, project count, or other particular portfolio artifact is a formal Daybreak Red requirement. Those activities may provide relevant evidence of disciplined technical work, but they must not be represented as an official scoring system, eligibility checklist, approval signal, or guaranteed route to access.

## NIST SP 800-115

NIST SP 800-115, **Technical Guide to Information Security Testing and Assessment**, remains a final NIST publication. It dates from **September 2008**; it is retained as a planning/testing reference and must not be described as a new 2026 standard.

Source rechecked 2026-08-29:

- https://csrc.nist.gov/pubs/sp/800/115/final

Controls adopted here: plan before execution, define boundaries, preserve evidence, analyze findings, remediate, and retest.

## UK NCSC penetration-testing guidance

Current NCSC guidance continues to treat penetration testing as an assurance activity that must be properly commissioned, scoped and used as part of a wider vulnerability-management process rather than as a magic bullet.

Source rechecked 2026-08-29:

- https://www.ncsc.gov.uk/guidance/penetration-testing

## OWASP ASVS

OWASP ASVS **5.0.0** remains the latest stable version checked on 2026-08-29. OWASP describes the master branch as bleeding-edge and identifies 5.0.0, dated May 2025, as the latest stable release.

Source rechecked 2026-08-29:

- https://github.com/OWASP/ASVS

## OWASP Web Security Testing Guide

OWASP WSTG **v4.2** remains the current stable version checked on 2026-08-29; OWASP states that version 5.0 remains under development.

Sources rechecked 2026-08-29:

- https://owasp.org/www-project-web-security-testing-guide/
- https://owasp.org/www-project-web-security-testing-guide/v42/

## OWASP WebGoat

WebGoat is a deliberately insecure training application. GitHub's official `WebGoat/WebGoat` `releases/latest` endpoint still resolves to **v2025.3** at the 2026-08-29 recheck.

WebGoat remains an optional, controlled local training target for this project. Its presence in the plan does not itself establish cybersecurity competence, independent validation, Daybreak eligibility, or authority to perform G2 technical testing.

Sources:

- https://github.com/WebGoat/WebGoat/releases/tag/v2025.3
- https://github.com/WebGoat/WebGoat

## Review rule

Recheck authoritative sources before a material scope change, before opening a technical-testing gate, before an external readiness/eligibility claim, and whenever a relevant provider or standard changes materially.
