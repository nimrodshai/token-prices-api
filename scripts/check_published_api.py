#!/usr/bin/env python3
"""Smoke-test a published pricing snapshot, including legacy GET paths."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
from urllib.error import URLError
from urllib.request import urlopen


DEFAULT_BASE_URL = "https://nimrodshai.github.io/token-prices-api"


def check_api(base_url: str) -> None:
    snapshot = None
    paths = (
        "/api/openai/prices.json", "/api/prices.json", "/api/prices/openai.json",
        "/api/openai/prices", "/api/prices", "/api/prices/openai",
        "/api/openai/prices?refresh=1",
    )
    for path in paths:
        with urlopen(base_url.rstrip("/") + path, timeout=20) as response:
            if path.endswith(".json"):
                if response.headers.get_content_type() != "application/json":
                    raise ValueError(f"{path}: expected application/json")
                if response.headers.get("Access-Control-Allow-Origin") != "*":
                    raise ValueError(f"{path}: cross-origin access is unavailable")
            payload = json.load(response)
        if not payload.get("ok") or not payload.get("prices") or not payload.get("pricesByModel"):
            raise ValueError(f"{path}: missing or empty pricing snapshot")
        if snapshot is None:
            snapshot = payload
            fetched_at = datetime.fromisoformat(payload["fetchedAt"])
            age = datetime.now(timezone.utc) - fetched_at
            if age < -timedelta(minutes=5) or age > timedelta(days=8):
                raise ValueError(f"{path}: snapshot timestamp is out of range: {fetched_at}")
        elif payload != snapshot:
            raise ValueError(f"{path}: snapshot differs from the canonical endpoint")
        print(f"OK {path}")

    for path in ("/", "/api/health", "/api/health.json"):
        with urlopen(base_url.rstrip("/") + path, timeout=20) as response:
            health = json.load(response)
        if not health.get("ok") or health.get("fetchedAt") != snapshot["fetchedAt"]:
            raise ValueError(f"{path}: health does not match the pricing snapshot")
        print(f"OK {path}")
    print(f"Verified {len(snapshot['prices'])} models, fetched at {snapshot['fetchedAt']}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    args = parser.parse_args()
    try:
        check_api(args.base_url)
    except (URLError, ValueError, KeyError, TypeError) as exc:
        parser.exit(1, f"API check failed: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
