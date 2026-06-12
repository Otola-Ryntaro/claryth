"""Runtime access and conservative direct-name matching for the PMDA top 20."""

from __future__ import annotations

from contextlib import contextmanager
from functools import lru_cache
import json
from pathlib import Path
import sqlite3
from typing import Iterator

from rapidfuzz import fuzz, process

from .checker import SEVERITY_RANK
from .config import settings
from .models import CheckResult, DrugCandidate, IngredientResult, TargetDrug
from .normalize import normalize_name


PMDA_PDF_BASE = "https://www.pmda.go.jp/PmdaSearch/iyakuDetail/ResultDataSetPDF"
LOCAL_API_BASE = f"http://{settings.api_host}:{settings.api_port}"


def available() -> bool:
    return settings.top20_database_path.exists()


@contextmanager
def connect_top20(path: Path | None = None) -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(path or settings.top20_database_path)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
    finally:
        connection.close()


def list_targets() -> list[TargetDrug]:
    if not available():
        return []
    with connect_top20() as connection:
        return [
            TargetDrug(
                id=row["id"],
                rank=row["rank"],
                label=row["label"],
                group_label=row["group_label"],
                is_default=bool(row["is_default"]),
            )
            for row in connection.execute("SELECT * FROM targets ORDER BY rank")
        ]


def metadata() -> dict[str, str]:
    if not available():
        return {}
    with connect_top20() as connection:
        return dict(connection.execute("SELECT key, value FROM metadata"))


def _candidate(row: sqlite3.Row, score: float) -> DrugCandidate:
    return DrugCandidate(
        drug_id=row["id"],
        display_name=row["display_name"],
        generic_name=row["generic_name"],
        category="ingredient",
        score=round(score, 1),
    )


def _pmda_pdf_url(source_path: str) -> str:
    return f"{PMDA_PDF_BASE}/{Path(source_path).stem}"


def evidence(interaction_id: int, target_id: str) -> dict[str, str | int]:
    if not available():
        raise RuntimeError("トップ20 PMDAデータベースがありません")
    with connect_top20() as connection:
        row = connection.execute(
            """SELECT i.*, d.revision_date, d.package_insert_no, d.source_path,
                      d.brand_names_json, d.generic_names_json
               FROM interactions i JOIN documents d ON d.id = i.document_id
               WHERE i.id = ?""",
            (interaction_id,),
        ).fetchone()
        target = connection.execute("SELECT * FROM targets WHERE id = ?", (target_id,)).fetchone()
        if row is None:
            raise KeyError(interaction_id)
        if target is None:
            raise KeyError(target_id)
        is_target_document = connection.execute(
            "SELECT 1 FROM target_documents WHERE target_id = ? AND document_id = ?",
            (target_id, row["document_id"]),
        ).fetchone()
        document_names = json.loads(row["brand_names_json"]) or json.loads(row["generic_names_json"])
        document_name = " / ".join(document_names) or "電子添文記載薬"
        if is_target_document:
            pair = f"{target['label']} × {row['raw_drug_text']}"
        else:
            pair = f"{document_name} × {target['label']}"
        return {
            "interaction_id": interaction_id,
            "pair": pair,
            "document_name": document_name,
            "section": row["section"],
            "severity": row["severity"],
            "drug_text": row["raw_drug_text"],
            "effect": row["raw_effect_text"] or "記載なし",
            "mechanism": row["raw_mechanism_text"] or "記載なし",
            "revision_date": row["revision_date"] or "不明",
            "package_insert_no": row["package_insert_no"] or "不明",
            "pdf_url": _pmda_pdf_url(row["source_path"]),
        }


def exact_candidates(normalized: str) -> list[DrugCandidate]:
    if not available():
        return []
    with connect_top20() as connection:
        rows = connection.execute(
            """SELECT DISTINCT d.* FROM aliases a
               JOIN drug_entities d ON d.id = a.drug_id
               WHERE a.normalized_alias = ? ORDER BY d.display_name""",
            (normalized,),
        ).fetchall()
    return [_candidate(row, 100) for row in rows]


