"""Parquet read/write -- same modes as binance-bars, but ts column is dedup key."""

from __future__ import annotations

import enum
import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)


class Mode(str, enum.Enum):
    APPEND = "append"
    OVERWRITE = "overwrite"
    SKIP = "skip"


def write_parquet(df: pd.DataFrame, path: Path, *, mode: Mode = Mode.APPEND) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    if mode == Mode.SKIP and path.exists():
        logger.info("[parquet_io] skip -- %s already exists", path)
        return

    if mode == Mode.APPEND and path.exists():
        existing = pd.read_parquet(path)
        df = pd.concat([existing, df], ignore_index=True)
        df = df.drop_duplicates(subset=["ts"], keep="last")
        df = df.sort_values("ts").reset_index(drop=True)

    # Atomic write: stage to a sibling .tmp file, then rename. If the
    # process is killed mid-write (OOM / SIGKILL / power loss / WSL
    # restart), the original parquet remains intact and only the .tmp
    # orphan is left (next run overwrites it).
    tmp = path.with_suffix(path.suffix + ".tmp")
    df.to_parquet(tmp, index=False)
    tmp.replace(path)
    logger.info("[parquet_io] wrote %s (%d rows, mode=%s)", path, len(df), mode.value)


def read_last_ts(path: Path) -> pd.Timestamp | None:
    path = Path(path)
    if not path.exists():
        return None
    df = pd.read_parquet(path, columns=["ts"])
    if df.empty:
        return None
    return df["ts"].max()
