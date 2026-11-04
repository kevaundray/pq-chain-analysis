"""Aggregate the precompile-usage parquet corpus per caller.

Source: ~/work/xatu/precompile-usage (precompile-tracer, geth callTracer; `caller` is the
execution-context address, i.e. the proxy/storage owner under DELEGATECALL).
Window "y1" = blocks 22,100,000..24,699,999 (2025-03-22 .. 2026-03-18, last full year of data).
"""

import duckdb
import os

SRC = os.path.expanduser("~/work/xatu/precompile-usage/blocks_*.parquet")
OUT = "data/agg"
Y1_START, Y1_END = 22_100_000, 24_699_999
os.makedirs(OUT, exist_ok=True)

ACTIVATION = """
CASE
  WHEN precompile_name IN ('modexp','ecadd','ecmul','ecpairing') THEN 4370000
  WHEN precompile_name = 'blake2f' THEN 9069000
  WHEN precompile_name = 'pointEval' THEN 19426587
  WHEN precompile_name LIKE 'bls12%' THEN 22431084
  WHEN precompile_name = 'p256verify' THEN 23935694
  ELSE 0 END
"""

c = duckdb.connect()
c.sql("SET memory_limit='48GB'; SET temp_directory='data/tmp'; SET threads=24; SET preserve_insertion_order=false")

c.sql(f"""
CREATE VIEW calls AS
SELECT block_number, tx_hash, precompile_name, lower(caller) AS caller, precompile_gas_used, input
FROM read_parquet('{SRC}')
WHERE block_number >= {ACTIVATION}
""")

print("alltime per caller")
c.sql(f"""
COPY (
  SELECT precompile_name, caller, count(*) AS calls, min(block_number) AS first_block,
         max(block_number) AS last_block
  FROM calls GROUP BY ALL
) TO '{OUT}/alltime_caller.parquet' (FORMAT parquet)
""")

print("y1 tx-caller-precompile triples")
c.sql(f"""
COPY (
  SELECT tx_hash, any_value(block_number) AS block_number, caller, precompile_name,
         count(*) AS calls, sum(precompile_gas_used) AS gas
  FROM calls WHERE block_number BETWEEN {Y1_START} AND {Y1_END}
  GROUP BY tx_hash, caller, precompile_name
) TO '{OUT}/y1_tx_caller.parquet' (FORMAT parquet)
""")

print("y1 per caller")
c.sql(f"""
COPY (
  SELECT precompile_name, caller, sum(calls) AS calls, count(*) AS txs, sum(gas) AS gas,
         min(block_number) AS first_block, max(block_number) AS last_block
  FROM '{OUT}/y1_tx_caller.parquet' GROUP BY ALL
) TO '{OUT}/y1_caller.parquet' (FORMAT parquet)
""")

# modexp input layout: <len(B)><len(E)><len(M)> as 32-byte words, then B,E,M.
# Keep the modulus itself when <= 64 bytes (EC field / group orders), else its length + prefix.
print("modexp moduli (alltime, per caller)")
c.sql(f"""
COPY (
  WITH m AS (
    SELECT caller, block_number, substr(input, 3) AS h
    FROM calls WHERE precompile_name = 'modexp' AND length(input) >= 2 + 192
  ), l AS (
    SELECT caller, block_number, h,
           try_cast(('0x' || substr(h, 1 + 64 - 8, 8)) AS BIGINT) AS bl,
           try_cast(('0x' || substr(h, 65 + 64 - 8, 8)) AS BIGINT) AS el,
           try_cast(('0x' || substr(h, 129 + 64 - 8, 8)) AS BIGINT) AS ml
    FROM m
  )
  SELECT caller, ml AS mod_len, el AS exp_len,
         CASE WHEN ml <= 64 THEN substr(h, 193 + 2*(bl + el), 2*ml)
              ELSE substr(h, 193 + 2*(bl + el), 16) END AS modulus,
         CASE WHEN el <= 4 THEN substr(h, 193 + 2*bl, 2*el) ELSE 'len' || el::VARCHAR END AS exponent,
         count(*) AS calls,
         count(*) FILTER (WHERE block_number BETWEEN {Y1_START} AND {Y1_END}) AS calls_y1,
         min(block_number) AS first_block, max(block_number) AS last_block
  FROM l GROUP BY ALL
) TO '{OUT}/modexp_moduli.parquet' (FORMAT parquet)
""")

print("ecpairing sizes y1")
c.sql(f"""
COPY (
  SELECT caller, (length(input) - 2) / 384 AS pairs, count(*) AS calls
  FROM calls WHERE precompile_name = 'ecpairing' AND block_number BETWEEN {Y1_START} AND {Y1_END}
  GROUP BY ALL
) TO '{OUT}/ecpairing_sizes_y1.parquet' (FORMAT parquet)
""")
print("done")
