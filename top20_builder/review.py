"""Review import and fail-closed promotion for the PMDA top-20 database."""

from __future__ import annotations

from contextlib import closing
import csv
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from typing import Iterable

from backend.app.normalize import normalize_name


REVIEW_STATUSES = {"candidate", "reviewed", "rejected"}
REVIEW_COLUMNS = [
    "candidate_id",
    "content_hash",
    "review_decision",
    "reviewer",
    "reviewed_at",
    "approval_id",
    "review_note",
    "section",
    "severity",
    "raw_drug_text",
    "raw_effect_text",
    "raw_mechanism_text",
    "package_insert_no",
    "revision_date",
    "source_path",
    "document_sha256",
]


def _content_hash(document_sha256: str, row: sqlite3.Row) -> str:
    payload = "\x1f".join(
        (
            document_sha256,
            row["section"],
            row["severity"],
            row["raw_drug_text"],
            row["raw_effect_text"] or "",
            row["raw_mechanism_text"] or "",
        )
    )
    return sha256(payload.encode("utf-8")).hexdigest()


def ensure_review_schema(connection: sqlite3.Connection) -> None:
    """Migrate a version-1 extracted DB without approving any row."""
    connection.row_factory = sqlite3.Row
    columns = {row["name"] for row in connection.execute("PRAGMA table_info(interactions)")}
    additions = {
        "content_hash": "TEXT",
        "review_status": "TEXT NOT NULL DEFAULT 'candidate'",
        "reviewer": "TEXT",
        "reviewed_at": "TEXT",
        "approval_id": "TEXT",
        "review_note": "TEXT",
    }
    for name, declaration in additions.items():
        if name not in columns:
            connection.execute(f"ALTER TABLE interactions ADD COLUMN {name} {declaration}")
    rows = connection.execute(
        """SELECT i.*, d.sha256 AS document_sha256
           FROM interactions i JOIN documents d ON d.id = i.document_id
           WHERE i.content_hash IS NULL OR i.content_hash = ''"""
    ).fetchall()
    connection.executemany(
        "UPDATE interactions SET content_hash = ? WHERE id = ?",
        [(_content_hash(row["document_sha256"], row), row["id"]) for row in rows],
    )
    connection.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_interactions_content_hash ON interactions(content_hash)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_interactions_review_status ON interactions(review_status)"
    )
    connection.execute("PRAGMA user_version = 2")
    connection.commit()


def _csv_safe(value: object) -> object:
    if isinstance(value, str) and value.startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def export_review_csv(database: Path, output: Path) -> int:
    output.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(database)) as connection:
        connection.row_factory = sqlite3.Row
        ensure_review_schema(connection)
        rows = connection.execute(
            """SELECT i.id AS candidate_id, i.content_hash,
                      CASE WHEN i.review_status = 'candidate' THEN '' ELSE i.review_status END
                        AS review_decision,
                      COALESCE(i.reviewer, '') AS reviewer,
                      COALESCE(i.reviewed_at, '') AS reviewed_at,
                      COALESCE(i.approval_id, '') AS approval_id,
                      COALESCE(i.review_note, '') AS review_note,
                      i.section, i.severity, i.raw_drug_text,
                      COALESCE(i.raw_effect_text, '') AS raw_effect_text,
                      COALESCE(i.raw_mechanism_text, '') AS raw_mechanism_text,
                      COALESCE(d.package_insert_no, '') AS package_insert_no,
                      COALESCE(d.revision_date, '') AS revision_date,
                      d.source_path, d.sha256 AS document_sha256
               FROM interactions i JOIN documents d ON d.id = i.document_id
               ORDER BY d.source_path, i.section, i.id"""
        ).fetchall()
    with output.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=REVIEW_COLUMNS)
        writer.writeheader()
        writer.writerows(
            {column: _csv_safe(row[column]) for column in REVIEW_COLUMNS} for row in rows
        )
    return len(rows)


def _validated_reviewed_at(value: str) -> str:
    normalized = value.strip().replace("Z", "+00:00")
    try:
        reviewed_at = datetime.fromisoformat(normalized)
    except ValueError as error:
        raise ValueError(f"reviewed_at must be ISO 8601: {value}") from error
    if reviewed_at.tzinfo is None:
        raise ValueError("reviewed_at must include a timezone")
    reviewed_at = reviewed_at.astimezone(timezone.utc)
    if reviewed_at > datetime.now(timezone.utc):
        raise ValueError("reviewed_at must not be in the future")
    return reviewed_at.isoformat(timespec="seconds")


