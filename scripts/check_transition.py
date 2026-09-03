from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime
import hashlib
from http.client import HTTPException, HTTPSConnection
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from check_governance import MAX_JSON_BYTES, validate, valid_rfc3339

ROOT = Path(__file__).resolve().parents[1]
AUTHORITY_PATH = "governance/AUTHORITY_STATE.json"
EVIDENCE_PATH = "evidence/EVIDENCE_REGISTER.json"
PROTECTED_TCB = {
    ".github/workflows/governance-integrity.yml",
    ".github/workflows/trusted-authority-guardian.yml",
    "scripts/check_governance.py",
    "scripts/check_transition.py",
}
GATES = ["G0", "G1", "G2", "G3", "G4", "G5"]
ISSUE_COMMENT_RE = re.compile(
    r"^https://github\.com/([^/]+)/([^/]+)/(issues|pull)/(\d+)#issuecomment-(\d+)$"
)
PR_URL_RE = re.compile(r"^https://github\.com/([^/]+)/([^/]+)/pull/(\d+)$")
GITHUB_API_PATH_RE = re.compile(
    r"^/repos/[^/]+/[^/]+/(?:issues/comments/\d+|pulls/\d+)$"
)
ZERO_SHA_RE = re.compile(r"^0{40}$")

OWNER_SOURCE = "GitHub repository-owner issue comment"
OWNER_INTEGRITY = "GitHub API: same-repository OWNER association; created_at equals updated_at; semantic digest matched"
CONTROL_SOURCE = "GitHub protected pull request"
CONTROL_INTEGRITY = "GitHub API: current pull request metadata"


def _reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise ValueError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def loads_strict(text: str) -> Any:
    return json.loads(text, object_pairs_hook=_reject_duplicates)


def normalize_ws(value: str) -> str:
    return " ".join(value.split())


def git_ref_exists(ref: str) -> bool:
    if not ref or ZERO_SHA_RE.fullmatch(ref):
        return False
    result = subprocess.run(
        ["git", "cat-file", "-e", f"{ref}^{{commit}}"], cwd=ROOT,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
    )
    return result.returncode == 0


def git_json(ref: str, path: str) -> tuple[Any | None, list[str]]:
    if not git_ref_exists(ref):
        return None, [f"git ref unavailable: {ref}"]
    size_result = subprocess.run(
        ["git", "cat-file", "-s", f"{ref}:{path}"], cwd=ROOT, capture_output=True,
        text=True, encoding="utf-8", check=False,
    )
    if size_result.returncode != 0:
        return None, [f"required {path} is missing at {ref}"]
    try:
        size = int(size_result.stdout.strip())
    except ValueError:
        return None, [f"cannot determine size of {path} at {ref}"]
    if size > MAX_JSON_BYTES:
        return None, [f"{path} at {ref} exceeds {MAX_JSON_BYTES} byte safety limit"]
    result = subprocess.run(
        ["git", "show", f"{ref}:{path}"], cwd=ROOT, capture_output=True,
        text=True, encoding="utf-8", check=False,
    )
    if result.returncode != 0:
        return None, [f"required {path} is missing at {ref}"]
    try:
        return loads_strict(result.stdout), []
    except (json.JSONDecodeError, ValueError, RecursionError) as exc:
        return None, [f"{path} at {ref} is invalid JSON: {exc}"]


def changed_files(previous_ref: str, current_ref: str) -> tuple[set[str], list[str]]:
    result = subprocess.run(
        ["git", "diff", "--name-only", previous_ref, current_ref], cwd=ROOT,
        capture_output=True, text=True, encoding="utf-8", check=False,
    )
    if result.returncode != 0:
        return set(), ["cannot enumerate candidate changed files"]
    return {line.strip() for line in result.stdout.splitlines() if line.strip()}, []


