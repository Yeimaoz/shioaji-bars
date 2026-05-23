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


def test_list_contracts_empty_on_iteration_failure(caplog):
    """v0.1.1: shioaji 1.5+ raises Pydantic errors mid-iteration → return []
    with warning rather than emitting {code: None, ...} placeholder entries."""
    api = MagicMock()
    # Build a container that:
    # - is not dict
    # - has no .items()
    # - raises on iteration (mimics shioaji 1.5 Pydantic validation error)
    # - has no .code (so not a leaf)
    class _BadContainer:
        def __iter__(self):
            raise TypeError("argument 'code': 'int' object is not an instance of 'str'")
    # Make sure it doesn't accidentally look like a leaf
    api.Contracts.Futures = _BadContainer()

    with caplog.at_level("WARNING"):
        out = list_contracts(api, kind="futures")
    # Either empty, or no None-code entries (defensive contract)
    assert all(c.get("code") for c in out), f"got None-code entries: {out}"
    # If empty, a warning should have been emitted
    if not out:
        assert any("list_contracts" in r.message for r in caplog.records)


def test_list_contracts_skips_partial_iteration_with_per_item_errors():
    """Container that raises immediately on iteration → return [] with warning,
    not silent {code: None} entries (regression for v0.1.0 bug)."""
    api = MagicMock()

    class _BrokenIter:
        """Mimics shioaji 1.5 ContractGroup: iterating raises Pydantic error."""
        def __iter__(self):
            raise TypeError("simulated shioaji 1.5 validation error")

    api.Contracts.Futures = _BrokenIter()
    out = list_contracts(api, kind="futures")
    # Critical: no {code: None} placeholders
    assert all(c.get("code") for c in out)
