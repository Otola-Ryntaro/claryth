"""Tests for multi-input parsing and conservative Japanese normalization."""

from backend.app.normalize import normalize_name, parse_inputs


def test_normalize_strength_width_and_form() -> None:
    assert normalize_name(" ワーファリン錠１mg ") == "ワーファリン"
    assert normalize_name("ベルソムラ錠（スボレキサント）20mg") == "ベルソムラ"


def test_parse_multiple_inputs_and_deduplicate() -> None:
    assert parse_inputs("ワーファリン、ベルソムラ\nワーファリン, ロキソニンS", None) == [
        "ワーファリン",
        "ベルソムラ",
        "ロキソニンS",
    ]


def test_parse_limits_to_twenty_items() -> None:
    text = "\n".join(f"薬剤{i}" for i in range(30))
    assert len(parse_inputs(text, None)) == 20

