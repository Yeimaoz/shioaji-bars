# shioaji-bars

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

Historical OHLCV bar + raw tick fetcher for shioaji (永豐金證券) SDK. CLI + Python lib dual API. Parquet output. Requires shioaji API token.

> **Usage skill:** an agent-oriented usage guide lives at
> [`skills/shioaji-bars/SKILL.md`](skills/shioaji-bars/SKILL.md) — credentials,
> the Taiwan trading-session re-fetch ban, fetch_kbars / fetch_ticks /
> fetch_snapshots / list_contracts, output schemas, and the public-crypto
> contrast.

## Install

```bash
pip install git+https://github.com/Yeimaoz/shioaji-bars.git@v0.2.0
```

Or for a fresh project, create a `.env`:

```
SHIOAJI_API_KEY=your_key_here
SHIOAJI_SECRET=your_secret_here
```

## Quickstart

### CLI

```bash
# List futures contracts
python -m shioaji_bars list-contracts --kind futures

# Fetch MTX 1-min kbars (start/end are YYYY-MM-DD)
python -m shioaji_bars fetch --contract MTX --interval 1m \
    --start 2024-12-01 --end 2024-12-31 \
    --output ./MTX_1min.parquet --mode append

# Fetch one trading day of raw ticks (per-day file; OVERWRITE)
# WARNING: heavy on the daily quota — one day at a time, resume; run after the close.
python -m shioaji_bars fetch-ticks --contract TXF --date 2026-06-13 \
    --output ./TXF/2026-06-13.parquet

# Current snapshots
python -m shioaji_bars snapshots --contracts MTX,TXF,TMF
```

### Python lib

```python
from shioaji_bars import login, logout, list_contracts, fetch_kbars, fetch_ticks, fetch_snapshots

api = login()  # reads SHIOAJI_API_KEY + SHIOAJI_SECRET from env / .env
try:
    contracts = list_contracts(api, kind="futures")
    df = fetch_kbars(api, contract="MTX", interval="1m",
                     start="2024-12-01", end="2024-12-31")
    ticks = fetch_ticks(api, contract="TXF", date="2026-06-13")  # one day, raw
    snap = fetch_snapshots(api, contracts=["MTX", "TXF"])
finally:
    logout(api)
```

## Capability matrix

| Subcommand | Lib method | Needs | Notes |
|---|---|---|---|
| `list-contracts` | `list_contracts` | token | shioaji ≥1.5 may return `[]` — see Known limitations |
| `fetch` | `fetch_kbars` | token + market-data scope | counts toward daily quota |
| `fetch-ticks` | `fetch_ticks` | token + market-data scope | **heavy** on daily quota; one day per call; raw, not aggregated; run after the close |
| `snapshots` | `fetch_snapshots` | token + market-data scope | live polling, not subscribe |

## Known limitations

**shioaji ≥1.5 contract iteration**: the SDK's `ContractCategory` /
`ContractGroup` containers in 1.5+ may raise Pydantic validation errors
mid-iteration (server occasionally returns `code: int` where schema
expects `str`). `list_contracts` is defensive — it returns `[]` (with
warning) rather than emitting `{code: None}` placeholder entries. For
known contract codes use direct SDK access instead:

```python
contract = api.Contracts.Futures.MXF.get("MXFR1")
df = fetch_kbars(api, contract="MTX", start="2024-12-01", end="2024-12-31")
```

`fetch_kbars` resolves shortcodes (MTX/TXF/TMF) via the rolling key
(`MXFR1` etc.) which works on all SDK versions.

**list-contracts exit code**: `list-contracts` returns exit code 0 even when
the result is empty (e.g. because shioaji 1.5+ iteration fails). This is a
known limitation; shell scripts that require a non-zero exit on empty results
must check the output explicitly (e.g. count lines). Changing the exit code
would be a breaking change for scripts that currently rely on exit 0.

