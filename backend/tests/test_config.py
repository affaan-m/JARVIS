from __future__ import annotations

import os
from unittest.mock import patch

from config import Settings


def test_settings_defaults() -> None:
    s = Settings()
    assert s.app_name == "SPECTER API"
    assert s.environment == "development"
    assert s.log_level == "INFO"
    assert s.frontend_origin == "http://localhost:3000"
    assert s.api_port == 8000


def test_settings_service_flags_all_unconfigured() -> None:
    s = Settings()
    flags = s.service_flags()

    assert isinstance(flags, dict)
    for key, value in flags.items():
        assert value is False, f"{key} should be False without env vars"


def test_settings_service_flags_with_convex_url() -> None:
    with patch.dict(os.environ, {"CONVEX_URL": "https://convex.example.com"}):
        s = Settings()
    flags = s.service_flags()
    assert flags["convex"] is True
    assert flags["mongodb"] is False


def test_settings_service_flags_with_exa_key() -> None:
    with patch.dict(os.environ, {"EXA_API_KEY": "exa-test-key"}):
        s = Settings()
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
        "LAMINAR_API_KEY": "lam-key",
        "TELEGRAM_BOT_TOKEN": "bot-token",
        "HIBP_API_KEY": "hibp-key",
        "PIMEYES_ACCOUNT_POOL": '[{"email": "a@b.com"}]',
    }
    with patch.dict(os.environ, env):
        s = Settings()
    flags = s.service_flags()

    for key, value in flags.items():
        assert value is True, f"{key} should be True when configured"


def test_settings_pimeyes_pool_empty_string_is_unconfigured() -> None:
    with patch.dict(os.environ, {"PIMEYES_ACCOUNT_POOL": ""}):
        s = Settings()
    flags = s.service_flags()
    assert flags["pimeyes_pool"] is False


def test_settings_pimeyes_pool_empty_list_is_unconfigured() -> None:
    s = Settings()
    flags = s.service_flags()
    assert flags["pimeyes_pool"] is False


def test_settings_pimeyes_pool_with_data_is_configured() -> None:
    with patch.dict(os.environ, {"PIMEYES_ACCOUNT_POOL": '[{"email":"test@test.com"}]'}):
        s = Settings()
    flags = s.service_flags()
    assert flags["pimeyes_pool"] is True


def test_settings_service_flags_has_all_expected_keys() -> None:
    s = Settings()
    flags = s.service_flags()
    expected_keys = {
        "convex", "mongodb", "exa", "browser_use", "openai",
        "gemini", "laminar", "telegram", "hibp", "pimeyes_pool",
    }
    assert set(flags.keys()) == expected_keys
