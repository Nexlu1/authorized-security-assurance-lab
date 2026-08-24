# Standards Baseline

Rechecked: **2026-08-23**.

This is a working benchmark, not a claim of certification, professional status, OpenAI endorsement, Daybreak eligibility, NCSC assurance, or CHECK status.

## OpenAI Daybreak / Trusted Access for Cyber

Current OpenAI guidance states that Daybreak Red is for advanced, authorized cybersecurity workflows and requires separate approval with stronger verification, monitoring, access controls, and human oversight. Trusted Access does not authorize work on systems outside those owned, operated, or explicitly authorized for testing.

Sources:

- https://help.openai.com/en/articles/20001258-openai-daybreak-trusted-access-for-cyber-overview
- https://openai.com/daybreak/

Controls adopted here: explicit scope, human approval, stronger gates for higher-impact work, fail-closed uncertainty handling, and no inference of authorization from technical reachability.

## NIST SP 800-115

NIST SP 800-115 remains a useful reference for planning and conducting technical security tests, analyzing findings, and developing mitigation strategies.

Source: https://csrc.nist.gov/pubs/sp/800/115/final

Controls adopted here: plan before execution, define boundaries, preserve evidence, analyze findings, remediate, and retest.

## UK NCSC penetration-testing guidance

NCSC guidance treats penetration testing as an authorized assurance activity with scoping, testing, reporting, and follow-up.

Source: https://www.ncsc.gov.uk/guidance/penetration-testing

## OWASP ASVS

OWASP ASVS **5.0.0** is the latest stable version checked on 2026-08-23. It provides a modern application-security verification baseline.

Source: https://owasp.org/www-project-application-security-verification-standard/

## OWASP Web Security Testing Guide

OWASP WSTG **v4.2** remains the stable testing-guide baseline used by this lab unless a later stable release is explicitly adopted.

Source: https://owasp.org/www-project-web-security-testing-guide/v42/

## OWASP WebGoat

WebGoat is a deliberately insecure training application. The current latest formal release checked is **v2025.3**. Official guidance uses loopback-only Docker mappings and OWASP advises keeping the deliberately vulnerable target local/disconnected where practical.

Sources:

- https://github.com/WebGoat/WebGoat/releases
- https://vwad.owasp.org/app/webgoat/
- https://devguide.owasp.org/en/07-training-education/01-vulnerable-apps/02-webgoat/

## Review rule

Recheck the authoritative sources before a material scope change, before opening a technical-testing gate, before an external readiness claim, or whenever a relevant provider/standard changes materially.
