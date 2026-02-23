"""Server configuration via environment variables and config file."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ServerSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="MYCROFT_",
        env_file=".env",
        env_file_encoding="utf-8",
    )

    # Anthropic
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-20250514"
    anthropic_max_tokens: int = 8192

    # Tavily
    tavily_api_key: str = ""

    # Server
    host: str = "0.0.0.0"
    port: int = 8765
    api_keys: list[str] = Field(default_factory=list)  # allowed client API keys

    # Git docs repo
    docs_repo_url: str = ""  # e.g. git@github.com:user/mycroft-docs.git
    docs_repo_local_path: Path = Path("./data/docs-repo")

    # State storage
    data_dir: Path = Path("./data")

    @property
    def projects_dir(self) -> Path:
        return self.data_dir / "projects"

    def validate_api_key(self, key: str) -> bool:
        if not self.api_keys:
            return True  # no keys configured = open access (dev mode)
        return key in self.api_keys


settings = ServerSettings()
