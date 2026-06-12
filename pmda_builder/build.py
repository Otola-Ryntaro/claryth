"""Build a review-only clarithromycin interaction database from PMDA XML files."""

from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
import time

from .parser import (
    InteractionRow,
    clarithromycin_product_kind,
    matching_reverse_keyword,
    parse_xml_bytes,
)
from .schema import create_schema


BUILD_VERSION = "0.1.0"


def row_hash(row: InteractionRow) -> str:
    payload = "\x1f".join(
        (row.section, row.severity, row.drug_text, row.effect_text, row.mechanism_text)
    )
    return sha256(payload.encode("utf-8")).hexdigest()


def insert_document(connection: sqlite3.Connection, data: object) -> int:
    cursor = connection.execute(
        """INSERT INTO source_documents(
             sha256, package_insert_no, company_identifier, revision_date,
             brand_names_json, generic_names_json, active_ingredients_json,
             yj_codes_json, is_clarithromycin, parse_status, parse_error
           ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'parsed', NULL)""",
        (
            data.sha256,
            data.package_insert_no,
            data.company_identifier,
            data.revision_date,
            json.dumps(data.brand_names, ensure_ascii=False),
            json.dumps(data.generic_names, ensure_ascii=False),
            json.dumps(data.active_ingredients, ensure_ascii=False),
            json.dumps(data.yj_codes, ensure_ascii=False),
            int(data.is_clarithromycin),
        ),
    )
    return int(cursor.lastrowid)


def insert_parse_error(
    connection: sqlite3.Connection, digest: str, error: Exception
) -> int:
    cursor = connection.execute(
        """INSERT INTO source_documents(
             sha256, package_insert_no, company_identifier, revision_date,
             brand_names_json, generic_names_json, active_ingredients_json,
             yj_codes_json, is_clarithromycin, parse_status, parse_error
           ) VALUES (?, '', '', '', '[]', '[]', '[]', '[]', 0, 'error', ?)""",
        (digest, f"{type(error).__name__}: {error}"[:2000]),
    )
    return int(cursor.lastrowid)


