#!/usr/bin/env python3
"""Fetch OHLCV bars and EMA values for a single instrument."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Sequence

try:
    import pandas as pd
except ImportError:  # pragma: no cover - runtime dependency guard
    pd = None

try:
    import yfinance as yf
except ImportError:  # pragma: no cover - runtime dependency guard
    yf = None

try:
    import requests
except ImportError:  # pragma: no cover - runtime dependency guard
    requests = None

try:
    from tvscreener import (
        CryptoField,
        CryptoScreener,
        StockField,
        StockScreener,
        StocksMarket,
        TimeInterval,
    )
    from tvscreener.filter import SearchFilter
except ImportError:  # pragma: no cover - runtime dependency guard
    CryptoField = None
    CryptoScreener = None
    StockField = None
    StockScreener = None
    StocksMarket = None
    TimeInterval = None
    SearchFilter = None


SUPPORTED_TIMEFRAMES = {"1m", "5m", "15m", "30m", "1h", "4h", "1d", "1wk"}
SUPPORTED_PROVIDERS = {"auto", "binance", "yfinance", "tvscreener"}
BINANCE_SPOT_BASE_URL = "https://api.binance.com"
BINANCE_FUTURES_BASE_URL = "https://fapi.binance.com"
YF_INTERVAL_MAP = {
    "1m": "1m",
    "5m": "5m",
    "15m": "15m",
    "30m": "30m",
    "1h": "60m",
    "4h": "60m",
    "1d": "1d",
    "1wk": "1wk",
}
BINANCE_INTERVAL_MAP = {
    "1m": "1m",
    "5m": "5m",
    "15m": "15m",
    "30m": "30m",
    "1h": "1h",
    "4h": "4h",
    "1d": "1d",
    "1wk": "1w",
}
RESAMPLE_RULES = {"4h": "4h"}
TV_TIMEFRAME_MAP = {
    "1m": "ONE_MINUTE",
    "5m": "FIVE_MINUTES",
    "15m": "FIFTEEN_MINUTES",
    "30m": "THIRTY_MINUTES",
    "1h": "SIXTY_MINUTES",
    "4h": "FOUR_HOURS",
    "1d": "ONE_DAY",
    "1wk": "ONE_WEEK",
}
INDEX_ALIASES = {
    "SPX": "^GSPC",
    "SP500": "^GSPC",
    "S&P500": "^GSPC",
    "NDX": "^NDX",
    "NASDAQ100": "^NDX",
    "DJI": "^DJI",
    "DOW": "^DJI",
}
CRYPTO_ALIASES = {
    "BTC": "BTC-USD",
    "BTCUSD": "BTC-USD",
    "BTCUSDT": "BTC-USD",
    "ETH": "ETH-USD",
    "ETHUSD": "ETH-USD",
    "ETHUSDT": "ETH-USD",
    "SOL": "SOL-USD",
    "SOLUSD": "SOL-USD",
    "SOLUSDT": "SOL-USD",
}
TV_STOCK_MARKET_MAP = {
    "US": "america",
    "HK": "hongkong",
    "CN": "china",
    "ETF": "america",
}
TV_CRYPTO_EXCHANGES = {"BINANCE", "BYBIT", "OKX", "COINW", "PIONEX", "BITGET", "MEXC"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch OHLCV bars and calculate EMA values."
    )
    parser.add_argument("--symbol", required=True, help="Ticker or exchange-prefixed symbol")
    parser.add_argument(
        "--provider",
        default="auto",
        choices=sorted(SUPPORTED_PROVIDERS),
        help="Data provider. tvscreener supports latest TradingView interval snapshots only.",
    )
    parser.add_argument(
        "--market",
        default="AUTO",
        choices=["AUTO", "US", "HK", "CN", "CRYPTO", "INDEX", "ETF"],
        help="Optional market hint for symbol normalization",
    )
    parser.add_argument(
        "--timeframe",
        required=True,
        choices=sorted(SUPPORTED_TIMEFRAMES),
        help="Bar interval",
    )
    parser.add_argument("--start", help="Inclusive start date or datetime in ISO format")
    parser.add_argument("--end", help="Inclusive end date or datetime in ISO format")
    parser.add_argument(
        "--recent",
        help="Relative window ending now, for example 30m, 6h, 2d, 1wk",
    )
    parser.add_argument(
        "--lookback",
        default="6mo",
        help="Used when --start is omitted, for example 30d, 6mo, 1y",
    )
    parser.add_argument(
        "--ema",
        nargs="+",
        type=int,
        default=[20, 50],
        help="EMA periods to compute",
    )
    parser.add_argument(
        "--tail",
        type=int,
        default=0,
        help="If set, only keep the last N rows after filtering",
    )
    parser.add_argument(
        "--format",
        choices=["json", "csv", "table"],
        default="json",
        help="Output format",
    )
    parser.add_argument("--output", help="Optional file path to write output")
    return parser.parse_args()


def require_base_dependencies() -> None:
    missing = []
    if pd is None:
        missing.append("pandas")
    if missing:
        joined = ", ".join(missing)
        raise SystemExit(
            f"Missing dependencies: {joined}. Install with "
            "`python3 -m pip install -r scripts/requirements.txt`."
        )


def require_yfinance_dependencies() -> None:
    require_base_dependencies()
    missing = []
    if yf is None:
        missing.append("yfinance")
    if missing:
        joined = ", ".join(missing)
        raise SystemExit(
            f"Missing dependencies: {joined}. Install with "
            "`python3 -m pip install -r scripts/requirements.txt`."
        )


def require_binance_dependencies() -> None:
    require_base_dependencies()
    missing = []
    if requests is None:
        missing.append("requests")
    if missing:
        joined = ", ".join(missing)
        raise SystemExit(
            f"Missing dependencies: {joined}. Install with "
            "`python3 -m pip install -r scripts/requirements.txt`."
        )


def require_tvscreener_dependencies() -> None:
    missing = []
    if CryptoScreener is None or StockScreener is None:
        missing.append("tvscreener")
    if missing:
        joined = ", ".join(missing)
        raise SystemExit(
            f"Missing dependencies: {joined}. Install with "
            "`python3 -m pip install -r scripts/requirements.txt`."
        )


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.strip().replace("Z", "+00:00")
    return datetime.fromisoformat(normalized)


def parse_duration(value: str) -> timedelta:
    match = re.fullmatch(r"\s*(\d+)\s*([a-zA-Z]+)\s*", value)
    if not match:
        raise ValueError(
            f"Invalid duration '{value}'. Use forms like 30m, 6h, 2d, 1wk."
        )

    amount = int(match.group(1))
    unit = match.group(2).lower()
    if unit in {"m", "min", "mins", "minute", "minutes"}:
        return timedelta(minutes=amount)
    if unit in {"h", "hr", "hrs", "hour", "hours"}:
        return timedelta(hours=amount)
    if unit in {"d", "day", "days"}:
        return timedelta(days=amount)
    if unit in {"w", "wk", "wks", "week", "weeks"}:
        return timedelta(weeks=amount)
    if unit in {"mo", "mon", "month", "months"}:
        return timedelta(days=30 * amount)
    if unit in {"y", "yr", "yrs", "year", "years"}:
        return timedelta(days=365 * amount)
    raise ValueError(
        f"Unsupported duration unit '{unit}'. Use m, h, d, wk, mo, or y."
    )


def make_end_exclusive(end_value: str | None) -> datetime | None:
    end_dt = parse_datetime(end_value)
    if end_dt is None:
        return None
    if "T" not in end_value and " " not in end_value:
        return end_dt + timedelta(days=1)
    return end_dt


def resolve_requested_window(args: argparse.Namespace) -> tuple[datetime | None, datetime | None]:
    if args.recent:
        if args.start or args.end:
            raise SystemExit("Use --recent by itself, or use --start/--end directly.")
        end_dt = datetime.now(timezone.utc)
        start_dt = end_dt - parse_duration(args.recent)
        return start_dt, end_dt

    return parse_datetime(args.start), make_end_exclusive(args.end)


def warmup_delta(timeframe: str, max_ema: int) -> timedelta:
    bars = max(max_ema, 1) * 3
    minute_map = {"1m": 1, "5m": 5, "15m": 15, "30m": 30, "1h": 60, "4h": 240}
    if timeframe in minute_map:
        return timedelta(minutes=minute_map[timeframe] * bars)
    if timeframe == "1d":
        return timedelta(days=bars)
    if timeframe == "1wk":
        return timedelta(days=7 * bars)
    raise ValueError(f"Unsupported timeframe: {timeframe}")


def normalize_symbol(raw_symbol: str, market: str) -> str:
    symbol = raw_symbol.strip().upper().replace(" ", "")
    symbol = symbol.replace(".O", "")
    if symbol in INDEX_ALIASES:
        return INDEX_ALIASES[symbol]
    if symbol in CRYPTO_ALIASES:
        return CRYPTO_ALIASES[symbol]

    if ":" in symbol:
        exchange, value = symbol.split(":", 1)
        exchange = exchange.upper()
        value = value.upper()
        if exchange in {"NASDAQ", "NYSE", "AMEX", "ARCA", "BATS"}:
            return value.replace(".", "-")
        if exchange in {"HKEX", "SEHK"}:
            return f"{int(value):04d}.HK"
        if exchange in {"SHSE", "SSE"}:
            return f"{value.zfill(6)}.SS"
        if exchange in {"SZSE", "SZ"}:
            return f"{value.zfill(6)}.SZ"
        if exchange in {"BINANCE", "BYBIT", "OKX"}:
            return normalize_crypto_pair(value)
        return value.replace(".", "-")

    if "/" in symbol:
        return normalize_crypto_pair(symbol)

    if symbol.endswith((".HK", ".SS", ".SZ")) or symbol.startswith("^"):
        return symbol

    if symbol.isdigit():
        if market == "HK" or len(symbol) <= 4:
            return f"{int(symbol):04d}.HK"
        if len(symbol) == 6:
            suffix = ".SS" if symbol.startswith(("5", "6", "9")) else ".SZ"
            return f"{symbol}{suffix}"

    if market == "CRYPTO":
        return normalize_crypto_pair(symbol)

    return symbol.replace(".", "-")


def normalize_crypto_pair(value: str) -> str:
    clean = value.strip().upper().replace("/", "").replace("-", "")
    quote_candidates = ("USDT", "USD", "BUSD", "USDC")
    for quote in quote_candidates:
        if clean.endswith(quote) and len(clean) > len(quote):
            base = clean[: -len(quote)]
            return f"{base}-USD"
    if clean in CRYPTO_ALIASES:
        return CRYPTO_ALIASES[clean]
    return clean


def normalize_symbol_for_tvscreener(raw_symbol: str, market: str) -> dict[str, str]:
    symbol = raw_symbol.strip().upper().replace(" ", "")

    if ":" in symbol:
        exchange, value = symbol.split(":", 1)
        exchange = exchange.upper()
        value = value.upper()

        if exchange == "SHSE":
            exchange = "SSE"
        elif exchange == "SEHK":
            exchange = "HKEX"

        if exchange in TV_CRYPTO_EXCHANGES:
            return {
                "kind": "crypto",
                "symbol": f"{exchange}:{normalize_tv_crypto_pair(value)}",
                "search_token": normalize_tv_crypto_pair(value),
            }

        return {
            "kind": "stock",
            "symbol": f"{exchange}:{normalize_tv_stock_token(exchange, value)}",
            "search_token": normalize_tv_stock_token(exchange, value),
            "stock_market": infer_tvscreener_stock_market(exchange, market),
        }

    if market == "CRYPTO" or is_probably_crypto_symbol(symbol):
        token = normalize_tv_crypto_pair(symbol)
        return {
            "kind": "crypto",
            "symbol": f"BINANCE:{token}",
            "search_token": token,
        }

    if symbol.isdigit():
        if market == "HK" or len(symbol) <= 4:
            token = str(int(symbol))
            return {
                "kind": "stock",
                "symbol": f"HKEX:{token}",
                "search_token": token,
                "stock_market": "hongkong",
            }
        if len(symbol) == 6:
            exchange = "SSE" if symbol.startswith(("5", "6", "9")) else "SZSE"
            return {
                "kind": "stock",
                "symbol": f"{exchange}:{symbol}",
                "search_token": symbol,
                "stock_market": "china",
            }

    return {
        "kind": "stock",
        "symbol": symbol.replace(".", "-"),
        "search_token": symbol.replace(".", "-"),
        "stock_market": infer_tvscreener_stock_market("", market),
    }


def normalize_tv_stock_token(exchange: str, value: str) -> str:
    if exchange == "HKEX":
        return str(int(value))
    if exchange in {"SSE", "SZSE"}:
        return value.zfill(6)
    return value.replace(".", "-")


def normalize_tv_crypto_pair(value: str) -> str:
    clean = value.strip().upper().replace("/", "").replace("-", "")
    if clean.endswith("USD") and not clean.endswith("USDT"):
        clean = f"{clean[:-3]}USDT"
    return clean


def normalize_symbol_for_binance(raw_symbol: str) -> str:
    symbol = raw_symbol.strip().upper().replace(" ", "")
    if ":" in symbol:
        exchange, value = symbol.split(":", 1)
        exchange = exchange.upper()
        if exchange not in TV_CRYPTO_EXCHANGES:
            raise SystemExit(f"Binance provider only supports crypto symbols, got {raw_symbol}.")
        symbol = value

    symbol = symbol.replace("/", "").replace("-", "")
    if symbol.endswith(".P"):
        symbol = symbol[:-2]
    if symbol.endswith("PERP"):
        symbol = symbol[:-4]

    if symbol.endswith("USD") and not symbol.endswith("USDT"):
        symbol = f"{symbol[:-3]}USDT"
    if symbol in {"BTC", "BTCUSD"}:
        return "BTCUSDT"
    if symbol in {"ETH", "ETHUSD"}:
        return "ETHUSDT"
    if symbol in {"SOL", "SOLUSD"}:
        return "SOLUSDT"
    return symbol


def is_probably_crypto_symbol(symbol: str) -> bool:
    candidates = ("USDT", "USD", "BUSD", "USDC", "PERP")
    return any(symbol.endswith(candidate) for candidate in candidates)


def is_crypto_request(raw_symbol: str, market: str) -> bool:
    if market == "CRYPTO":
        return True
    symbol = raw_symbol.strip().upper().replace(" ", "")
    if ":" in symbol:
        exchange, _ = symbol.split(":", 1)
        return exchange.upper() in TV_CRYPTO_EXCHANGES
    return is_probably_crypto_symbol(symbol)


def infer_binance_market_type(raw_symbol: str) -> str:
    symbol = raw_symbol.strip().upper().replace(" ", "")
    if ":" in symbol:
        _, symbol = symbol.split(":", 1)
    if symbol.endswith(".P") or symbol.endswith("PERP"):
        return "futures"
    return "spot"


def infer_tvscreener_stock_market(exchange: str, market: str) -> str:
    if exchange in {"HKEX"}:
        return "hongkong"
    if exchange in {"SSE", "SZSE"}:
        return "china"
    if exchange in {"NASDAQ", "NYSE", "AMEX", "ARCA", "BATS"}:
        return "america"
    return TV_STOCK_MARKET_MAP.get(market, "america")


def get_tvscreener_interval(timeframe: str) -> Any:
    attr_name = TV_TIMEFRAME_MAP[timeframe]
    return getattr(TimeInterval, attr_name)


def get_tvscreener_ema_fields(kind: str, ema_periods: Sequence[int]) -> list[Any]:
    field_class = CryptoField if kind == "crypto" else StockField
    selected_fields = []
    for period in sorted(set(ema_periods)):
        field_name = f"EXPONENTIAL_MOVING_AVERAGE_{period}"
        if not hasattr(field_class, field_name):
            raise SystemExit(
                f"tvscreener provider does not expose EMA {period}. "
                "Use supported periods such as 20, 50, or 200."
            )
        selected_fields.append(getattr(field_class, field_name))
    return selected_fields


def build_tvscreener(
    kind: str,
    stock_market: str | None,
    fields: Sequence[Any],
    exact_symbol: str | None = None,
    search_token: str | None = None,
) -> Any:
    if kind == "crypto":
        screener = CryptoScreener()
    else:
        screener = StockScreener()
        screener.set_markets(stock_market or "america")

    screener.specific_fields = list(fields)
    if exact_symbol:
        screener.symbols = {"query": {"types": []}, "tickers": [exact_symbol]}
    else:
        screener.set_range(0, 20)
        if search_token:
            screener.add_prebuilt_filter(SearchFilter(search_token))
    return screener


def pick_tvscreener_row(frame: "pd.DataFrame", exact_symbol: str, search_token: str) -> "pd.Series":
    if frame.empty:
        raise SystemExit(f"No TradingView data returned for {exact_symbol or search_token}.")

    if "Symbol" in frame.columns:
        exact_row = frame[frame["Symbol"] == exact_symbol]
        if not exact_row.empty:
            return exact_row.iloc[0]

        suffix_row = frame[frame["Symbol"].astype(str).str.endswith(f":{search_token}")]
        if not suffix_row.empty:
            return suffix_row.iloc[0]

    return frame.iloc[0]


def fetch_tvscreener_snapshot(
    raw_symbol: str,
    market: str,
    timeframe: str,
    ema_periods: Sequence[int],
) -> dict[str, object]:
    normalized = normalize_symbol_for_tvscreener(raw_symbol, market)
    kind = normalized["kind"]
    fields_class = CryptoField if kind == "crypto" else StockField
    base_fields = [
        fields_class.OPEN,
        fields_class.HIGH,
        fields_class.LOW,
        fields_class.PRICE,
    ]
    if hasattr(fields_class, "VOLUME"):
        base_fields.append(fields_class.VOLUME)
    ema_fields = get_tvscreener_ema_fields(kind, ema_periods)
    screener_fields = [*base_fields, *ema_fields]
    tv_interval = get_tvscreener_interval(timeframe)

    screener = build_tvscreener(
        kind=kind,
        stock_market=normalized.get("stock_market"),
        fields=screener_fields,
        exact_symbol=normalized["symbol"],
        search_token=normalized["search_token"],
    )
    frame = screener.get(time_interval=tv_interval)
    row = pick_tvscreener_row(frame, normalized["symbol"], normalized["search_token"])

    payload: dict[str, object] = {
        "symbol": row["Symbol"],
        "open": round(float(row["Open"]), 6),
        "high": round(float(row["High"]), 6),
        "low": round(float(row["Low"]), 6),
        "close": round(float(row["Price"]), 6),
    }
    if "Volume" in row:
        try:
            payload["volume"] = float(row["Volume"])
        except (TypeError, ValueError):
            payload["volume"] = row["Volume"]
    if "Update Mode" in row:
        payload["update_mode"] = row["Update Mode"]
    for period in sorted(set(ema_periods)):
        label = f"Exponential Moving Average ({period})"
        if label in row:
            payload[f"ema_{period}"] = round(float(row[label]), 6)

    payload["provider_requested_at"] = datetime.now(timezone.utc).isoformat()
    payload["provider_kind"] = kind
    return payload


def flatten_columns(frame: "pd.DataFrame") -> "pd.DataFrame":
    if isinstance(frame.columns, pd.MultiIndex):
        frame.columns = [column[0] for column in frame.columns]
    return frame


def fetch_history(
    symbol: str,
    timeframe: str,
    start: datetime | None,
    end_exclusive: datetime | None,
    lookback: str,
) -> "pd.DataFrame":
    interval = YF_INTERVAL_MAP[timeframe]
    kwargs = {
        "tickers": symbol,
        "interval": interval,
        "auto_adjust": False,
        "progress": False,
        "threads": False,
    }
    if start is not None or end_exclusive is not None:
        if start is not None:
            kwargs["start"] = start
        if end_exclusive is not None:
            kwargs["end"] = end_exclusive
    else:
        kwargs["period"] = lookback

    frame = yf.download(**kwargs)
    if frame.empty:
        raise SystemExit(f"No data returned for {symbol} at timeframe {timeframe}.")
    frame = flatten_columns(frame)
    frame = frame.dropna(subset=["Open", "High", "Low", "Close"])
    return frame


def datetime_to_milliseconds(value: datetime) -> int:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return int(value.timestamp() * 1000)


def fetch_binance_history(
    symbol: str,
    timeframe: str,
    start: datetime | None,
    end_exclusive: datetime | None,
    lookback: str,
    market_type: str,
) -> "pd.DataFrame":
    interval = BINANCE_INTERVAL_MAP[timeframe]
    effective_end = end_exclusive or datetime.now(timezone.utc)
    effective_start = start
    if effective_start is None:
        effective_start = effective_end - parse_duration(lookback)

    limit = 1000
    rows: list[list[Any]] = []
    current_start_ms = datetime_to_milliseconds(effective_start)
    end_ms = datetime_to_milliseconds(effective_end)
    base_url = BINANCE_FUTURES_BASE_URL if market_type == "futures" else BINANCE_SPOT_BASE_URL
    path = "/fapi/v1/klines" if market_type == "futures" else "/api/v3/klines"

    while current_start_ms < end_ms:
        response = requests.get(
            f"{base_url}{path}",
            params={
                "symbol": symbol,
                "interval": interval,
                "startTime": current_start_ms,
                "endTime": end_ms,
                "limit": limit,
            },
            timeout=20,
        )
        response.raise_for_status()
        batch = response.json()
        if not batch:
            break

        rows.extend(batch)
        last_open_time = int(batch[-1][0])
        next_open_time = last_open_time + 1
        if next_open_time <= current_start_ms:
            break
        current_start_ms = next_open_time
        if len(batch) < limit:
            break

    if not rows:
        raise SystemExit(f"No Binance data returned for {symbol} at timeframe {timeframe}.")

    frame = pd.DataFrame(
        rows,
        columns=[
            "Open time",
            "Open",
            "High",
            "Low",
            "Close",
            "Volume",
            "Close time",
            "Quote asset volume",
            "Number of trades",
            "Taker buy base asset volume",
            "Taker buy quote asset volume",
            "Ignore",
        ],
    )
    frame["Open time"] = pd.to_datetime(frame["Open time"], unit="ms", utc=True)
    frame = frame.set_index("Open time")

    numeric_columns = [
        "Open",
        "High",
        "Low",
        "Close",
        "Volume",
        "Quote asset volume",
        "Taker buy base asset volume",
        "Taker buy quote asset volume",
    ]
    for column in numeric_columns:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame["Close time"] = pd.to_datetime(frame["Close time"], unit="ms", utc=True)
    frame["Number of trades"] = pd.to_numeric(frame["Number of trades"], errors="coerce")
    frame = frame.dropna(subset=["Open", "High", "Low", "Close"])
    frame = frame[~frame.index.duplicated(keep="last")]
    frame = frame.sort_index()
    return frame


def resample_if_needed(frame: "pd.DataFrame", timeframe: str) -> "pd.DataFrame":
    rule = RESAMPLE_RULES.get(timeframe)
    if not rule:
        return frame

    aggregations = {
        "Open": "first",
        "High": "max",
        "Low": "min",
        "Close": "last",
    }
    if "Adj Close" in frame.columns:
        aggregations["Adj Close"] = "last"
    if "Volume" in frame.columns:
        aggregations["Volume"] = "sum"

    frame = frame.resample(rule).agg(aggregations)
    frame = frame.dropna(subset=["Open", "High", "Low", "Close"])
    return frame


def add_derived_columns(frame: "pd.DataFrame", ema_periods: Sequence[int]) -> "pd.DataFrame":
    enriched = frame.copy()
    enriched["range"] = enriched["High"] - enriched["Low"]
    enriched["body"] = enriched["Close"] - enriched["Open"]
    enriched["body_abs"] = enriched["body"].abs()
    enriched["upper_wick"] = enriched["High"] - enriched[["Open", "Close"]].max(axis=1)
    enriched["lower_wick"] = enriched[["Open", "Close"]].min(axis=1) - enriched["Low"]
    enriched["direction"] = enriched.apply(classify_direction, axis=1)

    for period in sorted(set(ema_periods)):
        enriched[f"ema_{period}"] = enriched["Close"].ewm(span=period, adjust=False).mean()
    return enriched


def classify_direction(row: "pd.Series") -> str:
    if row["Close"] > row["Open"]:
        return "bull"
    if row["Close"] < row["Open"]:
        return "bear"
    return "neutral"


def filter_requested_window(
    frame: "pd.DataFrame",
    requested_start: datetime | None,
    requested_end_exclusive: datetime | None,
) -> "pd.DataFrame":
    filtered = frame
    if requested_start is not None:
        filtered = filtered[filtered.index >= requested_start]
    if requested_end_exclusive is not None:
        filtered = filtered[filtered.index < requested_end_exclusive]
    return filtered


def dataframe_to_records(frame: "pd.DataFrame") -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for timestamp, row in frame.iterrows():
        record: dict[str, object] = {"timestamp": timestamp.isoformat()}
        for column, value in row.items():
            if hasattr(value, "item"):
                value = value.item()
            if hasattr(value, "isoformat"):
                value = value.isoformat()
            if isinstance(value, float):
                value = round(value, 6)
            record[to_snake_case(column)] = value
        records.append(record)
    return records


def to_snake_case(value: str) -> str:
    return value.strip().lower().replace(" ", "_")


def build_summary(
    frame: "pd.DataFrame",
    normalized_symbol: str,
    timeframe: str,
    ema_periods: Sequence[int],
) -> dict[str, object]:
    last_row = frame.iloc[-1]
    summary = {
        "symbol": normalized_symbol,
        "timeframe": timeframe,
        "bars": int(len(frame)),
        "first_timestamp": frame.index[0].isoformat(),
        "last_timestamp": frame.index[-1].isoformat(),
        "highest_high": round(float(frame["High"].max()), 6),
        "lowest_low": round(float(frame["Low"].min()), 6),
        "last_close": round(float(last_row["Close"]), 6),
    }
    for period in sorted(set(ema_periods)):
        key = f"ema_{period}"
        if key in frame.columns:
            summary[key] = round(float(last_row[key]), 6)
    return summary


def emit_output(
    frame: "pd.DataFrame",
    summary: dict[str, object],
    args: argparse.Namespace,
    normalized_symbol: str,
    resolved_provider: str,
) -> None:
    destination = Path(args.output) if args.output else None

    if args.format == "json":
        payload = {
            "input": {
                "symbol": args.symbol,
                "provider": resolved_provider,
                "normalized_symbol": normalized_symbol,
                "market": args.market,
                "timeframe": args.timeframe,
                "start": args.start,
                "end": args.end,
                "recent": args.recent,
                "lookback": args.lookback,
                "ema": args.ema,
            },
            "summary": summary,
            "bars": dataframe_to_records(frame),
        }
        content = json.dumps(payload, indent=2)
    elif args.format == "csv":
        content = frame.to_csv()
    else:
        content = frame.to_string()

    if destination:
        destination.write_text(content + ("\n" if not content.endswith("\n") else ""))
    else:
        sys.stdout.write(content)
        if not content.endswith("\n"):
            sys.stdout.write("\n")


def emit_tvscreener_output(
    snapshot: dict[str, object],
    args: argparse.Namespace,
) -> None:
    destination = Path(args.output) if args.output else None
    summary = {
        "symbol": snapshot["symbol"],
        "timeframe": args.timeframe,
        "bars": 1,
        "highest_high": snapshot["high"],
        "lowest_low": snapshot["low"],
        "last_close": snapshot["close"],
    }
    for period in sorted(set(args.ema)):
        key = f"ema_{period}"
        if key in snapshot:
            summary[key] = snapshot[key]

    if args.format == "json":
        payload = {
            "input": {
                "symbol": args.symbol,
                "provider": args.provider,
                "market": args.market,
                "timeframe": args.timeframe,
                "ema": args.ema,
            },
            "provider": {
                "name": "tvscreener",
                "mode": "latest_interval_snapshot",
                "requested_at": snapshot["provider_requested_at"],
            },
            "summary": summary,
            "snapshot": snapshot,
            "limitations": [
                "tvscreener returns the latest TradingView interval snapshot, not a historical multi-bar sequence.",
                "Use binance for crypto history or yfinance for non-crypto history until a TradingView chart-history provider is added.",
            ],
        }
        content = json.dumps(payload, indent=2)
    else:
        frame = pd.DataFrame([snapshot])
        content = frame.to_csv(index=False) if args.format == "csv" else frame.to_string(index=False)

    if destination:
        destination.write_text(content + ("\n" if not content.endswith("\n") else ""))
    else:
        sys.stdout.write(content)
        if not content.endswith("\n"):
            sys.stdout.write("\n")


def main() -> None:
    args = parse_args()
    resolved_provider = args.provider
    if resolved_provider == "auto":
        resolved_provider = "binance" if is_crypto_request(args.symbol, args.market) else "yfinance"

    if resolved_provider == "tvscreener":
        require_tvscreener_dependencies()
        if args.start or args.end or args.recent:
            raise SystemExit(
                "tvscreener provider only supports the latest interval snapshot. "
                "Use binance for crypto history or yfinance for non-crypto history."
            )
        snapshot = fetch_tvscreener_snapshot(
            raw_symbol=args.symbol,
            market=args.market,
            timeframe=args.timeframe,
            ema_periods=args.ema,
        )
        emit_tvscreener_output(snapshot, args)
        return

    try:
        requested_start, requested_end_exclusive = resolve_requested_window(args)
    except ValueError as error:
        raise SystemExit(str(error))

    if resolved_provider == "binance":
        require_binance_dependencies()
        normalized_symbol = normalize_symbol_for_binance(args.symbol)
        binance_market_type = infer_binance_market_type(args.symbol)
    else:
        require_yfinance_dependencies()
        normalized_symbol = normalize_symbol(args.symbol, args.market)
        binance_market_type = ""

    fetch_start = requested_start
    if requested_start is not None:
        fetch_start = requested_start - warmup_delta(args.timeframe, max(args.ema))

    if resolved_provider == "binance":
        frame = fetch_binance_history(
            symbol=normalized_symbol,
            timeframe=args.timeframe,
            start=fetch_start,
            end_exclusive=requested_end_exclusive,
            lookback=args.lookback,
            market_type=binance_market_type,
        )
    else:
        frame = fetch_history(
            symbol=normalized_symbol,
            timeframe=args.timeframe,
            start=fetch_start,
            end_exclusive=requested_end_exclusive,
            lookback=args.lookback,
        )
    frame = resample_if_needed(frame, args.timeframe)
    frame = add_derived_columns(frame, args.ema)
    frame = filter_requested_window(frame, requested_start, requested_end_exclusive)

    if frame.empty:
        raise SystemExit("No rows remained after applying the requested date filter.")

    if args.tail > 0:
        frame = frame.tail(args.tail)

    summary = build_summary(frame, normalized_symbol, args.timeframe, args.ema)
    emit_output(frame, summary, args, normalized_symbol, resolved_provider)


if __name__ == "__main__":
    main()
