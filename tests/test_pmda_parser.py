"""Tests for extracting PMDA interaction table rows without losing line breaks."""

from pmda_builder.parser import (
    clarithromycin_product_kind,
    matching_reverse_keyword,
    parse_xml_bytes,
)


def pmda_xml(generic: str, brand: str, contraindicated_drug: str, caution_drug: str) -> bytes:
    return f'''<?xml version="1.0" encoding="utf-8"?>
<PackIns xmlns="http://info.pmda.go.jp/namespace/prescription_drugs/package_insert/1.0">
  <PackageInsertNo>TEST-001</PackageInsertNo>
  <CompanyIdentifier>123456</CompanyIdentifier>
  <DateOfPreparationOrRevision>
    <PreparationOrRevision id="今回"><YearMonth>2026-06</YearMonth></PreparationOrRevision>
  </DateOfPreparationOrRevision>
  <ApprovalEtc><DetailBrandName><ApprovalBrandName><Lang>{brand}</Lang></ApprovalBrandName>
    <BrandCode><YJCode>123456789012</YJCode></BrandCode></DetailBrandName></ApprovalEtc>
  <GenericName><Detail><Lang>{generic}</Lang></Detail></GenericName>
  <CompositionAndProperty><ActiveIngredientName><Lang>{generic} 200mg</Lang></ActiveIngredientName></CompositionAndProperty>
  <Interactions>
    <ContraIndicatedCombinations><ContraIndicatedCombination><ContraIndication><Drug>
      <DrugName><Detail><Lang>{contraindicated_drug}<?enter?>〔販売名〕</Lang></Detail></DrugName>
      <ClinSymptomsAndMeasures><Detail><Lang>作用が増強する。</Lang></Detail></ClinSymptomsAndMeasures>
      <MechanismAndRiskFactors><Detail><Lang>CYP3A阻害。</Lang></Detail></MechanismAndRiskFactors>
    </Drug></ContraIndication></ContraIndicatedCombination></ContraIndicatedCombinations>
    <PrecautionsForCombinations><PrecautionsForCombination><PrecautionsForCombi><Drug>
      <DrugName><Detail><Lang>{caution_drug}</Lang></Detail></DrugName>
      <ClinSymptomsAndMeasures><Detail><Lang>注意する。</Lang></Detail></ClinSymptomsAndMeasures>
      <MechanismAndRiskFactors><Detail><Lang>血中濃度上昇。</Lang></Detail></MechanismAndRiskFactors>
    </Drug></PrecautionsForCombi></PrecautionsForCombination></PrecautionsForCombinations>
  </Interactions>
</PackIns>'''.encode("utf-8")


def test_parser_extracts_metadata_and_interaction_rows() -> None:
    data = parse_xml_bytes(pmda_xml("クラリスロマイシン", "クラリス錠200", "ピモジド", "ジゴキシン"))
    assert data.is_clarithromycin is True
    assert data.revision_date == "2026-06"
    assert data.yj_codes == ("123456789012",)
    assert len(data.interactions) == 2
    assert data.interactions[0].drug_text == "ピモジド\n〔販売名〕"
    assert data.interactions[0].severity == "contraindicated"
    assert data.interactions[1].severity == "caution"
    assert clarithromycin_product_kind(data) == "single_active"


def test_reverse_keyword_is_limited_to_interaction_row() -> None:
    data = parse_xml_bytes(pmda_xml("相手薬", "相手薬錠", "クラリスロマイシン", "別の薬"))
    assert data.is_clarithromycin is False
    assert matching_reverse_keyword(data.interactions[0]) == "クラリスロマイシン"
    assert matching_reverse_keyword(data.interactions[1]) is None


def test_secondary_eradication_packs_are_not_clarithromycin_products() -> None:
    for brand in ("ボノピオンパック", "ラベファインパック"):
        data = parse_xml_bytes(pmda_xml("メトロニダゾール", brand, "別の薬", "別の薬"))
        assert data.is_clarithromycin is False


def test_known_clarithromycin_pack_is_supplemental_combination() -> None:
    data = parse_xml_bytes(
        pmda_xml("クラリスロマイシン", "ボノサップパック400", "別の薬", "別の薬")
    )
    assert clarithromycin_product_kind(data) == "combination"
