"""CLI for shioaji-bars: list-contracts / fetch / snapshots."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

from shioaji_bars.contracts import list_contracts
from shioaji_bars.fetcher import fetch_kbars, fetch_snapshots, fetch_ticks
from shioaji_bars.parquet_io import Mode, write_parquet
from shioaji_bars.session import login, logout

logger = logging.getLogger(__name__)


def _cmd_list_contracts(args: argparse.Namespace) -> int:
    api = login()
    try:
        out = list_contracts(api, kind=args.kind)
    finally:
        logout(api)
    for c in out:
        print(f"{c['code']}\t{c['symbol']}\t{c.get('delivery_date') or '-'}")
    return 0


def _cmd_fetch(args: argparse.Namespace) -> int:
    api = login()
    try:
        df = fetch_kbars(api, contract=args.contract, interval=args.interval,
                         start=args.start, end=args.end)
        if df.empty:
            logger.warning(
                "[fetch] fetch_kbars returned 0 rows for contract=%s %s..%s; skipping write",
                args.contract, args.start, args.end,
            )
            return 0
        write_parquet(df, Path(args.output), mode=Mode(args.mode))
    finally:
        logout(api)
    return 0


def _cmd_fetch_ticks(args: argparse.Namespace) -> int:
    api = login()
    try:
        df = fetch_ticks(api, contract=args.contract, date=args.date)
        if df.empty:
            logger.warning(
                "[fetch-ticks] fetch_ticks returned 0 rows for contract=%s date=%s "
                "(empty trading day, or queried during the TW session — re-fetch "
                "outside trading hours)",
                args.contract, args.date,
            )
        # Per-day file uses OVERWRITE: a full day is fetched at once, so the
        # whole file is replaced. This sidesteps write_parquet's by-ts dedup,
        # which would wrongly drop legitimate same-ts trades. (empty df is a
        # no-op inside write_parquet, preserving any existing file.)
        write_parquet(df, Path(args.output), mode=Mode(args.mode))
    finally:
        logout(api)
    return 0


def _cmd_snapshots(args: argparse.Namespace) -> int:
    api = login()
    try:
        out = fetch_snapshots(api, contracts=args.contracts.split(","))
        df = pd.DataFrame(out)
        if args.output:
            write_parquet(df, Path(args.output), mode=Mode.OVERWRITE)
        else:
            print(df.to_string(index=False))
    finally:
        logout(api)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="shioaji-bars")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_ls = sub.add_parser("list-contracts", help="List shioaji contracts")
    p_ls.add_argument("--kind", choices=["futures", "options", "stocks", "indexs"],
                       default="futures")

    p_fetch = sub.add_parser("fetch", help="Fetch kbars -> parquet")
    p_fetch.add_argument("--contract", required=True,
                          help="MTX/TXF/TMF shortcode, MXFM4-style code, or 4-digit stock code")
    p_fetch.add_argument(
        "--interval", default="1m",
        help="(NOTE: shioaji always returns 1-min kbars; this flag is informational. "
             "Resample downstream if needed.)",
    )
    p_fetch.add_argument("--start", required=True, help="YYYY-MM-DD")
    p_fetch.add_argument("--end", required=True, help="YYYY-MM-DD")
    p_fetch.add_argument("--output", required=True)
    p_fetch.add_argument("--mode", choices=["append", "overwrite", "skip"],
                          default="append")

    p_ticks = sub.add_parser("fetch-ticks", help="Fetch one day of raw ticks -> parquet")
    p_ticks.add_argument("--contract", required=True,
                          help="MTX/TXF/TMF shortcode, MXFM4-style code, or 4-digit stock code")
    p_ticks.add_argument("--date", required=True, help="single trading day, YYYY-MM-DD")
    p_ticks.add_argument("--output", required=True,
                          help="parquet path; per-day convention is <SYM>/<date>.parquet")
    p_ticks.add_argument("--mode", choices=["append", "overwrite", "skip"],
                          default="overwrite",
                          help="default overwrite (per-day file; avoids by-ts dedup)")

    p_snap = sub.add_parser("snapshots", help="Current snapshot quotes")
    p_snap.add_argument("--contracts", required=True,
                         help="comma-separated, e.g. MTX,TXF,TMF")
    p_snap.add_argument("--output", default=None,
                         help="optional parquet path; else print table")

    args = parser.parse_args(argv if argv is not None else sys.argv[1:])
    logging.basicConfig(level=logging.INFO,
                         format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    if args.cmd == "list-contracts":
        return _cmd_list_contracts(args)
    if args.cmd == "fetch":
        return _cmd_fetch(args)
    if args.cmd == "fetch-ticks":
        return _cmd_fetch_ticks(args)
    if args.cmd == "snapshots":
        return _cmd_snapshots(args)
    return 2


if __name__ == "__main__":
    sys.exit(main())