def fuzzy_candidates(normalized: str, limit: int, threshold: float) -> list[DrugCandidate]:
    if not available():
        return []
    alias_map = _alias_index()
    matches = process.extract(
        normalized,
        alias_map.keys(),
        scorer=fuzz.WRatio,
        limit=limit * 2,
        score_cutoff=threshold,
    )
    candidates: dict[str, DrugCandidate] = {}
    for alias, score, _ in matches:
        for drug_id, display_name, generic_name in alias_map[alias]:
            current = candidates.get(drug_id)
            if current is None or score > current.score:
                candidates[drug_id] = DrugCandidate(
                    drug_id=drug_id,
                    display_name=display_name,
                    generic_name=generic_name,
                    category="ingredient",
                    score=round(score, 1),
                )
    return sorted(candidates.values(), key=lambda item: (-item.score, item.display_name))[:limit]


@lru_cache(maxsize=1)
def _alias_index() -> dict[str, tuple[tuple[str, str, str], ...]]:
    with connect_top20() as connection:
        rows = connection.execute(
            """SELECT a.normalized_alias, d.id, d.display_name, d.generic_name
               FROM aliases a JOIN drug_entities d ON d.id = a.drug_id"""
        ).fetchall()
    values: dict[str, list[tuple[str, str, str]]] = {}
    for row in rows:
        values.setdefault(row["normalized_alias"], []).append(
            (row["id"], row["display_name"], row["generic_name"])
        )
    return {key: tuple(items) for key, items in values.items()}


def _entity_ids_for_runtime_drug(runtime: sqlite3.Connection, drug_id: str) -> tuple[list[str], sqlite3.Row]:
    drug = runtime.execute("SELECT * FROM drugs WHERE id = ?", (drug_id,)).fetchone()
    if drug is None:
        raise KeyError(drug_id)
    ingredients = runtime.execute(
        """SELECT d.* FROM product_ingredients pi
           JOIN drugs d ON d.id = pi.ingredient_id WHERE pi.product_id = ?""",
        (drug_id,),
    ).fetchall() or [drug]
    entity_ids: list[str] = []
    with connect_top20() as top20:
        for ingredient in ingredients:
            normalized = normalize_name(ingredient["generic_name"] or ingredient["display_name"])
            entity_ids.extend(
                row[0]
                for row in top20.execute(
                    "SELECT DISTINCT drug_id FROM aliases WHERE normalized_alias = ?",
                    (normalized,),
                )
            )
    return list(dict.fromkeys(entity_ids)), drug


def _entity_ids(runtime: sqlite3.Connection, drug_id: str) -> tuple[list[str], sqlite3.Row | None]:
    if drug_id.startswith("pmda:"):
        return [drug_id], None
    return _entity_ids_for_runtime_drug(runtime, drug_id)


def _normalized_terms(values: list[str]) -> set[str]:
    return {term for value in values if len(term := normalize_name(value)) >= 4}


def _matching_evidence(connection: sqlite3.Connection, target_id: str, entity_id: str) -> list[sqlite3.Row]:
    target = connection.execute("SELECT * FROM targets WHERE id = ?", (target_id,)).fetchone()
    if target is None:
        raise KeyError(target_id)
    aliases = [
        row[0]
        for row in connection.execute(
            "SELECT alias FROM aliases WHERE drug_id = ?",
            (entity_id,),
        )
    ]
    input_terms = _normalized_terms(aliases)
    target_terms = _normalized_terms(json.loads(target["match_terms_json"]))
    rows = connection.execute(
        """SELECT i.*, d.revision_date, d.package_insert_no, d.source_path,
                  'target' AS direction
           FROM interactions i JOIN documents d ON d.id = i.document_id
           JOIN target_documents td ON td.document_id = d.id
           WHERE td.target_id = ?""",
        (target_id,),
    ).fetchall()
    evidence = [
        row for row in rows
        if any(term in normalize_name(row["raw_drug_text"]) for term in input_terms)
    ]
    reverse_rows = connection.execute(
        """SELECT i.*, d.revision_date, d.package_insert_no, d.source_path,
                  d.generic_names_json,
                  'input' AS direction
           FROM interactions i JOIN documents d ON d.id = i.document_id
           JOIN entity_documents ed ON ed.document_id = d.id
           WHERE ed.drug_id = ?""",
        (entity_id,),
    ).fetchall()
    evidence.extend(
        row for row in reverse_rows
        if len(json.loads(row["generic_names_json"])) == 1
        and any(term in normalize_name(row["raw_drug_text"]) for term in target_terms)
    )
    unique: dict[tuple[object, ...], sqlite3.Row] = {}
    for row in evidence:
        key = (row["severity"], row["raw_drug_text"], row["raw_effect_text"], row["raw_mechanism_text"])
        unique[key] = row
    return list(unique.values())


