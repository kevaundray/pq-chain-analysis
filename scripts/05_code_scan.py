"""Chain-wide fingerprint scan over unique runtime codes of contracts created at block >= 18,000,000.

Inputs: data/contracts/*.parquet (from 02_contracts_pass.py; code stored as ASCII hex '0x...').
Outputs:
  data/contracts_index.parquet  - every created contract (all history): address, block, deployer, factory, code_hash
  data/code_scan.parquet         - per unique code_hash (>=18M) with any fingerprint hit: counts, lattice class
"""

import os
import sys
from concurrent.futures import ProcessPoolExecutor

import duckdb
import pandas as pd

sys.path.insert(0, "scripts")
import code_features as cf  # noqa: E402


def scan(batch):
    out = []
    for h, code_hex in batch:
        s = code_hex.decode() if isinstance(code_hex, (bytes, bytearray)) else code_hex
        code = bytes.fromhex(s[2:])
        fp = cf.fingerprints(code)
        if any(fp.values()):
            fp["code_hash"] = h
            fp["lattice"] = cf.classify_lattice(fp)
            fp["codesize"] = len(code)
            out.append(fp)
    return out


def main():
    c = duckdb.connect()
    c.sql("SET memory_limit='40GB'; SET temp_directory='data/tmp'")
    if not os.path.exists("data/contracts_index.parquet"):
        c.sql("""
        COPY (
          SELECT lower(decode(contract_address)) AS address, block_number, lower(decode(deployer)) AS deployer,
                 lower(decode(factory)) AS factory, lower(decode(code_hash)) AS code_hash, n_code_bytes
          FROM read_parquet('data/contracts/*.parquet')
        ) TO 'data/contracts_index.parquet' (FORMAT parquet)
        """)

    cur = c.execute("""
      SELECT lower(decode(code_hash)) AS h, any_value(code) AS code
      FROM read_parquet('data/contracts/*.parquet') WHERE code IS NOT NULL AND octet_length(code) > 2
      GROUP BY 1
    """)
    rows = []
    submitted = 0
    with ProcessPoolExecutor(24) as ex:
        inflight = []
        while True:
            chunk = cur.fetchmany(5000)
            if not chunk:
                break
            inflight.append(ex.submit(scan, chunk))
            submitted += len(chunk)
            if len(inflight) >= 48:
                rows.extend(inflight.pop(0).result())
        for f in inflight:
            rows.extend(f.result())
    print("unique codes scanned:", submitted, flush=True)

    df = pd.DataFrame(rows)
    counts = c.sql("""SELECT code_hash h, count(*) n, min(block_number) first_block
                      FROM 'data/contracts_index.parquet' GROUP BY 1""").df()
    df = df.merge(counts, left_on="code_hash", right_on="h", how="left").drop(columns="h")
    df.to_parquet("data/code_scan.parquet", index=False)
    print("hits", len(df))
    print(df[list(cf.FINGERPRINTS)].gt(0).sum())
    print(df[df.lattice.notna()][["code_hash", "lattice", "codesize", "n", "first_block"]])


if __name__ == "__main__":
    main()
