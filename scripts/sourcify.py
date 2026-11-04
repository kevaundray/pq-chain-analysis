"""Cached Sourcify v2 client: verified sources, compilation target, proxy resolution, deployment.

get(a) stores data/sourcify/<address>.json (null when not verified on Sourcify).
CLI: python scripts/sourcify.py <address-file>  (also fetches resolved proxy implementations).
"""

import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import requests

BASE = "https://sourcify.dev/server/v2/contract/1/{a}?fields=sources,compilation,proxyResolution,deployment,abi"
ROOT = "data/sourcify"
session = requests.Session()


def get(a: str):
    a = a.lower()
    path = os.path.join(ROOT, a + ".json")
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    data = None
    for attempt in range(8):
        try:
            r = session.get(BASE.format(a=a), timeout=120)
        except requests.RequestException:
            time.sleep(2 + 2 * attempt)
            continue
        if r.status_code == 404:
            break
        if r.status_code == 429 or r.status_code >= 500:
            time.sleep(2 + 3 * attempt)
            continue
        if r.ok:
            data = r.json()
        break
    else:
        return None
    os.makedirs(ROOT, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f)
    return data


def implementations(d) -> list[str]:
    if not d:
        return []
    pr = d.get("proxyResolution") or {}
    return [i["address"].lower() for i in pr.get("implementations") or [] if i.get("address")]


def fetch(addresses, workers: int = 4):
    addrs = sorted({a.lower() for a in addresses})
    with ThreadPoolExecutor(workers) as ex:
        docs = list(ex.map(get, addrs))
    impls = sorted({i for d in docs for i in implementations(d)} - set(addrs))
    with ThreadPoolExecutor(workers) as ex:
        list(ex.map(get, impls))
    print(f"sourcify: {sum(d is not None for d in docs)}/{len(addrs)} verified, {len(impls)} impls", file=sys.stderr)


if __name__ == "__main__":
    fetch([l.strip() for l in open(sys.argv[1]) if l.strip()])