def insert_primary_rows(
    connection: sqlite3.Connection,
    document_id: int,
    rows: tuple[InteractionRow, ...],
    candidate_scope: str,
) -> None:
    connection.executemany(
        """INSERT OR IGNORE INTO pmda_interaction_candidates(
             source_document_id, section, severity, raw_drug_text,
             raw_effect_text, raw_mechanism_text, content_hash, candidate_scope
           ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            (
                document_id,
                row.section,
                row.severity,
                row.drug_text,
                row.effect_text,
                row.mechanism_text,
                row_hash(row),
                candidate_scope,
            )
            for row in rows
        ],
    )


def insert_reverse_rows(
    connection: sqlite3.Connection, document_id: int, rows: tuple[InteractionRow, ...]
) -> None:
    values = []
    for row in rows:
        keyword = matching_reverse_keyword(row)
        if keyword:
            values.append(
                (
                    document_id,
                    row.section,
                    row.severity,
                    keyword,
                    row.drug_text,
                    row.effect_text,
                    row.mechanism_text,
                    row_hash(row),
                )
            )
    connection.executemany(
        """INSERT OR IGNORE INTO reverse_hits(
             source_document_id, section, severity, hit_keyword, raw_drug_text,
             raw_effect_text, raw_mechanism_text, content_hash
           ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        values,
    )


def build_database(
    source_root: Path,
    output_path: Path,
    dataset_date: str,
    progress_every: int = 500,
) -> dict[str, object]:
    started = time.perf_counter()
    xml_paths = sorted(source_root.rglob("*.xml"))
    if not xml_paths:
        raise ValueError(f"XMLファイルがありません: {source_root}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(output_path.suffix + ".tmp")
    temporary.unlink(missing_ok=True)

    seen: dict[str, int] = {}
    parsed_count = 0
    error_count = 0
    with closing(sqlite3.connect(temporary)) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = DELETE")
        create_schema(connection)
        for index, path in enumerate(xml_paths, start=1):
            content = path.read_bytes()
            digest = sha256(content).hexdigest()
            document_id = seen.get(digest)
            if document_id is None:
                try:
                    data = parse_xml_bytes(content)
                    document_id = insert_document(connection, data)
                    parsed_count += 1
                    if data.is_clarithromycin:
                        product_kind = clarithromycin_product_kind(data)
                        candidate_scope = (
                            "primary" if product_kind == "single_active" else "supplemental"
                        )
                        connection.execute(
                            """INSERT INTO clarithromycin_documents(
                                 document_id, identification_method, product_kind, candidate_scope
                               ) VALUES (?, ?, ?, ?)""",
                            (
                                document_id,
                                "generic_name_active_ingredient_or_known_brand",
                                product_kind,
                                candidate_scope,
                            ),
                        )
                        insert_primary_rows(
                            connection, document_id, data.interactions, candidate_scope
                        )
                    else:
                        insert_reverse_rows(connection, document_id, data.interactions)
                except Exception as error:
                    document_id = insert_parse_error(connection, digest, error)
                    error_count += 1
                seen[digest] = document_id
            connection.execute(
                "INSERT INTO source_files(document_id, relative_path) VALUES (?, ?)",
                (document_id, path.relative_to(source_root).as_posix()),
            )
            if index % progress_every == 0:
                connection.commit()
                elapsed = time.perf_counter() - started
                print(f"indexed {index}/{len(xml_paths)} XML files ({elapsed:.1f}s)", flush=True)

        checked_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        connection.execute(
            """INSERT INTO source_coverage(
                 source_name, dataset_date, scope, discovered_file_count,
                 unique_document_count, parsed_document_count, parse_error_count,
                 build_version, checked_at
               ) VALUES ('PMDA', ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                dataset_date,
                "all_local_prescription_xml; clarithromycin primary 10.1/10.2; direct reverse hits",
                len(xml_paths),
                len(seen),
                parsed_count,
                error_count,
                BUILD_VERSION,
                checked_at,
            ),
        )
        connection.commit()
        summary = database_summary(connection)

    output_path.unlink(missing_ok=True)
    temporary.replace(output_path)
    summary["elapsed_seconds"] = round(time.perf_counter() - started, 3)
    summary["output_path"] = str(output_path)
    return summary


def scalar(connection: sqlite3.Connection, query: str) -> int:
    return int(connection.execute(query).fetchone()[0])


def database_summary(connection: sqlite3.Connection) -> dict[str, object]:
    return {
        "source_file_count": scalar(connection, "SELECT COUNT(*) FROM source_files"),
        "unique_document_count": scalar(connection, "SELECT COUNT(*) FROM source_documents"),
        "parse_error_count": scalar(
            connection, "SELECT COUNT(*) FROM source_documents WHERE parse_status = 'error'"
        ),
        "clarithromycin_document_count": scalar(
            connection, "SELECT COUNT(*) FROM clarithromycin_documents"
        ),
        "primary_candidate_count": scalar(
            connection,
            "SELECT COUNT(*) FROM pmda_interaction_candidates WHERE candidate_scope = 'primary'",
        ),
        "supplemental_candidate_count": scalar(
            connection,
            "SELECT COUNT(*) FROM pmda_interaction_candidates WHERE candidate_scope = 'supplemental'",
        ),
        "combination_document_count": scalar(
            connection,
            "SELECT COUNT(*) FROM clarithromycin_documents WHERE product_kind = 'combination'",
        ),
        "consolidated_primary_count": scalar(
            connection, "SELECT COUNT(*) FROM consolidated_primary_candidates"
        ),
        "reverse_hit_count": scalar(connection, "SELECT COUNT(*) FROM reverse_hits"),
        "contraindicated_candidate_count": scalar(
            connection,
            """SELECT COUNT(*) FROM pmda_interaction_candidates
               WHERE severity = 'contraindicated' AND candidate_scope = 'primary'""",
        ),
        "caution_candidate_count": scalar(
            connection,
            """SELECT COUNT(*) FROM pmda_interaction_candidates
               WHERE severity = 'caution' AND candidate_scope = 'primary'""",
        ),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path("database"))
    parser.add_argument(
        "--output", type=Path, default=Path("backend/data/pmda_clarith.sqlite")
    )
    parser.add_argument("--dataset-date", default=datetime.now().date().isoformat())
    parser.add_argument("--progress-every", type=int, default=500)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    summary = build_database(
        args.source, args.output, args.dataset_date, progress_every=args.progress_every
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
