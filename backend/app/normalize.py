"""Japanese drug-name normalization and multi-input parsing."""

import re
import unicodedata


SEPARATORS = re.compile(r"[\n,、;；]+")
STRENGTH = re.compile(r"\d+(?:\.\d+)?\s*(?:mg|g|μg|mcg|%|mL|ml)", re.IGNORECASE)
DOSAGE_FORM = re.compile(
    r"(?:錠|錠剤|カプセル|カプセル剤|細粒|顆粒|散|シロップ|ドライシロップ|液|テープ|パップ|軟膏|クリーム)$"
)
BRACKET_CONTENT = re.compile(r"[（(][^）)]*[）)]")
SPACES_AND_PUNCT = re.compile(r"[\s\-‐‑‒–—―・･_/]+")


def parse_inputs(text: str | None, inputs: list[str] | None) -> list[str]:
    raw = inputs or SEPARATORS.split(text or "")
    seen: set[str] = set()
    result: list[str] = []
    for item in raw:
        value = item.strip()
        if not value:
            continue
        key = normalize_name(value)
        if key and key not in seen:
            seen.add(key)
            result.append(value)
    return result


def normalize_name(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).strip().lower()
    value = BRACKET_CONTENT.sub("", value)
    value = STRENGTH.sub("", value)
    value = value.replace("一般名", "")
    value = SPACES_AND_PUNCT.sub("", value)
    value = DOSAGE_FORM.sub("", value)
    return value
