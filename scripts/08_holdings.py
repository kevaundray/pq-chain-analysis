"""Current USD holdings of key precompile callers -> data/holdings.parquet.

ERC-20: first page (up to 50 tokens) of Blockscout /addresses/<a>/tokens for addresses in
data/holdings_list.txt, priced at Blockscout exchange_rate. Dropped: tokens with non-"ok" reputation,
holdings above the token's circulating market cap, and any single holding above $30B (mispriced).
ETH: balance at the probe block (data/probe_latest.parquet) at the Blockscout ETH price.
"""

import glob
import json
import os

import pandas as pd

MAX_SINGLE = 3e10


def eth_price() -> float:
    """Blockscout exposes the native-coin USD rate on every address record."""
    for f in glob.glob("data/blockscout/address/*.json"):
        d = json.load(open(f))
        if d and d.get("exchange_rate"):
            return float(d["exchange_rate"])
    raise RuntimeError("no cached Blockscout address record with exchange_rate")


def main():
    price = eth_price()
    rows = []
    for f in glob.glob("data/blockscout/tokens/*.json"):
        a = os.path.basename(f)[:-5]
        d = json.load(open(f)) or {}
        total, n = 0.0, 0
        for it in d.get("items", []):
            t = it.get("token") or {}
            if t.get("reputation") not in (None, "ok"):
                continue
            rate, dec = t.get("exchange_rate"), t.get("decimals")
            if not rate or dec is None:
                continue
            v = int(it["value"]) / 10 ** int(dec) * float(rate)
            mcap = float(t.get("circulating_market_cap") or 0)
            if (mcap and v > mcap * 1.05) or v > MAX_SINGLE:
                continue
            total += v
            n += 1
        rows.append((a, total, n, bool(d.get("next_page_params"))))
    H = pd.DataFrame(rows, columns=["address", "erc20_usd", "n_tokens", "more_pages"])
    pr = pd.read_parquet("data/probe_latest.parquet", columns=["address", "balance_wei"])
    H = H.merge(pr, on="address", how="left")
    H["eth_usd"] = H.balance_wei.astype(float).fillna(0) / 1e18 * price
    H["usd"] = H.erc20_usd + H.eth_usd
    H["eth_price"] = price
    H.drop(columns="balance_wei").to_parquet("data/holdings.parquet", index=False)
    print(len(H), "addresses; total $%.1fB; eth price %.2f" % (H.usd.sum() / 1e9, price))


if __name__ == "__main__":
    main()