**load_dotenv at import**: importing `shioaji_bars` (or any submodule) calls
`load_dotenv()` at module level via `session.py`. This is intentional for the
CLI use-case — it allows credentials in a `.env` file without extra config.
If you embed this library in a larger application that manages its own env,
suppress the side effect by setting `DOTENV_PATH` to a non-existent path or
calling `dotenv.override_env({})` before importing.

**indexs kind spelling**: `Kind = Literal[..., 'indexs']` mirrors the
shioaji SDK's own `api.Contracts.Indexs` attribute name (which itself is a
known SDK typo). Using `kind='indices'` will raise `ValueError`.

## Contract string resolution

The `--contract` flag (and `contract=` lib arg) accepts:

| Input | Maps to |
|---|---|
| `MTX` | front-month MXF futures (e.g. MXFM4) |
| `TXF` | front-month TXF futures |
| `TMF` | front-month TMF futures |
| `MXFM4` | exact MXF April 2024 delivery |
| `2330` | TSMC stock (4-digit TSE code) |

## DataFrame schemas

### fetch_kbars

| Column | dtype | Notes |
|---|---|---|
| `ts` | datetime (UTC) | bar start |
| `open` / `high` / `low` / `close` | float | OHLC |
| `volume` | int | 口數（contracts / 張）|
| `amount` | float | 成交金額 (volume × avg_price, in TWD) |

shioaji `api.kbars` always returns 1-min bars regardless of `interval` arg. Resample downstream for 5m/15m/etc.

### fetch_ticks (8-column DataFrame, one trading day)

| Column | dtype | Notes |
|---|---|---|
| `ts` | datetime (UTC) | trade timestamp, tz-aware; **not unique** (same-ts trades preserved) |
| `price` | float | trade print price (shioaji's native field name is `close`) |
| `volume` | int | trade size |
| `bid_price` / `ask_price` | float | best bid / ask at print time |
| `bid_volume` / `ask_volume` | int | best-bid / best-ask size |
| `tick_type` | int8 | broker-side direction: 1=外盤/buy, 2=內盤/sell, 0=undetermined |

`fetch_ticks` stores **raw** ticks verbatim — no aggregation (no aggTrades-style
merge; the exchange-side aggregate id cannot be reconstructed client-side). One
day per call; loop + resume for multi-day backfills. `tick_type` is a
**broker-side** direction code and is **not** equivalent to a crypto exchange's
`is_buyer_maker` taker-side flag — do not mix across markets. Per-day files use
`Mode.OVERWRITE` so legitimate same-`ts` trades are not lost to `APPEND`'s by-`ts`
dedup. Empty day → typed zero-row frame.

### fetch_snapshots (returns `list[dict]`, NOT DataFrame)

```python
[{"code": "MXFR1", "close": 18000.0, "volume": 12345, "ts": 1704067260_000_000_000}, ...]
```

`ts` here is nanosecond-precision int (shioaji native). Convert via `pd.to_datetime(ts, unit="ns", utc=True)` if needed.

## Schema diff vs `binance-bars`

Sibling lib `binance-bars` uses int-ms timestamps (`open_time`) and lacks an `amount` (成交金額) column. The two libs are intentionally independent — caller normalizes if joining across markets.

## Error handling

| Condition | Exception |
|---|---|
| Missing `SHIOAJI_API_KEY` / `SHIOAJI_SECRET` env (or args) | `ShioajiAuthError` (raised by `login()` immediately) |
| API quota exceeded mid-fetch | shioaji's native error propagates to caller (no auto-retry) |

## Token capability test

Run the live test suite to discover what your token supports:

```bash
export SHIOAJI_API_KEY=...
export SHIOAJI_SECRET=...
pytest -m live -v
```

PASS = your token can do that capability. FAIL on `test_fetch_kbar_2330_recent` (for example) means your token lacks individual-stock market-data scope.

## Testing

```bash
pip install -e .[dev]
pytest -v          # unit tests only (mock shioaji); ~15 tests
pytest -m live -v  # real shioaji (requires env vars)
```

## License

MIT
