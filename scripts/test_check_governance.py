from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

import check_governance as cg

ROOT = Path(__file__).resolve().parents[1]


def baseline_authority():
    return json.loads((ROOT / "governance/AUTHORITY_STATE.json").read_text())


def baseline_evidence():
    return json.loads((ROOT / "evidence/EVIDENCE_REGISTER.json").read_text())


def approved_gate(text="I approve G0.", ts="2026-08-23T10:00:00Z", url="https://github.com/example-owner/authorized-security-assurance-lab/pull/1#issuecomment-1", scope="governance baseline"):
    return {
        "status": "approved",
        "approved_at": ts,
        "approval_text": text,
        "approval_artifact_url": url,
        "approval_artifact_timestamp": ts,
        "authorized_scope": scope,
    }


class GovernanceValidationTests(unittest.TestCase):
    def test_bootstrap_state_is_valid(self):
        self.assertEqual(cg.validate(baseline_authority(), baseline_evidence()), [])

    def test_duplicate_json_key_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "x.json"
            p.write_text('{"a": 1, "a": 2}')
            with self.assertRaises(ValueError):
                cg.load_json(p)

    def test_g1_cannot_open_before_g0(self):
        a = baseline_authority()
        a["gates"]["G1"] = approved_gate(text="I approve G1.", scope="local activation")
        self.assertTrue(any("G1 cannot be approved while prerequisite G0" in e for e in cg.validate(a, baseline_evidence())))

    def test_approved_timestamp_must_equal_authenticated_artifact(self):
        a = baseline_authority()
        a["gates"]["G0"] = approved_gate()
        a["gates"]["G0"]["approved_at"] = "2026-08-23T10:00:01Z"
        self.assertTrue(any("approved_at must equal" in e for e in cg.validate(a, baseline_evidence())))

    def test_approved_gate_requires_comment_url(self):
        a = baseline_authority()
        a["gates"]["G0"] = approved_gate(url="https://example.com/not-github")
        self.assertTrue(any("issue-comment URL" in e for e in cg.validate(a, baseline_evidence())))

    def test_g2_boolean_must_match_gate(self):
        a = baseline_authority()
        a["activation"]["g2_technical_security_testing_authorized"] = True
        self.assertTrue(any("G2 gate and technical-testing boolean" in e for e in cg.validate(a, baseline_evidence())))


    def test_hold_release_requires_g1(self):
        a = baseline_authority()
        a["activation"]["phase0_hold"] = "released_activation_permitted"
        self.assertTrue(any("cannot release before G1 approval" in e for e in cg.validate(a, baseline_evidence())))

    def test_target_bootstrap_values_are_pinned(self):
        a = baseline_authority()
        a["target"]["planned_exposure"] = "lan"
        self.assertTrue(any("controlled bootstrap target" in e for e in cg.validate(a, baseline_evidence())))

    def test_evidence_ids_are_sequential(self):
        e = baseline_evidence()
        e["entries"] = [{
            "id": "E-0002", "date_time": "2026-08-23T10:00:00Z", "kind": "Control transition",
            "observation": "x", "source_method": "x", "artifact_url": None, "integrity": "x",
            "status": "Recorded", "notes": "x",
        }]
        self.assertTrue(any("id must be E-0001" in x for x in cg.validate(baseline_authority(), e)))

    def test_evidence_chronology_is_monotonic(self):
        e = baseline_evidence()
        base = {"kind": "Control transition", "observation": "x", "source_method": "x", "artifact_url": None, "integrity": "x", "status": "Recorded", "notes": "x"}
        e["entries"] = [
            {"id": "E-0001", "date_time": "2026-08-23T11:00:00Z", **base},
            {"id": "E-0002", "date_time": "2026-08-23T10:00:00Z", **base},
        ]
        self.assertTrue(any("chronologically earlier" in x for x in cg.validate(baseline_authority(), e)))

    def test_boolean_is_not_accepted_as_schema_version(self):
        a = baseline_authority()
        a["schema_version"] = True
        self.assertTrue(any("integer 1" in e for e in cg.validate(a, baseline_evidence())))

    def test_last_transition_id_format(self):
        a = baseline_authority()
        a["last_transition"] = {
            "transition_id": "1", "kind": "control_transition", "changed_authority_fields": ["activation.phase0_hold"],
            "statement": "release", "artifact_url": "https://github.com/example-owner/authorized-security-assurance-lab/pull/2",
            "artifact_timestamp": "2026-08-23T10:00:00Z",
        }
        self.assertTrue(any("T-0001 format" in e for e in cg.validate(a, baseline_evidence())))

    def test_owner_transition_requires_issue_comment_url(self):
        a = baseline_authority()
        a["last_transition"] = {
            "transition_id": "T-0001", "kind": "owner_approval", "changed_authority_fields": ["gates.G0"],
            "statement": "approve", "artifact_url": "https://github.com/example-owner/authorized-security-assurance-lab/pull/2",
            "artifact_timestamp": "2026-08-23T10:00:00Z",
        }
        self.assertTrue(any("owner approval artifact" in e for e in cg.validate(a, baseline_evidence())))

    def test_g4_is_independent_of_g1_g2_g3_after_g0(self):
        a = baseline_authority()
        a["gates"]["G0"] = approved_gate()
        a["gates"]["G4"] = approved_gate(text="I approve publication.", scope="future sanitized publication of lab findings or evidence")
        errors = cg.validate(a, baseline_evidence())
        self.assertFalse(any("G4 cannot be approved" in e for e in errors))

    def test_g2_requires_activation_hold_release(self):
        a = baseline_authority()
        a["gates"]["G0"] = approved_gate()
        a["gates"]["G1"] = approved_gate(text="I approve G1.", scope="activation")
        a["gates"]["G2"] = approved_gate(text="I approve G2.", scope="bounded technical testing")
        a["activation"]["g2_technical_security_testing_authorized"] = True
        self.assertTrue(any("activation hold remains closed" in e for e in cg.validate(a, baseline_evidence())))

    def test_oversized_json_file_is_rejected_before_parse(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "large.json"
            p.write_bytes(b" " * (cg.MAX_JSON_BYTES + 1))
            with self.assertRaises(ValueError):
                cg.load_json(p)

    def test_authorized_scope_has_safety_limit(self):
        a=baseline_authority(); a["gates"]["G0"]=approved_gate(scope="x"*2001)
        self.assertTrue(any("authorized_scope exceeds" in e for e in cg.validate(a,baseline_evidence())))


if __name__ == "__main__":
    unittest.main()
