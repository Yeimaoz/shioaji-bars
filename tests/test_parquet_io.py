from pathlib import Path

import pandas as pd

from shioaji_bars.parquet_io import write_parquet, read_last_ts, Mode


def _df(rows):
    """Helper: build kbars-shaped df. rows = list of (ts_str, close)."""
    return pd.DataFrame({
        "ts": pd.to_datetime([r[0] for r in rows], utc=True),
        "open": [r[1] for r in rows],
        "high": [r[1] for r in rows],
        "low": [r[1] for r in rows],
        "close": [r[1] for r in rows],
        "volume": [100] * len(rows),
        "amount": [r[1] * 100 for r in rows],
    })


def test_write_append_dedups_and_sorts(tmp_path):
    path = tmp_path / "x.parquet"
    write_parquet(_df([("2024-01-01T00:00:00Z", 100.0),
                        ("2024-01-01T00:02:00Z", 102.0)]),
                  path, mode=Mode.OVERWRITE)
    write_parquet(_df([("2024-01-01T00:01:00Z", 101.0),
                        ("2024-01-01T00:02:00Z", 102.0)]),  # dup ts
                  path, mode=Mode.APPEND)
    out = pd.read_parquet(path)
    assert len(out) == 3
    assert list(out["close"]) == [100.0, 101.0, 102.0]


def test_read_last_ts_existing(tmp_path):
    path = tmp_path / "x.parquet"
    write_parquet(_df([("2024-01-01T00:00:00Z", 100.0),
                        ("2024-01-01T00:03:00Z", 103.0)]),
                  path, mode=Mode.OVERWRITE)
    ts = read_last_ts(path)
    assert ts == pd.Timestamp("2024-01-01T00:03:00Z")


def test_read_last_ts_missing(tmp_path):
    assert read_last_ts(tmp_path / "nope.parquet") is None


def test_write_skip_if_exists(tmp_path):
    path = tmp_path / "x.parquet"
    write_parquet(_df([("2024-01-01T00:00:00Z", 100.0)]), path, mode=Mode.OVERWRITE)
    write_parquet(_df([("2024-01-01T00:01:00Z", 999.0)]), path, mode=Mode.SKIP)
    out = pd.read_parquet(path)
    assert len(out) == 1
    assert out["close"].iloc[0] == 100.0


def test_write_atomic_preserves_prior_on_simulated_crash(tmp_path, monkeypatch):
    """If df.to_parquet raises mid-write, the prior parquet must be intact.

    Atomic write contract: stage to .tmp + rename. A crash before rename
    leaves the original file untouched and only an orphan .tmp behind.
    """
    path = tmp_path / "x.parquet"
    write_parquet(_df([("2024-01-02 09:01:00", 10.0)]),
                  path, mode=Mode.OVERWRITE)
    initial_last = read_last_ts(path)
    assert initial_last is not None

    real_to_parquet = pd.DataFrame.to_parquet

    def crashing_to_parquet(self, *args, **kwargs):
        if args and str(args[0]).endswith(".tmp"):
            Path(args[0]).write_bytes(b"PARTIAL_GARBAGE")
        raise OSError("simulated crash")

    monkeypatch.setattr(pd.DataFrame, "to_parquet", crashing_to_parquet)

    try:
        write_parquet(_df([("2024-01-02 09:02:00", 11.0)]),
                      path, mode=Mode.APPEND)
    except OSError:
        pass

    monkeypatch.setattr(pd.DataFrame, "to_parquet", real_to_parquet)
    assert path.exists()
    assert read_last_ts(path) == initial_last  # prior data intact
