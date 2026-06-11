import sys
from unittest.mock import MagicMock, patch
import pandas as pd

from shioaji_bars.cli import main, _cmd_fetch


def test_cli_list_contracts_dispatches():
    fake_api = MagicMock()
    with patch("shioaji_bars.cli.login", return_value=fake_api), \
         patch("shioaji_bars.cli.logout"), \
         patch("shioaji_bars.cli.list_contracts",
               return_value=[{"code": "MXFM4", "symbol": "MTX",
                              "delivery_date": "2024-04-17"}]) as lc, \
         patch.object(sys, "argv", ["shioaji-bars", "list-contracts",
                                     "--kind", "futures"]):
        rc = main()
    assert rc == 0
    lc.assert_called_once_with(fake_api, kind="futures")


def test_cli_fetch_writes_parquet(tmp_path):
    fake_api = MagicMock()
    df = pd.DataFrame({
        "ts": pd.to_datetime(["2024-01-01T00:00:00Z"], utc=True),
        "open": [100.0], "high": [101.0], "low": [99.0], "close": [100.5],
        "volume": [1000], "amount": [100500.0],
    })
    out = tmp_path / "MTX.parquet"
    with patch("shioaji_bars.cli.login", return_value=fake_api), \
         patch("shioaji_bars.cli.logout"), \
         patch("shioaji_bars.cli.fetch_kbars", return_value=df), \
         patch.object(sys, "argv", ["shioaji-bars", "fetch",
                                     "--contract", "MTX",
                                     "--interval", "1m",
                                     "--start", "2024-01-01",
                                     "--end", "2024-01-02",
                                     "--output", str(out),
                                     "--mode", "overwrite"]):
        rc = main()
    assert rc == 0
    assert out.exists()


def test_cmd_fetch_empty_df_overwrite_does_not_destroy_existing(tmp_path):
    """_cmd_fetch with empty fetch result must NOT overwrite an existing parquet.

    Regression for: empty df silently destroys existing data in OVERWRITE mode.
    """
    import argparse
    from shioaji_bars.parquet_io import write_parquet, Mode

    # Pre-create parquet with existing data
    existing_df = pd.DataFrame({
        "ts": pd.to_datetime(["2024-01-01T00:00:00Z"], utc=True),
        "open": [100.0], "high": [101.0], "low": [99.0], "close": [100.5],
        "volume": [1000], "amount": [100500.0],
    })
    out = tmp_path / "MTX.parquet"
    write_parquet(existing_df, out, mode=Mode.OVERWRITE)

    # fetch_kbars returns empty df
    empty_df = pd.DataFrame(columns=existing_df.columns)
    fake_api = MagicMock()
    args = argparse.Namespace(
        contract="MTX", interval="1m",
        start="2024-01-01", end="2024-01-01",
        output=str(out), mode="overwrite",
    )
    with patch("shioaji_bars.cli.login", return_value=fake_api), \
         patch("shioaji_bars.cli.logout"), \
         patch("shioaji_bars.cli.fetch_kbars", return_value=empty_df):
        rc = _cmd_fetch(args)

    assert rc == 0
    result = pd.read_parquet(out)
    assert len(result) == 1, "existing parquet must not be destroyed by empty fetch"


def test_cmd_fetch_empty_df_append_does_not_modify_existing(tmp_path):
    """_cmd_fetch with empty fetch result + append mode must leave file unchanged."""
    import argparse
    from shioaji_bars.parquet_io import write_parquet, Mode

    existing_df = pd.DataFrame({
        "ts": pd.to_datetime(["2024-01-01T00:00:00Z"], utc=True),
        "open": [100.0], "high": [101.0], "low": [99.0], "close": [100.5],
        "volume": [1000], "amount": [100500.0],
    })
    out = tmp_path / "MTX.parquet"
    write_parquet(existing_df, out, mode=Mode.OVERWRITE)
    mtime_before = out.stat().st_mtime

    empty_df = pd.DataFrame(columns=existing_df.columns)
    fake_api = MagicMock()
    args = argparse.Namespace(
        contract="MTX", interval="1m",
        start="2024-01-01", end="2024-01-01",
        output=str(out), mode="append",
    )
    with patch("shioaji_bars.cli.login", return_value=fake_api), \
         patch("shioaji_bars.cli.logout"), \
         patch("shioaji_bars.cli.fetch_kbars", return_value=empty_df):
        rc = _cmd_fetch(args)

    assert rc == 0
    assert out.stat().st_mtime == mtime_before, "file must not be touched"
