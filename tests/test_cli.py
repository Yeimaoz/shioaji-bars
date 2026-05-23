import sys
from unittest.mock import MagicMock, patch
import pandas as pd

from shioaji_bars.cli import main


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
