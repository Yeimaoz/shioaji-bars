"""Fetch historical kbars + live snapshots via shioaji SDK."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

# Map common short symbols -> primary contract attribute path in api.Contracts.
# Spec design D8 §8 open question: "smart-detect (length+digit pattern)".
# Phase 1a impl: if contract looks like a known shortcode, resolve via
# api.Contracts.Futures.{SHORT_TO_CODE[short]}; if it looks like an explicit
# delivery code (e.g. MXFM4 with digit+letter at end), look up nested.
# Else assume stock code (digits).

_FUT_SHORTCODE_MAP = {
    "MTX": "MXF",   # 小台
    "TXF": "TXF",   # 大台
    "TMF": "TMF",   # 微台
}


def _resolve_contract(api: Any, contract: str) -> Any:
    """Resolve a user-given contract string to a shioaji.Contract instance.

    Strategy:
    - Stock code (all digits, length 4): api.Contracts.Stocks.TSE.{code}
    - Shortcode (MTX/TXF/TMF): pick the nearest-month from api.Contracts.Futures.{MXF/TXF/TMF}
      Prefers MXFR1/TXFR1/TMFR1 rolling front-month key (shioaji standard).
    - Explicit delivery code (e.g. MXFM4): nested lookup
    """
    # Try Futures lookup first
    fut = getattr(api.Contracts, "Futures", None)
    if fut is not None:
        if contract in _FUT_SHORTCODE_MAP:
            # shortcode -> rolling front-month (MXFR1/TXFR1/TMFR1 — shioaji standard)
            group_key = _FUT_SHORTCODE_MAP[contract]
            group = getattr(fut, group_key, None)
            if group is not None:
                # H1 fix: Prefer explicit rolling key (R1 = front-month rolling)
                rolling_key = group_key + "R1"
                # group may be dict-like or attr-accessor -- try both
                if isinstance(group, dict) and rolling_key in group:
                    return group[rolling_key]
                if hasattr(group, "items") and rolling_key in group:
                    return group[rolling_key]
                if hasattr(group, rolling_key):
                    return getattr(group, rolling_key)
                # Fallback: iterate values (dict iteration unordered -- last resort)
                if isinstance(group, dict):
                    for _k, v in group.items():
                        return v
                if hasattr(group, "items"):
                    for _k, v in group.items():
                        return v
                return group
        # Try explicit delivery code (e.g. MXFM4)
        prefix = contract[:3]
        if hasattr(fut, prefix):
            group = getattr(fut, prefix)
            if hasattr(group, contract):
                return getattr(group, contract)
            # also try dict-key lookup
            if isinstance(group, dict) and contract in group:
                return group[contract]

    # Stocks fallback (4-digit code)
    if contract.isdigit() and len(contract) == 4:
        stocks = getattr(api.Contracts, "Stocks", None)
        if stocks is not None:
            # Try TSE first, then OTC
            for exchange in ("TSE", "OTC"):
                exg = getattr(stocks, exchange, None)
                if exg is not None:
                    # exg can be dict-like or attribute-access
                    if isinstance(exg, dict) and contract in exg:
                        return exg[contract]
                    if hasattr(exg, "items") and contract in exg:
                        return exg[contract]
                    if hasattr(exg, contract):
                        return getattr(exg, contract)

    raise ValueError(f"could not resolve contract: {contract!r}")


def _to_iso_date(t: str | datetime) -> str:
    """shioaji.kbars expects YYYY-MM-DD strings."""
    if isinstance(t, datetime):
        return t.strftime("%Y-%m-%d")
    return t  # assume already correct


def fetch_kbars(
    api: Any,
    contract: str,
    interval: str = "1m",
    start: str | datetime = None,
    end: str | datetime = None,
) -> pd.DataFrame:
    """Fetch historical kbars from shioaji.

    Args:
        api: logged-in shioaji.Shioaji() instance
        contract: "MTX" / "TXF" / "TMF" shortcode, "MXFM4"-style explicit
            delivery code, or 4-digit stock code.
        interval: INFORMATIONAL ONLY -- shioaji api.kbars always returns 1-min
            bars regardless of this arg. Kept for API symmetry with binance-bars.
            Resample downstream if you want 5m/15m/etc.
        start: YYYY-MM-DD str or datetime
        end: YYYY-MM-DD str or datetime

    Returns:
        DataFrame cols: ts (UTC datetime), open, high, low, close, volume, amount
    """
    c = _resolve_contract(api, contract)
    if start is None or end is None:
        raise ValueError("start and end required for fetch_kbars")
    raw = api.kbars(contract=c, start=_to_iso_date(start), end=_to_iso_date(end))
    # shioaji returns object with attribute lists (ts in ns)
    df = pd.DataFrame({
        "ts": pd.to_datetime(list(raw.ts), unit="ns", utc=True),
        "open": list(raw.Open),
        "high": list(raw.High),
        "low": list(raw.Low),
        "close": list(raw.Close),
        "volume": list(raw.Volume),
        "amount": list(raw.Amount),
    })
    return df


def fetch_snapshots(api: Any, contracts: list[str]) -> list[dict]:
    """Fetch current snapshot quotes for multiple contracts."""
    resolved = [_resolve_contract(api, c) for c in contracts]
    snaps = api.snapshots(resolved)
    out = []
    for s in snaps:
        out.append({
            "code": getattr(s, "code", None),
            "close": getattr(s, "close", None),
            "volume": getattr(s, "volume", None),
            "ts": getattr(s, "ts", None),
        })
    return out
