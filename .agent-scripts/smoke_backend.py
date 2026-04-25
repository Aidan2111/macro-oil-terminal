"""Smoke-test the fixture backend in-process via TestClient."""

from __future__ import annotations

import json
import sys

from fastapi.testclient import TestClient

sys.path.insert(0, "/Users/aidanbothost/Documents/macro_oil_terminal")
from backend.main import app  # noqa: E402

c = TestClient(app)
checks = [
    ("/health", ["status", "mode"]),
    ("/api/build-info", ["sha", "region"]),
    ("/api/spread", ["brent_price", "wti_price", "spread_usd", "series"]),
    ("/api/inventory", ["commercial_mbbl", "cushing_mbbl"]),
    ("/api/cftc", ["managed_money_net"]),
    ("/api/fleet/snapshot", ["vessels"]),
    ("/api/fleet/categories", ["vessel_counts"]),
    ("/api/thesis/latest", ["thesis", "empty"]),
    ("/api/thesis/history", ["theses"]),
    ("/api/positions", ["positions"]),
    ("/api/positions/account", ["equity", "buying_power"]),
    ("/api/positions/orders", ["orders"]),
]
fail = 0
for path, expected in checks:
    r = c.get(path)
    print(f"{path}: {r.status_code}")
    if r.status_code != 200:
        print(f"  BODY: {r.text[:200]}")
        fail += 1
        continue
    data = r.json()
    if isinstance(data, dict):
        missing = [k for k in expected if k not in data]
        if missing:
            print(f"  MISSING KEYS: {missing}")
            fail += 1

print()
print("=== /api/positions/stream — content-type check ===")
# Use a streaming GET; iter once to confirm the comment-frame, then close.
try:
    with c.stream("GET", "/api/positions/stream", timeout=2.0) as resp:
        print(f"status={resp.status_code} content-type={resp.headers.get('content-type')}")
        first = next(iter(resp.iter_text()))
        print(f"first frame: {first!r}")
except Exception as exc:
    print(f"  stream-check exception (non-fatal): {exc!r}")

print()
print("=== thesis/latest payload shape ===")
r = c.get("/api/thesis/latest")
d = r.json()
print("top:", list(d.keys()))
t = d["thesis"]
print("audit:", list(t.keys()))
print("thesis (raw):", list(t["thesis"].keys()))
print("instruments[0]:", json.dumps(t["instruments"][0], indent=2))
print("checklist[0]:", json.dumps(t["checklist"][0], indent=2))
print("context:", json.dumps(t["context"], indent=2))

sys.exit(fail)
