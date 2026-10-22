BEGIN;

CREATE TABLE alembic_version (
    version_num VARCHAR(32) NOT NULL,
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

-- Running upgrade  -> 0001_bootstrap

CREATE TABLE onion_sources (
    id UUID NOT NULL,
    canonical_url VARCHAR(255) NOT NULL,
    name VARCHAR(160) NOT NULL,
    description TEXT DEFAULT '' NOT NULL,
    category VARCHAR(60) DEFAULT 'UNKNOWN' NOT NULL,
    availability_status VARCHAR(40) DEFAULT 'NOT_CHECKED' NOT NULL,
    authorization_note TEXT NOT NULL,
    approved_for_collection BOOLEAN DEFAULT true NOT NULL,
    collection_enabled BOOLEAN DEFAULT false NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT uq_onion_sources_canonical_url UNIQUE (canonical_url)
);

CREATE INDEX ix_onion_sources_category ON onion_sources (category);

CREATE TABLE audit_logs (
    id UUID NOT NULL,
    actor VARCHAR(80) NOT NULL,
    action VARCHAR(80) NOT NULL,
    entity_type VARCHAR(60) NOT NULL,
    entity_id UUID NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (id)
);

CREATE INDEX ix_audit_logs_entity ON audit_logs (entity_type, entity_id);

INSERT INTO alembic_version (version_num) VALUES ('0001_bootstrap') RETURNING alembic_version.version_num;

COMMIT;
