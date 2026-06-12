"""Central runtime configuration for the localhost-only service."""

from dataclasses import dataclass
from pathlib import Path
import os


ROOT = Path(__file__).resolve().parents[2]


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
    api_host: str = "127.0.0.1"
    api_port: int = int(os.getenv("CLARITH_API_PORT", "8765"))
    fuzzy_limit: int = 5
    fuzzy_threshold: float = 62.0


settings = Settings()
