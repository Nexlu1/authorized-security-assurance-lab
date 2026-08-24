from __future__ import annotations

from datetime import datetime
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
AUTHORITY_PATH = ROOT / "governance" / "AUTHORITY_STATE.json"
EVIDENCE_PATH = ROOT / "evidence" / "EVIDENCE_REGISTER.json"
MAX_JSON_BYTES = 1_000_000
MAX_EVIDENCE_ENTRIES = 10_000
MAX_TEXT_LENGTH = 20_000

AUTHORITY_KEYS = {
    "schema_version", "authority", "gates", "activation", "target",
    "prohibitions", "status_definitions", "evidence_register", "last_transition",
}
GATE_NAMES = ["G0", "G1", "G2", "G3", "G4", "G5"]
GATE_STATUSES = {"closed_not_approved", "approved"}
HOLD_STATES = {"active_activation_prohibited", "released_activation_permitted"}
EVIDENCE_STATUSES = {
    "Recorded", "Observed", "Externally verified", "Reproduced", "Validated",
    "Remediated", "Retested", "Rejected", "Uncertain",
}
RFC3339_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$")
ISSUE_COMMENT_RE = re.compile(r"^https://github\.com/[^/]+/[^/]+/(?:issues|pull)/\d+#issuecomment-\d+$")


def _reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise ValueError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def load_json(path: Path) -> Any:
    if path.stat().st_size > MAX_JSON_BYTES:
        raise ValueError(f"JSON file exceeds {MAX_JSON_BYTES} byte safety limit: {path}")
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_reject_duplicates)


def valid_rfc3339(value: Any) -> bool:
    if not isinstance(value, str) or not RFC3339_RE.fullmatch(value):
        return False
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None


