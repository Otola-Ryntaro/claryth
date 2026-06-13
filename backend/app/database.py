"""SQLite schema, seed loading, and read-only query helpers."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .config import settings
from .normalize import normalize_name


SCHEMA = """
PRAGMA user_version = 1;
CREATE TABLE IF NOT EXISTS metadata (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS drugs (
  id TEXT PRIMARY KEY,
  display_name TEXT NOT NULL,
  generic_name TEXT,
  category TEXT NOT NULL CHECK(category IN ('prescription','otc','ingredient'))
);
CREATE TABLE IF NOT EXISTS aliases (
  normalized_alias TEXT NOT NULL,
  alias TEXT NOT NULL,
  drug_id TEXT NOT NULL REFERENCES drugs(id),
  PRIMARY KEY(normalized_alias, drug_id)
);
CREATE INDEX IF NOT EXISTS idx_alias_normalized ON aliases(normalized_alias);
CREATE TABLE IF NOT EXISTS product_ingredients (
  product_id TEXT NOT NULL REFERENCES drugs(id),
  ingredient_id TEXT NOT NULL REFERENCES drugs(id),
  PRIMARY KEY(product_id, ingredient_id)
);
CREATE TABLE IF NOT EXISTS interactions (
  ingredient_id TEXT PRIMARY KEY REFERENCES drugs(id),
  severity TEXT NOT NULL CHECK(severity IN ('contraindicated','caution')),
  effect TEXT NOT NULL,
  mechanism TEXT NOT NULL,
  action TEXT NOT NULL,
  source_url TEXT NOT NULL,
  source_revision TEXT NOT NULL,
  verified INTEGER NOT NULL DEFAULT 0
);
"""


@contextmanager
def connect(path: Path | None = None) -> Iterator[sqlite3.Connection]:
    db_path = path or settings.database_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        yield connection
    finally:
        connection.close()


def initialize_database(path: Path | None = None, seed_path: Path | None = None) -> None:
    target = path or settings.database_path
    seed_file = seed_path or settings.seed_path
    payload = json.loads(seed_file.read_text(encoding="utf-8"))
    with connect(target) as connection:
        connection.executescript(SCHEMA)
        for table in ("interactions", "product_ingredients", "aliases", "drugs", "metadata"):
            connection.execute(f"DELETE FROM {table}")
        connection.executemany(
            "INSERT INTO metadata(key, value) VALUES (?, ?)",
            list(payload["metadata"].items()),
        )
        for drug in payload["drugs"]:
            connection.execute(
                "INSERT INTO drugs(id, display_name, generic_name, category) VALUES (?, ?, ?, ?)",
                (drug["id"], drug["display_name"], drug.get("generic_name"), drug["category"]),
            )
            aliases = set(drug.get("aliases", [])) | {drug["display_name"]}
            if drug.get("generic_name"):
                aliases.add(drug["generic_name"])
            connection.executemany(
                "INSERT OR IGNORE INTO aliases(normalized_alias, alias, drug_id) VALUES (?, ?, ?)",
                [(normalize_name(alias), alias, drug["id"]) for alias in aliases],
            )
            connection.executemany(
                "INSERT INTO product_ingredients(product_id, ingredient_id) VALUES (?, ?)",
                [(drug["id"], ingredient_id) for ingredient_id in drug.get("ingredients", [])],
            )
        connection.executemany(
            """INSERT INTO interactions(
                 ingredient_id, severity, effect, mechanism, action,
                 source_url, source_revision, verified
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                (
                    item["ingredient_id"], item["severity"], item["effect"],
                    item["mechanism"], item["action"], item["source_url"],
                    item["source_revision"], int(item.get("verified", False)),
                )
                for item in payload["interactions"]
            ],
        )
        connection.commit()


def ensure_database() -> None:
    if not settings.database_path.exists():
        initialize_database()


def metadata(connection: sqlite3.Connection) -> dict[str, str]:
    return {row["key"]: row["value"] for row in connection.execute("SELECT key, value FROM metadata")}
