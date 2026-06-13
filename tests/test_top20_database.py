"""Coverage tests for all configured top-20 representative ingredients."""

from backend.app.database import connect
from backend.app.top20 import check, connect_top20
from backend.app.top20 import clinically_ready
from top20_builder.targets import DEFAULT_TARGET_ID, TARGETS


def test_target_configuration_is_unique_and_complete() -> None:
    assert len(TARGETS) == 20
    assert len({target.id for target in TARGETS}) == 20
    assert len({target.rank for target in TARGETS}) == 20
    assert DEFAULT_TARGET_ID == "clarithromycin"


def test_extracted_database_is_not_clinically_ready() -> None:
    assert clinically_ready() is False


def test_every_target_has_a_single_ingredient_pmda_document() -> None:
    with connect_top20() as connection:
        counts = dict(
            connection.execute(
                "SELECT target_id, COUNT(*) FROM target_documents GROUP BY target_id"
            )
        )
    assert set(counts) == {target.id for target in TARGETS}
    assert all(count > 0 for count in counts.values())


def test_every_target_can_run_a_check(clinically_reviewed_top20: None) -> None:
    with connect() as runtime:
        results = [
            check(runtime, "サワシリン", "rx-sawacillin", target.id)
            for target in TARGETS
        ]
    assert [result.target_id for result in results] == [target.id for target in TARGETS]
    assert all(result.status in {"contraindicated", "caution", "not_listed"} for result in results)


def test_positive_result_links_to_exact_evidence_and_pmda_pdf(clinically_reviewed_top20: None) -> None:
    with connect() as runtime:
        result = check(runtime, "ワーファリン", "rx-warfarin", "clarithromycin")
    assert result.status == "caution"
    assert result.source_section == "10.2"
    assert result.evidence_url is not None
    assert "/v1/evidence/" in result.evidence_url
    assert result.source_url is not None
    assert "/PmdaSearch/iyakuDetail/ResultDataSetPDF/" in result.source_url
