from __future__ import annotations

import ast
from dataclasses import dataclass
from decimal import Decimal
from decimal import ROUND_HALF_UP
import re
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request


OPENAI_PRICING_MARKDOWN_URL = "https://developers.openai.com/api/docs/pricing.md"
USD_PER_1M_QUANT = Decimal("0.0001")


class OpenAIPricingError(RuntimeError):
    pass


@dataclass(frozen=True)
class OpenAIModelPrice:
    model_id: str
    display_name: str
    tier: str
    input_usd_per_1m_tokens: Decimal
    output_usd_per_1m_tokens: Decimal
    cached_input_usd_per_1m_tokens: Decimal | None = None
    cache_write_usd_per_1m_tokens: Decimal | None = None

    @property
    def total_usd_per_1m_tokens(self) -> Decimal:
        return (self.input_usd_per_1m_tokens + self.output_usd_per_1m_tokens).quantize(
            USD_PER_1M_QUANT,
            rounding=ROUND_HALF_UP,
        )


def normalize_text(value: Any) -> str:
    return str(value or "").strip()


def normalize_model_id(name: str) -> str:
    match = re.match(r"([a-z0-9][a-z0-9.-]*)", normalize_text(name).lower())
    return match.group(1) if match else ""


def parse_decimal(value: Any) -> Decimal | None:
    if value in {None, "", "-", "Free"}:
        return None
    text = normalize_text(value).replace("$", "").replace(",", "")
    try:
        return Decimal(text)
    except Exception:
        return None


def split_markdown_table_row(line: str) -> list[str]:
    stripped = normalize_text(line)
    if not stripped.startswith("|") or not stripped.endswith("|"):
        return []
    return [cell.strip() for cell in stripped.strip("|").split("|")]


def extract_standard_pricing_table_rows(markdown_text: str) -> list[list[str]]:
    lines = markdown_text.splitlines()
    table_start = -1
    for index, line in enumerate(lines):
        if normalize_text(line).lower() == "### standard pricing data":
            table_start = index
            break
    if table_start < 0:
        raise OpenAIPricingError("Could not find the standard pricing table in OpenAI pricing markdown.")

    rows: list[list[str]] = []
    for line in lines[table_start + 1:]:
        stripped = normalize_text(line)
        if not stripped:
            if rows:
                break
            continue
        cells = split_markdown_table_row(stripped)
        if not cells:
            if rows:
                break
            continue
        rows.append(cells)
    if len(rows) < 3:
        raise OpenAIPricingError("OpenAI standard pricing markdown table is missing rows.")
    return rows


def parse_standard_pricing_table(markdown_text: str) -> list[OpenAIModelPrice]:
    rows = extract_standard_pricing_table_rows(markdown_text)
    header = [cell.lower() for cell in rows[0]]
    data_rows = rows[2:]

    def header_index(label: str) -> int:
        try:
            return header.index(label)
        except ValueError as exc:
            raise OpenAIPricingError(f"OpenAI pricing table is missing '{label}'.") from exc

    model_index = header_index("model")
    input_index = header_index("short context input")
    cached_input_index = header_index("short context cached input")
    cache_write_index = header_index("short context cache writes")
    output_index = header_index("short context output")

    prices: list[OpenAIModelPrice] = []
    for row in data_rows:
        if len(row) <= max(model_index, input_index, cached_input_index, cache_write_index, output_index):
            continue
        display_name = normalize_text(row[model_index])
        model_id = normalize_model_id(display_name)
        input_price = parse_decimal(row[input_index])
        output_price = parse_decimal(row[output_index])
        if not model_id or input_price is None or output_price is None:
            continue
        prices.append(
            OpenAIModelPrice(
                model_id=model_id,
                display_name=display_name,
                tier="standard",
                input_usd_per_1m_tokens=input_price,
                output_usd_per_1m_tokens=output_price,
                cached_input_usd_per_1m_tokens=parse_decimal(row[cached_input_index]),
                cache_write_usd_per_1m_tokens=parse_decimal(row[cache_write_index]),
            )
        )

    if not prices:
        raise OpenAIPricingError("OpenAI standard pricing markdown table did not contain usable rows.")
    return prices


