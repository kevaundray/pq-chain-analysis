"""One pass over Xatu canonical_execution_contracts (all partitions, genesis..head).

Per partition writes data/contracts/<p>.parquet with the index columns for every created
contract. For partitions >= CODE_FROM (block 18,000,000, Aug 2023) it also keeps the runtime
code for the first row of each code_hash within the partition; older partitions are index-only
(bandwidth: code is ~45% of the table). Remote partitions are read with column projection, so
init_code is never downloaded. Partitions already fully downloaded under
data/xatu/canonical_execution_contracts are read locally.
"""

import os
import sys
from concurrent.futures import ThreadPoolExecutor

import duckdb

BASE = "https://data.ethpandaops.io/xatu/mainnet/databases/default/canonical_execution_contracts/1000"
LOCAL = "data/xatu/canonical_execution_contracts"
OUT = "data/contracts"
CODE_FROM = 18_000
os.makedirs(OUT, exist_ok=True)

QUERY = """
COPY (
  SELECT contract_address, block_number, transaction_hash, deployer, factory, code_hash, n_code_bytes,
         {code}
  FROM read_parquet('{src}')
) TO '{dst}' (FORMAT parquet)
"""
WITH_CODE = """CASE WHEN row_number() OVER (PARTITION BY code_hash ORDER BY block_number, create_index) = 1
              THEN code END AS code"""
NO_CODE = "NULL::BLOB AS code"

def run(p: int) -> str:
    dst = f"{OUT}/{p}.parquet"
    if os.path.exists(dst):
        return "skip"
    local = f"{LOCAL}/{p}000.parquet"
    src = local if os.path.exists(local) else f"{BASE}/{p}000.parquet"
    c = duckdb.connect()
    c.sql("LOAD httpfs; SET threads=2")
    for attempt in range(6):
        try:
            c.sql(QUERY.format(src=src, dst=dst + ".tmp", code=WITH_CODE if p >= CODE_FROM else NO_CODE))
            os.replace(dst + ".tmp", dst)
            return "ok"
        except duckdb.Error as e:
            msg = str(e)
            if "404" in msg:
                return "missing"
            if attempt == 5:
                return "error: " + msg[:200]
    return "error"


if __name__ == "__main__":
    start, end = int(sys.argv[1]), int(sys.argv[2])
    parts = list(range(end, start - 1, -1))
    stats = {}
    with ThreadPoolExecutor(int(sys.argv[3]) if len(sys.argv) > 3 else 16) as ex:
        for i, (p, r) in enumerate(zip(parts, ex.map(run, parts))):
            k = r.split(":")[0]
            stats[k] = stats.get(k, 0) + 1
            if k == "error":
                print(p, r, flush=True)
            if i % 500 == 0:
                print(i, stats, flush=True)
    print("final", stats)
