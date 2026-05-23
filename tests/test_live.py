"""Real shioaji API tests — require SHIOAJI_API_KEY + SHIOAJI_SECRET env vars.

These are USER-RUN tests. They double as a capability report: which PASS =
your token can access what.

Run:
    export SHIOAJI_API_KEY=... SHIOAJI_SECRET=...
    pytest -m live -v
"""

import os
from datetime import datetime, timedelta

import pytest

from shioaji_bars import (
    fetch_kbars, fetch_snapshots, list_contracts, login, logout,
)


@pytest.fixture(scope="module")
def api():
    if not (os.environ.get("SHIOAJI_API_KEY") and os.environ.get("SHIOAJI_SECRET")):
        pytest.skip("SHIOAJI_API_KEY/SHIOAJI_SECRET not set; skipping live tests")
    a = login()
    yield a
    logout(a)


@pytest.mark.live
def test_login_succeeds(api):
    assert api is not None


@pytest.mark.live
def test_list_futures(api):
    out = list_contracts(api, kind="futures")
    assert len(out) > 0
    codes = {c["code"] for c in out}
    # at least one MTX-prefixed contract
    assert any(c.startswith("MXF") for c in codes)


@pytest.mark.live
def test_list_options(api):
    out = list_contracts(api, kind="options")
    assert len(out) > 0


@pytest.mark.live
def test_list_stocks(api):
    out = list_contracts(api, kind="stocks")
    assert len(out) > 100  # TSE has thousands


@pytest.mark.live
def test_fetch_kbar_mtx_recent(api):
    # last full trading day
    end = datetime.now()
    start = end - timedelta(days=7)
    df = fetch_kbars(api, contract="MTX", interval="1m",
                     start=start.strftime("%Y-%m-%d"),
                     end=end.strftime("%Y-%m-%d"))
    assert len(df) > 0
    assert df["close"].min() > 0


@pytest.mark.live
def test_fetch_kbar_2330_recent(api):
    """Individual stock (TSMC). Some tokens lack stock-data scope -> expected FAIL for those."""
    end = datetime.now()
    start = end - timedelta(days=7)
    df = fetch_kbars(api, contract="2330", interval="1m",
                     start=start.strftime("%Y-%m-%d"),
                     end=end.strftime("%Y-%m-%d"))
    assert len(df) > 0


@pytest.mark.live
def test_snapshots_mtx(api):
    out = fetch_snapshots(api, contracts=["MTX"])
    assert len(out) == 1
    assert out[0]["code"] is not None