def extract_flagship_standard_rows(markdown_text: str) -> list[list[Any]]:
    marker = 'id="latest-models"'
    start_index = markdown_text.find(marker)
    if start_index < 0:
        raise OpenAIPricingError("Could not find the flagship pricing section in OpenAI pricing markdown.")

    standard_index = markdown_text.find('data-value="standard"', start_index)
    if standard_index < 0:
        raise OpenAIPricingError("Could not find the standard pricing pane in OpenAI pricing markdown.")

    rows_index = markdown_text.find("rows=[", standard_index)
    if rows_index < 0:
        raise OpenAIPricingError("Could not find standard pricing rows in OpenAI pricing markdown.")

    content_start = rows_index + len("rows=[")
    depth = 1
    cursor = content_start
    while cursor < len(markdown_text) and depth > 0:
        char = markdown_text[cursor]
        if char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
        cursor += 1

    if depth != 0:
        raise OpenAIPricingError("OpenAI pricing markdown rows block is not balanced.")

    body = markdown_text[content_start:cursor - 1]
    sanitized = re.sub(r"\bnull\b", "None", body)
    try:
        rows = ast.literal_eval(f"[{sanitized}]")
    except Exception as exc:
        raise OpenAIPricingError("Could not parse OpenAI pricing rows from markdown.") from exc
    return rows if isinstance(rows, list) else []


def parse_openai_pricing_markdown(markdown_text: str) -> list[OpenAIModelPrice]:
    try:
        return parse_standard_pricing_table(markdown_text)
    except OpenAIPricingError:
        pass

    parsed_rows = extract_flagship_standard_rows(markdown_text)
    prices: list[OpenAIModelPrice] = []
    for row in parsed_rows:
        if not isinstance(row, list) or len(row) < 4:
            continue
        display_name = normalize_text(row[0])
        model_id = normalize_model_id(display_name)
        if not model_id:
            continue
        input_price = parse_decimal(row[1])
        output_price = parse_decimal(row[-1])
        if input_price is None or output_price is None:
            continue
        cached_input = parse_decimal(row[2]) if len(row) >= 4 else None
        cache_write = parse_decimal(row[3]) if len(row) >= 5 else None
        prices.append(
            OpenAIModelPrice(
                model_id=model_id,
                display_name=display_name,
                tier="standard",
                input_usd_per_1m_tokens=input_price,
                output_usd_per_1m_tokens=output_price,
                cached_input_usd_per_1m_tokens=cached_input,
                cache_write_usd_per_1m_tokens=cache_write,
            )
        )
    if not prices:
        raise OpenAIPricingError("OpenAI pricing markdown did not contain any usable model rows.")
    return prices


def fetch_openai_pricing_markdown(
    *,
    url: str = OPENAI_PRICING_MARKDOWN_URL,
    timeout_seconds: float = 20.0,
) -> str:
    request = urllib_request.Request(
        url,
        headers={
            "Accept": "text/markdown,text/plain;q=0.9,*/*;q=0.8",
            "User-Agent": "TokenPricesAPI/1.0",
        },
    )
    try:
        with urllib_request.urlopen(request, timeout=timeout_seconds) as response:
            return response.read().decode("utf-8")
    except urllib_error.URLError as exc:
        raise OpenAIPricingError(f"Could not load OpenAI pricing markdown: {exc}") from exc


__all__ = [
    "OPENAI_PRICING_MARKDOWN_URL",
    "OpenAIModelPrice",
    "OpenAIPricingError",
    "fetch_openai_pricing_markdown",
    "parse_openai_pricing_markdown",
    "parse_standard_pricing_table",
]

