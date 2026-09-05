-- MCR authority database schema v1.
-- Synthetic/control schema only. Real case data is forbidden in GitHub fixtures.

PRAGMA foreign_keys = ON;

CREATE TABLE schema_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
) STRICT;

INSERT INTO schema_meta(key, value) VALUES
    ('schema_name', 'mcr-authority-db'),
    ('schema_version', '1'),
    ('authority_rule', 'source-bytes-sha256; blob-dedup-does-not-collapse-occurrences');

CREATE TABLE blob_object (
    blob_id INTEGER PRIMARY KEY,
    sha256 TEXT NOT NULL UNIQUE
        CHECK(length(sha256) = 64)
        CHECK(sha256 = lower(sha256))
        CHECK(sha256 NOT GLOB '*[^0-9a-f]*'),
    size_bytes INTEGER NOT NULL CHECK(size_bytes >= 0),
    media_type TEXT CHECK(media_type IS NULL OR length(media_type) > 0)
) STRICT;

CREATE TABLE source_container (
    container_id INTEGER PRIMARY KEY,
    container_blob_id INTEGER NOT NULL REFERENCES blob_object(blob_id),
    container_kind TEXT NOT NULL CHECK(length(container_kind) > 0),
    note TEXT
) STRICT;

CREATE TABLE occurrence (
    occurrence_id INTEGER PRIMARY KEY,
    blob_id INTEGER NOT NULL REFERENCES blob_object(blob_id),
    source_container_id INTEGER REFERENCES source_container(container_id),
    ordinal INTEGER CHECK(ordinal IS NULL OR ordinal >= 0),
    byte_offset INTEGER CHECK(byte_offset IS NULL OR byte_offset >= 0),
    byte_length INTEGER CHECK(byte_length IS NULL OR byte_length >= 0),
    original_name_text TEXT,
    original_name_raw BLOB,
    locator_note TEXT,
    CHECK(
        (byte_offset IS NULL AND byte_length IS NULL)
        OR
        (byte_offset IS NOT NULL AND byte_length IS NOT NULL)
    )
) STRICT;

CREATE TRIGGER occurrence_range_within_container
BEFORE INSERT ON occurrence
WHEN NEW.source_container_id IS NOT NULL AND NEW.byte_offset IS NOT NULL
BEGIN
    SELECT CASE
        WHEN NEW.byte_offset > (
                 SELECT b.size_bytes
                 FROM source_container sc
                 JOIN blob_object b ON b.blob_id = sc.container_blob_id
                 WHERE sc.container_id = NEW.source_container_id
             )
          OR NEW.byte_length > (
                 SELECT b.size_bytes
                 FROM source_container sc
                 JOIN blob_object b ON b.blob_id = sc.container_blob_id
                 WHERE sc.container_id = NEW.source_container_id
             ) - NEW.byte_offset
        THEN RAISE(ABORT, 'occurrence byte range exceeds source container')
    END;
END;

CREATE TABLE derivative (
    derivative_id INTEGER PRIMARY KEY,
    source_occurrence_id INTEGER NOT NULL REFERENCES occurrence(occurrence_id),
    output_blob_id INTEGER NOT NULL REFERENCES blob_object(blob_id),
    derivative_kind TEXT NOT NULL CHECK(length(derivative_kind) > 0),
    tool_name TEXT NOT NULL CHECK(length(tool_name) > 0),
    tool_version TEXT NOT NULL CHECK(length(tool_version) > 0),
    parameters_jcs_sha256 TEXT
        CHECK(parameters_jcs_sha256 IS NULL OR (
            length(parameters_jcs_sha256) = 64
            AND parameters_jcs_sha256 = lower(parameters_jcs_sha256)
            AND parameters_jcs_sha256 NOT GLOB '*[^0-9a-f]*'
        )),
    note TEXT
) STRICT;

CREATE TABLE format_identification (
    identification_id INTEGER PRIMARY KEY,
    blob_id INTEGER NOT NULL REFERENCES blob_object(blob_id),
    tool_name TEXT NOT NULL CHECK(length(tool_name) > 0),
    tool_version TEXT NOT NULL CHECK(length(tool_version) > 0),
    signature_db_sha256 TEXT
        CHECK(signature_db_sha256 IS NULL OR (
            length(signature_db_sha256) = 64
            AND signature_db_sha256 = lower(signature_db_sha256)
            AND signature_db_sha256 NOT GLOB '*[^0-9a-f]*'
        )),
    pronom_puid TEXT,
    media_type TEXT,
    result_state TEXT NOT NULL CHECK(result_state IN ('IDENTIFIED','UNKNOWN','CONFLICT','ERROR')),
    detail TEXT
) STRICT;

