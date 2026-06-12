"""SQLite schema for source traceability and review-only interaction candidates."""

from __future__ import annotations

import sqlite3


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE source_documents (
  id INTEGER PRIMARY KEY,
  sha256 TEXT NOT NULL UNIQUE,
  package_insert_no TEXT,
  company_identifier TEXT,
  revision_date TEXT,
  brand_names_json TEXT NOT NULL,
  generic_names_json TEXT NOT NULL,
  active_ingredients_json TEXT NOT NULL,
  yj_codes_json TEXT NOT NULL,
  is_clarithromycin INTEGER NOT NULL DEFAULT 0,
  parse_status TEXT NOT NULL CHECK(parse_status IN ('parsed','error')),
  parse_error TEXT
);

CREATE TABLE source_files (
  id INTEGER PRIMARY KEY,
  document_id INTEGER NOT NULL REFERENCES source_documents(id),
  relative_path TEXT NOT NULL UNIQUE
);

CREATE TABLE clarithromycin_documents (
  document_id INTEGER PRIMARY KEY REFERENCES source_documents(id),
  identification_method TEXT NOT NULL,
  product_kind TEXT NOT NULL CHECK(product_kind IN ('single_active','combination')),
  candidate_scope TEXT NOT NULL CHECK(candidate_scope IN ('primary','supplemental'))
);

CREATE TABLE pmda_interaction_candidates (
  id INTEGER PRIMARY KEY,
  source_document_id INTEGER NOT NULL REFERENCES source_documents(id),
  section TEXT NOT NULL CHECK(section IN ('10.1','10.2')),
  severity TEXT NOT NULL CHECK(severity IN ('contraindicated','caution')),
  raw_drug_text TEXT NOT NULL,
  raw_effect_text TEXT,
  raw_mechanism_text TEXT,
  content_hash TEXT NOT NULL,
  candidate_scope TEXT NOT NULL CHECK(candidate_scope IN ('primary','supplemental')),
  extraction_status TEXT NOT NULL DEFAULT 'candidate'
    CHECK(extraction_status IN ('candidate','reviewed','rejected')),
  review_note TEXT,
  UNIQUE(source_document_id, section, content_hash)
);

CREATE TABLE reverse_hits (
  id INTEGER PRIMARY KEY,
  source_document_id INTEGER NOT NULL REFERENCES source_documents(id),
  section TEXT NOT NULL CHECK(section IN ('10.1','10.2')),
  severity TEXT NOT NULL CHECK(severity IN ('contraindicated','caution')),
  hit_keyword TEXT NOT NULL,
  raw_drug_text TEXT NOT NULL,
  raw_effect_text TEXT,
  raw_mechanism_text TEXT,
  content_hash TEXT NOT NULL,
  extraction_status TEXT NOT NULL DEFAULT 'candidate'
    CHECK(extraction_status IN ('candidate','reviewed','rejected')),
  review_note TEXT,
  UNIQUE(source_document_id, section, content_hash)
);

CREATE TABLE source_coverage (
  id INTEGER PRIMARY KEY,
  source_name TEXT NOT NULL,
  dataset_date TEXT NOT NULL,
  scope TEXT NOT NULL,
  discovered_file_count INTEGER NOT NULL,
  unique_document_count INTEGER NOT NULL,
  parsed_document_count INTEGER NOT NULL,
  parse_error_count INTEGER NOT NULL,
  build_version TEXT NOT NULL,
  checked_at TEXT NOT NULL
);

CREATE INDEX idx_candidates_severity ON pmda_interaction_candidates(severity);
CREATE INDEX idx_reverse_keyword ON reverse_hits(hit_keyword);
CREATE INDEX idx_source_clarith ON source_documents(is_clarithromycin);

CREATE VIEW consolidated_primary_candidates AS
SELECT
  severity,
  section,
  raw_drug_text,
  raw_effect_text,
  raw_mechanism_text,
  content_hash,
  COUNT(DISTINCT source_document_id) AS evidence_document_count,
  MAX(d.revision_date) AS latest_revision_date
FROM pmda_interaction_candidates c
JOIN source_documents d ON d.id = c.source_document_id
WHERE c.candidate_scope = 'primary'
GROUP BY severity, section, raw_drug_text, raw_effect_text, raw_mechanism_text, content_hash;
"""


def create_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(SCHEMA)