def check(runtime: sqlite3.Connection, input_name: str, drug_id: str, target_id: str) -> CheckResult:
    if not available():
        raise RuntimeError("トップ20 PMDAデータベースがありません")
    entity_ids, runtime_drug = _entity_ids(runtime, drug_id)
    with connect_top20() as connection:
        target = connection.execute("SELECT * FROM targets WHERE id = ?", (target_id,)).fetchone()
        if target is None:
            raise KeyError(target_id)
        dataset_date = connection.execute("SELECT value FROM metadata WHERE key='dataset_date'").fetchone()[0]
        if runtime_drug is None:
            entity = connection.execute("SELECT * FROM drug_entities WHERE id = ?", (drug_id,)).fetchone()
            if entity is None:
                raise KeyError(drug_id)
            display_name = entity["display_name"]
            generic_name = entity["generic_name"]
            category = "ingredient"
        else:
            display_name = runtime_drug["display_name"]
            generic_name = runtime_drug["generic_name"]
            category = runtime_drug["category"]
        ingredient_results: list[IngredientResult] = []
        for entity_id in entity_ids:
            entity = connection.execute("SELECT * FROM drug_entities WHERE id = ?", (entity_id,)).fetchone()
            if entity is None:
                continue
            evidence = _matching_evidence(connection, target_id, entity_id)
            if evidence:
                best_rank = min(SEVERITY_RANK[row["severity"]] for row in evidence)
                row = max(
                    (row for row in evidence if SEVERITY_RANK[row["severity"]] == best_rank),
                    key=lambda item: item["revision_date"] or "",
                )
                severity = row["severity"]
                action = "併用しないでください。最新の電子添文を確認してください。" if severity == "contraindicated" else "必要な観察、用量調整、代替薬を最新の電子添文で確認してください。"
                ingredient_results.append(
                    IngredientResult(
                        drug_id=entity_id,
                        generic_name=entity["generic_name"],
                        status=severity,
                        effect=row["raw_effect_text"] or "電子添文の相互作用欄に記載があります。",
                        mechanism=row["raw_mechanism_text"] or "電子添文の相互作用欄を確認してください。",
                        action=action,
                        evidence_url=(
                            f"{LOCAL_API_BASE}/v1/evidence/{row['id']}?target_id={target_id}"
                        ),
                        source_url=_pmda_pdf_url(row["source_path"]),
                        source_section=row["section"],
                        source_revision=row["revision_date"],
                    )
                )
            else:
                ingredient_results.append(
                    IngredientResult(
                        drug_id=entity_id,
                        generic_name=entity["generic_name"],
                        status="not_listed",
                        effect=f"確認した電子添文10.1・10.2では、{target['label']}との直接名称による相互作用記載を確認できませんでした。",
                        mechanism="薬効群記載、患者背景、用量、腎・肝機能による影響を除外する結果ではありません。",
                        action="双方の最新電子添文と患者背景を別途確認してください。",
                    )
                )
        if not ingredient_results:
            ingredient_results.append(
                IngredientResult(
                    drug_id=drug_id,
                    generic_name=generic_name or display_name,
                    status="not_listed",
                    effect="PMDA薬剤名マスターとの成分対応を確認できませんでした。",
                    mechanism="相互作用が存在しないことを示す結果ではありません。",
                    action="最新の電子添文で個別に確認してください。",
                )
            )
        decisive = min(ingredient_results, key=lambda item: SEVERITY_RANK[item.status])
        return CheckResult(
            input_name=input_name,
            drug_id=drug_id,
            display_name=display_name,
            generic_name=generic_name,
            category=category,
            ingredients=[item.generic_name for item in ingredient_results],
            status=decisive.status,
            effect=decisive.effect or "電子添文の相互作用欄を確認してください。",
            mechanism=decisive.mechanism or "電子添文の相互作用欄を確認してください。",
            action=decisive.action or "最新の電子添文を確認してください。",
            evidence_url=decisive.evidence_url,
            source_url=decisive.source_url,
            source_section=decisive.source_section,
            source_revision=decisive.source_revision,
            dataset_updated_at=dataset_date,
            ingredient_results=ingredient_results,
            target_id=target_id,
            target_name=target["label"],
        )


# The local alias table is immutable during an API process lifetime. Loading it
# at import keeps typo resolution latency predictable for the first request.
if available():
    _alias_index()
