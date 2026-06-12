"""Conservative exact and fuzzy drug-name resolution."""

from __future__ import annotations

import sqlite3

from rapidfuzz import fuzz, process

from .config import settings
from .models import DrugCandidate, ResolutionItem
from .normalize import normalize_name
from .top20 import exact_candidates as top20_exact_candidates
from .top20 import fuzzy_candidates as top20_fuzzy_candidates


def _candidate(row: sqlite3.Row, score: float) -> DrugCandidate:
    return DrugCandidate(
        drug_id=row["id"],
        display_name=row["display_name"],
        generic_name=row["generic_name"],
        category=row["category"],
        score=round(score, 1),
    )


def _runtime_fuzzy_candidates(
    connection: sqlite3.Connection,
    normalized: str,
    limit: int,
    threshold: float,
) -> list[DrugCandidate]:
    alias_rows = connection.execute(
        """SELECT a.normalized_alias, a.alias, d.* FROM aliases a
           JOIN drugs d ON d.id = a.drug_id"""
    ).fetchall()
    alias_map: dict[str, list[sqlite3.Row]] = {}
    for row in alias_rows:
        alias_map.setdefault(row["normalized_alias"], []).append(row)
    matches = process.extract(
        normalized,
        alias_map.keys(),
        scorer=fuzz.WRatio,
        limit=limit * 2,
        score_cutoff=threshold,
    )
    candidates: dict[str, DrugCandidate] = {}
    for matched_alias, score, _ in matches:
        for row in alias_map[matched_alias]:
            current = candidates.get(row["id"])
            if current is None or score > current.score:
                candidates[row["id"]] = _candidate(row, score)
    return sorted(candidates.values(), key=lambda item: (-item.score, item.display_name))[:limit]


def llm_candidate_pool(
    connection: sqlite3.Connection,
    input_name: str,
    limit: int = 20,
) -> list[DrugCandidate]:
    """Return only DB-backed low-confidence choices that an LLM may rank."""
    normalized = normalize_name(input_name)
    candidates: dict[str, DrugCandidate] = {}
    for candidate in _runtime_fuzzy_candidates(connection, normalized, limit, 25.0):
        candidates[candidate.drug_id] = candidate
    for candidate in top20_fuzzy_candidates(normalized, limit, 25.0):
        current = candidates.get(candidate.drug_id)
        if current is None or candidate.score > current.score:
            candidates[candidate.drug_id] = candidate
    return sorted(candidates.values(), key=lambda item: (-item.score, item.display_name))[:limit]


def resolve_one(connection: sqlite3.Connection, input_name: str) -> ResolutionItem:
    normalized = normalize_name(input_name)
    exact = connection.execute(
        """SELECT DISTINCT d.* FROM aliases a
           JOIN drugs d ON d.id = a.drug_id
           WHERE a.normalized_alias = ?
           ORDER BY CASE d.category WHEN 'prescription' THEN 0 WHEN 'otc' THEN 1 ELSE 2 END""",
        (normalized,),
    ).fetchall()
    if len(exact) == 1:
        return ResolutionItem(
            input_name=input_name,
            normalized_input=normalized,
            status="resolved",
            selected=_candidate(exact[0], 100),
        )
    if len(exact) > 1:
        return ResolutionItem(
            input_name=input_name,
            normalized_input=normalized,
            status="unresolved",
            candidates=[_candidate(row, 100) for row in exact],
            message="複数の薬剤が一致しました。対象を選択してください。",
        )

    pmda_exact = top20_exact_candidates(normalized)
    if len(pmda_exact) == 1:
        return ResolutionItem(
            input_name=input_name,
            normalized_input=normalized,
            status="resolved",
            selected=pmda_exact[0],
        )
    if len(pmda_exact) > 1:
        return ResolutionItem(
            input_name=input_name,
            normalized_input=normalized,
            status="unresolved",
            candidates=pmda_exact[: settings.fuzzy_limit],
            message="複数のPMDA薬剤文書が一致しました。対象を選択してください。",
        )

    candidates = {
        candidate.drug_id: candidate
        for candidate in _runtime_fuzzy_candidates(
            connection, normalized, settings.fuzzy_limit, settings.fuzzy_threshold
        )
    }
    for candidate in top20_fuzzy_candidates(
        normalized, settings.fuzzy_limit, settings.fuzzy_threshold
    ):
        current = candidates.get(candidate.drug_id)
        if current is None or candidate.score > current.score:
            candidates[candidate.drug_id] = candidate
    ordered = sorted(candidates.values(), key=lambda item: (-item.score, item.display_name))[
        : settings.fuzzy_limit
    ]
    if ordered:
        return ResolutionItem(
            input_name=input_name,
            normalized_input=normalized,
            status="unresolved",
            candidates=ordered,
            message="近い薬剤名が見つかりました。自動確定せず候補を表示しています。",
        )
    return ResolutionItem(
        input_name=input_name,
        normalized_input=normalized,
        status="unsupported",
        message="現在の薬剤マスターでは特定できませんでした。",
    )
