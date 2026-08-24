from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import unittest

import check_transition as ct

ROOT = Path(__file__).resolve().parents[1]
REPO = "example-owner/authorized-security-assurance-lab"
PR = 7
COMMENT_URL = f"https://github.com/{REPO}/issues/3#issuecomment-123"
COMMENT_TS = "2026-08-23T10:00:00Z"


def authority():
    return json.loads((ROOT / "governance/AUTHORITY_STATE.json").read_text())


def evidence():
    return json.loads((ROOT / "evidence/EVIDENCE_REGISTER.json").read_text())


def approved_gate(scope: str, text: str = "PLACEHOLDER"):
    return {
        "status": "approved",
        "approved_at": COMMENT_TS,
        "approval_text": text,
        "approval_artifact_url": COMMENT_URL,
        "approval_artifact_timestamp": COMMENT_TS,
        "authorized_scope": scope,
    }


def owner_approval_candidate():
    prev = authority()
    cur = deepcopy(prev)
    cur["gates"]["G0"] = approved_gate("governance baseline only; no target activation or technical testing")
    cur["gates"]["G1"] = approved_gate("local WebGoat prerequisites, image acquisition, startup, and containment validation only; no technical vulnerability testing")
    text = ct.canonical_owner_approval_text(cur, ["G0", "G1"])
    cur["gates"]["G0"]["approval_text"] = text
    cur["gates"]["G1"]["approval_text"] = text
    cur["last_transition"] = {
        "transition_id": "T-0001", "kind": "owner_approval",
        "changed_authority_fields": ["gates.G0", "gates.G1"],
        "statement": text, "artifact_url": COMMENT_URL,
        "artifact_timestamp": COMMENT_TS,
    }
    ev0 = evidence(); ev1 = deepcopy(ev0)
    ev1["entries"].append({
        "id": "E-0001", "date_time": COMMENT_TS, "kind": "Owner authorization",
        "observation": text, "source_method": ct.OWNER_SOURCE,
        "artifact_url": COMMENT_URL, "integrity": ct.OWNER_INTEGRITY,
        "status": "Observed", "notes": "Public owner-authenticated authorization artifact; G2 remains closed.",
    })
    return prev, cur, ev0, ev1, text


def comment_payload(text: str, *, login="example-owner", association="OWNER", created=COMMENT_TS, updated=COMMENT_TS, url=COMMENT_URL, issue=3):
    return {
        "html_url": url,
        "issue_url": f"https://api.github.com/repos/{REPO}/issues/{issue}",
        "user": {"login": login}, "author_association": association,
        "created_at": created, "updated_at": updated, "body": text,
    }


def pr_payload(pr=PR, created="2026-08-23T10:05:00Z"):
    return {"html_url": f"https://github.com/{REPO}/pull/{pr}", "number": pr, "created_at": created}


def approved_prior():
    _, cur, _, ev, _ = owner_approval_candidate()
    return cur, ev


