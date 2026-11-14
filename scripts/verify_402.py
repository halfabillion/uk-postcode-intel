"""Verify live gateway: tools/list and an unpaid 402 for every tool. Usage: python verify_402.py"""
import json
import subprocess

G = "https://uk-postcode-intel.mcpize.run/mcp"
PAYTO = "0xd9784f8122af988E51b3183F725b0b53BCb8278A"
USDC_BASE = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
EXPECT = {"full_area_intelligence": 150000, "area_report": 50000, "house_prices": 20000,
          "postcode_lookup": 10000, "crime_summary": 10000, "flood_warnings": 10000,
          "food_hygiene_nearby": 10000}


SID = None


def post(body):
    global SID
    hdr = ["-H", f"mcp-session-id: {SID}"] if SID else []
    # curl: Cloudflare in front of the gateway rejects Python-urllib signatures (error 1010)
    out = subprocess.run(["curl", "-s", "-w", "\n%{http_code}", G, "-H",
                          "Content-Type: application/json", "-H",
                          "Accept: application/json, text/event-stream", *hdr, "-D", "/tmp/v402h.txt",
                          "-d", json.dumps(body)],
                         capture_output=True, text=True, timeout=90).stdout
    txt, _, code = out.rpartition("\n")
    for line in open("/tmp/v402h.txt"):
        if line.lower().startswith("mcp-session-id:") and not SID:
            SID = line.split(":", 1)[1].strip()
    if txt.startswith("event:") or "\ndata:" in txt or txt.startswith("data:"):
        txt = next(l[5:].strip() for l in txt.splitlines() if l.startswith("data:"))
    return int(code), txt


post({"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {"protocolVersion": "2025-03-26",
      "capabilities": {}, "clientInfo": {"name": "verify", "version": "1"}}})
post({"jsonrpc": "2.0", "method": "notifications/initialized"})


st, txt = post({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
names = [t["name"] for t in json.loads(txt)["result"]["tools"]]
print(f"tools/list HTTP {st}: {len(names)} tools: {names}")
ok_all = True
for name in sorted(set(names) | set(EXPECT)):
    st, txt = post({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                    "params": {"name": name, "arguments": {"postcode": "SW1A 1AA"}}})
    amt = pay = asset = net = None
    if st == 402:
        a = json.loads(txt)["accepts"][0]
        amt, pay, asset, net = int(a["maxAmountRequired"]), a["payTo"], a["asset"], a["network"]
    ok = (st == 402 and amt == EXPECT.get(name) and pay == PAYTO and asset == USDC_BASE
          and net == "base")
    ok_all &= ok
    print(f"{'OK ' if ok else 'BAD'} {name:24} HTTP {st} amount={amt} "
          f"(expect {EXPECT.get(name)}) network={net} payTo_ok={pay == PAYTO}")
print("ALL OK" if ok_all else "MISMATCH — check dashboard Payments tab")
