from unittest.mock import MagicMock, patch
import pytest

from shioaji_bars.session import login, logout, ShioajiAuthError


def test_login_with_explicit_credentials():
    fake_api = MagicMock()
    with patch("shioaji_bars.session.shioaji.Shioaji", return_value=fake_api) as ctor:
        api = login(api_key="key123", secret="sec456")
    assert api is fake_api
    fake_api.login.assert_called_once_with(api_key="key123", secret_key="sec456")
    ctor.assert_called_once()


def test_login_reads_from_env(monkeypatch):
    monkeypatch.setenv("SHIOAJI_API_KEY", "env_key")
    monkeypatch.setenv("SHIOAJI_SECRET", "env_secret")
    fake_api = MagicMock()
    with patch("shioaji_bars.session.shioaji.Shioaji", return_value=fake_api):
        _ = login()
    fake_api.login.assert_called_once_with(api_key="env_key", secret_key="env_secret")


def test_login_missing_credentials_raises(monkeypatch):
    monkeypatch.delenv("SHIOAJI_API_KEY", raising=False)
    monkeypatch.delenv("SHIOAJI_SECRET", raising=False)
    monkeypatch.delenv("SHIOAJI_SECRET_KEY", raising=False)
    with pytest.raises(ShioajiAuthError, match="SHIOAJI_API_KEY"):
        login()


def test_login_accepts_shioaji_secret_key_env_alias(monkeypatch):
    """v0.1.1: SHIOAJI_SECRET_KEY (shioaji-doc convention) is a valid alias."""
    monkeypatch.setenv("SHIOAJI_API_KEY", "env_key")
    monkeypatch.delenv("SHIOAJI_SECRET", raising=False)
    monkeypatch.setenv("SHIOAJI_SECRET_KEY", "env_secret_via_key_alias")
    fake_api = MagicMock()
    with patch("shioaji_bars.session.shioaji.Shioaji", return_value=fake_api):
        _ = login()
    fake_api.login.assert_called_once_with(
        api_key="env_key", secret_key="env_secret_via_key_alias"
    )


def test_login_prefers_shioaji_secret_over_secret_key(monkeypatch):
    """If both env vars set, SHIOAJI_SECRET wins (matches docstring order)."""
    monkeypatch.setenv("SHIOAJI_API_KEY", "env_key")
    monkeypatch.setenv("SHIOAJI_SECRET", "primary")
    monkeypatch.setenv("SHIOAJI_SECRET_KEY", "alias")
    fake_api = MagicMock()
    with patch("shioaji_bars.session.shioaji.Shioaji", return_value=fake_api):
        _ = login()
    fake_api.login.assert_called_once_with(api_key="env_key", secret_key="primary")


def test_logout_calls_api():
    fake_api = MagicMock()
    logout(fake_api)
    fake_api.logout.assert_called_once()
