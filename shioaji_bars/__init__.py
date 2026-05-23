"""shioaji-bars -- historical OHLCV fetcher via shioaji SDK."""

from shioaji_bars.contracts import list_contracts
from shioaji_bars.fetcher import fetch_kbars, fetch_snapshots
from shioaji_bars.parquet_io import Mode, read_last_ts, write_parquet
from shioaji_bars.session import ShioajiAuthError, login, logout

__version__ = "0.1.1"

__all__ = [
    "login",
    "logout",
    "list_contracts",
    "fetch_kbars",
    "fetch_snapshots",
    "Mode",
    "read_last_ts",
    "write_parquet",
    "ShioajiAuthError",
]
