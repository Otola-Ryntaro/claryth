"""SQLite schema for the generalized PMDA interaction index."""

import sqlite3


SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE documents (
  id INTEGER PRIMARY KEY,
  sha256 TEXT NOT NULL UNIQUE,
  package_insert_no TEXT,
  revision_date TEXT,
  brand_names_json TEXT NOT NULL,
  generic_names_json TEXT NOT NULL,
  source_path TEXT NOT NULL
);
CREATE TABLE drug_entities (
  id TEXT PRIMARY KEY,
  display_name TEXT NOT NULL,
  generic_name TEXT NOT NULL,
  category TEXT NOT NULL DEFAULT 'ingredient'
);
CREATE TABLE aliases (
  normalized_alias TEXT NOT NULL,
  alias TEXT NOT NULL,
  drug_id TEXT NOT NULL REFERENCES drug_entities(id),
  PRIMARY KEY(normalized_alias, drug_id)
);
CREATE TABLE entity_documents (
  drug_id TEXT NOT NULL REFERENCES drug_entities(id),
  document_id INTEGER NOT NULL REFERENCES documents(id),
  PRIMARY KEY(drug_id, document_id)
);
CREATE TABLE targets (
  id TEXT PRIMARY KEY,
  rank INTEGER NOT NULL UNIQUE,
  label TEXT NOT NULL,
  group_label TEXT NOT NULL,
  match_terms_json TEXT NOT NULL,
  is_default INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE target_documents (
  target_id TEXT NOT NULL REFERENCES targets(id),
  document_id INTEGER NOT NULL REFERENCES documents(id),
  PRIMARY KEY(target_id, document_id)
);
CREATE TABLE interactions (
  id INTEGER PRIMARY KEY,
  document_id INTEGER NOT NULL REFERENCES documents(id),
  section TEXT NOT NULL,
  severity TEXT NOT NULL,
  raw_drug_text TEXT NOT NULL,
  raw_effect_text TEXT,
  raw_mechanism_text TEXT
);
CREATE INDEX idx_aliases_normalized ON aliases(normalized_alias);
CREATE INDEX idx_entity_documents_drug ON entity_documents(drug_id);
CREATE INDEX idx_interactions_document ON interactions(document_id);
CREATE INDEX idx_target_documents_target ON target_documents(target_id);
"""


def create_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(SCHEMA)
