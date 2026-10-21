from __future__ import annotations

import unittest
from datetime import datetime
from datetime import timezone
from decimal import Decimal

from token_prices.openai_pricing import parse_openai_pricing_markdown
from token_prices.server import build_price_response


SAMPLE_PRICING_MARKDOWN = """
## Flagship models

<AccordionGroup id="latest-models" title="Latest models">
  <div data-value="standard">
    rows=[
      ["gpt-5.5 (<272K context length)", 5, 0.5, "-", 30],
      ["gpt-5.4 (<272K context length)", 2.5, 0.25, "-", 15],
      ["gpt-5.4-mini", 0.75, 0.075, "-", 4.5],
      ["gpt-5.4-nano", 0.2, 0.02, "-", 1.25]
    ]
  </div>
</AccordionGroup>
"""

SAMPLE_TABLE_PRICING_MARKDOWN = """
# Pricing

Flagship models

Prices per 1M tokens.

Standard

### Standard pricing data

| Model | Short context input | Short context cached input | Short context cache writes | Short context output | Long context input | Long context cached input | Long context cache writes | Long context output |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| gpt-5.6-luna | $1.00 | $0.10 | $1.25 | $6.00 | $2.00 | $0.20 | $2.50 | $9.00 |
| gpt-5.5 (<272K context length) | $5.00 | $0.50 | - | $30.00 | $10.00 | $1.00 | - | $45.00 |
| gpt-5.4-mini | $0.75 | $0.075 | - | $4.50 | - | - | - | - |
"""

SAMPLE_SPLIT_TABLE_PRICING_MARKDOWN = """
### Standard pricing data

| Model | Short context input | Short context output | Short context cached input | Short context 30m write | Short context 12h write | Long context input | Long context output |
| --- | --- | --- | --- | --- | --- | --- | --- |
| gpt-6.1-sol | $2.00 | $10.00 | $0.10 | $2.50 | $5.00 | $4.00 | $15.00 |
| gpt-5.5 | $5.00 | $30.00 | $0.50 | - | - | $10.00 | $45.00 |

| Model | Input | Output | Cached input |
| --- | --- | --- | --- |
| gpt-5.4-mini | $0.75 | $4.50 | $0.075 |

### Batch pricing data

| Model | Input | Output | Cached input |
| --- | --- | --- | --- |
| gpt-5.4-mini | $0.375 | $2.25 | $0.0375 |
"""


class OpenAIPricingTests(unittest.TestCase):
    def test_parse_split_standard_tables_without_batch_or_long_context_rates(self) -> None:
        prices = parse_openai_pricing_markdown(SAMPLE_SPLIT_TABLE_PRICING_MARKDOWN)

        self.assertEqual([price.model_id for price in prices], ["gpt-6.1-sol", "gpt-5.5", "gpt-5.4-mini"])
        self.assertEqual(prices[0].input_usd_per_1m_tokens, Decimal("2.00"))
        self.assertEqual(prices[0].output_usd_per_1m_tokens, Decimal("10.00"))
        self.assertEqual(prices[0].cache_write_usd_per_1m_tokens, Decimal("2.50"))
        self.assertEqual(prices[-1].output_usd_per_1m_tokens, Decimal("4.50"))
        self.assertEqual(prices[-1].cached_input_usd_per_1m_tokens, Decimal("0.075"))
        self.assertIsNone(prices[-1].cache_write_usd_per_1m_tokens)

    def test_parse_openai_pricing_markdown_extracts_fallback_rows(self) -> None:
        prices = parse_openai_pricing_markdown(SAMPLE_PRICING_MARKDOWN)

        self.assertEqual([price.model_id for price in prices], [
            "gpt-5.5",
            "gpt-5.4",
            "gpt-5.4-mini",
            "gpt-5.4-nano",
        ])
        self.assertEqual(prices[0].display_name, "gpt-5.5 (<272K context length)")
        self.assertEqual(prices[-1].input_usd_per_1m_tokens, Decimal("0.2"))
        self.assertEqual(prices[-1].output_usd_per_1m_tokens, Decimal("1.25"))

    def test_parse_openai_pricing_markdown_extracts_current_standard_table(self) -> None:
        prices = parse_openai_pricing_markdown(SAMPLE_TABLE_PRICING_MARKDOWN)

        self.assertEqual([price.model_id for price in prices], [
            "gpt-5.6-luna",
            "gpt-5.5",
            "gpt-5.4-mini",
        ])
        self.assertEqual(prices[0].cached_input_usd_per_1m_tokens, Decimal("0.10"))
        self.assertEqual(prices[0].cache_write_usd_per_1m_tokens, Decimal("1.25"))
        self.assertEqual(prices[-1].input_usd_per_1m_tokens, Decimal("0.75"))
        self.assertEqual(prices[-1].output_usd_per_1m_tokens, Decimal("4.50"))

    def test_token_pricing_api_response_contains_prices_by_model(self) -> None:
        prices = parse_openai_pricing_markdown(SAMPLE_TABLE_PRICING_MARKDOWN)
        response = build_price_response(
            prices,
            fetched_at=datetime(2026, 7, 30, tzinfo=timezone.utc),
            fetched=True,
        )

        self.assertTrue(response["ok"])
        self.assertEqual(response["service"], "token-prices-api")
        self.assertEqual(response["pricesByModel"]["gpt-5.4-mini"]["input"], 0.75)
        self.assertEqual(response["pricesByModel"]["gpt-5.4-mini"]["output"], 4.5)


if __name__ == "__main__":
    unittest.main()

