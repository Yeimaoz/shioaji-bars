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
    with pytest.raises(ShioajiAuthError, match="SHIOAJI_API_KEY"):
        login()


def test_logout_calls_api():
    fake_api = MagicMock()
    logout(fake_api)
    fake_api.logout.assert_called_once()
