import hashlib
import sqlite3
from pathlib import Path

SCHEMA = Path("schema/authority_v1.sql")


def expect_integrity_error(fn, contains=None):
    try:
        fn()
    except sqlite3.IntegrityError as exc:
        if contains is not None:
            assert contains in str(exc), (contains, str(exc))
        return
    raise AssertionError("expected sqlite3.IntegrityError")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main():
    db = sqlite3.connect(":memory:")
    db.executescript(SCHEMA.read_text(encoding="utf-8"))

    # One blob per byte identity.
    h_container = "a" * 64
    h_child = "b" * 64
    db.execute(
        "INSERT INTO blob_object(sha256,size_bytes,media_type) VALUES(?,?,?)",
        (h_container, 1000, "application/zip"),
    )
    db.execute(
        "INSERT INTO blob_object(sha256,size_bytes,media_type) VALUES(?,?,?)",
        (h_child, 10, "text/plain"),
    )
    expect_integrity_error(
        lambda: db.execute(
            "INSERT INTO blob_object(sha256,size_bytes) VALUES(?,?)",
            (h_container, 1000),
        )
    )

    # Malformed hash spellings are rejected.
    for bad_hash in ("A" * 64, "g" * 64, "00"):
        expect_integrity_error(
            lambda bad_hash=bad_hash: db.execute(
                "INSERT INTO blob_object(sha256,size_bytes) VALUES(?,1)",
                (bad_hash,),
            )
        )

    db.execute(
        "INSERT INTO source_container(container_blob_id,container_kind) VALUES(1,'zip')"
    )

    # Hostile original names are PRESERVED AS METADATA. They are not storage paths.
    # The same bytes may occur more than once: occurrence identity is not collapsed.
    for ordinal, offset in ((0, 100), (1, 200)):
        db.execute(
            """INSERT INTO occurrence(
                 blob_id,source_container_id,ordinal,byte_offset,byte_length,
                 original_name_text,original_name_raw
               ) VALUES(2,1,?,?,?,?,?)""",
            (ordinal, offset, 10, "../evil.txt", b"../evil.txt"),
        )
    assert db.execute("SELECT count(*) FROM occurrence").fetchone()[0] == 2

    # Declared ranges cannot escape the source container.
    expect_integrity_error(
        lambda: db.execute(
            """INSERT INTO occurrence(
                 blob_id,source_container_id,byte_offset,byte_length
               ) VALUES(2,1,999,10)"""
        ),
        "occurrence byte range exceeds source container",
    )

    # Parser success is parsing state, not validation truth.
    db.execute(
        """INSERT INTO parser_run(
             source_occurrence_id,parser_name,parser_version,parser_mode,result_state
           ) VALUES(1,'synthetic-parser','1.0','read-only','PARSED_WITH_WARNINGS')"""
    )
    expect_integrity_error(
        lambda: db.execute(
            """INSERT INTO parser_run(
                 source_occurrence_id,parser_name,parser_version,parser_mode,result_state
               ) VALUES(1,'synthetic-parser','1.0','read-only','PASS')"""
        )
    )

    # Authority records are append-only.
    expect_integrity_error(
        lambda: db.execute(
            "UPDATE occurrence SET original_name_text='changed' WHERE occurrence_id=1"
        ),
        "occurrence is append-only",
    )

    # Hash-chain continuity is enforced. SHA(JCS) itself is verified by application code.
    e1 = b'{"event":1}'
    e1_sha = sha(e1)
    db.execute(
        """INSERT INTO audit_event(
             event_seq,event_id,event_type,event_datetime,outcome,canonical_event_jcs,
             previous_event_sha256,current_event_sha256
           ) VALUES(1,'evt-1','ingest','2026-09-04T00:00:00Z','RECORDED',?,?,?)""",
        (e1, None, e1_sha),
    )
    e2 = b'{"event":2}'
    e2_sha = sha(e2)
    db.execute(
        """INSERT INTO audit_event(
             event_seq,event_id,event_type,event_datetime,outcome,canonical_event_jcs,
             previous_event_sha256,current_event_sha256
           ) VALUES(2,'evt-2','parse','2026-09-04T00:00:01Z','RECORDED',?,?,?)""",
        (e2, e1_sha, e2_sha),
    )
    db.execute(
        """INSERT INTO audit_event_link(event_seq,entity_kind,entity_id,role)
           VALUES(2,'parser_run',1,'created')"""
    )
    expect_integrity_error(
        lambda: db.execute(
            """INSERT INTO audit_event(
                 event_seq,event_id,event_type,event_datetime,outcome,canonical_event_jcs,
                 previous_event_sha256,current_event_sha256
               ) VALUES(3,'evt-3','parse','2026-09-04T00:00:02Z','RECORDED',?,?,?)""",
            (b"{}", "c" * 64, "d" * 64),
        ),
        "audit hash chain mismatch",
    )

    assert db.execute("PRAGMA foreign_key_check").fetchall() == []
    assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    print("authority_v1 synthetic qualification PASS")


if __name__ == "__main__":
    main()
