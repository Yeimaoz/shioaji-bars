---
name: shioaji-bars
description: |
  Use when fetching Taiwan stock / TAIFEX futures historical 1-min OHLCV bars,
  single-day raw tick-by-tick trades, or live snapshots via the SinoPac shioaji
  SDK into parquet. Requires a shioaji account + API key (this is an
  authenticated, non-public data source). Covers login/credentials, the Taiwan
  trading-session re-fetch ban, fetch_kbars / fetch_ticks / fetch_snapshots /
  list_contracts usage, output schemas, and how this differs from a public
  crypto bars fetcher (public-vs-authenticated).
  抓台股 / 台指期歷史 1 分 K、單日逐筆成交、即時 snapshot 或列合約落 parquet 時使用；
  需永豐金 shioaji 帳號。
---

# shioaji-bars usage

`shioaji-bars` is a thin fetcher over the SinoPac (永豐金) **shioaji** SDK that
pulls Taiwan-market historical bars, raw ticks, and live snapshots into parquet.
CLI + Python lib, dual API.

## A. When to use / when not

**Use it for:**

- Historical 1-min OHLCV bars for Taiwan stocks (4-digit code) or TAIFEX
  futures (`MTX` / `TXF` / `TMF`) → parquet.
- A single trading day of **raw tick-by-tick trades** (futures or stocks).
- A point-in-time **snapshot** quote for one or more contracts.
- Listing available contracts.

**Do NOT use it when:**

- **You have no shioaji account.** This is an *authenticated* data source —
  every call needs a valid API key + secret. There is no public/anonymous mode.
  If you only need crypto data, use a public crypto bars fetcher instead; this
  package will not help you.
- You need 5m / 15m / daily bars. `fetch_kbars` always returns **1-min** bars
  (the `interval` arg is informational only) — resample downstream.
- You need order placement or live streaming subscriptions. Use the shioaji SDK
  (or `rshioaji`) directly for those.

> **Fail-loud rule:** if you do not have a 永豐金 shioaji account, this package
> is entirely inapplicable. `login()` raises `ShioajiAuthError` immediately when
> credentials are missing — it does not silently degrade.

## B. Install

```bash
pip install "shioaji-bars @ git+https://github.com/Yeimaoz/shioaji-bars.git@v0.2.0"
```

Runtime deps: `shioaji` (vendor SDK, from PyPI), `pandas`, `pyarrow`,
`python-dotenv`.

Verify the install (do **not** assert an exact version string in scripts —
prefer the package metadata):

```python
import importlib.metadata as m
print(m.version("shioaji-bars"))
```

## C. Credentials (handle securely)

You must supply your **own** shioaji API key + secret, applied for from the
official SinoPac / shioaji developer portal. Apply via the official channel:
<https://sinotrade.github.io/> (shioaji official docs). This skill deliberately
does **not** walk through the application flow and never shows a real key.

Two ways to provide credentials (first non-empty wins):

1. **Environment variables:**
   - `SHIOAJI_API_KEY`
   - `SHIOAJI_SECRET` (or `SHIOAJI_SECRET_KEY` — both names are accepted; the
     latter matches the shioaji docs convention)
2. **A `.env` file** — `shioaji_bars` calls `load_dotenv()` at import time, so a
   `.env` is picked up automatically. Keep it **outside** any tracked tree and
   `.gitignore` it. Example placement: `~/.config/shioaji/.env` (or any path
   outside your project).

```
# .env  (never commit this)
SHIOAJI_API_KEY=<YOUR_API_KEY>
SHIOAJI_SECRET=<YOUR_SECRET>
```

**Hard rules:**

- API key / secret never go into git, issues, PRs, or logs. Always use
  placeholders (`<YOUR_API_KEY>` / `<YOUR_SECRET>`) in examples.
- Missing credentials → `ShioajiAuthError` (fail-loud, not a silent skip).

## D. ⚠️ Do NOT re-fetch during Taiwan trading hours (the #1 footgun)

Bulk re-fetch / backfill during an open Taiwan session hits the shioaji
producer-side rate limit and you get throttled or partial data. Schedule heavy
work **after the close.**

| Window (Taiwan time, `Asia/Taipei`) | Status |
|---|---|
| 08:45–13:45 (day session) | ❌ do not bulk-fetch |
| 15:00–05:00 next day (night session) | ❌ do not bulk-fetch |
| 13:45–15:00 | ✅ safe window |
| 05:00–08:45 | ✅ safe window (best: batch right after close) |

- Judge the session using `Asia/Taipei`, **not** server local time — on a
  machine that is not at UTC+8, a naive `date.today()` can be off by a day.
- A public crypto market has no such session/throttle limitation — that
  contrast is a useful reminder that this source is authenticated and
  rate-limited.
- Treat these windows as operational guidance; **follow the official SinoPac
  announcements** for the authoritative trading calendar.

> Recommendation: run any scheduled refresh as a **post-close batch job**.

## E. Fetch bars / list contracts / snapshots

Log in once, do all the work, log out once (in a `finally`):

