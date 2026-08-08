from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolve .env from repo root (parent of backend/) or cwd
_REPO_ROOT = Path(__file__).resolve().parents[2]
_ENV_CANDIDATES = [
    _REPO_ROOT / ".env",
    Path.cwd() / ".env",
    Path.cwd().parent / ".env",
]
_ENV_FILE = next((p for p in _ENV_CANDIDATES if p.exists()), _REPO_ROOT / ".env")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.5-flash"
    embedding_model: str = "gemini-embedding-2"
    embedding_dims: int = 768
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "nexusrag"
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "nexusrag"
    data_dir: str = "./data"
    bundle_dir: str = "./data/bundle"
    upload_dir: str = "./data/uploads"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    def _resolve_data_path(self, value: str) -> Path:
        p = Path(value)
        if p.is_absolute():
            return p
        return (_REPO_ROOT / p).resolve()

    @property
    def data_path(self) -> Path:
        return self._resolve_data_path(self.data_dir)

    @property
    def bundle_path(self) -> Path:
        return self._resolve_data_path(self.bundle_dir)

    @property
    def upload_path(self) -> Path:
        return self._resolve_data_path(self.upload_dir)


@lru_cache
def get_settings() -> Settings:
    return Settings()
