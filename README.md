# shioaji-bars

Historical OHLCV bar fetcher for shioaji (永豐金證券) SDK. CLI + Python lib. Parquet output. Requires shioaji API token.

## Quickstart

```bash
pip install git+https://github.com/Yeimaoz/shioaji-bars.git@v0.1.0
export SHIOAJI_API_KEY=...
export SHIOAJI_SECRET=...

# CLI
python -m shioaji_bars list-contracts --kind futures

# Lib
python -c "from shioaji_bars import login, fetch_kbars; api = login(); df = fetch_kbars(api, contract='MTX', interval='1m', start='2024-12-01'); print(df.tail())"
```

## License

MIT
