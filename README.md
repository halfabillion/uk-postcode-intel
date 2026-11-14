# UK Postcode Intel

An MCP server that returns structured area information for a UK postcode from official open government data.

The headline tool, `full_area_intelligence`, fetches several sources in parallel and returns one JSON report. Six cheaper tools expose the same sources individually, or as a lighter bundle.

## Hosted endpoint

- MCP (Streamable HTTP): <https://uk-postcode-intel.mcpize.run/mcp>
- Public listing: <https://mcpize.com/mcp/uk-postcode-intel>

The hosted endpoint charges per tool call in USDC on Base, using the [x402](https://www.x402.org/) protocol. Payment goes to `0xd9784f8122af988E51b3183F725b0b53BCb8278A`. The asset is USD Coin on Base (`0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913`). No account or API key is required. An unpaid `tools/call` returns HTTP 402 with the payment requirement.

## Tools and prices

| Tool | Price per call | Description |
|---|---|---|
| `full_area_intelligence` | $0.15 | Complete area report: summary, location, deprivation, Census 2021 demographics, crime, flood, house prices (postcode and neighbours), food hygiene, plus source status and attribution. |
| `area_report` | $0.05 | Lighter bundle: location, crime, flood, nearby food hygiene, and Land Registry sales at the postcode. |
| `house_prices` | $0.02 | Recorded residential sale prices at the postcode (England and Wales), with median, min and max. |
| `postcode_lookup` | $0.01 | Coordinates, council, ward, constituency, region, and LSOA/MSOA codes via postcodes.io. |
| `crime_summary` | $0.01 | Latest month of street crime within about one mile, by category, with top streets and outcomes. |
| `flood_warnings` | $0.01 | Live Environment Agency flood alerts or warnings and nearby river gauges (England). |
| `food_hygiene_nearby` | $0.01 | Nearest food businesses with Food Standards Agency hygiene ratings, plus the rating distribution. |

Prices are in US dollars, charged as USDC. On the wire, `maxAmountRequired` is in 6-decimal USDC units: `150000` ($0.15), `50000` ($0.05), `20000` ($0.02) and `10000` ($0.01).

`full_area_intelligence` includes a plain-English `summary`; location (coordinates, ward, council, constituency, region, LSOA/MSOA, rural-urban class); deprivation (England: IoD 2025 IMD and domain deciles; other UK nations: a national rank from the ONS Postcode Directory where published); Census 2021 demographics for the neighbourhood compared with the council and the nation (England and Wales); street crime; live flood alerts (England); HM Land Registry sold prices at the postcode and neighbouring postcodes within about 400 m, including a 5-year median and median by property type; and nearby FSA ratings. Sources are fetched in parallel with a timeout. If one source is down or out of coverage, it is recorded under `sources_status` and the rest of the report is still returned.

### Coverage

| Source | Coverage |
|---|---|
| Location (postcodes.io / ONSPD) | United Kingdom |
| IoD 2025 IMD and domain deciles | England (bundled MHCLG extract) |
| National deprivation rank from ONSPD | Wales, Scotland, Northern Ireland (where published) |
| Census 2021 demographics | England and Wales |
| Street crime (data.police.uk) | England, Wales and Northern Ireland |
| Live flood alerts and gauges | England |
| Land Registry Price Paid | England and Wales |
| FSA food hygiene ratings | Requested for any UK postcode |

Some police forces do not currently publish street-level data to data.police.uk (the code notes Greater Manchester Police as an example). A zero crime count does not mean the area is crime-free.

## How to call the hosted server

### MCP client

Point an MCP client that supports Streamable HTTP at the hosted endpoint:

```json
{
  "mcpServers": {
    "uk-postcode-intel": {
      "type": "http",
      "url": "https://uk-postcode-intel.mcpize.run/mcp"
    }
  }
}
```

An x402-capable client will settle the 402 payment requirement and retry the tool call. A client that does not handle x402 can still complete the initialize handshake and list tools; unpaid tool calls will fail with HTTP 402.

### Raw HTTP

Send `Content-Type: application/json` and `Accept: application/json, text/event-stream`. The gateway may respond with Server-Sent Events. Capture the `mcp-session-id` response header from `initialize` and send it on later requests.

```bash
ENDPOINT=https://uk-postcode-intel.mcpize.run/mcp

# 1. Initialize and read mcp-session-id
curl -sS -D /tmp/pci-headers.txt \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":0,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"demo","version":"1"}}}' \
  "$ENDPOINT"

SID=$(awk -F': ' 'tolower($1)=="mcp-session-id"{print $2}' /tmp/pci-headers.txt | tr -d '\r')

# 2. notifications/initialized
curl -sS \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "mcp-session-id: $SID" \
  -d '{"jsonrpc":"2.0","method":"notifications/initialized"}' \
  "$ENDPOINT"

# 3. Unpaid tools/call — expect HTTP 402
curl -sS -D - \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "mcp-session-id: $SID" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"postcode_lookup","arguments":{"postcode":"SW1A 1AA"}}}' \
  "$ENDPOINT"
```

A 402 response includes an `accepts` entry with `maxAmountRequired` (6-decimal USDC units), `payTo` (`0xd9784f8122af988E51b3183F725b0b53BCb8278A`), `asset` (Base USDC `0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913`) and `network` (`base`).

`scripts/verify_402.py` runs this check against all seven tools on the live gateway.

## Run locally

Requires [uv](https://docs.astral.sh/uv/) and Python 3.11+ (`.python-version` pins 3.13).

```bash
git clone https://github.com/halfabillion/uk-postcode-intel
cd uk-postcode-intel
uv sync
uv run uk-postcode-intel
```

The server listens on `http://localhost:8080` (override with `PORT`). Health check: `http://localhost:8080/health`. MCP: `http://localhost:8080/mcp`. Optional environment variables are listed in `.env.example`.

A local process does not apply x402 charges; those are enforced by the hosted gateway. Official upstream APIs are called at request time and may rate-limit or be unavailable.

`Makefile` targets: `make dev`, `make install`, `make run`, `make test`, `make lint`, `make format`, `make clean`.

## Tests

Default tests are offline. They cover postcode normalisation, registration of all seven tools, the bundled IoD 2025 deprivation lookup, census-response shaping, summary text, and graceful degradation when upstream sources fail. They do not call live APIs.

```bash
uv sync
uv run pytest
```

Live tests hit the upstream APIs and are skipped unless `LIVE=1` is set:

```bash
LIVE=1 uv run pytest
```

## Licence

This software is released under the MIT Licence, Copyright (c) 2026 Ali Ghaedi. See [LICENSE](LICENSE).

Data returned by the tools, and the bundled IoD 2025 extract, are not covered by the MIT licence. See [DATA_LICENSES.md](DATA_LICENSES.md) for sources, attributions and third-party terms (including OS, Royal Mail, ONS, MHCLG, data.police.uk, Environment Agency, the Food Standards Agency and HM Land Registry).
