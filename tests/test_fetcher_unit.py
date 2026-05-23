from unittest.mock import MagicMock

import pandas as pd

from shioaji_bars.fetcher import fetch_kbars, fetch_snapshots


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
    # Verify rolling MXFR1 was the contract passed (not arbitrary dict item)
    args, kwargs = api.kbars.call_args
    assert kwargs.get("contract") is rolling or (args and args[0] is rolling)


def test_fetch_kbars_uses_explicit_contract_code():
    """Passing 'MXFM4' (specific delivery code) should look up that exact contract."""
    api = MagicMock()
    api.kbars.return_value = _mock_kbars_response()
    specific = MagicMock(code="MXFM4")
    # H2 fix: dict form for group; explicit code lookup uses dict key
    api.Contracts.Futures.MXF = {"MXFR1": MagicMock(code="MXFR1"), "MXFM4": specific}
    fetch_kbars(api, contract="MXFM4", interval="1m",
                start="2024-01-01", end="2024-01-02")
    args, kwargs = api.kbars.call_args
    assert kwargs.get("contract") is specific or (args and args[0] is specific)


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
