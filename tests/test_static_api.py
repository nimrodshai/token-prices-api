from __future__ import annotations

from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
from threading import Thread
import unittest
from urllib.request import urlopen

from scripts.build_static_api import build_site
from test_openai_pricing import SAMPLE_TABLE_PRICING_MARKDOWN
from token_prices.openai_pricing import OpenAIPricingError


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args: object) -> None:
        pass


class StaticAPITests(unittest.TestCase):
    def test_published_json_preserves_api_schema(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            count = build_site(output, markdown_text=SAMPLE_TABLE_PRICING_MARKDOWN)
            prices = json.loads((output / "api/openai/prices.json").read_text())
            health = json.loads((output / "api/health.json").read_text())

            self.assertEqual(count, 3)
            self.assertTrue(prices["ok"])
            self.assertEqual(prices["provider"], "openai")
            self.assertEqual(prices["currency"], "USD")
            self.assertEqual(prices["unit"], "per_1m_tokens")
            self.assertEqual(prices["pricesByModel"]["gpt-5.6-luna"], {
                "input": 1.0, "cached_input": 0.1, "cache_write": 1.25, "output": 6.0,
            })
            self.assertFalse(prices["fetched"])
            self.assertEqual(health["fetchedAt"], prices["fetchedAt"])

    def test_static_host_serves_canonical_json_and_legacy_get_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            build_site(Path(directory), markdown_text=SAMPLE_TABLE_PRICING_MARKDOWN)
            server = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHandler, directory=directory))
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f"http://127.0.0.1:{server.server_port}"
            try:
                for path in (
                    "/api/openai/prices.json", "/api/prices.json", "/api/prices/openai.json",
                    "/api/openai/prices", "/api/prices", "/api/prices/openai",
                    "/api/openai/prices?refresh=1",
                ):
                    with self.subTest(path=path), urlopen(base + path, timeout=5) as response:
                        self.assertEqual(response.status, 200)
                        if path.endswith(".json"):
                            self.assertEqual(response.headers.get_content_type(), "application/json")
                        payload = json.load(response)
                        self.assertEqual(payload["pricesByModel"]["gpt-5.6-luna"]["output"], 6.0)
                for path in ("/", "/api/health", "/api/health.json"):
                    with self.subTest(path=path), urlopen(base + path, timeout=5) as response:
                        self.assertTrue(json.load(response)["ok"])
            finally:
                server.shutdown()
                server.server_close()
                thread.join()

    def test_invalid_source_does_not_replace_last_successful_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            build_site(output, markdown_text=SAMPLE_TABLE_PRICING_MARKDOWN)
            previous = (output / "api/openai/prices.json").read_bytes()
            with self.assertRaises(OpenAIPricingError):
                build_site(output, markdown_text="Upstream pricing is temporarily unavailable.")
            self.assertEqual((output / "api/openai/prices.json").read_bytes(), previous)


if __name__ == "__main__":
    unittest.main()
