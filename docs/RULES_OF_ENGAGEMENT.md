# Rules of Engagement

## Core rule

All activity must remain inside an explicitly authorized, controlled environment.

## Required controls

- Confirm the canonical target and gate state before each session.
- Prefer loopback/localhost binding for deliberately vulnerable services.
- Use synthetic accounts, credentials, and data.
- Record the objective before execution and the result afterwards.
- Preserve enough evidence to reproduce a finding without collecting unrelated data.
- Apply the least-impactful technique that can answer the test question.
- Stop immediately if a test reaches an unexpected external host or service.
- Separate observed facts from hypotheses and unverified interpretations.
- Retest after remediation and preserve both pre-fix and post-fix evidence.

## Prohibited by this lab

- Testing third-party live systems without explicit authorization.
- Internet-wide or uncontrolled scanning.
- Destructive denial-of-service testing.
- Persistence outside a disposable authorized lab target.
- Credential theft or collection of real credentials.
- Exfiltration of real data.
- Malware propagation or self-spreading payloads.
- Concealment intended to defeat an owner's monitoring or oversight.

## Stop conditions

Stop if authorization becomes unclear, the target escapes the expected boundary, unexpected real data appears, or the effect of the next action cannot be bounded confidently.
