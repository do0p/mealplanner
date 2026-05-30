from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # The LLM is only contacted at recipe import/parsing time. The app runs fine
    # without it; only new imports are blocked while it is unreachable.
    llm_provider: str = "anthropic"  # "ollama" or "anthropic"

    ollama_base_url: str = "http://172.17.176.1:11434"
    ollama_model: str = "qwen3:4b"
    ollama_timeout: float = 600.0
    ollama_num_ctx: int = 8192
    ollama_chunk_tokens: int = 2000

    # Anthropic API (used when llm_provider="anthropic"). Key must be set via env.
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-haiku-4-5-20251001"
    anthropic_timeout: float = 120.0
    anthropic_chunk_tokens: int = 5000
    anthropic_max_output_tokens: int = 16384

    # Everything persistent lives under data_dir (sqlite db + uploaded files).
    data_dir: str = "./data"

    @property
    def db_path(self) -> Path:
        return Path(self.data_dir) / "mealplanner.db"

    @property
    def db_url(self) -> str:
        return f"sqlite:///{self.db_path}"

    @property
    def uploads_dir(self) -> Path:
        return Path(self.data_dir) / "uploads"


settings = Settings()
