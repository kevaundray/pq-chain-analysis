"""Cached, rate-limited Blockscout (eth.blockscout.com) API v2 client.

fetch(addresses, kinds) stores JSON under data/blockscout/<kind>/<address>.json.
kinds: "address" (name, proxy, verification, ETH balance), "tokens" (first page of ERC-20
holdings, sorted by fiat value), "token" (token metadata incl. market cap; only for tokens),
"counters" (tx / transfer counters).
"""

import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import requests

BASE = "https://eth.blockscout.com/api/v2"
ROOT = "data/blockscout"
PATHS = {
    "address": "/addresses/{a}",
    "tokens": "/addresses/{a}/tokens?type=ERC-20",
    "token": "/tokens/{a}",
    "counters": "/addresses/{a}/counters",
}

session = requests.Session()


def _get(url: str):
    for attempt in range(8):
        try:
            r = session.get(url, timeout=60)
        except requests.RequestException:
            time.sleep(2 + attempt * 2)
            continue
        if r.status_code == 429 or r.status_code >= 500:
            time.sleep(2 + attempt * 3)
            continue
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()
    raise RuntimeError(f"giving up on {url}")


def get(kind: str, a: str):
    a = a.lower()
    path = os.path.join(ROOT, kind, a + ".json")
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    try:
        data = _get(BASE + PATHS[kind].format(a=a))
    except RuntimeError:
        return None
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f)
    return data


def fetch(addresses, kinds, workers: int = 3):
    jobs = [(k, a) for a in addresses for k in kinds]
    with ThreadPoolExecutor(workers) as ex:
        for i, _ in enumerate(ex.map(lambda j: get(*j), jobs)):
            if i % 200 == 0:
                print(f"blockscout {i}/{len(jobs)}", file=sys.stderr, flush=True)


def load_addresses():
    """DataFrame of all cached address records: address, name, proxy_type, impl, impl_name, verified, eth, creator."""
    import glob

    import pandas as pd

    rows = []
    for f in glob.glob(os.path.join(ROOT, "address", "*.json")):
        a = os.path.basename(f)[:-5]
        with open(f) as fh:
            d = json.load(fh)
        if not d:
            rows.append(dict(address=a))
            continue
        impl = d.get("implementations") or []
        rows.append(dict(
            address=a, name=d.get("name"), proxy_type=d.get("proxy_type"),
            impl=";".join((i.get("address_hash") or "").lower() for i in impl),
            impl_name=";".join(str(i.get("name")) for i in impl)[:80],
            verified=d.get("is_verified"), eth=int(d.get("coin_balance") or 0) / 1e18,
            creator=(d.get("creator_address_hash") or "").lower(),
        ))
    return pd.DataFrame(rows)



if __name__ == "__main__":
    kinds = sys.argv[1].split(",")
    addrs = [l.strip() for l in open(sys.argv[2]) if l.strip()]
    fetch(addrs, kinds)
