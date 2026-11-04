"""USD value moved in transactions that invoked pre-quantum crypto (1-in-10 systematic sample of y1).

Sample: 1000-block partitions p with (p - 22100) % 10 == 0 over blocks 22,100,000..24,699,999 where both
Xatu erc20_transfers and native_transfers partitions are present. Scale totals by 1 / sampling_fraction.
Prices: DefiLlama historical prices at 30-day bins (token decimals from the same response).
Transfers above $5B are dropped as mispriced/spam.

Outputs:
  data/flows_tx.parquet       tx_hash, block_number, tx_max_usd, tx_sum_usd
  data/flows_touch.parquet    tx_hash, caller, touch_usd (transfers where caller is from/to/token)
  data/flows_meta.json        sampled partitions, fraction, token coverage
"""

import glob
import json
import os
import time

import duckdb
import numpy as np
import pandas as pd
import requests

Y1_START, Y1_END = 22_100, 24_699
T0_BLOCK, T0_TS = 22_100_000, 1_742_617_295  # 2025-03-22 04:21:35 UTC
BIN = 30 * 86400
MAX_USD = 5e9
E = "data/xatu/canonical_execution_erc20_transfers/{p}000.parquet"
N = "data/xatu/canonical_execution_native_transfers/{p}000.parquet"


def present(path):
    return os.path.exists(path) and os.path.getsize(path) > 0


def le_to_float(blobs: pd.Series) -> np.ndarray:
    arr = np.frombuffer(b"".join(b.ljust(32, b"\0")[:32] for b in blobs), dtype="<u8").reshape(-1, 4)
    return arr[:, 0].astype(np.float64) + arr[:, 1].astype(np.float64) * 2.0**64 + arr[:, 2].astype(np.float64) * 2.0**128


def llama(ts: int, coins: list[str]) -> dict:
    out = {}
    for i in range(0, len(coins), 80):
        url = f"https://coins.llama.fi/prices/historical/{ts}/" + ",".join(coins[i:i + 80]) + "?searchWidth=12h"
        for attempt in range(6):
            try:
                r = requests.get(url, timeout=60)
                if r.ok:
                    out.update(r.json().get("coins", {}))
                    break
            except requests.RequestException:
                pass
            time.sleep(2 + 2 * attempt)
    return out


def main():
    parts = [p for p in range(Y1_START, Y1_END + 1, 10) if present(E.format(p=p)) and present(N.format(p=p))]
    frac = len(parts) / (Y1_END - Y1_START + 1)
    print("sampled partitions", len(parts), "fraction", frac, flush=True)
    c = duckdb.connect()
    c.sql("SET memory_limit='40GB'; SET temp_directory='data/tmp'")
    plist = ",".join(str(p) for p in parts)
    c.sql(f"""CREATE TABLE txs AS SELECT DISTINCT tx_hash, block_number FROM 'data/agg/y1_tx_caller.parquet'
              WHERE block_number // 1000 IN ({plist})""")
    efiles = [E.format(p=p) for p in parts]
    nfiles = [N.format(p=p) for p in parts]
    c.sql(f"""CREATE TABLE et AS
      SELECT decode(e.transaction_hash) tx_hash, lower(decode(erc20)) token, lower(decode(from_address)) f,
             lower(decode(to_address)) t, value v, e.block_number
      FROM read_parquet({efiles}) e SEMI JOIN txs ON txs.tx_hash = decode(e.transaction_hash)""")
    c.sql(f"""CREATE TABLE nt AS
      SELECT decode(n.transaction_hash) tx_hash, 'eth' token, lower(decode(from_address)) f,
             lower(decode(to_address)) t, value v, n.block_number
      FROM read_parquet({nfiles}) n SEMI JOIN txs ON txs.tx_hash = decode(n.transaction_hash)""")
    print(c.sql("SELECT (SELECT count(*) FROM txs), (SELECT count(*) FROM et), (SELECT count(*) FROM nt)").fetchall(), flush=True)

    tr = c.sql("SELECT * FROM et UNION ALL SELECT * FROM nt").df()
    tr["amount"] = le_to_float(tr.v)
    tr["bin"] = ((T0_TS + (tr.block_number - T0_BLOCK) * 12) // BIN) * BIN
    tok_counts = tr[tr.token != "eth"].token.value_counts()
    tokens = list(tok_counts.index[:1500])
    prices = {}
    for b in sorted(tr.bin.unique()):
        coins = ["coingecko:ethereum"] + [f"ethereum:{t}" for t in tokens]
        res = llama(int(b) + BIN // 2, coins)
        for k, v in res.items():
            if v.get("confidence", 1) < 0.8:
                continue
            t = "eth" if k == "coingecko:ethereum" else k.split(":", 1)[1].lower()
            dec = 18 if t == "eth" else v.get("decimals")
            if dec is None:
                continue
            prices[(int(b), t)] = (v["price"], int(dec))
        print("priced bin", b, len(res), flush=True)
    pr = pd.DataFrame([(b, t, p, d) for (b, t), (p, d) in prices.items()], columns=["bin", "token", "price", "decimals"])
    tr = tr.merge(pr, on=["bin", "token"], how="left")
    tr["usd"] = tr.amount / 10.0 ** tr.decimals.fillna(0) * tr.price
    tr.loc[tr.price.isna() | (tr.usd > MAX_USD), "usd"] = 0.0
    tr = tr.drop(columns=["v"])
    c.register("tr", tr)
    c.sql("""COPY (SELECT tx_hash, any_value(block_number) block_number, max(usd) tx_max_usd, sum(usd) tx_sum_usd
              FROM tr GROUP BY 1) TO 'data/flows_tx.parquet' (FORMAT parquet)""")
    c.sql(f"""COPY (
      SELECT y.tx_hash, y.caller, sum(tr.usd) touch_usd
      FROM (SELECT DISTINCT tx_hash, caller FROM 'data/agg/y1_tx_caller.parquet' WHERE block_number // 1000 IN ({plist})) y
      JOIN tr ON tr.tx_hash = y.tx_hash AND (tr.f = y.caller OR tr.t = y.caller OR tr.token = y.caller)
      GROUP BY 1, 2) TO 'data/flows_touch.parquet' (FORMAT parquet)""")
    priced_share = float((tr.price.notna()).mean())
    json.dump({"partitions": parts, "fraction": frac, "transfers": len(tr), "priced_share": priced_share,
               "tokens_priced": int(pr.token.nunique())}, open("data/flows_meta.json", "w"))
    print("done", priced_share)


if __name__ == "__main__":
    main()