def import_review_csv(database: Path, review_csv: Path) -> dict[str, int]:
    if review_csv.stat().st_size > 256 * 1024 * 1024:
        raise ValueError("review CSV exceeds the 256 MiB limit")
    with review_csv.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames or not set(REVIEW_COLUMNS).issubset(reader.fieldnames):
            raise ValueError("review CSV columns are missing or incompatible")
        csv_rows = list(reader)

    with closing(sqlite3.connect(database)) as connection:
        connection.row_factory = sqlite3.Row
        ensure_review_schema(connection)
        database_rows = {
            int(row["id"]): row
            for row in connection.execute("SELECT id, content_hash FROM interactions")
        }
        seen: set[int] = set()
        updates: list[tuple[str, str | None, str | None, str | None, str | None, int]] = []
        counts = {status: 0 for status in REVIEW_STATUSES}
        for row in csv_rows:
            try:
                candidate_id = int(row["candidate_id"])
            except (TypeError, ValueError) as error:
                raise ValueError("candidate_id must be an integer") from error
            if candidate_id in seen:
                raise ValueError(f"duplicate candidate_id: {candidate_id}")
            seen.add(candidate_id)
            database_row = database_rows.get(candidate_id)
            if database_row is None:
                raise ValueError(f"unknown candidate_id: {candidate_id}")
            if row["content_hash"].strip() != database_row["content_hash"]:
                raise ValueError(f"content hash mismatch: {candidate_id}")
            decision = row["review_decision"].strip() or "candidate"
            if decision not in REVIEW_STATUSES:
                raise ValueError(f"invalid review decision for {candidate_id}: {decision}")
            reviewer = row["reviewer"].strip() or None
            reviewed_at = row["reviewed_at"].strip() or None
            approval_id = row["approval_id"].strip() or None
            note = row["review_note"].strip() or None
            if reviewer and (len(reviewer) > 200 or "\x00" in reviewer):
                raise ValueError(f"invalid reviewer for candidate {candidate_id}")
            if approval_id and (len(approval_id) > 200 or "\x00" in approval_id):
                raise ValueError(f"invalid approval_id for candidate {candidate_id}")
            if note and (len(note) > 2000 or "\x00" in note):
                raise ValueError(f"invalid review_note for candidate {candidate_id}")
            if decision in {"reviewed", "rejected"}:
                if not reviewer or not reviewed_at or not approval_id:
                    raise ValueError(
                        f"review metadata is required for {decision} candidate {candidate_id}"
                    )
                reviewed_at = _validated_reviewed_at(reviewed_at)
            else:
                reviewer = reviewed_at = approval_id = note = None
            updates.append((decision, reviewer, reviewed_at, approval_id, note, candidate_id))
            counts[decision] += 1
        if seen != set(database_rows):
            missing = sorted(set(database_rows) - seen)
            raise ValueError(f"review CSV does not cover every candidate; first missing ID: {missing[0]}")
        with connection:
            connection.executemany(
                """UPDATE interactions
                   SET review_status = ?, reviewer = ?, reviewed_at = ?,
                       approval_id = ?, review_note = ? WHERE id = ?""",
                updates,
            )
        return counts


def _metadata_upsert(connection: sqlite3.Connection, values: dict[str, str]) -> None:
    connection.executemany(
        "INSERT OR REPLACE INTO metadata(key, value) VALUES (?, ?)", values.items()
    )


