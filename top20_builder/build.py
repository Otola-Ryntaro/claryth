"""Build the generalized top-20 interaction database from local PMDA XML."""

from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import re
import sqlite3
import time

from backend.app.normalize import normalize_name
from pmda_builder.parser import parse_xml_bytes
from .schema import create_schema
from .targets import DEFAULT_TARGET_ID, TARGETS


LATIN_SUFFIX = re.compile(r"(?<=[ぁ-んァ-ヶ一-龠々])\s*[A-Za-z].*$")


def japanese_name(value: str) -> str:
    return LATIN_SUFFIX.sub("", value).strip() or value.strip()


def entity_id(generic_name: str) -> str:
    digest = sha256(normalize_name(generic_name).encode("utf-8")).hexdigest()[:16]
    return f"pmda:{digest}"


def interaction_hash(document_sha256: str, row: object) -> str:
    payload = "\x1f".join(
        (
            document_sha256,
            row.section,
            row.severity,
            row.drug_text,
            row.effect_text,
            row.mechanism_text,
        )
    )
    return sha256(payload.encode("utf-8")).hexdigest()


def build_database(source_root: Path, output_path: Path, dataset_date: str, progress_every: int = 1000) -> dict[str, object]:
    started = time.perf_counter()
    paths = sorted(source_root.rglob("*.xml"))
    if not paths:
        raise ValueError(f"XMLファイルがありません: {source_root}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(output_path.suffix + ".tmp")
    temporary.unlink(missing_ok=True)
    seen: set[str] = set()
    errors = 0
    with closing(sqlite3.connect(temporary)) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = DELETE")
        create_schema(connection)
        connection.executemany(
            "INSERT INTO targets(id, rank, label, group_label, match_terms_json, is_default) VALUES (?, ?, ?, ?, ?, ?)",
            [
                (target.id, target.rank, target.label, target.group_label, json.dumps(target.match_terms, ensure_ascii=False), int(target.id == DEFAULT_TARGET_ID))
                for target in TARGETS
            ],
        )
        for index, path in enumerate(paths, start=1):
            content = path.read_bytes()
            digest = sha256(content).hexdigest()
            if digest in seen:
                continue
            seen.add(digest)
            try:
                data = parse_xml_bytes(content)
            except Exception:
                errors += 1
                continue
            cursor = connection.execute(
                """INSERT INTO documents(
                     sha256, package_insert_no, revision_date, brand_names_json,
                     generic_names_json, source_path
                   ) VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    digest,
                    data.package_insert_no,
                    data.revision_date,
                    json.dumps(data.brand_names, ensure_ascii=False),
                    json.dumps(data.generic_names, ensure_ascii=False),
                    path.relative_to(source_root).as_posix(),
                ),
            )
            document_id = int(cursor.lastrowid)
            generic_names = tuple(dict.fromkeys(japanese_name(name) for name in data.generic_names if name.strip()))
            for generic_name in generic_names:
                drug_id = entity_id(generic_name)
                connection.execute(
                    "INSERT OR IGNORE INTO drug_entities(id, display_name, generic_name) VALUES (?, ?, ?)",
                    (drug_id, generic_name, generic_name),
                )
                connection.execute(
                    "INSERT OR IGNORE INTO entity_documents(drug_id, document_id) VALUES (?, ?)",
                    (drug_id, document_id),
                )
                aliases = {generic_name, *data.brand_names}
                connection.executemany(
                    "INSERT OR IGNORE INTO aliases(normalized_alias, alias, drug_id) VALUES (?, ?, ?)",
                    [(normalize_name(alias), alias, drug_id) for alias in aliases if normalize_name(alias)],
                )
            connection.executemany(
                """INSERT INTO interactions(
                     document_id, content_hash, section, severity, raw_drug_text,
                     raw_effect_text, raw_mechanism_text
                   ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                [
                    (
                        document_id,
                        interaction_hash(digest, row),
                        row.section,
                        row.severity,
                        row.drug_text,
                        row.effect_text,
                        row.mechanism_text,
                    )
                    for row in data.interactions
                ],
            )
            if len(generic_names) == 1:
                identity = "\n".join((*generic_names, *data.brand_names))
                for target in TARGETS:
                    excluded = any(
                        term in brand
                        for brand in data.brand_names
                        for term in target.excluded_brand_terms
                    )
                    if not excluded and any(term in identity for term in target.document_terms):
                        connection.execute(
                            "INSERT OR IGNORE INTO target_documents(target_id, document_id) VALUES (?, ?)",
                            (target.id, document_id),
                        )
            if index % progress_every == 0:
                connection.commit()
                print(f"indexed {index}/{len(paths)} XML files", flush=True)
        metadata = {
            "dataset_date": dataset_date,
            "build_version": "0.1.0",
            "source_file_count": str(len(paths)),
            "unique_document_count": str(len(seen)),
            "parse_error_count": str(errors),
            "review_status": "pmda_extracted_review_required",
            "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        connection.executemany("INSERT INTO metadata(key, value) VALUES (?, ?)", metadata.items())
        connection.commit()
        summary = {
            **metadata,
            "drug_entity_count": connection.execute("SELECT COUNT(*) FROM drug_entities").fetchone()[0],
            "alias_count": connection.execute("SELECT COUNT(*) FROM aliases").fetchone()[0],
            "interaction_count": connection.execute("SELECT COUNT(*) FROM interactions").fetchone()[0],
            "target_document_counts": dict(connection.execute("SELECT target_id, COUNT(*) FROM target_documents GROUP BY target_id")),
        }
    output_path.unlink(missing_ok=True)
    temporary.replace(output_path)
    summary["elapsed_seconds"] = round(time.perf_counter() - started, 3)
    summary["output_path"] = str(output_path)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path("database"))
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("backend/data/top20_interactions.candidate.sqlite"),
    )
    parser.add_argument("--dataset-date", default=datetime.now().date().isoformat())
    parser.add_argument("--progress-every", type=int, default=1000)
    args = parser.parse_args()
    print(json.dumps(build_database(args.source, args.output, args.dataset_date, args.progress_every), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