CREATE TABLE parser_run (
    parser_run_id INTEGER PRIMARY KEY,
    source_occurrence_id INTEGER NOT NULL REFERENCES occurrence(occurrence_id),
    parser_name TEXT NOT NULL CHECK(length(parser_name) > 0),
    parser_version TEXT NOT NULL CHECK(length(parser_version) > 0),
    parser_mode TEXT NOT NULL CHECK(length(parser_mode) > 0),
    result_state TEXT NOT NULL CHECK(
        result_state IN ('PARSED','PARSED_WITH_WARNINGS','REJECTED','ERROR')
    ),
    warnings_jcs BLOB,
    output_record_jcs BLOB
) STRICT;

CREATE TABLE chronology (
    chronology_id INTEGER PRIMARY KEY,
    occurrence_id INTEGER NOT NULL REFERENCES occurrence(occurrence_id),
    raw_date_text TEXT NOT NULL,
    local_components_jcs BLOB,
    original_numeric_offset TEXT,
    zone_id TEXT,
    zone_source TEXT,
    utc_instant TEXT,
    ambiguity_flags_jcs BLOB,
    parser_name TEXT,
    parser_version TEXT,
    CHECK(utc_instant IS NULL OR length(utc_instant) > 0)
) STRICT;

CREATE TABLE risk_state (
    risk_state_id INTEGER PRIMARY KEY,
    occurrence_id INTEGER NOT NULL REFERENCES occurrence(occurrence_id),
    risk_family TEXT NOT NULL CHECK(length(risk_family) > 0),
    state_name TEXT NOT NULL CHECK(length(state_name) > 0),
    state_value TEXT NOT NULL,
    detector_name TEXT NOT NULL CHECK(length(detector_name) > 0),
    detector_version TEXT NOT NULL CHECK(length(detector_version) > 0),
    detail_jcs BLOB
) STRICT;

CREATE TABLE audit_event (
    event_seq INTEGER PRIMARY KEY CHECK(event_seq > 0),
    event_id TEXT NOT NULL UNIQUE CHECK(length(event_id) > 0),
    event_type TEXT NOT NULL CHECK(length(event_type) > 0),
    event_datetime TEXT NOT NULL CHECK(length(event_datetime) > 0),
    outcome TEXT NOT NULL CHECK(length(outcome) > 0),
    canonical_event_jcs BLOB NOT NULL,
    previous_event_sha256 TEXT,
    current_event_sha256 TEXT NOT NULL UNIQUE
        CHECK(length(current_event_sha256) = 64)
        CHECK(current_event_sha256 = lower(current_event_sha256))
        CHECK(current_event_sha256 NOT GLOB '*[^0-9a-f]*'),
    CHECK(previous_event_sha256 IS NULL OR (
        length(previous_event_sha256) = 64
        AND previous_event_sha256 = lower(previous_event_sha256)
        AND previous_event_sha256 NOT GLOB '*[^0-9a-f]*'
    ))
) STRICT;

CREATE TABLE audit_event_link (
    event_seq INTEGER NOT NULL REFERENCES audit_event(event_seq),
    entity_kind TEXT NOT NULL CHECK(
        entity_kind IN (
            'blob_object','source_container','occurrence','derivative',
            'format_identification','parser_run','chronology','risk_state'
        )
    ),
    entity_id INTEGER NOT NULL CHECK(entity_id > 0),
    role TEXT NOT NULL CHECK(length(role) > 0),
    PRIMARY KEY(event_seq, entity_kind, entity_id, role)
) STRICT;

CREATE TRIGGER audit_event_chain
BEFORE INSERT ON audit_event
BEGIN
    SELECT CASE
        WHEN NEW.event_seq = 1 AND NEW.previous_event_sha256 IS NOT NULL
        THEN RAISE(ABORT, 'first audit event must have null previous hash')
        WHEN NEW.event_seq > 1 AND NEW.previous_event_sha256 IS NULL
        THEN RAISE(ABORT, 'non-first audit event requires previous hash')
        WHEN NEW.event_seq > 1 AND (
            SELECT current_event_sha256
            FROM audit_event
            WHERE event_seq = NEW.event_seq - 1
        ) IS NULL
        THEN RAISE(ABORT, 'previous audit event missing')
        WHEN NEW.event_seq > 1 AND NEW.previous_event_sha256 != (
            SELECT current_event_sha256
            FROM audit_event
            WHERE event_seq = NEW.event_seq - 1
        )
        THEN RAISE(ABORT, 'audit hash chain mismatch')
    END;
END;

