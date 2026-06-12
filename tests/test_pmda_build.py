"""Integration tests for deduplication, primary extraction, and reverse hits."""

from contextlib import closing
from pathlib import Path
import sqlite3

from pmda_builder.build import build_database
from pmda_builder.export import export_review_artifacts
from pmda_builder.validate import validate_database


def test_builds_review_database_and_artifacts() -> None:
    test_root = Path(__file__).parent
    source = test_root / "fixtures" / "pmda_source"
    database = test_root / ".pmda_test.sqlite"
    artifacts = test_root / ".pmda_artifacts"
    generated_paths = [
        database,
        artifacts / "clarithromycin_documents.csv",
        artifacts / "primary_candidates.csv",
        artifacts / "primary_candidates_consolidated.csv",
        artifacts / "supplemental_combination_candidates.csv",
        artifacts / "reverse_hits.csv",
        artifacts / "summary.json",
    ]
    for path in generated_paths:
        path.unlink(missing_ok=True)

    try:
        summary = build_database(source, database, "2026-06-12", progress_every=100)
        assert summary["source_file_count"] == 3
        assert summary["unique_document_count"] == 2
        assert summary["clarithromycin_document_count"] == 1
        assert summary["primary_candidate_count"] == 2
        assert summary["reverse_hit_count"] == 1
        assert validate_database(database) == []

        export_review_artifacts(database, artifacts)
        assert (artifacts / "clarithromycin_documents.csv").exists()
        assert (artifacts / "primary_candidates.csv").exists()
        assert (artifacts / "reverse_hits.csv").exists()
        assert (artifacts / "summary.json").exists()

        with closing(sqlite3.connect(database)) as connection:
            assert connection.execute("SELECT COUNT(*) FROM source_files").fetchone()[0] == 3
    finally:
        for path in generated_paths:
            path.unlink(missing_ok=True)