def _check_authority(data: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["authority root must be an object"]
    if set(data) != AUTHORITY_KEYS:
        errors.append(f"authority root keys differ: {sorted(set(data) ^ AUTHORITY_KEYS)}")
    if type(data.get("schema_version")) is not int or data.get("schema_version") != 1:
        errors.append("authority schema_version must be integer 1")

    authority = data.get("authority")
    if not isinstance(authority, dict) or set(authority) != {"canonical_source", "markdown_documents_authoritative", "rule"}:
        errors.append("authority metadata has unexpected shape")
    else:
        if authority.get("canonical_source") != "governance/AUTHORITY_STATE.json":
            errors.append("authority canonical_source mismatch")
        if authority.get("markdown_documents_authoritative") is not False:
            errors.append("Markdown must remain non-authoritative")
        if not isinstance(authority.get("rule"), str) or not authority["rule"].strip():
            errors.append("authority rule must be non-empty text")

    gates = data.get("gates")
    if not isinstance(gates, dict) or list(gates) != GATE_NAMES:
        errors.append("gates must contain G0..G5 in canonical order")
        gates = {}
    for gate in GATE_NAMES:
        item = gates.get(gate)
        if not isinstance(item, dict):
            errors.append(f"{gate} must be an object")
            continue
        status = item.get("status")
        if status not in GATE_STATUSES:
            errors.append(f"{gate} has invalid status")
            continue
        if status == "closed_not_approved":
            if set(item) != {"status"}:
                errors.append(f"closed {gate} must contain only status")
        else:
            expected = {"status", "approved_at", "approval_text", "approval_artifact_url", "approval_artifact_timestamp", "authorized_scope"}
            if set(item) != expected:
                errors.append(f"approved {gate} has unexpected fields")
            if not valid_rfc3339(item.get("approved_at")):
                errors.append(f"{gate} approved_at must be RFC3339")
            if not isinstance(item.get("approval_text"), str) or not item["approval_text"].strip():
                errors.append(f"{gate} approval_text must be non-empty")
            elif len(item["approval_text"]) > 10_000:
                errors.append(f"{gate} approval_text exceeds safety length limit")
            if not valid_rfc3339(item.get("approval_artifact_timestamp")):
                errors.append(f"{gate} approval artifact timestamp must be RFC3339")
            if item.get("approved_at") != item.get("approval_artifact_timestamp"):
                errors.append(f"{gate} approved_at must equal authenticated artifact timestamp")
            if not isinstance(item.get("approval_artifact_url"), str) or not ISSUE_COMMENT_RE.fullmatch(item["approval_artifact_url"]):
                errors.append(f"{gate} approval artifact URL must be a GitHub PR issue-comment URL")
            if not isinstance(item.get("authorized_scope"), str) or not item["authorized_scope"].strip():
                errors.append(f"{gate} authorized_scope must be non-empty")
            elif len(item["authorized_scope"]) > 2_000:
                errors.append(f"{gate} authorized_scope exceeds safety length limit")

    dependencies = {
        "G1": ("G0",),
        "G2": ("G0", "G1"),
        "G3": ("G0", "G1", "G2"),
        "G4": ("G0",),
        "G5": ("G0",),
    }
    for gate, required in dependencies.items():
        if isinstance(gates.get(gate), dict) and gates[gate].get("status") == "approved":
            for dependency in required:
                if not isinstance(gates.get(dependency), dict) or gates[dependency].get("status") != "approved":
                    errors.append(f"{gate} cannot be approved while prerequisite {dependency} is not approved")

    activation = data.get("activation")
    if not isinstance(activation, dict) or set(activation) != {"phase0_hold", "g2_technical_security_testing_authorized"}:
        errors.append("activation object has unexpected shape")
        activation = {}
    if activation.get("phase0_hold") not in HOLD_STATES:
        errors.append("invalid phase0_hold")
    if type(activation.get("g2_technical_security_testing_authorized")) is not bool:
        errors.append("g2 authorization flag must be boolean")
    g2_approved = isinstance(gates.get("G2"), dict) and gates["G2"].get("status") == "approved"
    if activation.get("g2_technical_security_testing_authorized") != g2_approved:
        errors.append("G2 gate and technical-testing boolean must agree")
    if g2_approved and activation.get("phase0_hold") != "released_activation_permitted":
        errors.append("G2 cannot be approved while the activation hold remains closed")
    if activation.get("phase0_hold") == "released_activation_permitted":
        if not isinstance(gates.get("G1"), dict) or gates["G1"].get("status") != "approved":
            errors.append("G1 activation hold cannot release before G1 approval")

    target = data.get("target")
    expected_target = {
        "planned_product": "OWASP WebGoat",
        "planned_release": "v2025.3",
        "planned_image": "webgoat/webgoat:v2025.3",
        "planned_runtime": "owned_local_computer_only",
        "planned_webgoat_binding": "127.0.0.1:8080:8080",
        "planned_webwolf_binding": "127.0.0.1:9090:9090",
        "planned_exposure": "loopback_only",
        "planned_data": "synthetic_only",
    }
    if not isinstance(target, dict) or set(target) != set(expected_target):
        errors.append("target object has unexpected shape")
    else:
        for key, value in expected_target.items():
            if target.get(key) != value:
                errors.append(f"target {key} differs from controlled bootstrap target")

    if data.get("evidence_register") != "evidence/EVIDENCE_REGISTER.json":
        errors.append("evidence register path mismatch")
    if not isinstance(data.get("prohibitions"), list) or not all(isinstance(x, str) and x and len(x) <= 2_000 for x in data["prohibitions"]):
        errors.append("prohibitions must be non-empty bounded strings")
    elif len(data["prohibitions"]) > 100:
        errors.append("prohibitions list exceeds safety limit")
    defs = data.get("status_definitions")
    if not isinstance(defs, dict) or set(defs) != EVIDENCE_STATUSES:
        errors.append("status_definitions must define the exact public evidence vocabulary")

    last = data.get("last_transition")
    if last is not None:
        expected = {"transition_id", "kind", "changed_authority_fields", "statement", "artifact_url", "artifact_timestamp"}
        if not isinstance(last, dict) or set(last) != expected:
            errors.append("last_transition has unexpected shape")
        else:
            if not isinstance(last.get("transition_id"), str) or not re.fullmatch(r"T-\d{4}", last["transition_id"]):
                errors.append("last_transition transition_id must use T-0001 format")
            if last.get("kind") not in {"owner_approval", "control_transition"}:
                errors.append("last_transition kind is invalid")
            if not isinstance(last.get("changed_authority_fields"), list) or not all(isinstance(x, str) and x for x in last["changed_authority_fields"]):
                errors.append("last_transition changed_authority_fields must be a string array")
            elif len(last["changed_authority_fields"]) > 10:
                errors.append("last_transition changed_authority_fields exceeds safety limit")
            if not isinstance(last.get("statement"), str) or not last["statement"].strip():
                errors.append("last_transition statement is required")
            elif len(last["statement"]) > 10_000:
                errors.append("last_transition statement exceeds safety length limit")
            artifact_url = last.get("artifact_url")
            if not isinstance(artifact_url, str) or not artifact_url.startswith("https://github.com/"):
                errors.append("last_transition artifact_url must be a GitHub URL")
            elif last.get("kind") == "owner_approval" and not ISSUE_COMMENT_RE.fullmatch(artifact_url):
                errors.append("owner approval artifact must be a GitHub PR issue-comment URL")
            elif last.get("kind") == "control_transition" and not re.fullmatch(r"https://github\.com/[^/]+/[^/]+/pull/\d+", artifact_url):
                errors.append("control transition artifact must be a GitHub PR URL")
            if not valid_rfc3339(last.get("artifact_timestamp")):
                errors.append("last_transition artifact_timestamp must be RFC3339")
    return errors


def _check_evidence(data: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(data, dict) or set(data) != {"schema_version", "authority", "entries"}:
        return ["evidence root has unexpected shape"]
    if type(data.get("schema_version")) is not int or data.get("schema_version") != 1:
        errors.append("evidence schema_version must be integer 1")
    auth = data.get("authority")
    if not isinstance(auth, dict) or set(auth) != {"canonical_source", "markdown_view_authoritative", "rule"}:
        errors.append("evidence authority metadata has unexpected shape")
    else:
        if auth.get("canonical_source") != "evidence/EVIDENCE_REGISTER.json":
            errors.append("evidence canonical_source mismatch")
        if auth.get("markdown_view_authoritative") is not False:
            errors.append("evidence Markdown view must remain non-authoritative")
    entries = data.get("entries")
    if not isinstance(entries, list):
        return errors + ["evidence entries must be an array"]
    if len(entries) > MAX_EVIDENCE_ENTRIES:
        return errors + [f"evidence entries exceed safety limit of {MAX_EVIDENCE_ENTRIES}"]
    ids: set[str] = set()
    previous_time: datetime | None = None
    expected_fields = {"id", "date_time", "kind", "observation", "source_method", "artifact_url", "integrity", "status", "notes"}
    for i, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict) or set(entry) != expected_fields:
            errors.append(f"evidence entry {i} has unexpected shape")
            continue
        eid = entry.get("id")
        if not isinstance(eid, str) or not re.fullmatch(r"E-\d{4}", eid):
            errors.append(f"evidence entry {i} has invalid id")
        elif eid in ids:
            errors.append(f"duplicate evidence id {eid}")
        else:
            ids.add(eid)
            expected_id = f"E-{i:04d}"
            if eid != expected_id:
                errors.append(f"evidence entry {i} id must be {expected_id}")
        if not valid_rfc3339(entry.get("date_time")):
            errors.append(f"evidence {eid} date_time must be RFC3339")
        else:
            value = entry["date_time"]
            parsed = datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
            if previous_time is not None and parsed < previous_time:
                errors.append(f"evidence {eid} is chronologically earlier than the preceding entry")
            previous_time = parsed
        if entry.get("status") not in EVIDENCE_STATUSES:
            errors.append(f"evidence {eid} has invalid status")
        for field in ("kind", "observation", "source_method", "integrity", "notes"):
            if not isinstance(entry.get(field), str) or not entry[field].strip():
                errors.append(f"evidence {eid} {field} must be non-empty text")
            elif len(entry[field]) > MAX_TEXT_LENGTH:
                errors.append(f"evidence {eid} {field} exceeds safety length limit")
        url = entry.get("artifact_url")
        if url is not None and (not isinstance(url, str) or not url.startswith("https://")):
            errors.append(f"evidence {eid} artifact_url must be null or https URL")
    return errors


def validate(authority: Any, evidence: Any) -> list[str]:
    return _check_authority(authority) + _check_evidence(evidence)


def main() -> int:
    try:
        authority = load_json(AUTHORITY_PATH)
        evidence = load_json(EVIDENCE_PATH)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError, RecursionError) as exc:
        print(f"governance validation failed: {exc}", file=sys.stderr)
        return 1
    errors = validate(authority, evidence)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print("Public governance state validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
