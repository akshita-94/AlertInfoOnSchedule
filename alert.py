#!/usr/bin/env python3
"""Send a stateless daily rate alert to Telegram."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from html.parser import HTMLParser
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


ALERT_SCHEDULES = (
    ("Morning Alert", 7, 30),
    ("Noon Alert", 12, 0),
    ("Night Alert", 22, 45),
)

MARKET_SYMBOLS = ("GOOGL", "MRNA", "FXAIX")
DEFAULT_TIMEOUT_SECONDS = 20


class AlertError(RuntimeError):
    """Raised when a required alert step cannot be completed."""


@dataclass(frozen=True)
class AlertLine:
    label: str
    value: str

    def render(self) -> str:
        return f"{self.label}: {self.value}"


def load_dotenv(path: Path = Path(".env")) -> None:
    """Load local .env values without requiring an extra dependency."""
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def get_json(url: str, params: dict[str, str] | None = None) -> Any:
    payload = get_text(url, params)

    try:
        return json.loads(payload)
    except json.JSONDecodeError as exc:
        raise AlertError("Response was not valid JSON") from exc


def get_text(url: str, params: dict[str, str] | None = None) -> str:
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"

    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "AlertingData/1.0",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=DEFAULT_TIMEOUT_SECONDS) as response:
            return response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:200]
        raise AlertError(f"HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise AlertError(f"Network error: {exc.reason}") from exc
    except TimeoutError as exc:
        raise AlertError("Request timed out") from exc


def post_form_json(url: str, fields: dict[str, str]) -> Any:
    request = urllib.request.Request(
        url,
        data=urllib.parse.urlencode(fields).encode("utf-8"),
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "AlertingData/1.0",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=DEFAULT_TIMEOUT_SECONDS) as response:
            payload = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:200]
        raise AlertError(f"Telegram HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise AlertError(f"Telegram network error: {exc.reason}") from exc
    except TimeoutError as exc:
        raise AlertError("Telegram request timed out") from exc

    try:
        return json.loads(payload)
    except json.JSONDecodeError as exc:
        raise AlertError("Telegram response was not valid JSON") from exc


def parse_decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise AlertError(f"Could not parse number: {value}") from exc


def format_decimal(value: Any, places: int) -> str:
    decimal = parse_decimal(value)
    quantizer = Decimal("1").scaleb(-places)
    rounded = decimal.quantize(quantizer, rounding=ROUND_HALF_UP)
    return f"{rounded:,.{places}f}"


def format_currency(value: Any, currency: str) -> str:
    if currency == "INR":
        return f"₹{format_decimal(value, 2)}"
    if currency == "USD":
        return f"${format_decimal(value, 2)}"
    return f"{format_decimal(value, 2)} {currency}"


def unavailable(source: str, exc: Exception) -> AlertLine:
    return AlertLine(source, f"unavailable ({exc})")


class VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.items: list[str] = []

    def handle_data(self, data: str) -> None:
        text = " ".join(data.split())
        if text:
            self.items.append(text)


def html_text_items(html: str) -> list[str]:
    parser = VisibleTextParser()
    parser.feed(html)
    return parser.items


def parse_rupee_text(value: str) -> Decimal:
    cleaned = value.replace("₹", "").replace(",", "").strip()
    return parse_decimal(cleaned)


def fetch_groww_gold_22k_inr() -> AlertLine:
    html = get_text("https://groww.in/gold-rates")
    items = html_text_items(html)

    try:
        section_start = items.index("Today Gold Rates Price Per Gram in India")
    except ValueError as exc:
        raise AlertError("missing per-gram gold section") from exc

    try:
        row_start = next(
            index for index in range(section_start, len(items)) if items[index] == "1 Gram"
        )
    except StopIteration as exc:
        raise AlertError("missing 1 Gram row") from exc

    prices = [item for item in items[row_start + 1 : row_start + 12] if item.startswith("₹")]
    if len(prices) < 2:
        raise AlertError("missing 22K per-gram price")

    price = parse_rupee_text(prices[1])
    return AlertLine("Gold India 22K", f"{format_currency(price, 'INR')}/g")


def fetch_spot_gold_22k_inr() -> AlertLine:
    data = get_json("https://api.goldprice.dev/v1/carat", {"currency": "INR"})
    price = data.get("price_gram_22k")
    if price is None:
        raise AlertError("missing price_gram_22k")
    return AlertLine("Gold India 22K Spot", f"{format_currency(price, 'INR')}/g")


def fetch_gold_22k_inr() -> AlertLine:
    provider = os.getenv("GOLD_DATA_PROVIDER", "groww").strip().lower()

    if provider == "spot":
        return fetch_spot_gold_22k_inr()
    if provider != "groww":
        raise AlertError(f"unknown GOLD_DATA_PROVIDER={provider}")

    return fetch_groww_gold_22k_inr()


def fetch_usd_inr() -> AlertLine:
    data = get_json("https://api.frankfurter.dev/v1/latest", {"base": "USD", "symbols": "INR"})
    rate = data.get("rates", {}).get("INR")
    if rate is None:
        raise AlertError("missing INR rate")
    return AlertLine("USD/INR", format_decimal(rate, 4))


def first_present(mapping: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        value = mapping.get(key)
        if value not in (None, "", "N/A", "N/D"):
            return value
    return None


def latest_close(result: dict[str, Any]) -> Any:
    quotes = result.get("indicators", {}).get("quote", [])
    if not quotes:
        return None

    closes = quotes[0].get("close", [])
    for value in reversed(closes):
        if value is not None:
            return value
    return None


def fetch_yahoo_market_quote(symbol: str) -> AlertLine:
    data = get_json(
        f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol)}",
        {"range": "5d", "interval": "1d"},
    )

    chart = data.get("chart", {})
    if chart.get("error"):
        raise AlertError(chart["error"])

    results = chart.get("result") or []
    if not results:
        raise AlertError("missing chart result")

    result = results[0]
    meta = result.get("meta", {})
    price = first_present(meta, ("regularMarketPrice", "previousClose")) or latest_close(result)
    if price is None:
        raise AlertError("missing price")

    currency = meta.get("currency") or "USD"
    return AlertLine(symbol, format_currency(price, currency))


def fetch_yahoo_market_quotes() -> list[AlertLine]:
    lines: list[AlertLine] = []
    for symbol in MARKET_SYMBOLS:
        try:
            lines.append(fetch_yahoo_market_quote(symbol))
        except Exception as exc:
            lines.append(unavailable(symbol, exc))

    return lines


def fetch_alpha_vantage_quote(symbol: str, api_key: str) -> AlertLine:
    data = get_json(
        "https://www.alphavantage.co/query",
        {
            "function": "GLOBAL_QUOTE",
            "symbol": symbol,
            "apikey": api_key,
        },
    )

    if "Note" in data:
        raise AlertError(data["Note"])
    if "Information" in data:
        raise AlertError(data["Information"])

    quote = data.get("Global Quote", {})
    price = quote.get("05. price")
    if not price:
        raise AlertError("missing price")
    return AlertLine(symbol, format_currency(price, "USD"))


def fetch_alpha_vantage_market_quotes(api_key: str) -> list[AlertLine]:
    lines: list[AlertLine] = []
    for symbol in MARKET_SYMBOLS:
        try:
            lines.append(fetch_alpha_vantage_quote(symbol, api_key))
        except Exception as exc:  # Keep the alert useful if one quote fails.
            lines.append(unavailable(symbol, exc))
    return lines


def fetch_market_quotes() -> list[AlertLine]:
    provider = os.getenv("MARKET_DATA_PROVIDER", "yahoo").strip().lower()

    if provider == "alpha_vantage":
        api_key = os.getenv("ALPHA_VANTAGE_API_KEY", "").strip()
        if not api_key:
            return [AlertLine(symbol, "unavailable (missing ALPHA_VANTAGE_API_KEY)") for symbol in MARKET_SYMBOLS]
        return fetch_alpha_vantage_market_quotes(api_key)

    if provider != "yahoo":
        return [AlertLine(symbol, f"unavailable (unknown MARKET_DATA_PROVIDER={provider})") for symbol in MARKET_SYMBOLS]

    return fetch_yahoo_market_quotes()


def nearest_alert(now: datetime) -> tuple[str, int]:
    current_minutes = now.hour * 60 + now.minute
    best_label = "AlertingData"
    best_distance = 24 * 60

    for label, hour, minute in ALERT_SCHEDULES:
        target_minutes = hour * 60 + minute
        distance = abs(current_minutes - target_minutes)
        distance = min(distance, 24 * 60 - distance)
        if distance < best_distance:
            best_label = label
            best_distance = distance

    return best_label, best_distance


def current_alert_label(now: datetime) -> str:
    override = os.getenv("ALERT_LABEL", "").strip()
    if override:
        return override

    best_label, best_distance = nearest_alert(now)
    return best_label if best_distance <= 90 else "AlertingData"


def scheduled_gate_enabled() -> bool:
    return os.getenv("SEND_ONLY_AT_SCHEDULED_TIME", "").strip().lower() in {"1", "true", "yes"}


def should_send_scheduled_alert(now: datetime) -> tuple[bool, str]:
    tolerance = int(os.getenv("SCHEDULE_TOLERANCE_MINUTES", "29"))
    label, distance = nearest_alert(now)
    if distance <= tolerance:
        return True, f"Within {distance} minutes of {label}."
    return False, f"Skipping: {now.strftime('%b %-d, %Y %-I:%M %p %Z')} is {distance} minutes from {label}."


def build_alert_message(now: datetime) -> str:
    lines: list[AlertLine] = []

    try:
        lines.append(fetch_gold_22k_inr())
    except Exception as exc:
        lines.append(unavailable("Gold India 22K", exc))

    try:
        lines.append(fetch_usd_inr())
    except Exception as exc:
        lines.append(unavailable("USD/INR", exc))

    lines.extend(fetch_market_quotes())

    timestamp = now.strftime("%b %-d, %Y %-I:%M %p %Z")
    return "\n".join(
        [
            current_alert_label(now),
            timestamp,
            "",
            *(line.render() for line in lines),
        ]
    )


def send_telegram_message(message: str) -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()

    if not token:
        raise AlertError("Missing TELEGRAM_BOT_TOKEN")
    if not chat_id:
        raise AlertError("Missing TELEGRAM_CHAT_ID")

    data = post_form_json(
        f"https://api.telegram.org/bot{token}/sendMessage",
        {
            "chat_id": chat_id,
            "text": message,
            "disable_web_page_preview": "true",
        },
    )
    if not data.get("ok"):
        raise AlertError(f"Telegram rejected message: {data}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send current market and currency rates to Telegram.")
    parser.add_argument("--dry-run", action="store_true", help="Print the alert instead of sending it.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    load_dotenv()

    timezone = ZoneInfo(os.getenv("ALERT_TIMEZONE", "America/Los_Angeles"))
    now = datetime.now(timezone)

    if scheduled_gate_enabled():
        should_send, reason = should_send_scheduled_alert(now)
        if not should_send:
            print(reason)
            return 0

    message = build_alert_message(now)

    if args.dry_run or os.getenv("DRY_RUN") == "1":
        print(message)
        return 0

    send_telegram_message(message)
    print("Alert sent.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AlertError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)
