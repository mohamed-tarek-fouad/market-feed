#!/usr/bin/env python3
"""Get fresh Binance candles for one market read (runs in Claude's session).

Run it from a clone of this repo:

    python3 get_prices.py --out RAW.json

1. Pushes an empty commit to the `request` branch. That starts the
   price-feed workflow, which fetches Binance prices on GitHub's servers and
   publishes them to the `data` branch.
2. Waits (up to --wait seconds) for `data` to answer that request, then copies
   the prices to RAW.json for the journal helper (trader_tools.py prepare --raw).

If the push fails, or the request isn't answered in time, it falls back to the
newest prices already on `data` when they are at most --max-age seconds old.

Prints one line starting with OK, STALE (older prices used) or FAIL.
Exit code 0 for OK and STALE, 2 for FAIL.
"""
import argparse
import json
import os
import subprocess
import sys
import time


def git(repo, *args, check=True):
    r = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True, timeout=90)
    if check and r.returncode != 0:
        raise RuntimeError(f"git {args[0]} failed: {' '.join(r.stderr.split())[:200]}")
    return r


def read_data(repo):
    """(status, latest) from the newest commit on the `data` branch."""
    if git(repo, "fetch", "-q", "--depth=1", "origin", "data", check=False).returncode != 0:
        return None, None

    def show(name):
        r = git(repo, "show", f"FETCH_HEAD:{name}", check=False)
        if r.returncode != 0:
            return None
        try:
            return json.loads(r.stdout)
        except ValueError:
            return None

    return show("status.json"), show("latest.json")


def now_ms():
    return int(time.time() * 1000)


def hhmm(ms):
    return time.strftime("%H:%M UTC", time.gmtime(ms / 1000))


def save(path, latest):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(latest, f, separators=(",", ":"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, help="where to write the prices for the helper")
    ap.add_argument("--repo", default=os.path.dirname(os.path.abspath(__file__)))
    ap.add_argument("--wait", type=int, default=180, help="seconds to wait for fresh prices")
    ap.add_argument("--max-age", type=int, default=1200, help="oldest fallback prices, seconds")
    a = ap.parse_args()

    t_req = now_ms()
    sha, note = None, ""
    try:
        git(a.repo, "-c", "user.name=market-read", "-c", "user.email=market-read@users.noreply.github.com",
            "commit", "-q", "--allow-empty", "-m", "request " + time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
        sha = git(a.repo, "rev-parse", "HEAD").stdout.strip()
        git(a.repo, "push", "-q", "-f", "origin", "HEAD:refs/heads/request")
    except Exception as e:
        sha, note = None, f"could not ask GitHub for fresh prices ({e})"

    status = latest = None
    if sha:
        deadline = time.time() + a.wait
        while time.time() < deadline:
            time.sleep(8)
            status, latest = read_data(a.repo)
            if status and status.get("request") == sha:
                if status.get("ok") and latest and latest.get("request") == sha:
                    save(a.out, latest)
                    print(f"OK prices from {hhmm(latest['server_time'])} via {latest.get('source', '?')}, "
                          f"answered in {(now_ms() - t_req) // 1000}s")
                    return 0
                tries = "; ".join(f"{t.get('host')}: {t.get('error')}" for t in status.get("tries", []))
                note = f"GitHub could not get prices from Binance ({tries})"
                break
            if latest and latest.get("server_time", 0) >= t_req - 60_000:
                save(a.out, latest)
                print(f"OK prices from {hhmm(latest['server_time'])} (a newer run answered first)")
                return 0
        else:
            note = f"GitHub did not answer within {a.wait}s"
    else:
        # No push access (a scheduled read without a GitHub login): wait for the
        # workflow's own 5-minute run to publish prices that include the 15m
        # candle that just closed.
        need = t_req - t_req % (15 * 60 * 1000)
        deadline = time.time() + a.wait
        status, latest = read_data(a.repo)
        while (not latest or latest.get("server_time", 0) < need) and time.time() < deadline:
            time.sleep(10)
            status, latest = read_data(a.repo)
        if latest and latest.get("server_time", 0) >= need:
            save(a.out, latest)
            print(f"OK prices from {hhmm(latest['server_time'])} (scheduled copy; {note})")
            return 0

    if latest and latest.get("server_time"):
        age = (now_ms() - latest["server_time"]) // 1000
        if age <= a.max_age:
            save(a.out, latest)
            print(f"STALE using prices from {hhmm(latest['server_time'])} ({age // 60} min old): {note}")
            return 0
        print(f"FAIL newest prices are {age // 60} min old: {note}")
        return 2
    print(f"FAIL no prices on the data branch: {note}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
