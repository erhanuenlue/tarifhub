-- tarifhub canonical schema (PostgreSQL 16 + pgvector).
-- Consolidated current-state view of the schema. Ordered changes live in
-- db/migrations/. The Python canonical model and the FastAPI serving layer map onto
-- these columns; they are a FROZEN contract — extend additively, never break.

CREATE EXTENSION IF NOT EXISTS vector;

-- Immutable, versioned, hashed tariff facts (the system of record).
CREATE TABLE IF NOT EXISTS tariff (
    id                       BIGINT        GENERATED ALWAYS AS IDENTITY,
    tariff_code              TEXT          NOT NULL,
    tariff_system            TEXT          NOT NULL
        CHECK (tariff_system IN ('TARDOC','EAL','SL','MiGeL','SwissDRG','TARPSY','ST_REHA')),
    designation_de           TEXT          NOT NULL,          -- canonical reference language
    designation_fr           TEXT,
    designation_it           TEXT,
    category                 TEXT,
    tax_points               NUMERIC(12,4) CHECK (tax_points  IS NULL OR tax_points  >= 0),
    price_chf                NUMERIC(12,2) CHECK (price_chf    IS NULL OR price_chf    >= 0),
    unit                     TEXT,
    valid_from               DATE,
    valid_to                 DATE,
    source_url               TEXT,
    source_version           TEXT,
    harmonization_confidence REAL          NOT NULL DEFAULT 0
        CHECK (harmonization_confidence >= 0 AND harmonization_confidence <= 1),
    requires_review          BOOLEAN       NOT NULL DEFAULT TRUE,
    metadata                 JSONB         NOT NULL DEFAULT '{}'::jsonb,
    embedding                vector(1024),                    -- multilingual-e5-large
    record_hash              TEXT          NOT NULL,
    version                  INTEGER       NOT NULL DEFAULT 1 CHECK (version >= 1),
    created_at               TIMESTAMPTZ   NOT NULL DEFAULT now(),
    PRIMARY KEY (id),
    CONSTRAINT uq_tariff_version UNIQUE (tariff_system, tariff_code, version),
    CONSTRAINT uq_tariff_hash    UNIQUE (record_hash),
    CONSTRAINT ck_valid_range    CHECK (valid_to IS NULL OR valid_from IS NULL OR valid_from <= valid_to)
);

CREATE INDEX IF NOT EXISTS ix_tariff_code   ON tariff (tariff_system, tariff_code);
CREATE INDEX IF NOT EXISTS ix_tariff_review ON tariff (requires_review);
-- Approximate nearest-neighbour index for semantic search (cosine distance).
CREATE INDEX IF NOT EXISTS ix_tariff_embedding
    ON tariff USING hnsw (embedding vector_cosine_ops);

-- Append-only audit / lineage log.
CREATE TABLE IF NOT EXISTS audit_log (
    id             BIGINT      GENERATED ALWAYS AS IDENTITY,
    event_time     TIMESTAMPTZ NOT NULL DEFAULT now(),
    event_type     TEXT        NOT NULL,
    tariff_system  TEXT,
    tariff_code    TEXT,
    record_hash    TEXT,
    source_file    TEXT,
    parser_version TEXT,
    confidence     REAL,
    validation_ok  BOOLEAN,
    detail         JSONB,
    PRIMARY KEY (id)
);

CREATE INDEX IF NOT EXISTS ix_audit_record ON audit_log (record_hash);
CREATE INDEX IF NOT EXISTS ix_audit_time   ON audit_log (event_time);
