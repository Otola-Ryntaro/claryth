"""HTTP contract and failure-mode tests for the local FastAPI service."""

from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.integrity import IntegrityResult
from backend.app.models import DrugCandidate


AUTH_HEADERS = {"X-Clarith-Token": "test-token-0123456789-abcdefghijklmnopqrstuvwxyz"}


def authenticated_client() -> TestClient:
    return TestClient(app, headers=AUTH_HEADERS)


def test_dataset_and_health_endpoints() -> None:
    with patch("backend.app.main.ollama_status", new=AsyncMock(side_effect=AssertionError)):
        with authenticated_client() as client:
            dataset = client.get("/v1/dataset")
            health = client.get("/health")
    assert dataset.status_code == 200
    assert dataset.json()["dataset_version"] == "0.1.1-prototype"
    assert health.status_code == 200
    assert health.json()["database"] == "ok"
    assert health.json()["clinical_ready"] is False
    assert health.json()["clinical_source"] == "top20"
    assert "ollama" not in health.json()


def test_llm_status_is_separate_from_health() -> None:
    status = {"server": False, "model_available": False, "model_loaded": False}
    with patch("backend.app.main.ollama_status", new=AsyncMock(return_value=status)):
        with authenticated_client() as client:
            response = client.get("/v1/llm/status")
    assert response.status_code == 200
    assert response.json()["server"] is False
    assert response.json()["model"]


def test_resolve_and_check_without_ollama(clinically_reviewed_top20: None) -> None:
    with authenticated_client() as client:
        resolution = client.post(
            "/v1/resolve",
            json={"text": "ワーファリン錠1mg、ロキソニンS", "use_llm": False},
        )
        items = resolution.json()["items"]
        checked = client.post(
            "/v1/check",
            json={
                "items": [
                    {"input_name": item["input_name"], "drug_id": item["selected"]["drug_id"]}
                    for item in items
                ],
            },
        )
    assert resolution.status_code == 200
    assert checked.status_code == 200
    assert [item["status"] for item in checked.json()["results"]] == ["caution", "not_listed"]


def test_unknown_drug_id_is_rejected(clinically_reviewed_top20: None) -> None:
    with authenticated_client() as client:
        response = client.post(
            "/v1/check",
            json={"items": [{"input_name": "不明", "drug_id": "missing"}]},
        )
    assert response.status_code == 422


def test_nonlocal_web_origin_is_rejected() -> None:
    with authenticated_client() as client:
        response = client.get("/v1/dataset", headers={"Origin": "https://example.com"})
    assert response.status_code == 403


def test_localhost_prefix_attack_is_rejected() -> None:
    with authenticated_client() as client:
        response = client.get("/v1/dataset", headers={"Origin": "http://localhost.evil.example"})
    assert response.status_code == 403


def test_unrecognized_chrome_extension_origin_is_rejected() -> None:
    with authenticated_client() as client:
        response = client.get(
            "/v1/dataset",
            headers={"Origin": "chrome-extension://aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"},
        )
    assert response.status_code == 403


def test_unreviewed_top20_database_blocks_clinical_check() -> None:
    with authenticated_client() as client:
        response = client.post(
            "/v1/check",
            json={"items": [{"input_name": "ワーファリン", "drug_id": "rx-warfarin"}]},
        )
    assert response.status_code == 503
    assert "医学レビュー未完了" in response.json()["detail"]


def test_unreviewed_seed_database_blocks_fallback_check() -> None:
    with patch("backend.app.main.top20.available", return_value=False):
        with authenticated_client() as client:
            response = client.post(
                "/v1/check",
                json={"items": [{"input_name": "ワーファリン", "drug_id": "rx-warfarin"}]},
            )
    assert response.status_code == 503
    assert "医学レビュー未完了" in response.json()["detail"]


def test_integrity_failure_blocks_reviewed_clinical_check(monkeypatch) -> None:
    from backend.app import main, top20

    failure = IntegrityResult(False, "database hash mismatch: top20")
    monkeypatch.setattr(top20, "clinically_ready", lambda: True)
    monkeypatch.setattr(main, "verify_release_manifest", lambda: failure)
    with authenticated_client() as client:
        health = client.get("/health")
        response = client.post(
            "/v1/check",
            json={"items": [{"input_name": "ワーファリン", "drug_id": "rx-warfarin"}]},
        )
    assert health.json()["integrity_ok"] is False
    assert health.json()["clinical_ready"] is False
    assert response.status_code == 503
    assert "完全性検証" in response.json()["detail"]


def test_ollama_warmup_endpoint() -> None:
    with patch("backend.app.main.warmup_ollama", new=AsyncMock(return_value=True)):
        with authenticated_client() as client:
            response = client.post("/v1/ollama/warmup")
    assert response.status_code == 200
    assert response.json()["status"] == "ready"


def test_ollama_warmup_failure_is_not_reported_as_ready() -> None:
    with patch("backend.app.main.warmup_ollama", new=AsyncMock(return_value=False)):
        with authenticated_client() as client:
            response = client.post("/v1/ollama/warmup")
    assert response.status_code == 503


