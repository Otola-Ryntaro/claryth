"""Export PMDA clarithromycin candidate data for medical review."""

from __future__ import annotations

import argparse
from contextlib import closing
import csv
import json
from pathlib import Path
import sqlite3

from .build import database_summary


def write_csv(path: Path, columns: list[str], rows: list[sqlite3.Row]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows({column: row[column] for column in columns} for row in rows)


def export_review_artifacts(database: Path, output_dir: Path) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(database)) as connection:
        connection.row_factory = sqlite3.Row
        document_rows = connection.execute(
            """SELECT d.id AS source_document_id, c.product_kind, c.candidate_scope,
                      d.package_insert_no, d.revision_date,
                      d.brand_names_json, d.generic_names_json, d.active_ingredients_json,
                      d.yj_codes_json, d.sha256, MIN(f.relative_path) AS source_path
               FROM clarithromycin_documents c
               JOIN source_documents d ON d.id = c.document_id
               JOIN source_files f ON f.document_id = d.id
               GROUP BY d.id ORDER BY d.revision_date DESC, d.package_insert_no"""
        ).fetchall()
        document_columns = list(document_rows[0].keys()) if document_rows else []
        if document_columns:
            write_csv(output_dir / "clarithromycin_documents.csv", document_columns, document_rows)

        primary_rows = connection.execute(
            """SELECT c.id AS candidate_id, c.severity, c.section, c.raw_drug_text,
                      c.raw_effect_text, c.raw_mechanism_text, c.extraction_status,
                      d.package_insert_no, d.revision_date, d.brand_names_json,
                      MIN(f.relative_path) AS source_path, d.sha256
               FROM pmda_interaction_candidates c
               JOIN source_documents d ON d.id = c.source_document_id
               JOIN source_files f ON f.document_id = d.id
               WHERE c.candidate_scope = 'primary'
               GROUP BY c.id ORDER BY c.severity, c.raw_drug_text, d.revision_date DESC"""
        ).fetchall()
        primary_columns = list(primary_rows[0].keys()) if primary_rows else []
        if primary_columns:
            write_csv(output_dir / "primary_candidates.csv", primary_columns, primary_rows)

        supplemental_rows = connection.execute(
            """SELECT c.id AS candidate_id, c.severity, c.section, c.raw_drug_text,
                      c.raw_effect_text, c.raw_mechanism_text, c.extraction_status,
                      d.package_insert_no, d.revision_date, d.brand_names_json,
                      MIN(f.relative_path) AS source_path, d.sha256
               FROM pmda_interaction_candidates c
               JOIN source_documents d ON d.id = c.source_document_id
               JOIN source_files f ON f.document_id = d.id
               WHERE c.candidate_scope = 'supplemental'
               GROUP BY c.id ORDER BY c.severity, c.raw_drug_text, d.revision_date DESC"""
        ).fetchall()
        supplemental_columns = list(supplemental_rows[0].keys()) if supplemental_rows else []
        if supplemental_columns:
            write_csv(
                output_dir / "supplemental_combination_candidates.csv",
                supplemental_columns,
                supplemental_rows,
            )

        consolidated_rows = connection.execute(
            """SELECT * FROM consolidated_primary_candidates
               ORDER BY severity, raw_drug_text"""
        ).fetchall()
        consolidated_columns = list(consolidated_rows[0].keys()) if consolidated_rows else []
        if consolidated_columns:
            write_csv(
                output_dir / "primary_candidates_consolidated.csv",
                consolidated_columns,
                consolidated_rows,
            )

        reverse_rows = connection.execute(
            """SELECT r.id AS reverse_hit_id, r.hit_keyword, r.severity, r.section,
                      r.raw_drug_text, r.raw_effect_text, r.raw_mechanism_text,
                      r.extraction_status, d.package_insert_no, d.revision_date,
                      d.brand_names_json, MIN(f.relative_path) AS source_path, d.sha256
               FROM reverse_hits r
               JOIN source_documents d ON d.id = r.source_document_id
               JOIN source_files f ON f.document_id = d.id
               GROUP BY r.id ORDER BY r.severity, d.brand_names_json"""
        ).fetchall()
        reverse_columns = list(reverse_rows[0].keys()) if reverse_rows else []
        if reverse_columns:
            write_csv(output_dir / "reverse_hits.csv", reverse_columns, reverse_rows)

        summary = database_summary(connection)
        coverage = connection.execute("SELECT * FROM source_coverage ORDER BY id DESC LIMIT 1").fetchone()
        summary["coverage"] = dict(coverage) if coverage else None
    (output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database", type=Path, default=Path("backend/data/pmda_clarith.sqlite")
    )
    parser.add_argument("--output", type=Path, default=Path("artifacts/pmda_clarith"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    summary = export_review_artifacts(args.database, args.output)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