def promote_reviewed_database(source: Path, output: Path) -> dict[str, object]:
    if source.resolve() == output.resolve():
        raise ValueError("promotion output must differ from the candidate database")
    with closing(sqlite3.connect(source)) as connection:
        connection.row_factory = sqlite3.Row
        ensure_review_schema(connection)
        source_sha256 = sha256(source.read_bytes()).hexdigest()
        for row in connection.execute(
            """SELECT i.*, d.sha256 AS document_sha256
               FROM interactions i JOIN documents d ON d.id = i.document_id"""
        ):
            if row["content_hash"] != _content_hash(row["document_sha256"], row):
                raise ValueError(f"promotion blocked: content hash mismatch for {row['id']}")
        counts = dict(
            connection.execute(
                "SELECT review_status, COUNT(*) FROM interactions GROUP BY review_status"
            )
        )
        candidate_count = int(counts.get("candidate", 0))
        if candidate_count:
            raise ValueError(f"promotion blocked: {candidate_count} candidate row(s) remain")
        incomplete = connection.execute(
            """SELECT id FROM interactions
               WHERE review_status IN ('reviewed','rejected')
                 AND (reviewer IS NULL OR reviewed_at IS NULL OR approval_id IS NULL)
               LIMIT 1"""
        ).fetchone()
        if incomplete:
            raise ValueError(f"promotion blocked: approval metadata missing for {incomplete['id']}")
        for row in connection.execute("SELECT DISTINCT reviewed_at FROM interactions"):
            _validated_reviewed_at(row[0])
        reviewers = sorted(
            row[0] for row in connection.execute("SELECT DISTINCT reviewer FROM interactions")
        )
        approval_ids = sorted(
            row[0] for row in connection.execute("SELECT DISTINCT approval_id FROM interactions")
        )
        reviewed_at = connection.execute("SELECT MAX(reviewed_at) FROM interactions").fetchone()[0]
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = output.with_suffix(output.suffix + ".tmp")
        temporary.unlink(missing_ok=True)
        with closing(sqlite3.connect(temporary)) as promoted:
            connection.backup(promoted)

    try:
        with closing(sqlite3.connect(temporary)) as promoted:
            with promoted:
                promoted.execute("DELETE FROM interactions WHERE review_status != 'reviewed'")
                _metadata_upsert(
                    promoted,
                    {
                        "review_status": "clinically_reviewed",
                        "reviewer": json.dumps(reviewers, ensure_ascii=False),
                        "reviewed_at": reviewed_at,
                        "approval_id": json.dumps(approval_ids, ensure_ascii=False),
                        "source_database_sha256": source_sha256,
                        "source_reviewed_count": str(counts.get("reviewed", 0)),
                        "source_rejected_count": str(counts.get("rejected", 0)),
                        "promoted_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    },
                )
                promoted.execute("PRAGMA user_version = 2")
            promoted.execute("VACUUM")
            integrity = promoted.execute("PRAGMA integrity_check").fetchone()[0]
            if integrity != "ok":
                raise ValueError(f"promoted database integrity failed: {integrity}")
            approved_count = promoted.execute("SELECT COUNT(*) FROM interactions").fetchone()[0]
        output.unlink(missing_ok=True)
        temporary.replace(output)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return {
        "review_status": "clinically_reviewed",
        "source_sha256": source_sha256,
        "reviewed_count": approved_count,
        "rejected_count": int(counts.get("rejected", 0)),
        "reviewers": reviewers,
        "approval_ids": approval_ids,
        "reviewed_at": reviewed_at,
        "output": str(output),
    }


def _ingredient_drugs(seed: dict[str, object]) -> Iterable[dict[str, object]]:
    return (drug for drug in seed["drugs"] if drug["category"] == "ingredient")


def _seed_terms(drug: dict[str, object]) -> set[str]:
    values = [drug["display_name"], drug.get("generic_name") or "", *drug.get("aliases", [])]
    return {term for value in values if (term := normalize_name(str(value)))}


def _entity_ids(connection: sqlite3.Connection, terms: set[str]) -> list[str]:
    if not terms:
        return []
    placeholders = ",".join("?" for _ in terms)
    return [
        row[0]
        for row in connection.execute(
            f"SELECT DISTINCT drug_id FROM aliases WHERE normalized_alias IN ({placeholders})",
            sorted(terms),
        )
    ]


def _severity(connection: sqlite3.Connection, drug: dict[str, object], target_id: str) -> str:
    target = connection.execute("SELECT * FROM targets WHERE id = ?", (target_id,)).fetchone()
    if target is None:
        raise ValueError(f"unknown target: {target_id}")
    exact_input_terms = _seed_terms(drug)
    input_terms = {term for term in exact_input_terms if len(term) >= 4}
    target_terms = {
        term
        for value in json.loads(target["match_terms_json"])
        if len(term := normalize_name(value)) >= 4
    }
    evidence: list[sqlite3.Row] = []
    for row in connection.execute(
        """SELECT i.* FROM interactions i
           JOIN target_documents td ON td.document_id = i.document_id
           WHERE td.target_id = ?""",
        (target_id,),
    ):
        if any(term in normalize_name(row["raw_drug_text"]) for term in input_terms):
            evidence.append(row)
    for entity_id in _entity_ids(connection, exact_input_terms):
        for row in connection.execute(
            """SELECT i.*, d.generic_names_json FROM interactions i
               JOIN documents d ON d.id = i.document_id
               JOIN entity_documents ed ON ed.document_id = d.id
               WHERE ed.drug_id = ?""",
            (entity_id,),
        ):
            if len(json.loads(row["generic_names_json"])) == 1 and any(
                term in normalize_name(row["raw_drug_text"]) for term in target_terms
            ):
                evidence.append(row)
    if any(row["severity"] == "contraindicated" for row in evidence):
        return "contraindicated"
    if evidence:
        return "caution"
    return "not_listed"


def _golden_results(
    connection: sqlite3.Connection, seed: dict[str, object]
) -> list[dict[str, str]]:
    targets = list(connection.execute("SELECT id, label FROM targets ORDER BY rank"))
    return [
        {
            "target_id": target["id"],
            "target_name": target["label"],
            "drug_id": drug["id"],
            "drug_name": drug["display_name"],
            "expected_status": _severity(connection, drug, target["id"]),
        }
        for drug in _ingredient_drugs(seed)
        for target in targets
    ]


def verify_approved_golden_results(
    database: Path, seed_path: Path, golden_path: Path
) -> dict[str, object]:
    payload = json.loads(golden_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise ValueError("approved golden results have an unsupported schema")
    database_sha256 = sha256(database.read_bytes()).hexdigest()
    if payload.get("database_sha256") != database_sha256:
        raise ValueError("approved golden results do not match the runtime database")
    approval = payload.get("approval")
    if not isinstance(approval, dict) or not all(
        isinstance(approval.get(key), str) and approval[key].strip()
        for key in ("reviewer", "reviewed_at", "approval_id")
    ):
        raise ValueError("approved golden results require reviewer, reviewed_at, and approval_id")
    _validated_reviewed_at(approval["reviewed_at"])
    seed = json.loads(seed_path.read_text(encoding="utf-8"))
    with closing(sqlite3.connect(database)) as connection:
        connection.row_factory = sqlite3.Row
        actual = _golden_results(connection, seed)
    expected = payload.get("results")
    if not isinstance(expected, list) or expected != actual:
        raise ValueError("approved golden results do not match every runtime result")
    return {
        "database_sha256": database_sha256,
        "result_count": len(actual),
        "reviewer": approval["reviewer"],
        "reviewed_at": approval["reviewed_at"],
        "approval_id": approval["approval_id"],
    }


def generate_promotion_reports(
    database: Path, seed_path: Path, output_dir: Path
) -> dict[str, object]:
    seed = json.loads(seed_path.read_text(encoding="utf-8"))
    output_dir.mkdir(parents=True, exist_ok=True)
    manual = {
        item["ingredient_id"]: item["severity"]
        for item in seed["interactions"]
        if item.get("verified")
    }
    with closing(sqlite3.connect(database)) as connection:
        connection.row_factory = sqlite3.Row
        targets = list(connection.execute("SELECT id, label FROM targets ORDER BY rank"))
        mapping_rows = []
        diff_rows = []
        golden = _golden_results(connection, seed)
        for drug in _ingredient_drugs(seed):
            terms = _seed_terms(drug)
            entity_ids = _entity_ids(connection, terms)
            entity_names = [
                row[0]
                for entity_id in entity_ids
                for row in connection.execute(
                    "SELECT generic_name FROM drug_entities WHERE id = ?", (entity_id,)
                )
            ]
            mapping_rows.append(
                {
                    "runtime_drug_id": drug["id"],
                    "display_name": drug["display_name"],
                    "generic_name": drug.get("generic_name") or "",
                    "normalized_terms": " | ".join(sorted(terms)),
                    "pmda_entity_ids": " | ".join(entity_ids),
                    "pmda_entity_names": " | ".join(entity_names),
                    "mapping_status": (
                        "unmatched" if not entity_ids else "exact" if len(entity_ids) == 1 else "ambiguous"
                    ),
                }
            )
            status = _severity(connection, drug, "clarithromycin")
            manual_status = manual.get(drug["id"], "not_listed")
            diff_rows.append(
                {
                    "drug_id": drug["id"],
                    "drug_name": drug["display_name"],
                    "manual_seed_status": manual_status,
                    "promoted_pmda_status": status,
                    "differs": str(manual_status != status).lower(),
                }
            )

        for filename, columns, rows in (
            (
                "drug_master_mapping.csv",
                [
                    "runtime_drug_id",
                    "display_name",
                    "generic_name",
                    "normalized_terms",
                    "pmda_entity_ids",
                    "pmda_entity_names",
                    "mapping_status",
                ],
                mapping_rows,
            ),
            (
                "manual_seed_diff.csv",
                [
                    "drug_id",
                    "drug_name",
                    "manual_seed_status",
                    "promoted_pmda_status",
                    "differs",
                ],
                diff_rows,
            ),
        ):
            with (output_dir / filename).open("w", encoding="utf-8-sig", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=columns)
                writer.writeheader()
                writer.writerows(
                    {key: _csv_safe(value) for key, value in row.items()} for row in rows
                )
        (output_dir / "golden_results.draft.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "database_sha256": sha256(database.read_bytes()).hexdigest(),
                    "approval": {"reviewer": "", "reviewed_at": "", "approval_id": ""},
                    "results": golden,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        summary = {
            "mapping_count": len(mapping_rows),
            "unmatched_count": sum(row["mapping_status"] == "unmatched" for row in mapping_rows),
            "ambiguous_count": sum(row["mapping_status"] == "ambiguous" for row in mapping_rows),
            "manual_seed_difference_count": sum(row["differs"] == "true" for row in diff_rows),
            "golden_result_count": len(golden),
        }
        (output_dir / "promotion_report.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        return summary
