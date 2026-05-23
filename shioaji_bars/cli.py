"""CLI for shioaji-bars: list-contracts / fetch / snapshots."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

from shioaji_bars.contracts import list_contracts
from shioaji_bars.fetcher import fetch_kbars, fetch_snapshots
from shioaji_bars.parquet_io import Mode, write_parquet
from shioaji_bars.session import login, logout


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
    finally:
        logout(api)
    write_parquet(df, Path(args.output), mode=Mode(args.mode))
    return 0


def _cmd_snapshots(args: argparse.Namespace) -> int:
    api = login()
    try:
        out = fetch_snapshots(api, contracts=args.contracts.split(","))
    finally:
        logout(api)
    df = pd.DataFrame(out)
    if args.output:
        df.to_parquet(args.output, index=False)
    else:
        print(df.to_string(index=False))
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
    if args.cmd == "snapshots":
        return _cmd_snapshots(args)
    return 2


if __name__ == "__main__":
    sys.exit(main())
