#!/usr/bin/env python3
"""Render a simple candlestick chart PNG from fetch_bars JSON output."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


WIDTH = 1600
HEIGHT = 900
TOP_PAD = 90
BOTTOM_PAD = 90
LEFT_PAD = 80
RIGHT_PAD = 160
GRID_LINES = 6
BG = "#f8f8f6"
GRID = "#d8d5cc"
TEXT = "#1f2328"
UP = "#1f9d55"
DOWN = "#d94841"
WICK = "#30343a"
EMA_COLORS = {
    "ema_20": "#1f77b4",
    "ema_50": "#ff7f0e",
    "ema_200": "#9467bd",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render a candlestick chart from fetch_bars JSON output.")
    parser.add_argument("--input", required=True, help="Path to fetch_bars JSON output")
    parser.add_argument("--output", required=True, help="PNG output path")
    parser.add_argument("--title", default="", help="Optional chart title")
    return parser.parse_args()


def load_payload(path: Path) -> dict:
    return json.loads(path.read_text())


def render_chart(payload: dict, output_path: Path, title: str = "") -> Path:
    bars = payload.get("bars", [])
    if not bars:
        raise SystemExit("No bars found in payload. render_chart.py expects historical bar output.")

    image = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()

    chart_left = LEFT_PAD
    chart_top = TOP_PAD
    chart_right = WIDTH - RIGHT_PAD
    chart_bottom = HEIGHT - BOTTOM_PAD
    chart_width = chart_right - chart_left
    chart_height = chart_bottom - chart_top

    price_values = []
    for bar in bars:
        price_values.extend([bar["high"], bar["low"], bar["open"], bar["close"]])
        for key in EMA_COLORS:
            if key in bar:
                price_values.append(bar[key])

    min_price = min(price_values)
    max_price = max(price_values)
    if max_price == min_price:
        max_price += 1
        min_price -= 1
    padding = (max_price - min_price) * 0.08
    min_price -= padding
    max_price += padding

    def price_to_y(price: float) -> int:
        normalized = (price - min_price) / (max_price - min_price)
        return int(chart_bottom - normalized * chart_height)

    draw_grid(draw, font, chart_left, chart_top, chart_right, chart_bottom, min_price, max_price)
    draw_title(draw, font, payload, title)
    draw_candles(draw, bars, chart_left, chart_width, price_to_y)
    draw_emas(draw, bars, chart_left, chart_width, price_to_y)
    draw_footer(draw, font, payload, chart_left, chart_bottom, chart_right)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path)
    return output_path


def draw_grid(
    draw: ImageDraw.ImageDraw,
    font: ImageFont.ImageFont,
    left: int,
    top: int,
    right: int,
    bottom: int,
    min_price: float,
    max_price: float,
) -> None:
    for index in range(GRID_LINES):
        ratio = index / (GRID_LINES - 1)
        y = int(top + (bottom - top) * ratio)
        draw.line((left, y, right, y), fill=GRID, width=1)
        price = max_price - (max_price - min_price) * ratio
        draw.text((right + 12, y - 7), f"{price:,.2f}", fill=TEXT, font=font)


def draw_title(draw: ImageDraw.ImageDraw, font: ImageFont.ImageFont, payload: dict, title: str) -> None:
    summary = payload.get("summary", {})
    chart_title = title or f"{summary.get('symbol', 'Unknown')}  {summary.get('timeframe', '')}"
    draw.text((LEFT_PAD, 24), chart_title, fill=TEXT, font=font)

    input_meta = payload.get("input", {})
    meta_text = f"provider={input_meta.get('provider', 'unknown')}  ema={input_meta.get('ema', [])}"
    draw.text((LEFT_PAD, 48), meta_text, fill=TEXT, font=font)


def draw_candles(
    draw: ImageDraw.ImageDraw,
    bars: list[dict],
    left: int,
    width: int,
    price_to_y,
) -> None:
    count = len(bars)
    candle_slot = max(width / max(count, 1), 8)
    candle_width = max(int(candle_slot * 0.55), 3)

    for index, bar in enumerate(bars):
        center_x = int(left + candle_slot * index + candle_slot / 2)
        wick_top = price_to_y(bar["high"])
        wick_bottom = price_to_y(bar["low"])
        open_y = price_to_y(bar["open"])
        close_y = price_to_y(bar["close"])
        color = UP if bar["close"] >= bar["open"] else DOWN

        draw.line((center_x, wick_top, center_x, wick_bottom), fill=WICK, width=2)
        body_top = min(open_y, close_y)
        body_bottom = max(open_y, close_y)
        if body_top == body_bottom:
            body_bottom += 1
        draw.rectangle(
            (
                center_x - candle_width // 2,
                body_top,
                center_x + candle_width // 2,
                body_bottom,
            ),
            fill=color,
            outline=color,
        )


def draw_emas(
    draw: ImageDraw.ImageDraw,
    bars: list[dict],
    left: int,
    width: int,
    price_to_y,
) -> None:
    count = len(bars)
    candle_slot = max(width / max(count, 1), 8)

    for ema_key, color in EMA_COLORS.items():
        if ema_key not in bars[0]:
            continue
        points = []
        for index, bar in enumerate(bars):
            x = int(left + candle_slot * index + candle_slot / 2)
            y = price_to_y(bar[ema_key])
            points.append((x, y))
        if len(points) >= 2:
            draw.line(points, fill=color, width=3)


def draw_footer(
    draw: ImageDraw.ImageDraw,
    font: ImageFont.ImageFont,
    payload: dict,
    left: int,
    bottom: int,
    right: int,
) -> None:
    bars = payload.get("bars", [])
    if not bars:
        return

    first_ts = bars[0]["timestamp"]
    last_ts = bars[-1]["timestamp"]
    draw.text((left, bottom + 24), f"{first_ts}  ->  {last_ts}", fill=TEXT, font=font)

    legend_x = right - 140
    current_y = 24
    for ema_key, color in EMA_COLORS.items():
        if ema_key not in bars[0]:
            continue
        draw.line((legend_x, current_y + 7, legend_x + 22, current_y + 7), fill=color, width=3)
        draw.text((legend_x + 30, current_y), ema_key.upper(), fill=TEXT, font=font)
        current_y += 20


def main() -> None:
    args = parse_args()
    payload = load_payload(Path(args.input))
    render_chart(payload, Path(args.output), args.title)


if __name__ == "__main__":
    main()
