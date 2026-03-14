#!/usr/bin/env python3
"""Build a data + chart bundle for market analysis."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from render_chart import render_chart


DEFAULT_SYMBOL = "BINANCE:BTCUSDT.P"
DEFAULT_MARKET = "CRYPTO"
DEFAULT_TIMEFRAME = "5m"
DEFAULT_RECENT = "2h"
DEFAULT_PROVIDER = "auto"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a market analysis bundle with data and a chart image.")
    parser.add_argument("--symbol", default=DEFAULT_SYMBOL, help="Default: Binance BTC perpetual")
    parser.add_argument("--market", default=DEFAULT_MARKET, help="Default: CRYPTO")
    parser.add_argument("--timeframe", default=DEFAULT_TIMEFRAME, help="Default: 5m")
    parser.add_argument("--provider", default=DEFAULT_PROVIDER, help="Default: auto")
    parser.add_argument("--recent", default=DEFAULT_RECENT, help="Default: 2h")
    parser.add_argument("--start", default="", help="Optional explicit start datetime")
    parser.add_argument("--end", default="", help="Optional explicit end datetime")
    parser.add_argument("--lookback", default="", help="Optional lookback when recent/start are omitted")
    parser.add_argument("--ema", nargs="+", type=int, default=[20, 50], help="EMA periods")
    parser.add_argument("--title", default="", help="Optional chart title")
    parser.add_argument("--user-image", default="", help="Optional path to a user-provided screenshot")
    parser.add_argument("--output-dir", default="", help="Optional output directory")
    return parser.parse_args()


def default_output_dir() -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return Path(tempfile.gettempdir()) / "al-brooks-price-action" / stamp


def build_fetch_command(args: argparse.Namespace, bars_path: Path) -> list[str]:
    fetch_script = Path(__file__).with_name("fetch_bars.py")
    command = [
        sys.executable,
        str(fetch_script),
        "--symbol",
        args.symbol,
        "--market",
        args.market,
        "--timeframe",
        args.timeframe,
        "--provider",
        args.provider,
        "--format",
        "json",
        "--output",
        str(bars_path),
        "--ema",
        *[str(value) for value in args.ema],
    ]

    if args.start:
        command.extend(["--start", args.start])
    if args.end:
        command.extend(["--end", args.end])
    if args.recent:
        command.extend(["--recent", args.recent])
    elif args.lookback:
        command.extend(["--lookback", args.lookback])

    return command


def derive_assumptions(args: argparse.Namespace) -> list[str]:
    assumptions = []
    if args.symbol == DEFAULT_SYMBOL:
        assumptions.append("Defaulted symbol to Binance BTC perpetual.")
    if args.timeframe == DEFAULT_TIMEFRAME:
        assumptions.append("Defaulted timeframe to 5m.")
    if args.recent == DEFAULT_RECENT and not args.start and not args.end:
        assumptions.append("Defaulted recent window to 2h.")
    return assumptions


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir) if args.output_dir else default_output_dir()
    output_dir.mkdir(parents=True, exist_ok=True)

    bars_path = output_dir / "bars.json"
    chart_path = output_dir / "chart.png"
    bundle_path = output_dir / "bundle.json"

    command = build_fetch_command(args, bars_path)
    subprocess.run(command, check=True)

    payload = json.loads(bars_path.read_text())
    chart_title = args.title or f"{payload['summary']['symbol']}  {payload['summary']['timeframe']}  recent"
    render_chart(payload, chart_path, chart_title)

    bundle = {
        "symbol": payload["summary"]["symbol"],
        "timeframe": payload["summary"]["timeframe"],
        "provider": payload["input"]["provider"],
        "summary": payload["summary"],
        "request": {
            "symbol": args.symbol,
            "market": args.market,
            "timeframe": args.timeframe,
            "provider": args.provider,
            "recent": args.recent,
            "start": args.start,
            "end": args.end,
            "lookback": args.lookback,
            "ema": args.ema,
        },
        "assumptions": derive_assumptions(args),
        "artifacts": {
            "bars_json": str(bars_path),
            "chart_png": str(chart_path),
            "bundle_json": str(bundle_path),
            "user_image": args.user_image,
        },
    }

    bundle_path.write_text(json.dumps(bundle, indent=2))
    sys.stdout.write(json.dumps(bundle, indent=2) + "\n")


if __name__ == "__main__":
    main()
