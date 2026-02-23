"""Client configuration."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class ClientSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="MYCROFT_CLIENT_",
        env_file=".env",
        env_file_encoding="utf-8",
    )

    server_url: str = "ws://localhost:8765/ws"
    api_key: str = ""


client_settings = ClientSettings()
