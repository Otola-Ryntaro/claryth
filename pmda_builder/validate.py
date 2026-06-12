"""Validate referential integrity and expected PMDA extraction coverage."""

from __future__ import annotations

import argparse
from contextlib import closing
from pathlib import Path
import sqlite3


def validate_database(path: Path) -> list[str]:
    errors: list[str] = []
    with closing(sqlite3.connect(path)) as connection:
        foreign_keys = connection.execute("PRAGMA foreign_key_check").fetchall()
        if foreign_keys:
            errors.append(f"foreign key errors: {len(foreign_keys)}")
        checks = {
            "source documents": "SELECT COUNT(*) FROM source_documents",
            "clarithromycin documents": "SELECT COUNT(*) FROM clarithromycin_documents",
            "contraindicated candidates": "SELECT COUNT(*) FROM pmda_interaction_candidates WHERE severity='contraindicated' AND candidate_scope='primary'",
            "caution candidates": "SELECT COUNT(*) FROM pmda_interaction_candidates WHERE severity='caution' AND candidate_scope='primary'",
        }
        for label, query in checks.items():
            if connection.execute(query).fetchone()[0] == 0:
                errors.append(f"missing {label}")
        empty_drug = connection.execute(
            "SELECT COUNT(*) FROM pmda_interaction_candidates WHERE trim(raw_drug_text) = ''"
        ).fetchone()[0]
        if empty_drug:
            errors.append(f"empty drug text: {empty_drug}")
        coverage = connection.execute("SELECT COUNT(*) FROM source_coverage").fetchone()[0]
        if coverage != 1:
            errors.append(f"source coverage rows must be 1, got {coverage}")
    return errors


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database", type=Path, default=Path("backend/data/pmda_clarith.sqlite")
    )
    args = parser.parse_args()
    errors = validate_database(args.database)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        raise SystemExit(1)
    print("PMDA clarithromycin candidate database is valid")


if __name__ == "__main__":
    main()
