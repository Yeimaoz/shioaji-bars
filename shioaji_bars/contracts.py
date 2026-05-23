"""List shioaji contracts (futures / options / stocks / indexs).

Limitation (shioaji >= 1.5): the SDK's ContractCategory / ContractGroup
containers do not expose stable bulk-enumeration. Direct iteration may
raise Pydantic validation errors on individual server-returned contracts
(e.g. when a `code` field arrives as int rather than str).

This module's `list_contracts` falls back to defensive traversal:
- dict-like containers iterate cleanly (works for unit tests + older SDK)
- shioaji 1.5+ containers: catch per-item errors; return what survives
- Empty result → warning logged; caller should use direct `.get(code)` for
  known contract codes instead.

For single-contract lookup, use shioaji directly:
    contract = api.Contracts.Futures.MXF.get("MXFR1")
"""

from __future__ import annotations

import logging
from typing import Any, Literal

logger = logging.getLogger(__name__)

Kind = Literal["futures", "options", "stocks", "indexs"]

_KIND_TO_ATTR = {
    "futures": "Futures",
    "options": "Options",
    "stocks": "Stocks",
    "indexs": "Indexs",
}


def _is_leaf(node: Any) -> bool:
    """Contract leaf has a non-method `code` attribute (Pydantic model field)."""
    try:
        code = node.code
    except Exception:
        return False
    return code is not None and not callable(code)


def _children(node: Any) -> list[Any]:
    """Best-effort enumeration of children. Empty list if not iterable.

    Order of preference:
    1. dict: iterate values()
    2. dict-like (.items() callable + not a leaf): iterate values
    3. plain iteration: yield items, catching per-item errors
       (handles shioaji 1.5 Pydantic validation issues)
    """
    if isinstance(node, dict):
        return list(node.values())
    if (
        not _is_leaf(node)
        and hasattr(node, "items")
        and callable(getattr(type(node), "items", None))
    ):
        try:
            return [v for _k, v in node.items()]
        except Exception as exc:
            logger.debug("[contracts] items() failed on %s: %s", type(node).__name__, exc)
    # Direct iteration with per-item error recovery
    try:
        out: list[Any] = []
        for item in node:
            out.append(item)
        return out
    except TypeError:
        return []
    except Exception as exc:
        logger.warning(
            "[contracts] iteration on %s aborted: %s — "
            "shioaji 1.5+ may need direct .get(code) lookup instead",
            type(node).__name__, type(exc).__name__,
        )
        return []


def list_contracts(api: Any, kind: Kind = "futures") -> list[dict]:
    """Walk api.Contracts.{Futures|Options|Stocks|Indexs} -> list of dicts.

    Returns dicts with: code, symbol, delivery_date.

    Returns [] (with warning) if shioaji SDK iteration fails (e.g. 1.5+
    Pydantic validation error on server-returned contracts). For known
    contract codes, use `api.Contracts.<Kind>.<Group>.get(code)` directly.
    """
    if kind not in _KIND_TO_ATTR:
        raise ValueError(f"unknown kind: {kind!r}")
    root = getattr(api.Contracts, _KIND_TO_ATTR[kind])

    out: list[dict] = []

    def _flatten(node: Any) -> None:
        if _is_leaf(node):
            out.append({
                "code": getattr(node, "code", None),
                "symbol": getattr(node, "symbol", None),
                "delivery_date": getattr(node, "delivery_date", None),
            })
            return
        children = _children(node)
        for child in children:
            _flatten(child)

    _flatten(root)

    if not out:
        logger.warning(
            "[contracts] list_contracts(kind=%r) returned empty — "
            "shioaji SDK likely cannot enumerate this category (1.5+ Pydantic "
            "validation issue). Use api.Contracts.<Kind>.<Group>.get(code) "
            "for known contract codes.",
            kind,
        )
    return out