def api_get(url: str, token: str | None, purpose: str) -> tuple[Any | None, list[str]]:
    if not token:
        return None, [f"GITHUB_TOKEN is required to authenticate {purpose}"]
    try:
        parsed = urlsplit(url)
    except ValueError as exc:
        return None, [f"GitHub {purpose} API URL is invalid: {exc}"]
    if (
        parsed.scheme != "https"
        or parsed.netloc != "api.github.com"
        or parsed.query
        or parsed.fragment
        or not GITHUB_API_PATH_RE.fullmatch(parsed.path)
    ):
        return None, [
            f"GitHub {purpose} API URL is outside the approved HTTPS api.github.com endpoint set"
        ]
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "User-Agent": "authorized-security-assurance-governance",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    connection = HTTPSConnection("api.github.com", timeout=15)
    try:
        connection.request("GET", parsed.path, headers=headers)
        response = connection.getresponse()
        body = response.read()
        if response.status < 200 or response.status >= 300:
            return None, [f"GitHub {purpose} API returned HTTP {response.status}"]
        return loads_strict(body.decode("utf-8")), []
    except (HTTPException, TimeoutError, OSError, UnicodeError, json.JSONDecodeError, ValueError, RecursionError) as exc:
        return None, [f"GitHub {purpose} API verification failed: {exc}"]
    finally:
        connection.close()


def comment_api_url(repository: str, artifact_url: str) -> tuple[str | None, list[str]]:
    match = ISSUE_COMMENT_RE.fullmatch(artifact_url)
    if not match:
        return None, ["owner approval artifact URL is not a GitHub issue/PR comment URL"]
    if f"{match.group(1)}/{match.group(2)}" != repository:
        return None, ["owner approval artifact belongs to a different repository"]
    comment_id = match.group(5)
    return f"https://api.github.com/repos/{repository}/issues/comments/{comment_id}", []


def approval_semantics(current: dict[str, Any], opened: list[str]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "approve_gates": {
            gate: {"authorized_scope": current["gates"][gate]["authorized_scope"]}
            for gate in opened
        },
        "resulting_gate_statuses": {
            gate: current["gates"][gate]["status"] for gate in GATES
        },
        "activation": current["activation"],
        "target": current["target"],
        "prohibitions": current["prohibitions"],
    }


