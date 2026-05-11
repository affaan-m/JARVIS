from __future__ import annotations

import os
from unittest.mock import patch

from config import Settings

ALL_SERVICE_FLAGS = {
    "convex", "mongodb", "exa", "browser_use", "openai",
    "gemini", "anthropic", "laminar", "telegram", "hibp",
    "pimeyes_pool", "supermemory", "daytona", "hud", "agentmail",
    "pimeyes", "sixtyfour", "browser_use_profile",
}


def _settings_with_env(env: dict[str, str] | None = None) -> Settings:
    with patch.dict(os.environ, env or {}, clear=True):
        return Settings(_env_file=None)  # type: ignore[call-arg]


def test_settings_defaults() -> None:
    s = _settings_with_env()
    assert s.app_name == "JARVIS API"
    assert s.environment == "development"
    assert s.log_level == "INFO"
    assert s.frontend_origin == "http://localhost:3000"
    assert s.api_port == 8000


def test_settings_service_flags_all_unconfigured() -> None:
    s = _settings_with_env()
    flags = s.service_flags()

    assert isinstance(flags, dict)
    for key, value in flags.items():
        assert value is False, f"{key} should be False without env vars"


def test_settings_service_flags_with_convex_url() -> None:
    s = _settings_with_env({"CONVEX_URL": "https://convex.example.com"})
    flags = s.service_flags()
    assert flags["convex"] is True
    assert flags["mongodb"] is False


def test_settings_service_flags_with_exa_key() -> None:
    s = _settings_with_env({"EXA_API_KEY": "exa-test-key"})
    flags = s.service_flags()
    assert flags["exa"] is True


def test_settings_service_flags_with_all_keys() -> None:
    env = {
        "CONVEX_URL": "https://convex.example.com",
        "MONGODB_URI": "mongodb://localhost:27017",
        "EXA_API_KEY": "exa-key",
        "BROWSER_USE_API_KEY": "bu-key",
        "OPENAI_API_KEY": "sk-key",
        "GEMINI_API_KEY": "gem-key",
        "ANTHROPIC_API_KEY": "anthropic-key",
        "LMNR_PROJECT_API_KEY": "lam-key",
        "TELEGRAM_BOT_TOKEN": "bot-token",
        "HIBP_API_KEY": "hibp-key",
        "PIMEYES_ACCOUNT_POOL": '[{"email": "a@b.com"}]',
        "SUPERMEMORY_API_KEY": "sm-key",
        "DAYTONA_API_KEY": "daytona-key",
        "HUD_API_KEY": "hud-key",
        "AGENTMAIL_API_KEY": "agentmail-key",
        "PIMEYES_EMAIL": "pimeyes@example.com",
        "PIMEYES_PASSWORD": "pimeyes-password",
        "SIXTYFOUR_API_KEY": "sixtyfour-key",
        "BROWSER_USE_PROFILE_ID": "profile-id",
    }
    s = _settings_with_env(env)
    flags = s.service_flags()

    for key, value in flags.items():
        assert value is True, f"{key} should be True when configured"


def test_settings_pimeyes_pool_empty_string_is_unconfigured() -> None:
    s = _settings_with_env({"PIMEYES_ACCOUNT_POOL": ""})
    flags = s.service_flags()
    assert flags["pimeyes_pool"] is False


def test_settings_pimeyes_pool_empty_list_is_unconfigured() -> None:
    s = _settings_with_env()
    flags = s.service_flags()
    assert flags["pimeyes_pool"] is False


def test_settings_pimeyes_pool_with_data_is_configured() -> None:
    s = _settings_with_env({"PIMEYES_ACCOUNT_POOL": '[{"email":"test@test.com"}]'})
    flags = s.service_flags()
    assert flags["pimeyes_pool"] is True


def test_settings_service_flags_has_all_expected_keys() -> None:
    s = _settings_with_env()
    flags = s.service_flags()
    assert set(flags.keys()) == ALL_SERVICE_FLAGS
