---
name: al-brooks-price-action
description: Analyze chart screenshots or user-described market segments with an Al Brooks price-action framework. Use when the user wants the agent to infer symbol, timeframe, and range from a screenshot or text, fetch OHLC and EMA data, and produce scenario-based trading analysis with levels, invalidation, and risk notes. For generic short-term BTC requests with missing venue or timeframe, default to Binance BTC perpetual on 5-minute bars.
---

# Al Brooks Price Action

Use this skill when the user wants chart analysis or a trade idea driven by price action, not just a raw indicator summary.

## What this skill does

- Parse context from a screenshot or text request.
- Resolve the symbol, exchange, timeframe, and date window.
- Fetch fresh OHLCV data and compute EMAs with `scripts/fetch_bars.py`.
- Build a data bundle with a generated chart image through `scripts/build_market_bundle.py`.
- Analyze structure with a Brooks lens.
- Return a scenario-based trade plan with clear invalidation.

## Workflow

1. Identify the instrument and scope.
   - Extract symbol, exchange, timeframe, visible date range, and whether the user cares about the latest bars or a historical segment.
   - If the screenshot omits one critical field, make the narrowest reasonable assumption and state it.
   - Ask one concise clarification only when the assumption could change the instrument or timeframe.

## Default assumptions

- If the user says `BTC` and asks for a short-term read like `最近半小时`, `最近一小时`, `看下 BTC 的线`, but does not specify exchange, contract type, or timeframe:
  - default symbol: `BINANCE:BTCUSDT.P`
  - default history provider: `binance`
  - default timeframe: `5m`
- If the user says only `最近半小时`, map it to `--recent 30m`.
- Only override these defaults when the user explicitly asks for spot, another exchange, another contract, or another timeframe.
- When these defaults are used, state them briefly in the analysis.

2. Fetch data before analyzing.
   - Use `python3 scripts/build_market_bundle.py ...` when you want both bar data and a chart image in the same turn.
   - Use `python3 scripts/fetch_bars.py ...` when you only need raw bars.
   - Use `--provider tvscreener` when you need the latest TradingView-aligned interval snapshot for a symbol.
   - Under `auto`, crypto history uses Binance and non-crypto history uses yfinance.
   - For symbols like `BINANCE:BTCUSDT.P`, history uses Binance futures klines. For `BTCUSDT`, history uses Binance spot klines.
   - Use the default history provider when the user asks for a visible range, `--recent`, or any multi-bar review.
   - Default EMAs: `20 50`.
   - Add `200` for daily or weekly swing analysis, or when the chart clearly references a longer baseline.
   - If the user asks about the latest setup, fetch immediately before answering and include the exact data range used.
   - If the user says "recent", "last", or "过去/最近一段", prefer `--recent`, for example `--recent 30m` or `--recent 6h`.

3. Read price action in this order.
   - Higher-timeframe context.
   - Market cycle: bull trend, bear trend, trading range, breakout mode, or reversal attempt.
   - Always-in direction.
   - Signal quality: body size, close location, overlap, follow-through, trapped traders.
   - Location: EMA, prior swing high or low, channel line, range edge, gap, or measured-move target.
   - Pattern quality: see `references/brooks-framework.md`.

4. Build scenarios, not certainty.
   - Provide a bull case, bear case, and wait condition when the chart is range-bound.
   - For each actionable idea, include trigger, invalidation, first target, stretch target, and failure condition.

5. Use the output contract in `references/output-template.md`.
   - Tie every recommendation to specific bars, levels, or EMA relationships.
   - Mention what data was fetched and what assumptions were made.

## Screenshot-first protocol

When the input is a screenshot:

- Inspect the image directly before searching.
- Extract what is visible:
  - symbol or company name
  - exchange
  - timeframe
  - visible start and end dates or the approximate segment
  - key swing highs and lows
  - visible EMA labels if present
- Then use `references/request-parsing.md` to normalize the symbol and fetch data.
- If the user did not send a screenshot, generate one from data first with `scripts/build_market_bundle.py`.
- Fetch a slightly wider window than the visible segment so EMA context and follow-through are not truncated.

## Command patterns

```bash
# Daily swing example
python3 scripts/fetch_bars.py \
  --symbol SHSE:600519 \
  --timeframe 1d \
  --start 2025-09-01 \
  --end 2025-10-31 \
  --ema 20 50 200

# Hong Kong 4h example
python3 scripts/fetch_bars.py \
  --symbol HKEX:700 \
  --timeframe 4h \
  --start 2026-01-01 \
  --end 2026-02-15 \
  --ema 20 50

# Crypto latest example
python3 scripts/fetch_bars.py \
  --symbol BTCUSDT \
  --market CRYPTO \
  --timeframe 1h \
  --lookback 30d \
  --ema 20 50

# "Analyze the last 30 minutes of BTC 5m candles"
python3 scripts/fetch_bars.py \
  --symbol BINANCE:BTCUSDT.P \
  --market CRYPTO \
  --timeframe 5m \
  --recent 30m \
  --ema 20 50

# "Check BTC for the last half hour" with omitted venue/timeframe
python3 scripts/fetch_bars.py \
  --symbol BINANCE:BTCUSDT.P \
  --market CRYPTO \
  --timeframe 5m \
  --recent 30m \
  --ema 20 50

# Build a chart + data bundle for the default BTC short-term case
python3 scripts/build_market_bundle.py

# Build a chart + data bundle for BTC over the last 2 hours
python3 scripts/build_market_bundle.py \
  --symbol BINANCE:BTCUSDT.P \
  --market CRYPTO \
  --timeframe 5m \
  --recent 2h

# Latest TradingView 5m snapshot for BTC
python3 scripts/fetch_bars.py \
  --provider tvscreener \
  --symbol BINANCE:BTCUSDT \
  --market CRYPTO \
  --timeframe 5m \
  --ema 20 50
```

## When to load references

- `references/request-parsing.md`
  Use when the user gives a screenshot, a vague market description, or a non-standard symbol format.
- `references/brooks-framework.md`
  Use when you need the Brooks pattern checklist and interpretation rules.
- `references/output-template.md`
  Use when writing the final analysis.
- `references/safety.md`
  Use whenever the user wants a current trade recommendation or position idea.

## Hard rules

- Never invent OHLC, EMA, or timestamps.
- Never present a trade as guaranteed.
- If data freshness matters, fetch fresh data and state the exact range used.
- If the chart is ambiguous, say what would confirm the bull case and what would confirm the bear case.
- If symbol resolution is uncertain, state the assumption explicitly before analyzing.
- If `tvscreener` is used, say clearly that it is a latest-interval snapshot, not a historical bar sequence.
