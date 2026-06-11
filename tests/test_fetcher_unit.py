from datetime import datetime, timezone
from unittest.mock import MagicMock

import pandas as pd
import pytest

from shioaji_bars.fetcher import fetch_kbars, fetch_snapshots, _to_iso_date


def _mock_kbars_response():
    """shioaji api.kbars returns object with .ts/.Open/.High/.Low/.Close/.Volume/.Amount lists."""
    obj = MagicMock()
    obj.ts = [1704067200_000_000_000, 1704067260_000_000_000]  # ns int
    obj.Open = [100.0, 101.0]
    obj.High = [105.0, 106.0]
    obj.Low = [95.0, 96.0]
    obj.Close = [102.0, 103.0]
    obj.Volume = [1000, 1100]
    obj.Amount = [102000.0, 113300.0]
    return obj


def test_fetch_kbars_returns_dataframe():
    api = MagicMock()
    api.kbars.return_value = _mock_kbars_response()
    # H2 fix: mock as dict so _resolve_contract dict-branch works
    rolling = MagicMock(code="MXFR1")
    api.Contracts.Futures.MXF = {"MXFR1": rolling, "MXFM4": MagicMock(code="MXFM4")}

    df = fetch_kbars(api, contract="MTX", interval="1m",
                     start="2024-01-01", end="2024-01-02")
    assert isinstance(df, pd.DataFrame)
    assert list(df.columns) == ["ts", "open", "high", "low", "close",
                                 "volume", "amount"]
    assert len(df) == 2
    assert df["close"].iloc[0] == 102.0
    # Verify rolling MXFR1 was the contract passed (disjunction fixed: kwargs-only)
    _args, kwargs = api.kbars.call_args
    assert kwargs.get("contract") is rolling


def test_fetch_kbars_ts_column_is_utc():
    """ts column must be UTC-aware; README API contract."""
    api = MagicMock()
    api.kbars.return_value = _mock_kbars_response()
    rolling = MagicMock(code="MXFR1")
    api.Contracts.Futures.MXF = {"MXFR1": rolling}

    df = fetch_kbars(api, contract="MTX", interval="1m",
                     start="2024-01-01", end="2024-01-02")
    assert df["ts"].dt.tz is not None, "ts column must be tz-aware"
    assert str(df["ts"].dt.tz) in ("UTC", "utc"), f"expected UTC tz, got {df['ts'].dt.tz}"


def test_fetch_kbars_uses_explicit_contract_code():
    """Passing 'MXFM4' (specific delivery code) should look up that exact contract."""
    api = MagicMock()
    api.kbars.return_value = _mock_kbars_response()
    specific = MagicMock(code="MXFM4")
    # H2 fix: dict form for group; explicit code lookup uses dict key
    api.Contracts.Futures.MXF = {"MXFR1": MagicMock(code="MXFR1"), "MXFM4": specific}
    fetch_kbars(api, contract="MXFM4", interval="1m",
                start="2024-01-01", end="2024-01-02")
    _args, kwargs = api.kbars.call_args
    assert kwargs.get("contract") is specific


def test_fetch_kbars_raises_when_start_is_none():
    """start=None must raise ValueError immediately."""
    api = MagicMock()
    rolling = MagicMock(code="MXFR1")
    api.Contracts.Futures.MXF = {"MXFR1": rolling}

    with pytest.raises(ValueError, match="start and end required"):
        fetch_kbars(api, contract="MTX", start=None, end="2024-01-02")


def test_fetch_kbars_raises_when_end_is_none():
    """end=None must raise ValueError immediately."""
    api = MagicMock()
    rolling = MagicMock(code="MXFR1")
    api.Contracts.Futures.MXF = {"MXFR1": rolling}

    with pytest.raises(ValueError, match="start and end required"):
        fetch_kbars(api, contract="MTX", start="2024-01-01", end=None)


def test_fetch_kbars_raises_for_unknown_contract():
    """Unresolvable contract string must raise ValueError."""
    api = MagicMock()
    api.Contracts.Futures = None
    api.Contracts.Stocks = None

    with pytest.raises(ValueError, match="could not resolve contract"):
        fetch_kbars(api, contract="FAKE", start="2024-01-01", end="2024-01-02")


