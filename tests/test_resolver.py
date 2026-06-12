"""Tests for exact matching, typo candidates, and unsupported terms."""

from backend.app.database import connect
from backend.app.resolver import llm_candidate_pool, resolve_one


def test_trade_name_with_strength_resolves_exactly() -> None:
    with connect() as connection:
        result = resolve_one(connection, "ワーファリン錠1mg")
    assert result.status == "resolved"
    assert result.selected is not None
    assert result.selected.drug_id == "rx-warfarin"


def test_fullwidth_spacing_and_dosage_form_resolve_without_llm() -> None:
    with connect() as connection:
        result = resolve_one(connection, "　ワーファリン錠１ｍｇ　")
    assert result.status == "resolved"
    assert result.selected is not None
    assert result.selected.drug_id == "rx-warfarin"


def test_typo_is_candidate_not_automatic_resolution() -> None:
    with connect() as connection:
        result = resolve_one(connection, "ワーファリソ")
    assert result.status == "unresolved"
    assert result.selected is None
    assert any(candidate.drug_id == "rx-warfarin" for candidate in result.candidates)


def test_unknown_name_is_unsupported_without_llm() -> None:
    with connect() as connection:
        result = resolve_one(connection, "完全に未知の薬剤")
    assert result.status == "unsupported"
    assert result.candidates == []


def test_llm_candidate_pool_contains_only_registered_drugs() -> None:
    with connect() as connection:
        candidates = llm_candidate_pool(connection, "ワルフアリン", limit=20)
    assert len(candidates) <= 20
    assert len({candidate.drug_id for candidate in candidates}) == len(candidates)
    assert any(candidate.drug_id == "rx-warfarin" for candidate in candidates)


def test_otc_product_resolves() -> None:
    with connect() as connection:
        result = resolve_one(connection, "アレグラFX")
    assert result.status == "resolved"
    assert result.selected is not None
    assert result.selected.category == "otc"


def test_reported_prescription_trade_names_resolve_exactly() -> None:
    with connect() as connection:
        dayvigo = resolve_one(connection, "デエビゴ")
        bayaspirin = resolve_one(connection, "バイアスピリン")
    assert dayvigo.selected is not None
    assert dayvigo.selected.drug_id == "rx-dayvigo"
    assert bayaspirin.selected is not None
    assert bayaspirin.selected.drug_id == "rx-bayaspirin"


def test_meiact_and_sawacillin_names_resolve_exactly() -> None:
    with connect() as connection:
        meiact = resolve_one(connection, "メイアクト")
        sawacillin = resolve_one(connection, "サワシリン")
        amoxicillin = resolve_one(connection, "アモキシシリン")
    assert meiact.selected is not None
    assert meiact.selected.drug_id == "rx-meiact-ms"
    assert sawacillin.selected is not None
    assert sawacillin.selected.drug_id == "rx-sawacillin"
    assert amoxicillin.selected is not None
    assert amoxicillin.selected.drug_id == "amoxicillin"
