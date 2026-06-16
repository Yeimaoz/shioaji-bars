"""Fetch historical kbars + live snapshots via shioaji SDK."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import pandas as pd

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo  # type: ignore[no-redef]

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

_TAIPEI_TZ = ZoneInfo("Asia/Taipei")


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
                logger.warning(
                    "[_resolve_contract] R1 key %r not found in %s for shortcode %r "
                    "— R1 key unavailable, cannot safely resolve front-month contract",
                    rolling_key, type(group).__name__, contract,
                )
                raise ValueError(
                    f"Cannot resolve front-month contract for shortcode {contract!r}: "
                    f"R1 key {rolling_key!r} not found in group {type(group).__name__}. "
                    "Ensure shioaji SDK is up to date or use an explicit delivery code "
                    "(e.g. 'MXFM4') instead of a shortcode."
                )
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
    """Convert start/end argument to YYYY-MM-DD string in Taiwan local time (CST, UTC+8).

    shioaji's kbars API interprets the date string as Taiwan Standard Time (UTC+8).
    If a tz-aware datetime is given, it is first converted to Asia/Taipei before
    taking the date, so that e.g. datetime(2024,1,1,20,0,tzinfo=timezone.utc)
    correctly becomes '2024-01-02' (CST 04:00 next day).

    str arguments are passed through unchanged and assumed to already be in Taiwan
    local date format (YYYY-MM-DD).
    """
    if isinstance(t, datetime):
        if t.tzinfo is not None:
            t = t.astimezone(_TAIPEI_TZ)
        return t.strftime("%Y-%m-%d")
    return t  # assume already correct


def fetch_kbars(
    api: Any,
    contract: str,
    interval: str = "1m",
    start: str | datetime | None = None,
    end: str | datetime | None = None,
) -> pd.DataFrame:
    """Fetch historical kbars from shioaji.

    Args:
        api: logged-in shioaji.Shioaji() instance
        contract: "MTX" / "TXF" / "TMF" shortcode, "MXFM4"-style explicit
            delivery code, or 4-digit stock code.
        interval: INFORMATIONAL ONLY -- shioaji api.kbars always returns 1-min
            bars regardless of this arg. Kept for API symmetry with binance-bars.
            Resample downstream if you want 5m/15m/etc.
        start: YYYY-MM-DD str or datetime (tz-aware datetimes are converted to
            Asia/Taipei before extracting the date)
        end: YYYY-MM-DD str or datetime (same timezone handling as start)

    Returns:
        DataFrame cols: ts (UTC datetime), open, high, low, close, volume, amount
    """
    if interval != "1m":
        logger.warning(
            "[fetch_kbars] interval=%r is informational only — shioaji always returns "
            "1-min bars regardless of this argument. Resample downstream if needed.",
            interval,
        )
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


# Canonical fetch_ticks output schema. shioaji's Ticks object exposes 8 parallel
# lists: ts / close / volume / bid_price / bid_volume / ask_price / ask_volume /
# tick_type (see shioaji _core.pyi `class Ticks`). We rename `close` -> `price`
# (it is the trade print price, not a bar close) and keep all 8 fields — the
# bid/ask price columns are core to TW microstructure work.
_TICKS_COLUMNS = [
    "ts",
    "price",
    "volume",
    "bid_price",
    "ask_price",
    "bid_volume",
    "ask_volume",
    "tick_type",
]


def _empty_ticks_frame() -> pd.DataFrame:
    """A zero-row DataFrame with the canonical fetch_ticks dtypes."""
    return pd.DataFrame({
        "ts": pd.Series([], dtype="datetime64[ns, UTC]"),
        "price": pd.Series([], dtype="float64"),
        "volume": pd.Series([], dtype="int64"),
        "bid_price": pd.Series([], dtype="float64"),
        "ask_price": pd.Series([], dtype="float64"),
        "bid_volume": pd.Series([], dtype="int64"),
        "ask_volume": pd.Series([], dtype="int64"),
        "tick_type": pd.Series([], dtype="int8"),
    })


def fetch_ticks(api: Any, contract: str, date: str) -> pd.DataFrame:
    """Fetch a single trading day of raw tick-by-tick trades from shioaji.

    Stores native ticks verbatim — NO aggregation. (An aggTrades-style merge
    would be lossy and the exchange-side aggregate id cannot be reconstructed
    client-side; TW tick volumes do not require it.) Downstream consumers that
    want bar-level features aggregate themselves.

    Args:
        api: logged-in shioaji.Shioaji() instance.
        contract: "MTX"/"TXF"/"TMF" shortcode, "MXFM4"-style explicit delivery
            code, or 4-digit stock code (resolved via the same `_resolve_contract`
            path as `fetch_kbars`).
        date: single trading day, "YYYY-MM-DD" (Taiwan local date). One day per
            call — loop + resume for multi-day backfills.

    Returns:
        DataFrame with 8 columns (canonical order):
            ts          datetime64[ns, UTC]  trade timestamp (tz-aware)
            price       float64              trade print price (shioaji `close`)
            volume      int64                trade size
            bid_price   float64              best bid at print time
            ask_price   float64              best ask at print time
            bid_volume  int64                best-bid size
            ask_volume  int64                best-ask size
            tick_type   int8                 broker-side direction code
                                             (1=外盤/buy, 2=內盤/sell, 0=undetermined)

        Multiple trades may share the same `ts` — all rows are preserved
        (no row dedup). An empty day returns a typed zero-row frame, not a raise.
    """
    c = _resolve_contract(api, contract)
    raw = api.ticks(contract=c, date=date)

    ts = list(raw.ts)
    if not ts:
        return _empty_ticks_frame()

    df = pd.DataFrame({
        "ts": pd.to_datetime(ts, unit="ns", utc=True),
        "price": pd.Series(list(raw.close), dtype="float64"),
        "volume": pd.Series(list(raw.volume), dtype="int64"),
        "bid_price": pd.Series(list(raw.bid_price), dtype="float64"),
        "ask_price": pd.Series(list(raw.ask_price), dtype="float64"),
        "bid_volume": pd.Series(list(raw.bid_volume), dtype="int64"),
        "ask_volume": pd.Series(list(raw.ask_volume), dtype="int64"),
        "tick_type": pd.Series(list(raw.tick_type), dtype="int8"),
    })
    return df[_TICKS_COLUMNS]


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
