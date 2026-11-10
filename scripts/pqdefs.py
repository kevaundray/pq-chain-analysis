"""Shared definitions: input paths and how precompile calls map to pre-quantum categories."""

Y1 = "data/agg/y1_caller.parquet"
AT = "data/agg/alltime_caller.parquet"
TXC = "data/agg/y1_tx_caller.parquet"
M = "data/agg/modexp_moduli.parquet"

# precompile_name -> category (NULL for non-pre-quantum precompiles such as sha256/identity/modexp)
PRECOMPILE_CAT = """CASE WHEN precompile_name='ecrecover' THEN 'ecrecover'
 WHEN precompile_name IN ('ecadd','ecmul','ecpairing') THEN 'bn254'
 WHEN precompile_name='pointEval' THEN 'kzg'
 WHEN precompile_name LIKE 'bls12%' THEN 'bls12381'
 WHEN precompile_name='p256verify' THEN 'p256' END"""

# modexp modulus -> category (elliptic-curve maths in software, or RSA); NULL otherwise
MOD_CLASS = """CASE
 WHEN mod_len >= 128 THEN 'rsa'
 WHEN modulus IN ('ffffffff00000001000000000000000000000000ffffffffffffffffffffffff',
                  'ffffffff00000000ffffffffffffffffbce6faada7179e84f3b9cac2fc632551') THEN 'sw_p256'
 WHEN modulus IN ('fffffffffffffffffffffffffffffffffffffffffffffffffffffffefffffc2f',
                  'fffffffffffffffffffffffffffffffebaaedce6af48a03bbfd25e8cd0364141') THEN 'sw_secp256k1'
 WHEN modulus IN ('30644e72e131a029b85045b68181585d97816a916871ca8d3c208c16d87cfd47',
                  '30644e72e131a029b85045b68181585d2833e84879b9709143e1f593f0000001') THEN 'sw_bn254'
 WHEN modulus IN ('7fffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffed',
                  '1000000000000000000000000000000014def9dea2f79cd65812631a5cf5d3ed') THEN 'sw_ed25519'
 WHEN modulus LIKE '%1a0111ea397fe69a4b1ba7b6434bacd7%'
   OR modulus = '73eda753299d7d483339d80809a1d80553bda402fffe5bfeffffffff00000001' THEN 'sw_bls12381'
 ELSE NULL END"""

CAT_ORDER = ["ecrecover", "bn254", "bls12381", "kzg", "p256", "sw_p256", "sw_secp256k1", "sw_bn254", "sw_ed25519",
             "sw_bls12381", "rsa"]


def base_tables(c):
    """Create modcls, mdom, cat_all, txcat, ycat in DuckDB connection `c`.

    modcls  (caller, cls, calls, calls_y1, first_block, last_block)  modexp usage by curve/RSA class
    mdom    (caller, cls)          a caller's dominant modexp class in the year (attributes its modexp txs)
    cat_all (caller, cat)          every caller ever seen using a category
    txcat   (tx_hash, block_number, caller, cat)  distinct y1 transactions per caller and category
    ycat    (caller, cat, txs)     distinct y1 transactions per caller and category
    """
    c.sql(f"""CREATE TABLE modcls AS SELECT caller, {MOD_CLASS} cls, sum(calls) calls, sum(calls_y1) calls_y1,
              min(first_block) first_block, max(last_block) last_block
              FROM '{M}' GROUP BY caller, cls HAVING cls IS NOT NULL""")
    c.sql("CREATE TABLE mdom AS SELECT caller, arg_max(cls, calls_y1) cls FROM modcls WHERE calls_y1 > 0 GROUP BY 1")
    c.sql(f"""CREATE TABLE cat_all AS
      SELECT DISTINCT caller, {PRECOMPILE_CAT} cat FROM '{AT}' WHERE {PRECOMPILE_CAT} IS NOT NULL
      UNION SELECT DISTINCT caller, cls FROM modcls""")
    c.sql(f"""CREATE TABLE txcat AS
      SELECT DISTINCT t.tx_hash, t.block_number, t.caller, coalesce({PRECOMPILE_CAT}, m.cls) cat
      FROM '{TXC}' t LEFT JOIN mdom m ON t.precompile_name = 'modexp' AND m.caller = t.caller
      WHERE {PRECOMPILE_CAT} IS NOT NULL OR (t.precompile_name = 'modexp' AND m.cls IS NOT NULL)""")
    c.sql("CREATE TABLE ycat AS SELECT caller, cat, count(DISTINCT tx_hash) txs FROM txcat GROUP BY ALL")