-- These records are append-only. Corrections/supersessions are represented by
-- new rows/events; source history is never silently rewritten.
CREATE TRIGGER schema_meta_no_update BEFORE UPDATE ON schema_meta
BEGIN SELECT RAISE(ABORT, 'schema_meta is append-only'); END;
CREATE TRIGGER schema_meta_no_delete BEFORE DELETE ON schema_meta
BEGIN SELECT RAISE(ABORT, 'schema_meta is append-only'); END;

CREATE TRIGGER blob_object_no_update BEFORE UPDATE ON blob_object
BEGIN SELECT RAISE(ABORT, 'blob_object is append-only'); END;
CREATE TRIGGER blob_object_no_delete BEFORE DELETE ON blob_object
BEGIN SELECT RAISE(ABORT, 'blob_object is append-only'); END;

CREATE TRIGGER source_container_no_update BEFORE UPDATE ON source_container
BEGIN SELECT RAISE(ABORT, 'source_container is append-only'); END;
CREATE TRIGGER source_container_no_delete BEFORE DELETE ON source_container
BEGIN SELECT RAISE(ABORT, 'source_container is append-only'); END;

CREATE TRIGGER occurrence_no_update BEFORE UPDATE ON occurrence
BEGIN SELECT RAISE(ABORT, 'occurrence is append-only'); END;
CREATE TRIGGER occurrence_no_delete BEFORE DELETE ON occurrence
BEGIN SELECT RAISE(ABORT, 'occurrence is append-only'); END;

CREATE TRIGGER derivative_no_update BEFORE UPDATE ON derivative
BEGIN SELECT RAISE(ABORT, 'derivative is append-only'); END;
CREATE TRIGGER derivative_no_delete BEFORE DELETE ON derivative
BEGIN SELECT RAISE(ABORT, 'derivative is append-only'); END;

CREATE TRIGGER format_identification_no_update BEFORE UPDATE ON format_identification
BEGIN SELECT RAISE(ABORT, 'format_identification is append-only'); END;
CREATE TRIGGER format_identification_no_delete BEFORE DELETE ON format_identification
BEGIN SELECT RAISE(ABORT, 'format_identification is append-only'); END;

CREATE TRIGGER parser_run_no_update BEFORE UPDATE ON parser_run
BEGIN SELECT RAISE(ABORT, 'parser_run is append-only'); END;
CREATE TRIGGER parser_run_no_delete BEFORE DELETE ON parser_run
BEGIN SELECT RAISE(ABORT, 'parser_run is append-only'); END;

CREATE TRIGGER chronology_no_update BEFORE UPDATE ON chronology
BEGIN SELECT RAISE(ABORT, 'chronology is append-only'); END;
CREATE TRIGGER chronology_no_delete BEFORE DELETE ON chronology
BEGIN SELECT RAISE(ABORT, 'chronology is append-only'); END;

CREATE TRIGGER risk_state_no_update BEFORE UPDATE ON risk_state
BEGIN SELECT RAISE(ABORT, 'risk_state is append-only'); END;
CREATE TRIGGER risk_state_no_delete BEFORE DELETE ON risk_state
BEGIN SELECT RAISE(ABORT, 'risk_state is append-only'); END;

CREATE TRIGGER audit_event_no_update BEFORE UPDATE ON audit_event
BEGIN SELECT RAISE(ABORT, 'audit_event is append-only'); END;
CREATE TRIGGER audit_event_no_delete BEFORE DELETE ON audit_event
BEGIN SELECT RAISE(ABORT, 'audit_event is append-only'); END;

CREATE TRIGGER audit_event_link_no_update BEFORE UPDATE ON audit_event_link
BEGIN SELECT RAISE(ABORT, 'audit_event_link is append-only'); END;
CREATE TRIGGER audit_event_link_no_delete BEFORE DELETE ON audit_event_link
BEGIN SELECT RAISE(ABORT, 'audit_event_link is append-only'); END;

CREATE INDEX occurrence_blob_idx ON occurrence(blob_id);
CREATE INDEX occurrence_container_idx ON occurrence(source_container_id);
CREATE INDEX derivative_source_idx ON derivative(source_occurrence_id);
CREATE INDEX derivative_output_idx ON derivative(output_blob_id);
CREATE INDEX format_identification_blob_idx ON format_identification(blob_id);
CREATE INDEX parser_run_occurrence_idx ON parser_run(source_occurrence_id);
CREATE INDEX chronology_occurrence_idx ON chronology(occurrence_id);
CREATE INDEX risk_state_occurrence_idx ON risk_state(occurrence_id);
CREATE INDEX audit_event_link_entity_idx ON audit_event_link(entity_kind, entity_id);