def test_llm_is_not_called_by_default() -> None:
    with patch("backend.app.main.suggest_drug_ids", new=AsyncMock(side_effect=AssertionError)):
        with authenticated_client() as client:
            response = client.post(
                "/v1/resolve",
                json={"text": "完全に未知の薬剤"},
            )
    assert response.status_code == 200
    assert response.json()["items"][0]["status"] == "unsupported"


def test_llm_can_only_return_an_unresolved_db_candidate() -> None:
    candidate = DrugCandidate(
        drug_id="rx-warfarin",
        display_name="ワーファリン",
        generic_name="ワルファリンカリウム",
        category="prescription",
        score=42,
    )
    with (
        patch("backend.app.main.llm_candidate_pool", return_value=[candidate]),
        patch("backend.app.main.suggest_drug_ids", new=AsyncMock(return_value=["rx-warfarin"])),
    ):
        with authenticated_client() as client:
            response = client.post(
                "/v1/resolve",
                json={"text": "完全に未知の薬剤", "use_llm": True},
            )
    item = response.json()["items"][0]
    assert item["status"] == "unresolved"
    assert item["selected"] is None
    assert item["llm_used"] is True
    assert item["candidates"][0]["drug_id"] == "rx-warfarin"
    assert "AI候補" in item["message"]


def test_invalid_or_failed_llm_output_stays_unsupported() -> None:
    candidate = DrugCandidate(
        drug_id="rx-warfarin",
        display_name="ワーファリン",
        generic_name="ワルファリンカリウム",
        category="prescription",
        score=42,
    )
    for suggestion in (["invented-id"], RuntimeError("ollama failed")):
        mock = AsyncMock(side_effect=suggestion) if isinstance(suggestion, Exception) else AsyncMock(return_value=suggestion)
        with (
            patch("backend.app.main.llm_candidate_pool", return_value=[candidate]),
            patch("backend.app.main.suggest_drug_ids", new=mock),
        ):
            with authenticated_client() as client:
                response = client.post(
                    "/v1/resolve",
                    json={"text": "完全に未知の薬剤", "use_llm": True},
                )
        assert response.json()["items"][0]["status"] == "unsupported"


def test_reported_three_drug_request_resolves_without_llm() -> None:
    with authenticated_client() as client:
        response = client.post(
            "/v1/resolve",
            json={"text": "デエビゴ\nアレグラ\nバイアスピリン", "use_llm": True},
        )
    assert response.status_code == 200
    assert all(item["status"] == "resolved" for item in response.json()["items"])


def test_meiact_sawacillin_and_amoxicillin_are_in_the_master() -> None:
    with authenticated_client() as client:
        response = client.post(
            "/v1/resolve",
            json={"text": "メイアクト\nサワシリン\nアモキシシリン", "use_llm": False},
        )
    assert response.status_code == 200
    assert all(item["status"] == "resolved" for item in response.json()["items"])


def test_top20_targets_have_default_clarithromycin() -> None:
    with authenticated_client() as client:
        response = client.get("/v1/targets")
    assert response.status_code == 200
    targets = response.json()
    assert len(targets) == 20
    assert [target["id"] for target in targets if target["is_default"]] == ["clarithromycin"]


def test_switching_target_changes_sawacillin_result(clinically_reviewed_top20: None) -> None:
    with authenticated_client() as client:
        resolved = client.post(
            "/v1/resolve", json={"text": "サワシリン", "use_llm": False}
        ).json()["items"][0]
        item = {"input_name": "サワシリン", "drug_id": resolved["selected"]["drug_id"]}
        clarith = client.post(
            "/v1/check",
            json={"target_id": "clarithromycin", "items": [item]},
        )
        warfarin = client.post(
            "/v1/check",
            json={"target_id": "warfarin", "items": [item]},
        )
    assert clarith.json()["results"][0]["status"] == "not_listed"
    assert warfarin.json()["results"][0]["status"] == "caution"
    assert "ワルファリン" in warfarin.json()["results"][0]["effect"]


def test_unknown_target_is_rejected(clinically_reviewed_top20: None) -> None:
    with authenticated_client() as client:
        response = client.post(
            "/v1/check",
            json={
                "target_id": "missing-target",
                "items": [{"input_name": "ワーファリン", "drug_id": "rx-warfarin"}],
            },
        )
    assert response.status_code == 422


def test_evidence_page_shows_exact_interaction_and_pmda_pdf(clinically_reviewed_top20: None) -> None:
    with authenticated_client() as client:
        checked = client.post(
            "/v1/check",
            json={
                "target_id": "clarithromycin",
                "items": [{"input_name": "ワーファリン", "drug_id": "rx-warfarin"}],
            },
        ).json()["results"][0]
        evidence_path = checked["evidence_url"].replace("http://127.0.0.1:8765", "")
        response = client.get(evidence_path)
    assert response.status_code == 200
    assert "該当相互作用" in response.text
    assert "クラリスロマイシン" in response.text
    assert "10.2" in response.text
    assert "ResultDataSetPDF" in response.text
