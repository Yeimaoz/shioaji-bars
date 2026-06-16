"""shioaji-bars -- historical OHLCV fetcher via shioaji SDK."""

from importlib.metadata import PackageNotFoundError, version

from shioaji_bars.contracts import list_contracts
from shioaji_bars.fetcher import fetch_kbars, fetch_snapshots, fetch_ticks
from shioaji_bars.parquet_io import Mode, read_last_ts, write_parquet
from shioaji_bars.session import ShioajiAuthError, login, logout

try:
    __version__ = version("shioaji-bars")
except PackageNotFoundError:  # running from source without install
    __version__ = "0.0.0+dev"

__all__ = [
    "login",
    "logout",
    "list_contracts",
    "fetch_kbars",
    "fetch_snapshots",
    "fetch_ticks",
    "Mode",
    "read_last_ts",
    "write_parquet",
    "ShioajiAuthError",
]
