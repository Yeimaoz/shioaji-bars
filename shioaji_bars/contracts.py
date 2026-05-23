"""List shioaji contracts (futures / options / stocks / indexs)."""

from __future__ import annotations

from typing import Any, Literal

Kind = Literal["futures", "options", "stocks", "indexs"]

_KIND_TO_ATTR = {
    "futures": "Futures",
    "options": "Options",
    "stocks": "Stocks",
    "indexs": "Indexs",
}


def list_contracts(api: Any, kind: Kind = "futures") -> list[dict]:
    """Iterate api.Contracts.{Futures|Options|Stocks|Indexs} -> list of dicts.

    Returns dicts with: code, symbol, delivery_date (futures/options only).
    """
    if kind not in _KIND_TO_ATTR:
        raise ValueError(f"unknown kind: {kind!r}")
    root = getattr(api.Contracts, _KIND_TO_ATTR[kind])

    out: list[dict] = []

    def _flatten(node: Any) -> None:
        # shioaji Contracts containers are dict or dict-like at branch levels;
        # leaf nodes are Contract instances (not pure dicts).
        if isinstance(node, dict):
            for _key, val in node.items():
                _flatten(val)
        elif hasattr(node, "__class__") and hasattr(node, "items") and callable(
            getattr(type(node), "items", None)
        ) and not hasattr(node, "code"):
            # dict-like container (non-dict with .items() and no contract attrs)
            for _key, val in node.items():
                _flatten(val)
        else:
            # leaf = a Contract instance
            out.append({
                "code": getattr(node, "code", None),
                "symbol": getattr(node, "symbol", None),
                "delivery_date": getattr(node, "delivery_date", None),
            })

    _flatten(root)
    return out
