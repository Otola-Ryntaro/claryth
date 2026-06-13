"""Medical-review import and top-20 runtime promotion tests."""

from __future__ import annotations

import csv
from contextlib import closing
import json
from pathlib import Path
import shutil
import sqlite3
from uuid import uuid4

import pytest

from top20_builder.build import build_database
from top20_builder.review import (
    export_review_csv,
    generate_promotion_reports,
    import_review_csv,
    promote_reviewed_database,
    verify_approved_golden_results,
)


def workspace() -> Path:
    path = Path("tests") / f".top20-review-{uuid4().hex}"
    path.mkdir()
    return path


def read_review_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        return list(reader.fieldnames or []), list(reader)


def write_review_csv(path: Path, columns: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def approved_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    for row in rows:
        row["review_decision"] = (
            "reviewed" if row["raw_drug_text"] == "クラリスロマイシン" else "rejected"
        )
        row["reviewer"] = "薬剤師テスト"
        row["reviewed_at"] = "2026-06-13T00:00:00+09:00"
        row["approval_id"] = "APR-TEST-001"
        row["review_note"] = "fixture review"
    return rows


def test_version_one_database_migrates_without_approving_rows() -> None:
    directory = workspace()
    try:
        database = directory / "version1.sqlite"
        review_csv = directory / "review.csv"
        with closing(sqlite3.connect(database)) as connection:
            connection.executescript(
                """
                PRAGMA user_version = 1;
                CREATE TABLE documents (
                  id INTEGER PRIMARY KEY, sha256 TEXT NOT NULL, package_insert_no TEXT,
                  revision_date TEXT, brand_names_json TEXT NOT NULL,
                  generic_names_json TEXT NOT NULL, source_path TEXT NOT NULL
                );
                CREATE TABLE interactions (
                  id INTEGER PRIMARY KEY, document_id INTEGER NOT NULL,
                  section TEXT NOT NULL, severity TEXT NOT NULL,
                  raw_drug_text TEXT NOT NULL, raw_effect_text TEXT,
                  raw_mechanism_text TEXT
                );
                INSERT INTO documents VALUES (
                  1, 'doc-sha', 'TEST', '2026-06', '[]', '["試験薬"]', 'test.xml'
                );
                INSERT INTO interactions VALUES (
                  1, 1, '10.2', 'caution', '相手薬', '注意', '機序'
                );
                """
            )
        assert export_review_csv(database, review_csv) == 1
        with closing(sqlite3.connect(database)) as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute("SELECT * FROM interactions").fetchone()
            assert connection.execute("PRAGMA user_version").fetchone()[0] == 2
            assert row["review_status"] == "candidate"
            assert len(row["content_hash"]) == 64
    finally:
        shutil.rmtree(directory)


def test_review_import_requires_complete_untampered_approval_metadata() -> None:
    directory = workspace()
    try:
        database = directory / "candidate.sqlite"
        review_csv = directory / "review.csv"
        build_database(Path("tests/fixtures/pmda_source"), database, "2026-06-12")
        assert export_review_csv(database, review_csv) == 4
        columns, rows = read_review_csv(review_csv)

        write_review_csv(review_csv, columns, rows[:-1])
        with pytest.raises(ValueError, match="does not cover every candidate"):
            import_review_csv(database, review_csv)

        rows[0]["content_hash"] = "0" * 64
        write_review_csv(review_csv, columns, rows)
        with pytest.raises(ValueError, match="content hash mismatch"):
            import_review_csv(database, review_csv)

        _, rows = read_review_csv(directory / "review.csv")
        export_review_csv(database, review_csv)
        columns, rows = read_review_csv(review_csv)
        approved_rows(rows)
        rows[0]["approval_id"] = ""
        write_review_csv(review_csv, columns, rows)
        with pytest.raises(ValueError, match="review metadata is required"):
            import_review_csv(database, review_csv)
    finally:
        shutil.rmtree(directory)


def test_only_reviewed_rows_are_promoted_and_reports_are_generated() -> None:
    directory = workspace()
    try:
        candidate = directory / "candidate.sqlite"
        promoted = directory / "promoted.sqlite"
        review_csv = directory / "review.csv"
        reports = directory / "reports"
        seed = directory / "seed.json"
        build_database(Path("tests/fixtures/pmda_source"), candidate, "2026-06-12")

        with pytest.raises(ValueError, match="candidate row"):
            promote_reviewed_database(candidate, promoted)

        export_review_csv(candidate, review_csv)
        columns, rows = read_review_csv(review_csv)
        write_review_csv(review_csv, columns, approved_rows(rows))
        counts = import_review_csv(candidate, review_csv)
        assert counts == {"candidate": 0, "reviewed": 1, "rejected": 3}

        result = promote_reviewed_database(candidate, promoted)
        assert result["reviewed_count"] == 1
        assert result["rejected_count"] == 3
        with closing(sqlite3.connect(promoted)) as connection:
            assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            assert connection.execute("SELECT COUNT(*) FROM interactions").fetchone()[0] == 1
            assert connection.execute(
                "SELECT COUNT(*) FROM interactions WHERE review_status != 'reviewed'"
            ).fetchone()[0] == 0
            metadata = dict(connection.execute("SELECT key, value FROM metadata"))
            assert metadata["review_status"] == "clinically_reviewed"
            assert metadata["approval_id"] == '["APR-TEST-001"]'

        seed.write_text(
            json.dumps(
                {
                    "metadata": {},
                    "drugs": [
                        {
                            "id": "partner",
                            "display_name": "相手薬",
                            "generic_name": "相手薬",
                            "category": "ingredient",
                            "aliases": [],
                        }
                    ],
                    "interactions": [],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        report = generate_promotion_reports(promoted, seed, reports)
        assert report["mapping_count"] == 1
        assert report["unmatched_count"] == 0
        assert report["golden_result_count"] == 20
        draft_path = reports / "golden_results.draft.json"
        golden = json.loads(draft_path.read_text(encoding="utf-8"))
        clarith = next(
            item for item in golden["results"] if item["target_id"] == "clarithromycin"
        )
        assert clarith["expected_status"] == "contraindicated"
        golden["approval"] = {
            "reviewer": "薬剤師テスト",
            "reviewed_at": "2026-06-13T00:00:00+09:00",
            "approval_id": "GOLDEN-TEST-001",
        }
        approved_path = reports / "golden_results.approved.json"
        approved_path.write_text(
            json.dumps(golden, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        verified = verify_approved_golden_results(promoted, seed, approved_path)
        assert verified["result_count"] == 20

        golden["results"][0]["expected_status"] = "caution"
        approved_path.write_text(
            json.dumps(golden, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        with pytest.raises(ValueError, match="do not match every runtime result"):
            verify_approved_golden_results(promoted, seed, approved_path)

        with closing(sqlite3.connect(candidate)) as connection:
            connection.execute(
                "UPDATE interactions SET raw_drug_text = 'tampered' WHERE review_status = 'reviewed'"
            )
            connection.commit()
        with pytest.raises(ValueError, match="content hash mismatch"):
            promote_reviewed_database(candidate, directory / "tampered.sqlite")
    finally:
        shutil.rmtree(directory)
