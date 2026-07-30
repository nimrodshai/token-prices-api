# Token Prices API

Standalone HTTP API for current LLM token pricing.

The service is intentionally independent from any product repository. PPP,
Assistyca, and other applications can consume the same URL.

## Endpoints

- `GET /api/health`
- `GET /api/openai/prices`
- `GET /api/openai/prices?refresh=1`
- `POST /internal/prices/refresh`

The API currently fetches OpenAI's public pricing markdown and parses the
standard pricing table into normalized JSON. It does not use an LLM and does not
need an OpenAI API key.

## Environment

- `TOKEN_PRICES_CACHE_TTL_SECONDS`: cache TTL in seconds. Defaults to one week.
- `TOKEN_PRICES_REFRESH_SECRET`: optional secret for `POST /internal/prices/refresh`.

If `TOKEN_PRICES_REFRESH_SECRET` is not set, the refresh endpoint is unprotected.
The GET refresh path is intentionally public because it only refreshes public
pricing data.

## Local Development

```bash
python3 scripts/run_token_pricing_server.py --host 127.0.0.1 --port 8899
curl http://127.0.0.1:8899/api/openai/prices
```

Run tests:

```bash
python3 -m unittest
```