```python
from shioaji_bars import (
    login, logout, list_contracts, fetch_kbars, fetch_snapshots, Mode,
    read_last_ts, write_parquet,
)

api = login()  # reads SHIOAJI_API_KEY + SHIOAJI_SECRET from env / .env
try:
    # List contracts (note the shioaji >=1.5 caveat below)
    contracts = list_contracts(api, kind="futures")

    # Historical 1-min bars
    df = fetch_kbars(api, contract="MTX", interval="1m",
                     start="2024-12-01", end="2024-12-31")

    # Snapshots — returns list[dict], NOT a DataFrame
    snaps = fetch_snapshots(api, contracts=["MTX", "TXF"])
finally:
    logout(api)
```

CLI equivalents:

```bash
python -m shioaji_bars list-contracts --kind futures
python -m shioaji_bars fetch --contract MTX --interval 1m \
    --start 2024-12-01 --end 2024-12-31 --output ./MTX_1min.parquet --mode append
python -m shioaji_bars snapshots --contracts MTX,TXF,TMF
```

**fetch_snapshots returns `list[dict]`, not a DataFrame.** Each dict is
`{"code", "close", "volume", "ts"}` (`ts` is a nanosecond-epoch int, possibly
`None`). To persist, wrap it yourself:

```python
import pandas as pd
pd.DataFrame(snaps)  # then write_parquet(...) if you want it on disk
```

**list_contracts on shioaji ≥1.5 often returns `[]`** — newer SDK containers
have no stable bulk enumeration (Pydantic validation can fail mid-iteration).
For a known code, look it up directly instead:

```python
contract = api.Contracts.Futures.MXF.get("MXFR1")
```

**Incremental append** for bars: read the last stored timestamp, fetch from the
next day, and append (`Mode.APPEND` dedups by `ts` and writes atomically):

```python
last = read_last_ts(path)            # None if file doesn't exist yet
df = fetch_kbars(api, "MTX", start=..., end=...)
df = df[df["ts"] > last] if last is not None else df
write_parquet(df, path, mode=Mode.APPEND)
```

**Contract strings:** `MTX` / `TXF` / `TMF` resolve to the rolling front-month
(R1) automatically; `MXFM4`-style codes target an explicit delivery month;
4-digit codes (e.g. `2330`) are TSE stocks.

**Timezone rule for `end`:** when fetching "up to today", build the end date
from `datetime.now(ZoneInfo("Asia/Taipei"))`, not `date.today()` — otherwise an
off-UTC+8 machine can request a day that has not happened yet in Taipei. For
intraday manual runs, drop the still-forming bar yourself.

## E2. Fetch raw ticks (`fetch_ticks`)

`fetch_ticks(api, contract, date)` returns **one trading day of raw,
tick-by-tick trades** for a single contract.

```python
from shioaji_bars import login, logout, fetch_ticks, write_parquet, Mode

api = login()
try:
    df = fetch_ticks(api, contract="TXF", date="2026-06-13")
    # per-day file convention: <SYM>/<date>.parquet, OVERWRITE mode
    write_parquet(df, "TXF/2026-06-13.parquet", mode=Mode.OVERWRITE)
finally:
    logout(api)
```

CLI:

```bash
python -m shioaji_bars fetch-ticks --contract TXF --date 2026-06-13 \
    --output TXF/2026-06-13.parquet
```

