"""Optional Ollama helpers constrained to ranking DB-backed name candidates."""

from __future__ import annotations

import json

import httpx
from pydantic import BaseModel, Field, ValidationError

from .config import settings


class NameSuggestion(BaseModel):
    drug_ids: list[str] = Field(max_length=3)


async def ollama_status() -> dict[str, bool]:
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            tags_response = await client.get(f"{settings.ollama_url}/api/tags")
            tags_response.raise_for_status()
            installed = {model["name"] for model in tags_response.json().get("models", [])}
            ps_response = await client.get(f"{settings.ollama_url}/api/ps")
            ps_response.raise_for_status()
            loaded = {model["name"] for model in ps_response.json().get("models", [])}
        return {
            "server": True,
            "model_available": settings.ollama_model in installed,
            "model_loaded": settings.ollama_model in loaded,
        }
    except (httpx.HTTPError, KeyError, ValueError):
        return {"server": False, "model_available": False, "model_loaded": False}


async def ollama_available() -> bool:
    status = await ollama_status()
    return status["server"] and status["model_available"]


async def warmup_ollama() -> bool:
    payload = {
        "model": settings.ollama_model,
        "prompt": "準備",
        "stream": False,
        "keep_alive": "10m",
        "options": {"temperature": 0, "num_predict": 1},
    }
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(f"{settings.ollama_url}/api/generate", json=payload)
            response.raise_for_status()
        return True
    except httpx.HTTPError:
        return False


async def suggest_drug_ids(input_name: str, choices: list[dict[str, str]]) -> list[str]:
    schema = NameSuggestion.model_json_schema()
    prompt = (
        "日本語の医薬品名の誤字・略称を解釈し、候補一覧から最大3件を選んでください。"
        "候補一覧にあるdrug_idだけを返し、確信がなければ空配列にしてください。"
        "候補の追加、薬剤情報や相互作用の推論は禁止です。\n"
        f"入力: {input_name}\n候補一覧: {json.dumps(choices, ensure_ascii=False)}"
    )
    payload = {
        "model": settings.ollama_model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "format": schema,
        "think": False,
        "keep_alive": "10m",
        "options": {"temperature": 0, "num_predict": 64},
    }
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(f"{settings.ollama_url}/api/chat", json=payload)
            response.raise_for_status()
        parsed = NameSuggestion.model_validate_json(response.json()["message"]["content"])
        allowed = {choice["drug_id"] for choice in choices}
        return [drug_id for drug_id in parsed.drug_ids if drug_id in allowed]
    except (httpx.HTTPError, KeyError, ValueError, ValidationError):
        return []