def test_fetch_kbars_stock_code_uses_tse_path():
    """4-digit stock code must resolve via api.Contracts.Stocks.TSE."""
    api = MagicMock()
    api.kbars.return_value = _mock_kbars_response()
    stock_contract = MagicMock(code="2330")
    api.Contracts.Futures = None
    api.Contracts.Stocks.TSE = {"2330": stock_contract}

    fetch_kbars(api, contract="2330", start="2024-01-01", end="2024-01-02")
    _args, kwargs = api.kbars.call_args
    assert kwargs.get("contract") is stock_contract


def test_fetch_kbars_r1_fallback_missing_raises_valueerror():
    """If R1 key is absent from the group, _resolve_contract must raise ValueError
    rather than silently returning the group object (wrong-contract bug)."""
    api = MagicMock()
    # Group has only non-R1 entries — no MXFR1 key
    other = MagicMock(code="MXFM4")
    api.Contracts.Futures.MXF = {"MXFM4": other}

    with pytest.raises(ValueError, match="Cannot resolve front-month"):
        fetch_kbars(api, contract="MTX", start="2024-01-01", end="2024-01-02")


def test_fetch_kbars_r1_fallback_logs_warning(caplog):
    """When R1 key is absent, a warning must be logged before the ValueError."""
    api = MagicMock()
    api.Contracts.Futures.MXF = {"MXFM4": MagicMock(code="MXFM4")}

    with caplog.at_level("WARNING"), pytest.raises(ValueError):
        fetch_kbars(api, contract="MTX", start="2024-01-01", end="2024-01-02")

    assert any("R1 key" in r.message for r in caplog.records), (
        "expected warning about missing R1 key"
    )


def test_fetch_kbars_interval_non_1m_logs_warning(caplog):
    """Passing interval != '1m' must emit a warning (shioaji ignores the value)."""
    api = MagicMock()
    api.kbars.return_value = _mock_kbars_response()
    rolling = MagicMock(code="MXFR1")
    api.Contracts.Futures.MXF = {"MXFR1": rolling}

    with caplog.at_level("WARNING"):
        fetch_kbars(api, contract="MTX", interval="5m",
                    start="2024-01-01", end="2024-01-02")

    assert any("interval" in r.message and "informational" in r.message
               for r in caplog.records), (
        "expected warning about interval being informational-only"
    )


def test_to_iso_date_naive_datetime():
    """Naive datetime uses strftime directly (no tz conversion)."""
    dt = datetime(2024, 1, 15, 8, 30)
    assert _to_iso_date(dt) == "2024-01-15"


def test_to_iso_date_utc_datetime_near_cst_midnight():
    """UTC 20:00 on Jan 1 = CST 04:00 Jan 2 → should return '2024-01-02'."""
    dt = datetime(2024, 1, 1, 20, 0, tzinfo=timezone.utc)
    assert _to_iso_date(dt) == "2024-01-02"


def test_to_iso_date_str_passthrough():
    """String input passes through unchanged."""
    assert _to_iso_date("2024-03-21") == "2024-03-21"


def test_fetch_snapshots_returns_list_of_dicts():
    api = MagicMock()
    snap1 = MagicMock(code="MXFR1", close=18000.0, volume=12345,
                       ts=1704067260_000_000_000)
    snap2 = MagicMock(code="TXFR1", close=18500.0, volume=23456,
                       ts=1704067260_000_000_000)
    api.snapshots.return_value = [snap1, snap2]
    api.Contracts.Futures.MXF = {"MXFR1": MagicMock(code="MXFR1")}
    api.Contracts.Futures.TXF = {"TXFR1": MagicMock(code="TXFR1")}

    out = fetch_snapshots(api, contracts=["MTX", "TXF"])
    assert isinstance(out, list)
    assert len(out) == 2
    assert {s["code"] for s in out} == {"MXFR1", "TXFR1"}