**⚠️ Quota (the #1 tick footgun):** `fetch_ticks` goes through the live shioaji
API and is **much heavier than `fetch_kbars`** — there is a per-day query quota.
Fetch **one day at a time and resume**; do **not** blast a multi-year backfill in
one go. Loop day-by-day, skip days you already have on disk, and stop on the
first error rather than retrying into the quota wall.

**⚠️ TW session:** same rule as §D — run **after the close**; mid-session
fetches hit the producer rate limit.

**Why `OVERWRITE` and one file per day:** a whole day is fetched at once, so the
day-file is replaced wholesale. This deliberately sidesteps the by-`ts` dedup
that `Mode.APPEND` applies — multiple trades legitimately share the same
timestamp, and `APPEND`'s dedup would wrongly drop them.

**`tick_type` ≠ binance `is_buyer_maker`:** `tick_type` is a **broker-side**
direction code — `1` = 外盤 (buy-side / hit-the-ask), `2` = 內盤 (sell-side /
hit-the-bid), `0` = undetermined. This is *not* the same semantic as a crypto
exchange's taker-side / `is_buyer_maker` flag. **Do not** mix the two when doing
cross-market order-flow comparison.

**No aggregation.** `fetch_ticks` stores native ticks verbatim. It does **not**
produce a crypto aggTrades-style merged stream: the exchange-side aggregate id
is a server product that cannot be reconstructed client-side, merging is lossy,
and TW tick volumes do not need it. If you want bar-level order-flow features,
aggregate the raw ticks yourself downstream.

**Single day per call.** For multiple days, loop + resume (skip days already on
disk).

## F. Output schemas

### `fetch_kbars` → DataFrame

| Column | dtype | Notes |
|---|---|---|
| `ts` | datetime64[ns, UTC] | bar start, tz-aware; `Mode.APPEND` dedup key |
| `open` / `high` / `low` / `close` | float64 | OHLC |
| `volume` | int64 | 口數 (contracts / 張) |
| `amount` | float64 | 成交金額 (≈ volume × avg price, TWD) |

### `fetch_ticks` → DataFrame (8 columns)

| Column | dtype | Notes |
|---|---|---|
| `ts` | datetime64[ns, UTC] | trade timestamp, tz-aware; **not** unique (same-ts trades preserved) |
| `price` | float64 | trade print price (shioaji native field name is `close`) |
| `volume` | int64 | trade size |
| `bid_price` | float64 | best bid at print time |
| `ask_price` | float64 | best ask at print time |
| `bid_volume` | int64 | best-bid size |
| `ask_volume` | int64 | best-ask size |
| `tick_type` | int8 | broker-side direction: 1=外盤/buy, 2=內盤/sell, 0=undetermined |

An empty day returns a typed zero-row frame (correct dtypes), not a raise.

### `fetch_snapshots` → `list[dict]` (NOT a DataFrame)

```python
[{"code": "MXFR1", "close": 18000.0, "volume": 12345, "ts": 1704067260_000_000_000}, ...]
```

`ts` is a nanosecond-epoch int (or `None`). Convert with
`pd.to_datetime(ts, unit="ns", utc=True)` if needed.

## G. Sibling package cross-reference (vs binance-bars)

`shioaji-bars` (authenticated Taiwan market) and `binance-bars` (public crypto)
are sibling OSS packages with deliberately aligned capabilities and API shapes
— learn one and you can carry the knowledge to the other. Concept → this
package's function ↔ the sibling's function:

| Concept | shioaji-bars (this package) | binance-bars (sibling) |
|---|---|---|
| Authentication | `login()` / `logout()` | —（public REST, no API key） |
| OHLCV bars | `fetch_kbars(api, contract, interval, start, end)` | `fetch_klines(market, symbol, interval, start, end)` |
| Tick-by-tick trades | `fetch_ticks(api, contract, date)` → DataFrame 8-col (raw · single contract, single day · caller writes the file; CLI `fetch-ticks`) | `fetch_aggtrades(symbols, date_from, date_to, output_dir)` → stats (aggregated · many symbols × many days · writes files itself; CLI `fetch-aggtrades`) |
| Live snapshot | `fetch_snapshots(api, contracts)` | —（offers funding / OI / basis derived data instead） |
| Derived data | — | `fetch_funding_rate` / `fetch_open_interest` / `fetch_basis` |
| Instrument listing | `list_contracts` | `list_symbols` |
| Write / cursor | `write_parquet` / `read_last_ts` | `write_parquet` / `read_last_open_time` |
| Tick timestamp col | `ts`（datetime64[ns, UTC]） | `timestamp_ms`（int64 unix-ms） |
| Tick direction col | `tick_type`（外盤/內盤, **≠** `is_buyer_maker`） | `is_buyer_maker`（taker side） |

Also differs in operational shape: this package is authenticated (`login()`
required), session-limited (❌ no bulk fetch during a TW session, §D), always
1-min (resample downstream), and has an `amount` (成交金額) column; the sibling
is anonymous, unthrottled by session, usually multi-interval, and has no
`amount` column.

**Key difference (tick-by-tick):** the two tick fetchers are not the same
shape. This package is a **reader** — `fetch_ticks` goes through the shioaji
per-day quota, returns one day for one contract as a DataFrame, and the caller
writes the file. The sibling is a **producer** — `fetch_aggtrades` batch-pulls
Binance Vision daily archives, writing one file per symbol-day itself,
resume-safe across many symbols × many days. Schema style follows each family's
own bars: this package is tz-aware datetime (`ts`), the sibling is int-ms
(`timestamp_ms`). The direction columns are **not equivalent** — `tick_type`
is a broker-side 外盤/內盤 code, `is_buyer_maker` is an exchange taker-side flag
— normalize before any cross-market order-flow comparison.

Caller normalizes if joining across markets — the two are intentionally
independent.

## H. Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| `ShioajiAuthError` on `login()` | `SHIOAJI_API_KEY` / `SHIOAJI_SECRET` missing — set env or `.env`. |
| `ValueError: could not resolve contract: ...` | Bad contract string. Use `MTX`/`TXF`/`TMF`, a `MXFM4`-style code, or a 4-digit stock code. |
| `ValueError: Cannot resolve front-month ...` | The R1 rolling key wasn't in the SDK group — update shioaji, or pass an explicit delivery code (`MXFM4`). |
| `list_contracts(...)` returns `[]` | shioaji ≥1.5 enumeration limitation — use `api.Contracts.<Kind>.<Group>.get(code)` for known codes. |
| Partial / throttled tick or bar data | Almost certainly fetched **during** a TW session — re-run in a safe window (§D). |
| Tick fetch errors after many days | Hitting the per-day quota — fetch one day at a time and resume (§E2). |
