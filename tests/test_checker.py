"""Golden behavior tests for deterministic DB-only interaction checks."""

from backend.app.checker import check_drug
from backend.app.database import connect


def test_contraindicated_result() -> None:
    with connect() as connection:
        result = check_drug(connection, "ベルソムラ", "rx-belsomra", "2026-06-12")
    assert result.status == "contraindicated"
    assert result.source_url is not None


def test_caution_result() -> None:
    with connect() as connection:
        result = check_drug(connection, "ワーファリン", "rx-warfarin", "2026-06-12")
    assert result.status == "caution"
    assert "INR" in result.action


def test_not_listed_is_not_worded_as_safe() -> None:
    with connect() as connection:
        result = check_drug(connection, "ロキソニンS", "otc-loxonin-s", "2026-06-12")
    assert result.status == "not_listed"
    assert "保証" in result.mechanism
    assert "相互作用なし" not in result.effect


def test_otc_combination_evaluates_every_ingredient() -> None:
    with connect() as connection:
        result = check_drug(connection, "イブA錠", "otc-eve-a", "2026-06-12")
    assert len(result.ingredient_results) == 3
    assert result.status == "not_listed"


def test_otc_interacting_ingredient_is_promoted_to_product_result() -> None:
    with connect() as connection:
        result = check_drug(connection, "アレグラFX", "otc-allegra-fx", "2026-06-12")
    assert result.status == "caution"
    assert result.ingredient_results[0].generic_name == "フェキソフェナジン塩酸塩"


def test_dayvigo_is_caution_and_bayaspirin_is_not_listed() -> None:
    with connect() as connection:
        dayvigo = check_drug(connection, "デエビゴ", "rx-dayvigo", "2026-06-12")
        bayaspirin = check_drug(connection, "バイアスピリン", "rx-bayaspirin", "2026-06-12")
    assert dayvigo.status == "caution"
    assert "CYP3A" in dayvigo.mechanism
    assert bayaspirin.status == "not_listed"


def test_meiact_and_sawacillin_are_supported_not_listed() -> None:
    with connect() as connection:
        meiact = check_drug(connection, "メイアクト", "rx-meiact-ms", "2026-06-12")
        sawacillin = check_drug(connection, "サワシリン", "rx-sawacillin", "2026-06-12")
    assert meiact.status == "not_listed"
    assert meiact.ingredients == ["セフジトレン ピボキシル"]
    assert sawacillin.status == "not_listed"
    assert sawacillin.ingredients == ["アモキシシリン水和物"]
