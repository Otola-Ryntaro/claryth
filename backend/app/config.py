"""Central runtime configuration for the localhost-only service."""

from dataclasses import dataclass
from pathlib import Path
import os


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_EXTENSION_ID = "nepmbhaakdinmdacjlkplkoghmoifpkk"


def _allowed_origins() -> tuple[str, ...]:
    configured = os.getenv("CLARITH_ALLOWED_ORIGINS")
    if configured:
        return tuple(value.strip() for value in configured.split(",") if value.strip())
    return (f"chrome-extension://{DEFAULT_EXTENSION_ID}",)


def strict_data_guard_enabled() -> bool:
    return os.getenv("CLARITH_STRICT_DATA_GUARD", "").lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    database_path: Path = Path(
        os.getenv("CLARITH_DB_PATH", ROOT / "backend" / "data" / "clarith.db")
    )
    seed_path: Path = Path(
        os.getenv("CLARITH_SEED_PATH", ROOT / "backend" / "data" / "seed.json")
    )
    top20_database_path: Path = Path(
        os.getenv(
            "CLARITH_TOP20_DB_PATH",
            ROOT / "backend" / "data" / "top20_interactions.sqlite",
        )
    )
    ollama_url: str = os.getenv("CLARITH_OLLAMA_URL", "http://127.0.0.1:11434")
    ollama_model: str = os.getenv("CLARITH_OLLAMA_MODEL", "qwen3.5:9b")
    auth_config_path: Path = Path(
        os.getenv("CLARITH_AUTH_CONFIG", ROOT / ".runtime" / "auth.json")
    )
    api_token: str | None = os.getenv("CLARITH_API_TOKEN")
    release_manifest_path: Path = Path(
        os.getenv("CLARITH_RELEASE_MANIFEST", ROOT / "backend" / "data" / "release_manifest.json")
    )
    release_signature_path: Path = Path(
        os.getenv("CLARITH_RELEASE_SIGNATURE", ROOT / "backend" / "data" / "release_manifest.sig")
    )
    release_public_key_path: Path = Path(
        os.getenv("CLARITH_RELEASE_PUBLIC_KEY", ROOT / "backend" / "app" / "release_public_key.pem")
    )
    product_mode: bool = os.getenv("CLARITH_MODE", "production").lower() == "production"
    allowed_origins: tuple[str, ...] = _allowed_origins()
    max_request_body_bytes: int = int(os.getenv("CLARITH_MAX_REQUEST_BODY_BYTES", "32768"))
    max_concurrent_requests: int = int(os.getenv("CLARITH_MAX_CONCURRENT_REQUESTS", "8"))
    max_concurrent_expensive_requests: int = int(
        os.getenv("CLARITH_MAX_CONCURRENT_EXPENSIVE_REQUESTS", "2")
    )
    api_host: str = "127.0.0.1"
    api_port: int = int(os.getenv("CLARITH_API_PORT", "8765"))
    fuzzy_limit: int = 5
    fuzzy_threshold: float = 62.0


settings = Settings()
