"""Streaming-friendly parser for PMDA prescription package-insert XML."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import re
from xml.etree import ElementTree as ET


CLARITHROMYCIN_TERMS = (
    "クラリスロマイシン",
    "クラリス",
    "クラリシッド",
    "ボノサップ",
    "ラベキュア",
)
REVERSE_DIRECT_TERMS = ("クラリスロマイシン", "クラリス", "クラリシッド")
SPACE = re.compile(r"[ \t\u3000]+")


@dataclass(frozen=True)
class InteractionRow:
    section: str
    severity: str
    drug_text: str
    effect_text: str
    mechanism_text: str


@dataclass(frozen=True)
class DocumentData:
    sha256: str
    package_insert_no: str
    company_identifier: str
    revision_date: str
    brand_names: tuple[str, ...]
    generic_names: tuple[str, ...]
    active_ingredients: tuple[str, ...]
    yj_codes: tuple[str, ...]
    is_clarithromycin: bool
    interactions: tuple[InteractionRow, ...]


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def clean_text(value: str) -> str:
    lines = []
    for line in value.replace("\r", "\n").split("\n"):
        cleaned = SPACE.sub(" ", line).strip()
        if cleaned:
            lines.append(cleaned)
    return "\n".join(lines)


def element_text(element: ET.Element | None) -> str:
    if element is None:
        return ""
    parts: list[str] = []

    def visit(node: ET.Element) -> None:
        if node.text:
            parts.append(node.text)
        for child in node:
            if local_name(child.tag) == "LineBreak":
                parts.append("\n")
            else:
                visit(child)
            if child.tail:
                parts.append(child.tail)

    visit(element)
    return clean_text("".join(parts))


def descendants(element: ET.Element, name: str) -> list[ET.Element]:
    return [node for node in element.iter() if local_name(node.tag) == name]


def first_descendant(element: ET.Element, name: str) -> ET.Element | None:
    return next((node for node in element.iter() if local_name(node.tag) == name), None)


def texts_under(root: ET.Element, container_name: str, value_name: str = "Lang") -> tuple[str, ...]:
    values: list[str] = []
    for container in descendants(root, container_name):
        for value in descendants(container, value_name):
            text = element_text(value)
            if text and text not in values:
                values.append(text)
    return tuple(values)


def extract_revision_date(root: ET.Element) -> str:
    revisions = descendants(root, "PreparationOrRevision")
    current = next((node for node in revisions if node.attrib.get("id") == "今回"), None)
    selected = current if current is not None else (revisions[0] if revisions else None)
    year_month = first_descendant(selected, "YearMonth") if selected is not None else None
    return element_text(year_month)


def extract_interactions(root: ET.Element) -> tuple[InteractionRow, ...]:
    specs = (
        ("ContraIndicatedCombinations", "10.1", "contraindicated"),
        ("PrecautionsForCombinations", "10.2", "caution"),
    )
    rows: list[InteractionRow] = []
    for container_name, section, severity in specs:
        for container in descendants(root, container_name):
            for drug in descendants(container, "Drug"):
                drug_text = element_text(first_descendant(drug, "DrugName"))
                if not drug_text:
                    continue
                rows.append(
                    InteractionRow(
                        section=section,
                        severity=severity,
                        drug_text=drug_text,
                        effect_text=element_text(first_descendant(drug, "ClinSymptomsAndMeasures")),
                        mechanism_text=element_text(first_descendant(drug, "MechanismAndRiskFactors")),
                    )
                )
    return tuple(rows)


def parse_xml_bytes(content: bytes) -> DocumentData:
    digest = sha256(content).hexdigest()
    parseable = content.replace(b"<?enter?>", b"<LineBreak/>")
    root = ET.fromstring(parseable)
    package_insert_no = element_text(first_descendant(root, "PackageInsertNo"))
    company_identifier = element_text(first_descendant(root, "CompanyIdentifier"))
    brand_names = texts_under(root, "ApprovalBrandName")
    generic_names = texts_under(root, "GenericName")
    active_ingredients = texts_under(root, "ActiveIngredientName")
    yj_codes = tuple(
        dict.fromkeys(element_text(node) for node in descendants(root, "YJCode") if element_text(node))
    )
    identity_text = "\n".join((*brand_names, *generic_names, *active_ingredients))
    is_clarithromycin = "クラリスロマイシン" in identity_text or any(
        term in "\n".join(brand_names) for term in CLARITHROMYCIN_TERMS[1:]
    )
    return DocumentData(
        sha256=digest,
        package_insert_no=package_insert_no,
        company_identifier=company_identifier,
        revision_date=extract_revision_date(root),
        brand_names=brand_names,
        generic_names=generic_names,
        active_ingredients=active_ingredients,
        yj_codes=yj_codes,
        is_clarithromycin=is_clarithromycin,
        interactions=extract_interactions(root),
    )


def parse_xml_file(path: Path) -> DocumentData:
    return parse_xml_bytes(path.read_bytes())


def clarithromycin_product_kind(data: DocumentData) -> str:
    other_generic_names = [
        generic_name
        for generic_name in data.generic_names
        if "クラリスロマイシン" not in generic_name
    ]
    combination_brand = any(
        term in brand
        for brand in data.brand_names
        for term in ("ボノサップ", "ラベキュア")
    )
    return "combination" if other_generic_names or combination_brand else "single_active"


def matching_reverse_keyword(row: InteractionRow) -> str | None:
    combined = "\n".join((row.drug_text, row.effect_text, row.mechanism_text))
    return next((term for term in REVERSE_DIRECT_TERMS if term in combined), None)