def authorization_digest(current: dict[str, Any], opened: list[str]) -> str:
    encoded = json.dumps(
        approval_semantics(current, opened), sort_keys=True, separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def canonical_owner_approval_text(current: dict[str, Any], opened: list[str]) -> str:
    digest = authorization_digest(current, opened)
    lines = [
        "Authority approval",
        f"Authorization digest: {digest}",
        f"Approve gates: {','.join(opened)}",
    ]
    for gate in opened:
        lines.append(f"{gate} scope: {current['gates'][gate]['authorized_scope']}")
    lines.append("No other gate is approved by this comment.")
    return "\n".join(lines)


def verify_owner_comment_payload(
    payload: Any, *, repository: str, expected_url: str,
    expected_timestamp: str, expected_text: str,
) -> list[str]:
    errors: list[str] = []
    if not isinstance(payload, dict):
        return ["owner approval payload must be an object"]
    owner, _repo = repository.split("/", 1)
    match = ISSUE_COMMENT_RE.fullmatch(expected_url)
    if not match or f"{match.group(1)}/{match.group(2)}" != repository:
        errors.append("approval artifact URL is not a comment in the current repository")
    if payload.get("html_url") != expected_url:
        errors.append("GitHub approval html_url does not match candidate artifact URL")
    if f"/repos/{repository}/issues/" not in str(payload.get("issue_url", "")):
        errors.append("GitHub approval artifact does not belong to the current repository")
    user = payload.get("user")
    if not isinstance(user, dict) or user.get("login") != owner:
        errors.append("approval artifact is not authored by the repository owner")
    if payload.get("author_association") != "OWNER":
        errors.append("approval artifact does not have OWNER author association")
    created = payload.get("created_at")
    updated = payload.get("updated_at")
    if not valid_rfc3339(created) or not valid_rfc3339(updated):
        errors.append("approval artifact timestamps must be timezone-aware RFC3339")
    elif created != updated:
        errors.append("approval comment was edited; use a new unedited owner comment")
    if created != expected_timestamp:
        errors.append("approval artifact created_at does not match candidate artifact timestamp")
    if str(payload.get("body", "")) != expected_text:
        errors.append("approval artifact body does not exactly match the canonical semantic-digest approval text")
    return errors


def verify_pr_payload(
    payload: Any, *, repository: str, pr_number: int, expected_url: str,
    expected_timestamp: str,
) -> list[str]:
    errors: list[str] = []
    owner, repo = repository.split("/", 1)
    match = PR_URL_RE.fullmatch(expected_url)
    if not match or (match.group(1), match.group(2), int(match.group(3))) != (owner, repo, pr_number):
        errors.append("control-transition artifact URL is not the current pull request")
    if not isinstance(payload, dict):
        return errors + ["pull request payload must be an object"]
    if payload.get("html_url") != expected_url:
        errors.append("GitHub pull request html_url does not match candidate artifact URL")
    if payload.get("number") != pr_number:
        errors.append("GitHub pull request number mismatch")
    created = payload.get("created_at")
    if not valid_rfc3339(created):
        errors.append("pull request created_at is not timezone-aware RFC3339")
    if created != expected_timestamp:
        errors.append("pull request created_at does not match candidate transition timestamp")
    return errors


def semantic_changes(previous: dict[str, Any], current: dict[str, Any]) -> list[str]:
    changes: list[str] = []
    for gate in GATES:
        if previous["gates"][gate] != current["gates"][gate]:
            changes.append(f"gates.{gate}")
    if previous["activation"]["phase0_hold"] != current["activation"]["phase0_hold"]:
        changes.append("activation.phase0_hold")
    if previous["activation"]["g2_technical_security_testing_authorized"] != current["activation"]["g2_technical_security_testing_authorized"]:
        changes.append("activation.g2_technical_security_testing_authorized")
    # Everything else in canonical authority is immutable after bootstrap.
    p = deepcopy(previous)
    c = deepcopy(current)
    for doc in (p, c):
        doc["last_transition"] = None
        for gate in GATES:
            doc["gates"][gate] = {"status": "<semantic>"}
        doc["activation"]["phase0_hold"] = "<semantic>"
        doc["activation"]["g2_technical_security_testing_authorized"] = "<semantic>"
    if p != c:
        changes.append("UNPERMITTED_CANONICAL_STRUCTURE_OR_METADATA")
    return changes


def new_evidence_entries(previous: Any, current: Any) -> tuple[list[dict[str, Any]], list[str]]:
    if not isinstance(previous, dict) or not isinstance(current, dict):
        return [], ["prior/current evidence registers must be objects"]
    if previous.get("schema_version") != current.get("schema_version") or previous.get("authority") != current.get("authority"):
        return [], ["evidence schema/authority metadata changed; only append-only entries may change during an authority transition"]
    old = previous.get("entries")
    new = current.get("entries")
    if not isinstance(old, list) or not isinstance(new, list):
        return [], ["prior/current evidence registers must contain entry arrays"]
    if len(new) < len(old) or new[:len(old)] != old:
        return [], ["public evidence register is not append-only"]
    if not all(isinstance(item, dict) for item in new[len(old):]):
        return [], ["new evidence entries must be objects"]
    return new[len(old):], []


def _transition_entry(entries: list[dict[str, Any]], *, transition: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
    url = transition["artifact_url"]
    ts = transition["artifact_timestamp"]
    statement = transition["statement"]
    kind = transition["kind"]
    expected_kind = "Owner authorization" if kind == "owner_approval" else "Control transition"
    source = OWNER_SOURCE if kind == "owner_approval" else CONTROL_SOURCE
    integrity = OWNER_INTEGRITY if kind == "owner_approval" else CONTROL_INTEGRITY
    matches = [entry for entry in entries if (
        entry.get("kind") == expected_kind
        and entry.get("date_time") == ts
        and entry.get("observation") == statement
        and entry.get("source_method") == source
        and entry.get("artifact_url") == url
        and entry.get("integrity") == integrity
        and entry.get("status") == "Observed"
    )]
    if len(matches) != 1:
        return None, [f"transition must append exactly one matching {expected_kind!r} Observed evidence entry"]
    return matches[0], []


def transition_errors(
    previous: Any, current: Any, previous_evidence: Any, current_evidence: Any,
    *, changed_paths: set[str], repository: str, pr_number: int,
    pr_payload: Any | None = None, owner_payload: Any | None = None,
) -> list[str]:
    errors = validate(previous, previous_evidence) + validate(current, current_evidence)
    if errors or not isinstance(previous, dict) or not isinstance(current, dict):
        return errors
    entries, evidence_errors = new_evidence_entries(previous_evidence, current_evidence)
    errors.extend(evidence_errors)
    changes = semantic_changes(previous, current)
    if "UNPERMITTED_CANONICAL_STRUCTURE_OR_METADATA" in changes:
        errors.append("canonical structure/metadata or controlled target/prohibition vocabulary changed in an authority transition")
        return errors
    semantic = [x for x in changes if x != "UNPERMITTED_CANONICAL_STRUCTURE_OR_METADATA"]
    if not semantic:
        if current.get("last_transition") != previous.get("last_transition"):
            errors.append("last_transition changed without an authority-state change")
        return errors

    if changed_paths & PROTECTED_TCB:
        errors.append("authority-changing pull request modifies the trusted control base")

    last = current.get("last_transition")
    if not isinstance(last, dict):
        errors.append("authority-state change requires a last_transition record")
        return errors
    if last.get("changed_authority_fields") != semantic:
        errors.append(f"last_transition changed_authority_fields must exactly equal {semantic}")
    current_tid = last.get("transition_id")
    previous_last = previous.get("last_transition")
    expected_number = 1
    if isinstance(previous_last, dict) and isinstance(previous_last.get("transition_id"), str) and re.fullmatch(r"T-\d{4}", previous_last["transition_id"]):
        expected_number = int(previous_last["transition_id"].split("-")[1]) + 1
    if current_tid != f"T-{expected_number:04d}":
        errors.append(f"last_transition transition_id must be T-{expected_number:04d}")

    opened: list[str] = []
    closed: list[str] = []
    for gate in GATES:
        if previous["gates"][gate]["status"] == current["gates"][gate]["status"] and previous["gates"][gate] != current["gates"][gate]:
            errors.append(f"{gate} approval metadata cannot change without a gate-state transition")
        before = previous["gates"][gate]["status"]
        after = current["gates"][gate]["status"]
        if before == "closed_not_approved" and after == "approved":
            opened.append(gate)
        elif before == "approved" and after == "closed_not_approved":
            closed.append(gate)
        elif before != after:
            errors.append(f"unsupported gate transition for {gate}")

    # Revocation semantics are intentionally fail-closed until a separately reviewed
    # revocation artifact format is introduced. Safer hold/target relocking remains available.
    if closed:
        errors.append("gate revocation is not supported by this control version; relock activation and open a control-maintenance PR if revocation is required")

    if opened:
        if "G2" in opened:
            if previous["gates"]["G1"]["status"] != "approved" or previous["activation"]["phase0_hold"] != "released_activation_permitted":
                errors.append("G2 may open only after G1 approval and activation-hold release already exist in trusted prior state")
        if "G3" in opened and previous["gates"]["G2"]["status"] != "approved":
            errors.append("G3 may open only after G2 approval already exists in trusted prior state")
        if "G5" in opened:
            errors.append("G5 scope expansion is fail-closed in control version 1; introduce and review a dedicated scope-migration control first")
        if last.get("kind") != "owner_approval":
            errors.append("opening any gate requires an owner_approval transition")
        expected_url = last.get("artifact_url")
        expected_ts = last.get("artifact_timestamp")
        statement = last.get("statement")
        canonical_text = canonical_owner_approval_text(current, opened)
        if statement != canonical_text:
            errors.append("last_transition statement does not match the canonical semantic-digest owner approval text")
        if not isinstance(expected_url, str) or not isinstance(expected_ts, str):
            errors.append("owner approval transition fields are invalid")
        else:
            errors.extend(verify_owner_comment_payload(
                owner_payload, repository=repository, expected_url=expected_url,
                expected_timestamp=expected_ts, expected_text=canonical_text,
            ))
            for gate in opened:
                item = current["gates"][gate]
                if item.get("approval_text") != canonical_text:
                    errors.append(f"{gate} approval_text must equal the canonical authenticated owner comment")
                if item.get("approval_artifact_url") != expected_url:
                    errors.append(f"{gate} approval_artifact_url mismatch")
                if item.get("approval_artifact_timestamp") != expected_ts or item.get("approved_at") != expected_ts:
                    errors.append(f"{gate} approval timestamps must equal authenticated comment created_at")
        _, ev_errors = _transition_entry(entries, transition=last)
        errors.extend(ev_errors)

    non_gate = [x for x in semantic if not x.startswith("gates.") and x != "activation.g2_technical_security_testing_authorized"]
    if non_gate:
        if opened or closed:
            errors.append("gate transitions may not be bundled with hold-release or target-active changes")
        if last.get("kind") != "control_transition":
            errors.append("hold/target state change requires a control_transition record")
        expected_url = last.get("artifact_url")
        expected_ts = last.get("artifact_timestamp")
        if isinstance(expected_url, str) and isinstance(expected_ts, str):
            errors.extend(verify_pr_payload(
                pr_payload, repository=repository, pr_number=pr_number,
                expected_url=expected_url, expected_timestamp=expected_ts,
            ))
        _, ev_errors = _transition_entry(entries, transition=last)
        errors.extend(ev_errors)

    if "activation.g2_technical_security_testing_authorized" in semantic and "gates.G2" not in semantic:
        errors.append("G2 technical-testing boolean cannot change independently of G2 gate")

    if previous["activation"]["phase0_hold"] == "active_activation_prohibited" and current["activation"]["phase0_hold"] == "released_activation_permitted":
        if previous["gates"]["G1"]["status"] != "approved":
            errors.append("Phase 0 hold can release only when G1 was already approved in trusted prior state")
        if current["gates"]["G2"]["status"] != "closed_not_approved" or current["activation"]["g2_technical_security_testing_authorized"]:
            errors.append("initial activation-hold release requires G2 to remain closed")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a candidate authority transition using trusted base code.")
    parser.add_argument("--previous-ref", required=True)
    parser.add_argument("--current-ref", required=True)
    parser.add_argument("--repository", default=os.getenv("GITHUB_REPOSITORY"))
    parser.add_argument("--pr-number", type=int)
    args = parser.parse_args()
    if not args.repository or "/" not in args.repository:
        print("ERROR: --repository/GITHUB_REPOSITORY is required", file=sys.stderr)
        return 1
    pr_number = args.pr_number
    if pr_number is None:
        raw = os.getenv("PR_NUMBER")
        if not raw or not raw.isdigit():
            print("ERROR: --pr-number/PR_NUMBER is required", file=sys.stderr)
            return 1
        pr_number = int(raw)

    previous, e1 = git_json(args.previous_ref, AUTHORITY_PATH)
    current, e2 = git_json(args.current_ref, AUTHORITY_PATH)
    previous_evidence, e3 = git_json(args.previous_ref, EVIDENCE_PATH)
    current_evidence, e4 = git_json(args.current_ref, EVIDENCE_PATH)
    paths, e5 = changed_files(args.previous_ref, args.current_ref)
    errors = [*e1, *e2, *e3, *e4, *e5]
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    # Read external artifacts only when the semantic transition actually needs them.
    # Non-authority PRs and structurally invalid authority changes do not consume API calls.
    token = os.getenv("GITHUB_TOKEN")
    owner_payload = None
    pr_payload = None
    preflight_changes = semantic_changes(previous, current) if isinstance(previous, dict) and isinstance(current, dict) else []
    semantic_preflight = [x for x in preflight_changes if x != "UNPERMITTED_CANONICAL_STRUCTURE_OR_METADATA"]
    opened_preflight = []
    if isinstance(previous, dict) and isinstance(current, dict):
        for gate in GATES:
            if previous["gates"][gate]["status"] == "closed_not_approved" and current["gates"][gate]["status"] == "approved":
                opened_preflight.append(gate)
    if opened_preflight and isinstance(current.get("last_transition"), dict):
        artifact_url = current["last_transition"].get("artifact_url")
        if isinstance(artifact_url, str):
            url, url_errors = comment_api_url(args.repository, artifact_url)
            errors.extend(url_errors)
            if url:
                owner_payload, fetch_errors = api_get(url, token, "owner approval comment")
                errors.extend(fetch_errors)
    non_gate_preflight = [x for x in semantic_preflight if not x.startswith("gates.") and x != "activation.g2_technical_security_testing_authorized"]
    if non_gate_preflight:
        pr_payload, pr_errors = api_get(
            f"https://api.github.com/repos/{args.repository}/pulls/{pr_number}", token,
            f"PR #{pr_number}",
        )
        errors.extend(pr_errors)
    errors.extend(transition_errors(
        previous, current, previous_evidence, current_evidence,
        changed_paths=paths, repository=args.repository, pr_number=pr_number,
        pr_payload=pr_payload, owner_payload=owner_payload,
    ))
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print("Trusted public authority-transition validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
