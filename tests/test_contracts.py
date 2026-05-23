from unittest.mock import MagicMock
import pytest

from shioaji_bars.contracts import list_contracts


def _mock_api_with_futures():
    api = MagicMock()
    # shioaji exposes api.Contracts.Futures.MXF / MXFM4 etc as nested attrs
    mxf_apr = MagicMock(code="MXFM4", symbol="MTX",
                         delivery_date="2024-04-17")
    mxf_may = MagicMock(code="MXFK4", symbol="MTX",
                         delivery_date="2024-05-15")
    api.Contracts.Futures = {"MXF": {"MXFM4": mxf_apr, "MXFK4": mxf_may}}
    return api


def test_list_contracts_futures():
    api = _mock_api_with_futures()
    out = list_contracts(api, kind="futures")
    assert len(out) == 2
    codes = {c["code"] for c in out}
    assert codes == {"MXFM4", "MXFK4"}
    assert all(c["symbol"] == "MTX" for c in out)


def test_list_contracts_unknown_kind_raises():
    api = MagicMock()
    with pytest.raises(ValueError, match="kind"):
        list_contracts(api, kind="bogus")
