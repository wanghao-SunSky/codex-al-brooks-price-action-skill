# Request Parsing

Use this file when the user supplies a screenshot, a company name, or a loosely described market segment.

## Extract these fields first

- instrument name or ticker
- exchange or market
- timeframe
- analysis window
- whether the user wants current analysis or a historical replay
- any visible EMA labels or key levels

## BTC default shortcut

If the user gives a generic BTC short-term request without venue or timeframe, use these defaults:

- symbol: `BINANCE:BTCUSDT.P`
- provider: `binance`
- timeframe: `5m`
- natural language `最近半小时` or `last half hour`: `--recent 30m`
- natural language `最近 2 小时` or `last 2 hours`: `--recent 2h`

Examples that should use this default:

- `查下 BTC 最近半小时的线`
- `分析下 BTC`
- `看下 BTC 短线`

Do not apply this shortcut if the user explicitly says:

- spot
- another exchange such as OKX or Bybit
- another contract symbol
- another timeframe such as `15m`, `1h`, or `4h`

## Screenshot protocol

When reading a screenshot, record:

- the exact ticker if shown
- the timeframe from the chart header
- the visible left and right date labels
- the most recent visible bar
- notable highs, lows, gaps, and range boundaries

If the screenshot only shows a company name, resolve it to a tradable ticker before fetching bars.

## Symbol normalization

`scripts/fetch_bars.py` normalizes common formats into the target provider's symbol format.

Examples:

- `HKEX:700` -> `0700.HK`
- `SHSE:600519` -> `600519.SS`
- `SZSE:000001` -> `000001.SZ`
- `NASDAQ:AAPL` -> `AAPL`
- `NYSE:BRK.B` -> `BRK-B`
- `BTCUSDT` -> `BTCUSDT` for Binance spot history, `BINANCE:BTCUSDT` for TradingView snapshot
- `BINANCE:BTCUSDT.P` -> `BTCUSDT` for Binance futures history
- `ETH/USDT` -> `ETHUSDT` for Binance history
- `SPX` -> `^GSPC`

## Timeframe rules

- `1m`, `5m`, `15m`, `30m`, `1h`, `4h`, `1d`, and `1wk` are supported.
- If the user says "daily", use `1d`.
- If the user says "4-hour", use `4h`.
- If the screenshot timeframe is unclear but the bar density matches swing trading, default to `1d` and state the assumption.
- If the user asks for TradingView-aligned latest values, use `--provider tvscreener` with the requested timeframe.
- If the user asks for crypto history, prefer Binance under the default `auto` provider.

## Date window rules

- If the user names a range, use it directly.
- If the user says "最近半小时", "last 30 minutes", "最近 6 小时", or similar, map it to `--recent`, for example `30m` or `6h`.
- If the user says "this leg" or "this section", estimate the visible window from the screenshot and fetch a wider surrounding range.
- For EMA reliability, fetch enough warmup bars before the requested start. The script does this automatically.
- For intraday crypto reads like `BTC 5min 最近半小时`, fetch with `--recent 30m` and still keep EMA warmup enabled.
- Do not use `tvscreener` for `--recent` or historical window requests; it only provides the latest interval snapshot.
- Binance history is the preferred source for crypto multi-bar reviews.
- If the user did not provide a screenshot, build one from fetched bars with `scripts/build_market_bundle.py`.

## Good command examples

```bash
python3 scripts/fetch_bars.py --symbol HKEX:700 --timeframe 1d --start 2025-11-01 --end 2026-01-31 --ema 20 50 200
python3 scripts/fetch_bars.py --symbol BTCUSDT --market CRYPTO --timeframe 1h --lookback 14d --ema 20 50
python3 scripts/fetch_bars.py --symbol BINANCE:BTCUSDT.P --market CRYPTO --timeframe 5m --recent 30m --ema 20 50
python3 scripts/build_market_bundle.py --symbol BINANCE:BTCUSDT.P --market CRYPTO --timeframe 5m --recent 2h
python3 scripts/fetch_bars.py --provider tvscreener --symbol BINANCE:BTCUSDT --market CRYPTO --timeframe 5m --ema 20 50
python3 scripts/fetch_bars.py --symbol NASDAQ:NVDA --timeframe 4h --start 2026-02-01 --end 2026-03-01 --ema 20 50
```
