"""Probe current (head) code hash / size / code head / ETH balance of every precompile caller."""

import sys

import duckdb
import pandas as pd

sys.path.insert(0, "scripts")
import rpc  # noqa: E402

c = duckdb.connect()
addrs = [r[0] for r in c.sql("SELECT DISTINCT caller FROM 'data/agg/alltime_caller.parquet'").fetchall()]
head = rpc.block_number()
print("callers", len(addrs), "block", head, flush=True)
res = rpc.probe(addrs, block=hex(head), workers=6)
df = pd.DataFrame(
    [(a, h, s, ch, str(b)) for a, (h, s, ch, b) in res.items()],
    columns=["address", "codehash", "codesize", "code_head", "balance_wei"],
)
df["probe_block"] = head
df.to_parquet("data/probe_latest.parquet", index=False)
print("done", len(df))
