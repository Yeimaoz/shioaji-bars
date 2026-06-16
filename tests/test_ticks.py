"""fetch_ticks single-day raw trades — schema / dtype / ts conversion / 8-col / same-ts fidelity.

All mock; no real shioaji (needs an account + would hit quota). The mock mimics
shioaji's columnar Ticks object (parallel lists), per shioaji _core.pyi:
    Ticks: ts / close / volume / bid_price / bid_volume / ask_price / ask_volume / tick_type
"""

import sys
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from shioaji_bars.fetcher import fetch_ticks
from shioaji_bars.parquet_io import Mode

# Canonical fetch_ticks output schema (8 cols). `close` is renamed to `price`;
# everything else keeps shioaji's native field name.
EXPECTED_COLS = [
    "ts",
    "price",
    "volume",
    "bid_price",
    "ask_price",
    "bid_volume",
    "ask_volume",
    "tick_type",
]


def _mock_ticks(*, n=2, same_ts=False):
    """Build a columnar Ticks-like object (parallel lists) like shioaji returns.

    ts are ns-epoch ints. If same_ts, both rows share the same ts (different
    price/volume) to exercise the no-dedup contract.
    """
    obj = MagicMock()
    if same_ts:
        obj.ts = [1704067200_000_000_000, 1704067200_000_000_000]
    else:
        obj.ts = [1704067200_000_000_000 + i * 1_000_000 for i in range(n)]
    obj.close = [100.0 + i for i in range(n)]
    obj.volume = [10 + i for i in range(n)]
    obj.bid_price = [99.5 + i for i in range(n)]
    obj.bid_volume = [5 + i for i in range(n)]
    obj.ask_price = [100.5 + i for i in range(n)]
    obj.ask_volume = [6 + i for i in range(n)]
    obj.tick_type = [1, 2][:n] if n <= 2 else [1] * n
    return obj


def _mock_empty_ticks():
    obj = MagicMock()
    obj.ts = []
    obj.close = []
    obj.volume = []
    obj.bid_price = []
    obj.bid_volume = []
    obj.ask_price = []
    obj.ask_volume = []
    obj.tick_type = []
    return obj


def _api_with_contract():
    api = MagicMock()
    rolling = MagicMock(code="MXFR1")
    api.Contracts.Futures.MXF = {"MXFR1": rolling}
    return api, rolling


def test_fetch_ticks_schema_and_dtypes():
    api, _ = _api_with_contract()
    api.ticks.return_value = _mock_ticks(n=2)

    df = fetch_ticks(api, contract="MTX", date="2024-01-01")

    assert isinstance(df, pd.DataFrame)
    assert list(df.columns) == EXPECTED_COLS, "8-col canonical schema (incl bid/ask price)"
    assert len(df) == 2
    # ts tz-aware UTC
    assert df["ts"].dt.tz is not None
    assert str(df["ts"].dt.tz) in ("UTC", "utc")
    # price (renamed from close) + bid/ask prices are float
    assert df["price"].dtype == "float64"
    assert df["bid_price"].dtype == "float64"
    assert df["ask_price"].dtype == "float64"
    # volumes int64
    assert df["volume"].dtype == "int64"
    assert df["bid_volume"].dtype == "int64"
    assert df["ask_volume"].dtype == "int64"
    # tick_type int8 (broker-side direction code; small domain)
    assert df["tick_type"].dtype == "int8"
    # close -> price rename carried the value
    assert df["price"].iloc[0] == 100.0


def test_fetch_ticks_empty_day():
    """Empty day returns a typed empty DataFrame (8 cols), not a raise."""
    api, _ = _api_with_contract()
    api.ticks.return_value = _mock_empty_ticks()

    df = fetch_ticks(api, contract="MTX", date="2024-01-01")
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 0
    assert list(df.columns) == EXPECTED_COLS
    # dtypes still correct on empty frame
    assert str(df["ts"].dt.tz) in ("UTC", "utc")
    assert df["tick_type"].dtype == "int8"
    assert df["price"].dtype == "float64"


def test_fetch_ticks_same_ts_preserved():
    """Two trades at the SAME ts must both survive — fetch_ticks does no row dedup."""
    api, _ = _api_with_contract()
    api.ticks.return_value = _mock_ticks(n=2, same_ts=True)

    df = fetch_ticks(api, contract="MTX", date="2024-01-01")
    assert len(df) == 2, "same-ts rows must NOT be deduped"
    assert df["ts"].nunique() == 1
    # distinct trades preserved
    assert df["price"].tolist() == [100.0, 101.0]


def test_fetch_ticks_resolves_contract():
    """fetch_ticks routes contract string through _resolve_contract before api.ticks."""
    api, rolling = _api_with_contract()
    api.ticks.return_value = _mock_ticks(n=1)

    fetch_ticks(api, contract="MTX", date="2024-06-13")
    args, kwargs = api.ticks.call_args
    # contract may be positional or kw depending on impl; accept either
    passed = kwargs.get("contract") if "contract" in kwargs else (args[0] if args else None)
    assert passed is rolling, "resolved front-month MXFR1 must be passed to api.ticks"


def test_fetch_ticks_single_date_not_range():
    """Signature takes a single date str (not start/end); date is forwarded to api.ticks."""
    api, _ = _api_with_contract()
    api.ticks.return_value = _mock_ticks(n=1)

    fetch_ticks(api, contract="MTX", date="2024-06-13")
    _args, kwargs = api.ticks.call_args
    assert kwargs.get("date") == "2024-06-13"


