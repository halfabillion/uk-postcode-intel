# Install UK Postcode Intel in Cline

UK Postcode Intel is an MCP server that returns structured area information for a UK postcode from official open government data. There are two ways to use it.

## Recommended: hosted remote server

No local install, account or API key is required.

In Cline, open MCP Servers, then Configure MCP Servers. Merge this entry into the existing `mcpServers` object in the MCP settings JSON; preserve all other servers and settings:

```json
{
  "mcpServers": {
    "uk-postcode-intel": {
      "type": "streamableHttp",
      "url": "https://uk-postcode-intel.mcpize.run/mcp",
      "disabled": false,
      "autoApprove": []
    }
  }
}
```

Set `"type"` to `"streamableHttp"` (camelCase). Omitting it, or using `"http"` or `"streamable-http"`, can make Cline fall back to SSE, which this endpoint does not use.

Save the settings and connect. Confirm that these seven tools appear: `full_area_intelligence`, `area_report`, `house_prices`, `postcode_lookup`, `crime_summary`, `flood_warnings`, `food_hygiene_nearby`.

### Payment

The hosted endpoint charges per tool call in USDC on Base using the [x402](https://www.x402.org/) protocol. An unpaid `tools/call` returns HTTP 402 with the payment requirement. `initialize` and tool listing do not require payment.

Prices: `full_area_intelligence` $0.15; `area_report` $0.05; `house_prices` $0.02; `postcode_lookup`, `crime_summary`, `flood_warnings` and `food_hygiene_nearby` $0.01 each.

Payment goes to `0xd9784f8122af988E51b3183F725b0b53BCb8278A`. The asset is USD Coin on Base (`0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913`). On the wire, `maxAmountRequired` is in 6-decimal USDC units.

A client that does not settle x402 payments can still complete the initialize handshake and list tools. Unpaid tool calls will fail with HTTP 402. Do not treat a 402 as an installation failure.

Do not add API keys, Authorization headers or environment secrets for the hosted endpoint.

## Alternative: run locally

Requires [uv](https://docs.astral.sh/uv/) and Python 3.11+ (`.python-version` pins 3.13).

```bash
git clone https://github.com/halfabillion/uk-postcode-intel
cd uk-postcode-intel
uv sync
uv run uk-postcode-intel
```

The local process listens on `http://localhost:8080` (override with `PORT`). Health check: `http://localhost:8080/health`. MCP: `http://localhost:8080/mcp`. A local process does not apply x402 charges; those are enforced by the hosted gateway.

To point Cline at a local process:

```json
{
  "mcpServers": {
    "uk-postcode-intel": {
      "type": "streamableHttp",
      "url": "http://localhost:8080/mcp",
      "disabled": false,
      "autoApprove": []
    }
  }
}
```

Optional environment variables are listed in `.env.example`. No API key is required. Official upstream APIs are called at request time and may rate-limit or be unavailable.

## Licence and data

Software: MIT Licence. Data returned by the tools, and the bundled IoD 2025 extract, are not covered by the MIT licence; see `DATA_LICENSES.md`.

Repository: https://github.com/halfabillion/uk-postcode-intel  
Public listing: https://mcpize.com/mcp/uk-postcode-intel
