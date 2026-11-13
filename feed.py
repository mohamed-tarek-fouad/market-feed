#!/usr/bin/env python3
"""Fetch Binance spot candles for Claude's market read.

Runs inside GitHub Actions (see .github/workflows/feed.yml). Writes the
candles in the compact format the journal helper reads, the same one the old
browser fetch produced:

    {"v": 2, "server_time": ms, "data": {SYMBOL: {TF: {t0, p0, n, rows}}}, "futures": {}}

where rows is "do,dh,dl,dc,vol;..." in cents.

Usage: python3 feed.py OUT_DIR
Always writes OUT_DIR/status.json. Writes OUT_DIR/latest.json only when every
fetch succeeded, so a failed run keeps the previous prices in place.
"""
import json
import math
import os
import sys
import time
import urllib.error
import urllib.request

SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "PAXGUSDT"]
FRAMES = {"15m": 1000, "1h": 500, "4h": 300}
HOSTS = [
    "https://data-api.binance.vision",
    "https://api.binance.com",
    "https://api-gcp.binance.com",
]


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "market-feed/1.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


def js_round(x):
    """Math.round from JavaScript, so the output matches the old browser fetch."""
    return math.floor(x + 0.5)


def cents(s):
    return js_round(float(s) * 100)


def encode(k):
    prev, rows = cents(k[0][1]), []
    for r in k:
        o, h, l, c = cents(r[1]), cents(r[2]), cents(r[3]), cents(r[4])
        rows.append(f"{o - prev},{h - o},{o - l},{c - o},{js_round(float(r[5]))}")
        prev = c
    return {"t0": k[0][0], "p0": cents(k[0][1]), "n": len(k), "rows": ";".join(rows)}


def fetch(host):
    server_time = get(f"{host}/api/v3/time")["serverTime"]
    data = {}
    for sym in SYMBOLS:
        data[sym] = {}
        for tf, n in FRAMES.items():
            k = get(f"{host}/api/v3/klines?symbol={sym}&interval={tf}&limit={n}")
            if not isinstance(k, list) or len(k) < 50:
                raise ValueError(f"{sym} {tf}: unexpected answer")
            data[sym][tf] = encode(k)
    return server_time, data


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else "out"
    os.makedirs(out, exist_ok=True)
    status = {
        "ok": False,
        "checked_ms": int(time.time() * 1000),
        "event": os.environ.get("EVENT", "manual"),
        "request": os.environ.get("REQUEST_ID", ""),
        "tries": [],
    }
    for host in HOSTS:
        try:
            server_time, data = fetch(host)
        except urllib.error.HTTPError as e:
            body = e.read()[:200].decode("utf-8", "replace")
            status["tries"].append({"host": host, "error": f"HTTP {e.code}", "body": body})
            continue
        except Exception as e:  # network errors, bad answers
            status["tries"].append({"host": host, "error": f"{type(e).__name__}: {e}"[:300]})
            continue
        feed = {"v": 2, "server_time": server_time, "data": data, "futures": {},
                "source": host, "request": status["request"]}
        with open(os.path.join(out, "latest.json"), "w", encoding="utf-8") as f:
            json.dump(feed, f, separators=(",", ":"))
        status.update(ok=True, host=host, server_time=server_time)
        break
    with open(os.path.join(out, "status.json"), "w", encoding="utf-8") as f:
        json.dump(status, f, indent=1)
    print(json.dumps(status))
    return 0 if status["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
