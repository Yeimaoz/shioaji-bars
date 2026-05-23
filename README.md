# shioaji-bars

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

Historical OHLCV bar fetcher for shioaji (永豐金證券) SDK. CLI + Python lib dual API. Parquet output. Requires shioaji API token.

## Install

```bash
pip install git+https://github.com/Yeimaoz/shioaji-bars.git@v0.1.0
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

# Current snapshots
python -m shioaji_bars snapshots --contracts MTX,TXF,TMF
```

### Python lib

```python
from shioaji_bars import login, logout, list_contracts, fetch_kbars, fetch_snapshots

api = login()  # reads SHIOAJI_API_KEY + SHIOAJI_SECRET from env / .env
try:
    contracts = list_contracts(api, kind="futures")
    df = fetch_kbars(api, contract="MTX", interval="1m",
                     start="2024-12-01", end="2024-12-31")
    snap = fetch_snapshots(api, contracts=["MTX", "TXF"])
finally:
    logout(api)
```

## Capability matrix

| Subcommand | Lib method | Needs | Notes |
|---|---|---|---|
| `list-contracts` | `list_contracts` | token | shioaji ≥1.5 may return `[]` — see Known limitations |
| `fetch` | `fetch_kbars` | token + market-data scope | counts toward daily quota |
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