class TransitionTests(unittest.TestCase):
    def errors(self, prev, cur, ev0, ev1, *, paths=None, owner=None, prdata=None, pr=PR):
        return ct.transition_errors(
            prev, cur, ev0, ev1,
            changed_paths=paths or {ct.AUTHORITY_PATH, ct.EVIDENCE_PATH},
            repository=REPO, pr_number=pr, pr_payload=prdata,
            owner_payload=owner,
        )

    def test_no_authority_change_passes(self):
        a=authority(); e=evidence()
        self.assertEqual(self.errors(a,deepcopy(a),e,deepcopy(e)),[])

    def test_g0_g1_owner_approval_passes(self):
        p,c,e0,e1,text=owner_approval_candidate()
        self.assertEqual(self.errors(p,c,e0,e1,owner=comment_payload(text)),[])

    def test_semantic_digest_changes_when_scope_changes(self):
        p,c,e0,e1,text=owner_approval_candidate()
        old=ct.authorization_digest(c,["G0","G1"])
        c["gates"]["G1"]["authorized_scope"] += " expanded"
        self.assertNotEqual(old,ct.authorization_digest(c,["G0","G1"]))

    def test_owner_comment_must_be_owner(self):
        p,c,e0,e1,text=owner_approval_candidate()
        errs=self.errors(p,c,e0,e1,owner=comment_payload(text,login="other",association="CONTRIBUTOR"))
        self.assertTrue(any("repository owner" in x or "OWNER" in x for x in errs))

    def test_owner_comment_must_be_unedited(self):
        p,c,e0,e1,text=owner_approval_candidate()
        errs=self.errors(p,c,e0,e1,owner=comment_payload(text,updated="2026-08-23T10:00:01Z"))
        self.assertTrue(any("edited" in x for x in errs))

    def test_owner_comment_must_be_same_repository(self):
        p,c,e0,e1,text=owner_approval_candidate()
        bad="https://github.com/other/repo/issues/3#issuecomment-123"
        c["last_transition"]["artifact_url"]=bad
        c["gates"]["G0"]["approval_artifact_url"]=bad
        c["gates"]["G1"]["approval_artifact_url"]=bad
        e1["entries"][0]["artifact_url"]=bad
        errs=self.errors(p,c,e0,e1,owner=comment_payload(text,url=bad))
        self.assertTrue(any("current repository" in x for x in errs))

    def test_owner_comment_body_must_match_semantic_digest(self):
        p,c,e0,e1,text=owner_approval_candidate()
        errs=self.errors(p,c,e0,e1,owner=comment_payload(text+"\nextra"))
        self.assertTrue(any("semantic-digest" in x for x in errs))

    def test_owner_comment_timestamp_must_match(self):
        p,c,e0,e1,text=owner_approval_candidate()
        errs=self.errors(p,c,e0,e1,owner=comment_payload(text,created="2026-08-23T10:00:01Z",updated="2026-08-23T10:00:01Z"))
        self.assertTrue(any("created_at" in x for x in errs))

    def test_candidate_statement_cannot_diverge_from_semantics(self):
        p,c,e0,e1,text=owner_approval_candidate()
        c["last_transition"]["statement"]="Authority approval\nAuthorization digest: " + "0"*64
        errs=self.errors(p,c,e0,e1,owner=comment_payload(text))
        self.assertTrue(any("canonical semantic-digest" in x for x in errs))

    def test_scope_tampering_after_approval_invalidates_digest(self):
        p,c,e0,e1,text=owner_approval_candidate()
        c["gates"]["G1"]["authorized_scope"]="broader scope"
        errs=self.errors(p,c,e0,e1,owner=comment_payload(text))
        self.assertTrue(any("canonical semantic-digest" in x or "approval_text" in x for x in errs))

    def test_evidence_is_append_only(self):
        p,c,e0,e1,text=owner_approval_candidate()
        old=deepcopy(e0)
        old["entries"]=[{"id":"E-0001","date_time":"2026-08-23T09:00:00Z","kind":"Control transition","observation":"old","source_method":"x","artifact_url":None,"integrity":"x","status":"Recorded","notes":"x"}]
        rewritten=deepcopy(old); rewritten["entries"][0]["observation"]="rewritten"
        rewritten["entries"].append(e1["entries"][0] | {"id":"E-0002"})
        errs=self.errors(p,c,old,rewritten,owner=comment_payload(text))
        self.assertTrue(any("append-only" in x for x in errs))

    def test_authority_change_cannot_self_amend_guardian(self):
        p,c,e0,e1,text=owner_approval_candidate()
        errs=self.errors(p,c,e0,e1,paths={ct.AUTHORITY_PATH,ct.EVIDENCE_PATH,".github/workflows/trusted-authority-guardian.yml"},owner=comment_payload(text))
        self.assertTrue(any("trusted control base" in x for x in errs))

    def test_authority_change_cannot_self_amend_governance_workflow(self):
        p,c,e0,e1,text=owner_approval_candidate()
        errs=self.errors(p,c,e0,e1,paths={ct.AUTHORITY_PATH,ct.EVIDENCE_PATH,".github/workflows/governance-integrity.yml"},owner=comment_payload(text))
        self.assertTrue(any("trusted control base" in x for x in errs))

    def test_authority_change_cannot_self_amend_transition_checker(self):
        p,c,e0,e1,text=owner_approval_candidate()
        errs=self.errors(p,c,e0,e1,paths={ct.AUTHORITY_PATH,ct.EVIDENCE_PATH,"scripts/check_transition.py"},owner=comment_payload(text))
        self.assertTrue(any("trusted control base" in x for x in errs))

    def test_approved_gate_metadata_cannot_be_silently_changed(self):
        p,e0=approved_prior(); c=deepcopy(p); e1=deepcopy(e0)
        c["gates"]["G1"]["authorized_scope"]="broader"
        errs=self.errors(p,c,e0,e1)
        self.assertTrue(any("metadata cannot change" in x for x in errs))

    def test_transition_id_must_increment(self):
        p,c,e0,e1,text=owner_approval_candidate(); c["last_transition"]["transition_id"]="T-0009"
        errs=self.errors(p,c,e0,e1,owner=comment_payload(text))
        self.assertTrue(any("T-0001" in x for x in errs))

    def test_changed_authority_fields_must_be_exact(self):
        p,c,e0,e1,text=owner_approval_candidate(); c["last_transition"]["changed_authority_fields"]=["gates.G0"]
        errs=self.errors(p,c,e0,e1,owner=comment_payload(text))
        self.assertTrue(any("exactly equal" in x for x in errs))

    def test_gate_revocation_is_fail_closed(self):
        p,e0=approved_prior(); c=deepcopy(p); e1=deepcopy(e0)
        c["gates"]["G1"]={"status":"closed_not_approved"}
        c["last_transition"]={"transition_id":"T-0002","kind":"owner_approval","changed_authority_fields":["gates.G1"],"statement":"revoke","artifact_url":COMMENT_URL,"artifact_timestamp":COMMENT_TS}
        errs=self.errors(p,c,e0,e1)
        self.assertTrue(any("revocation is not supported" in x for x in errs))

    def test_hold_release_passes_only_after_trusted_g1(self):
        p,e0=approved_prior(); c=deepcopy(p); e1=deepcopy(e0)
        c["activation"]["phase0_hold"]="released_activation_permitted"
        prts="2026-08-23T10:05:00Z"; statement="Release the activation hold for the already approved G1 local lab scope; G2 remains closed."
        c["last_transition"]={"transition_id":"T-0002","kind":"control_transition","changed_authority_fields":["activation.phase0_hold"],"statement":statement,"artifact_url":f"https://github.com/{REPO}/pull/{PR}","artifact_timestamp":prts}
        e1["entries"].append({"id":"E-0002","date_time":prts,"kind":"Control transition","observation":statement,"source_method":ct.CONTROL_SOURCE,"artifact_url":f"https://github.com/{REPO}/pull/{PR}","integrity":ct.CONTROL_INTEGRITY,"status":"Observed","notes":"Procedural hold release; G2 remains closed."})
        self.assertEqual(self.errors(p,c,e0,e1,prdata=pr_payload()),[])

    def test_hold_release_before_trusted_g1_is_rejected(self):
        p=authority(); e0=evidence(); c=deepcopy(p); e1=deepcopy(e0)
        c["activation"]["phase0_hold"]="released_activation_permitted"
        # Current-state validation itself rejects the release before G1.
        errs=self.errors(p,c,e0,e1)
        self.assertTrue(any("G1 approval" in x for x in errs))


    def test_g2_boolean_cannot_change_without_g2_gate(self):
        p,e0=approved_prior(); c=deepcopy(p); e1=deepcopy(e0)
        c["activation"]["g2_technical_security_testing_authorized"]=True
        errs=self.errors(p,c,e0,e1)
        self.assertTrue(any("G2 gate" in x for x in errs))

    def test_wrong_pr_control_artifact_is_rejected(self):
        p,e0=approved_prior(); c=deepcopy(p); e1=deepcopy(e0)
        c["activation"]["phase0_hold"]="released_activation_permitted"
        prts="2026-08-23T10:05:00Z"; statement="release"
        bad=f"https://github.com/{REPO}/pull/99"
        c["last_transition"]={"transition_id":"T-0002","kind":"control_transition","changed_authority_fields":["activation.phase0_hold"],"statement":statement,"artifact_url":bad,"artifact_timestamp":prts}
        e1["entries"].append({"id":"E-0002","date_time":prts,"kind":"Control transition","observation":statement,"source_method":ct.CONTROL_SOURCE,"artifact_url":bad,"integrity":ct.CONTROL_INTEGRITY,"status":"Observed","notes":"x"})
        errs=self.errors(p,c,e0,e1,prdata=pr_payload())
        self.assertTrue(any("current pull request" in x for x in errs))

    def test_g2_cannot_open_before_hold_release_is_trusted(self):
        p,e0=approved_prior(); c=deepcopy(p); e1=deepcopy(e0)
        # Candidate current state would also need the hold released; bundling it is rejected by design.
        c["activation"]["phase0_hold"]="released_activation_permitted"
        c["gates"]["G2"]={"status":"approved","approved_at":COMMENT_TS,"approval_text":"x","approval_artifact_url":COMMENT_URL,"approval_artifact_timestamp":COMMENT_TS,"authorized_scope":"bounded local WebGoat technical testing"}
        c["activation"]["g2_technical_security_testing_authorized"]=True
        text=ct.canonical_owner_approval_text(c,["G2"]); c["gates"]["G2"]["approval_text"]=text
        c["last_transition"]={"transition_id":"T-0002","kind":"owner_approval","changed_authority_fields":["gates.G2","activation.phase0_hold","activation.g2_technical_security_testing_authorized"],"statement":text,"artifact_url":COMMENT_URL,"artifact_timestamp":COMMENT_TS}
        e1["entries"].append({"id":"E-0002","date_time":COMMENT_TS,"kind":"Owner authorization","observation":text,"source_method":ct.OWNER_SOURCE,"artifact_url":COMMENT_URL,"integrity":ct.OWNER_INTEGRITY,"status":"Observed","notes":"x"})
        errs=self.errors(p,c,e0,e1,owner=comment_payload(text))
        self.assertTrue(any("trusted prior state" in x or "bundled" in x for x in errs))

    def test_g5_is_fail_closed_in_v1(self):
        p,c,e0,e1,text=owner_approval_candidate()
        # First make G0/G1 trusted, then attempt G5 independently.
        p=c; e0=e1; c=deepcopy(p); e1=deepcopy(e0)
        c["gates"]["G5"]={"status":"approved","approved_at":COMMENT_TS,"approval_text":"x","approval_artifact_url":COMMENT_URL,"approval_artifact_timestamp":COMMENT_TS,"authorized_scope":"add a new target"}
        text=ct.canonical_owner_approval_text(c,["G5"]); c["gates"]["G5"]["approval_text"]=text
        c["last_transition"]={"transition_id":"T-0002","kind":"owner_approval","changed_authority_fields":["gates.G5"],"statement":text,"artifact_url":COMMENT_URL,"artifact_timestamp":COMMENT_TS}
        e1["entries"].append({"id":"E-0002","date_time":COMMENT_TS,"kind":"Owner authorization","observation":text,"source_method":ct.OWNER_SOURCE,"artifact_url":COMMENT_URL,"integrity":ct.OWNER_INTEGRITY,"status":"Observed","notes":"x"})
        errs=self.errors(p,c,e0,e1,owner=comment_payload(text))
        self.assertTrue(any("G5 scope expansion is fail-closed" in x for x in errs))

    def test_evidence_metadata_is_immutable_in_transition(self):
        p,c,e0,e1,text=owner_approval_candidate()
        e1["authority"]["rule"]="rewritten policy"
        errs=self.errors(p,c,e0,e1,owner=comment_payload(text))
        self.assertTrue(any("evidence schema/authority metadata changed" in x for x in errs))

    def test_comment_api_url_accepts_same_repo_issue_comment(self):
        url,errs=ct.comment_api_url(REPO,COMMENT_URL)
        self.assertEqual(errs,[])
        self.assertEqual(url,f"https://api.github.com/repos/{REPO}/issues/comments/123")

    def test_comment_api_url_rejects_different_repo(self):
        url,errs=ct.comment_api_url(REPO,"https://github.com/other/repo/issues/3#issuecomment-123")
        self.assertIsNone(url)
        self.assertTrue(any("different repository" in x for x in errs))


if __name__ == "__main__":
    unittest.main()