def test_fetch_ticks_unknown_contract_raises():
    api = MagicMock()
    api.Contracts.Futures = None
    api.Contracts.Stocks = None
    with pytest.raises(ValueError, match="could not resolve contract"):
        fetch_ticks(api, contract="FAKE", date="2024-01-01")


# ---- CLI: fetch-ticks subcommand ----


def test_cli_fetch_ticks_invokes_fetch(tmp_path):
    """`fetch-ticks` subcommand: login -> fetch_ticks -> write_parquet(OVERWRITE) -> logout."""
    from shioaji_bars.cli import main

    out = tmp_path / "TXF" / "2026-06-13.parquet"
    df = pd.DataFrame({
        "ts": pd.to_datetime(["2026-06-13T01:00:00Z"], utc=True),
        "price": [18000.0],
        "volume": pd.Series([3], dtype="int64"),
        "bid_price": [17999.0],
        "ask_price": [18001.0],
        "bid_volume": pd.Series([5], dtype="int64"),
        "ask_volume": pd.Series([4], dtype="int64"),
        "tick_type": pd.Series([1], dtype="int8"),
    })
    fake_api = MagicMock()
    with patch("shioaji_bars.cli.login", return_value=fake_api) as p_login, \
         patch("shioaji_bars.cli.logout") as p_logout, \
         patch("shioaji_bars.cli.fetch_ticks", return_value=df) as p_fetch, \
         patch("shioaji_bars.cli.write_parquet") as p_write, \
         patch.object(sys, "argv", ["shioaji-bars", "fetch-ticks",
                                     "--contract", "TXF",
                                     "--date", "2026-06-13",
                                     "--output", str(out)]):
        rc = main()

    assert rc == 0
    p_fetch.assert_called_once()
    _fargs, fkwargs = p_fetch.call_args
    assert fkwargs.get("contract") == "TXF"
    assert fkwargs.get("date") == "2026-06-13"
    # write_parquet must default to OVERWRITE (per-day file, no by-ts dedup)
    _wargs, wkwargs = p_write.call_args
    assert wkwargs.get("mode") == Mode.OVERWRITE
    # login/logout lifecycle paired
    p_login.assert_called_once()
    p_logout.assert_called_once()


def test_cli_fetch_ticks_empty_writes_typed_empty(tmp_path):
    """fetch-ticks on an empty day still calls write_parquet (which no-ops on empty)."""
    from shioaji_bars.cli import main

    out = tmp_path / "TXF" / "2026-06-14.parquet"
    empty = fetch_ticks_empty_frame()
    fake_api = MagicMock()
    with patch("shioaji_bars.cli.login", return_value=fake_api), \
         patch("shioaji_bars.cli.logout"), \
         patch("shioaji_bars.cli.fetch_ticks", return_value=empty), \
         patch.object(sys, "argv", ["shioaji-bars", "fetch-ticks",
                                     "--contract", "TXF",
                                     "--date", "2026-06-14",
                                     "--output", str(out)]):
        rc = main()
    assert rc == 0


def fetch_ticks_empty_frame():
    """Helper: a typed empty ticks frame matching EXPECTED_COLS."""
    from shioaji_bars.fetcher import fetch_ticks as _ft
    api, _r = _api_with_contract()
    api.ticks.return_value = _mock_empty_ticks()
    return _ft(api, contract="MTX", date="2024-01-01")


# ---- parquet round-trip + same-ts fidelity through OVERWRITE ----


def test_ticks_parquet_roundtrip_same_ts(tmp_path):
    """write_parquet(OVERWRITE) then read back: same-ts rows survive, dtypes intact."""
    from shioaji_bars.parquet_io import write_parquet

    api, _ = _api_with_contract()
    api.ticks.return_value = _mock_ticks(n=2, same_ts=True)
    df = fetch_ticks(api, contract="MTX", date="2024-01-01")

    path = tmp_path / "MTX" / "2024-01-01.parquet"
    write_parquet(df, path, mode=Mode.OVERWRITE)
    out = pd.read_parquet(path)

    assert len(out) == 2, "OVERWRITE must NOT by-ts dedup same-ts trades"
    assert list(out.columns) == EXPECTED_COLS
    assert out["ts"].nunique() == 1
    assert out["price"].tolist() == [100.0, 101.0]


def test_ticks_overwrite_full_replace(tmp_path):
    """Re-fetching a day OVERWRITEs the whole file (no concat with stale rows)."""
    from shioaji_bars.parquet_io import write_parquet

    api, _ = _api_with_contract()
    api.ticks.return_value = _mock_ticks(n=2)
    df1 = fetch_ticks(api, contract="MTX", date="2024-01-01")

    path = tmp_path / "MTX" / "2024-01-01.parquet"
    write_parquet(df1, path, mode=Mode.OVERWRITE)

    api.ticks.return_value = _mock_ticks(n=1)
    df2 = fetch_ticks(api, contract="MTX", date="2024-01-01")
    write_parquet(df2, path, mode=Mode.OVERWRITE)

    out = pd.read_parquet(path)
    assert len(out) == 1, "second OVERWRITE fully replaces, not concat"
