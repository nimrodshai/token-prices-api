#!/usr/bin/env python3
"""Fetch public pricing once and generate the JSON API for GitHub Pages."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from token_prices.openai_pricing import fetch_openai_pricing_markdown  # noqa: E402
from token_prices.openai_pricing import OpenAIPricingError  # noqa: E402
from token_prices.openai_pricing import parse_openai_pricing_markdown  # noqa: E402
from token_prices.server import build_price_response, now_utc, SERVICE_NAME  # noqa: E402


PRICE_PATHS = (
    "api/openai/prices.json",
    "api/prices.json",
    "api/prices/openai.json",
    # Directory indexes preserve fetch(...).json() for the old GET paths.
    # GitHub Pages redirects requests without a trailing slash to these indexes.
    "api/openai/prices/index.html",
    "api/prices/index.html",
    "api/prices/openai/index.html",
)
HEALTH_PATHS = ("index.html", "api/health.json", "api/health/index.html")


def build_site(output_dir: Path, *, markdown_text: str) -> int:
    # Parse and serialize everything before writing. A failed upstream fetch or
    # parse fails the build, leaving the last successful Pages deploy available.
    prices = parse_openai_pricing_markdown(markdown_text)
    fetched_at = now_utc()
    payload = build_price_response(prices, fetched_at=fetched_at, fetched=False)
    price_json = json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    health_json = json.dumps(
        {"ok": True, "service": SERVICE_NAME, "fetchedAt": fetched_at.isoformat()},
        indent=2,
    ) + "\n"

    for paths, content in ((PRICE_PATHS, price_json), (HEALTH_PATHS, health_json)):
        for relative_path in paths:
            path = output_dir / relative_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
    (output_dir / ".nojekyll").touch()
    return len(prices)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=REPO_ROOT / "_site")
    parser.add_argument("--source", type=Path, help="Local pricing markdown for offline builds.")
    args = parser.parse_args(argv)

    try:
        print("Loading OpenAI pricing markdown...", flush=True)
        source = args.source.read_text(encoding="utf-8") if args.source else fetch_openai_pricing_markdown()
        count = build_site(args.output, markdown_text=source)
    except (OpenAIPricingError, OSError, ValueError) as exc:
        parser.exit(1, f"Build failed: {exc}\n")
    print(f"Built {count} model prices in {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
