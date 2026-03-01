from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "SPECTER API"
    environment: str = Field(default="development", alias="SPECTER_ENV")
    log_level: str = Field(default="INFO", alias="SPECTER_LOG_LEVEL")
    frontend_origin: str = Field(default="http://localhost:3000", alias="SPECTER_FRONTEND_ORIGIN")
    api_port: int = Field(default=8000, alias="SPECTER_API_PORT")

    convex_url: str | None = Field(default=None, alias="CONVEX_URL")
    mongodb_uri: str | None = Field(default=None, alias="MONGODB_URI")
    exa_api_key: str | None = Field(default=None, alias="EXA_API_KEY")
    browser_use_api_key: str | None = Field(default=None, alias="BROWSER_USE_API_KEY")
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    gemini_api_key: str | None = Field(default=None, alias="GEMINI_API_KEY")
    laminar_api_key: str | None = Field(default=None, alias="LMNR_PROJECT_API_KEY")
    anthropic_api_key: str | None = Field(default=None, alias="ANTHROPIC_API_KEY")
    telegram_bot_token: str | None = Field(default=None, alias="TELEGRAM_BOT_TOKEN")
    hibp_api_key: str | None = Field(default=None, alias="HIBP_API_KEY")
    pimeyes_account_pool: str = Field(default="[]", alias="PIMEYES_ACCOUNT_POOL")
    daytona_api_key: str | None = Field(default=None, alias="DAYTONA_API_KEY")
    daytona_api_url: str | None = Field(default=None, alias="DAYTONA_API_URL")
    supermemory_api_key: str | None = Field(default=None, alias="SUPERMEMORY_API_KEY")
    hud_api_key: str | None = Field(default=None, alias="HUD_API_KEY")

    def service_flags(self) -> dict[str, bool]:
        return {
            "convex": bool(self.convex_url),
            "mongodb": bool(self.mongodb_uri),
            "exa": bool(self.exa_api_key),
            "browser_use": bool(self.browser_use_api_key),
            "openai": bool(self.openai_api_key),
            "gemini": bool(self.gemini_api_key),
            "anthropic": bool(self.anthropic_api_key),
            "laminar": bool(self.laminar_api_key),
            "telegram": bool(self.telegram_bot_token),
            "hibp": bool(self.hibp_api_key),
            "pimeyes_pool": self.pimeyes_account_pool not in {"", "[]"},
            "daytona": bool(self.daytona_api_key),
            "supermemory": bool(self.supermemory_api_key),
            "hud": bool(self.hud_api_key),
        }


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
