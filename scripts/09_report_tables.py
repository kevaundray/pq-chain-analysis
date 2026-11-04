"""Build all report tables -> data/report/*.csv (+ prints them).

Metric semantics (used consistently in every table):
  txs_y1        distinct transactions in the y1 window (blocks 22.1M-24.7M) in which at least one member
                contract invoked the crypto (exact, from the full precompile trace corpus)
  usd_tx_y1     USD size of those transactions = sum over distinct txs of the largest single ERC-20/ETH transfer in
                the tx, estimated from the 1-in-10 block sample and scaled by 10. Group values are computed over
                distinct txs, so a tx that touches several members is counted once per group (groups may overlap).
  usd_held_now  ERC-20 (first 50 tokens) + ETH currently held by member contracts that were in the holdings fetch list
Roles/mutability: rule-based per code family (07_classify.py), overridden by curated rows (data/curation).
"""

import glob
import json
import os

import duckdb
import pandas as pd

OUT = "data/report"
Y1 = "data/agg/y1_caller.parquet"
AT = "data/agg/alltime_caller.parquet"
TXC = "data/agg/y1_tx_caller.parquet"
M = "data/agg/modexp_moduli.parquet"

PRECOMPILE_CAT = """CASE WHEN precompile_name='ecrecover' THEN 'ecrecover'
 WHEN precompile_name IN ('ecadd','ecmul','ecpairing') THEN 'bn254'
 WHEN precompile_name='pointEval' THEN 'kzg'
 WHEN precompile_name LIKE 'bls12%' THEN 'bls12381'
 WHEN precompile_name='p256verify' THEN 'p256' END"""
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
GROUP = {"ecrecover": "1. ecrecover", **{k: "2. EC precompile" for k in ("bn254", "bls12381", "kzg", "p256")},
         **{k: "3. EC in software" for k in ("sw_p256", "sw_secp256k1", "sw_bn254", "sw_ed25519", "sw_bls12381")},
         "rsa": "4. RSA"}
CURATED_MUT = {"immutable": "immutable", "immutable_logic_configurable_params": "immutable",
               "upgradeable_proxy_admin": "upgradeable", "owner_controlled_account_upgrade": "owner_controlled"}


def save(df, name):
    df.to_csv(f"{OUT}/{name}.csv", index=False)
    print(f"\n## {name}\n" + df.to_string(index=False))


def order_cats(df):
    return df.set_index("cat").loc[[k for k in CAT_ORDER if k in set(df.cat)]].reset_index()


def main():
    os.makedirs(OUT, exist_ok=True)
    c = duckdb.connect()
    c.sql("SET memory_limit='30GB'; SET threads=16; SET temp_directory='data/tmp'")
    meta = json.load(open("data/flows_meta.json"))
    fr = meta["fraction"]
    plist = ",".join(map(str, meta["partitions"]))

    def scalar(q):
        return c.execute(q).fetchall()[0][0]

    # ---------- base tables ----------
    c.sql(f"""CREATE TABLE modcls AS SELECT caller, {MOD_CLASS} cls, sum(calls) calls, sum(calls_y1) calls_y1
              FROM '{M}' GROUP BY ALL HAVING cls IS NOT NULL""")
    c.sql("CREATE TABLE mdom AS SELECT caller, arg_max(cls, calls_y1) cls FROM modcls WHERE calls_y1 > 0 GROUP BY 1")
    c.sql(f"""CREATE TABLE cat_all AS
      SELECT DISTINCT caller, {PRECOMPILE_CAT} cat FROM '{AT}' WHERE {PRECOMPILE_CAT} IS NOT NULL
      UNION SELECT DISTINCT caller, cls FROM modcls""")
    c.sql(f"""CREATE TABLE txcat AS
      SELECT DISTINCT t.tx_hash, t.block_number, t.caller, coalesce({PRECOMPILE_CAT}, m.cls) cat
      FROM '{TXC}' t LEFT JOIN mdom m ON t.precompile_name = 'modexp' AND m.caller = t.caller
      WHERE {PRECOMPILE_CAT} IS NOT NULL OR (t.precompile_name = 'modexp' AND m.cls IS NOT NULL)""")
    c.sql("CREATE TABLE ycat AS SELECT caller, cat, count(DISTINCT tx_hash) txs FROM txcat GROUP BY ALL")
    c.sql(f"""CREATE TABLE ft AS SELECT tx_hash::VARCHAR tx_hash, tx_max_usd FROM 'data/flows_tx.parquet'""")
    c.sql(f"""CREATE TABLE stx AS SELECT DISTINCT t.tx_hash, t.caller, t.cat, ft.tx_max_usd
              FROM txcat t JOIN ft USING (tx_hash) WHERE t.block_number // 1000 IN ({plist})""")
    c.sql("CREATE TABLE H AS SELECT * FROM 'data/holdings.parquet'")

    rows = []
    for f in sorted(glob.glob("data/curation/out_*.jsonl")):
        rows += [json.loads(line) for line in open(f) if line.strip()]
    cur = pd.DataFrame(rows).drop_duplicates("address")
    cur["address"] = cur.address.str.lower()
    cur["cur_mut"] = cur.upgradeability.map(CURATED_MUT)
    c.register("cur", cur)
    c.sql("""CREATE TABLE cls AS
      SELECT cf.address caller, cf.family,
        CASE WHEN cur.address IS NOT NULL THEN
               CASE WHEN cur.is_account THEN coalesce(nullif(fc.role, 'application'), 'account_contract') ELSE 'application' END
             ELSE coalesce(fc.role, CASE WHEN cf.family = 'nocode' THEN 'no_code_now' ELSE 'unclassified' END) END role,
        coalesce(cur.cur_mut, fc.mutability, 'unclassified') mutability,
        cur.address IS NOT NULL curated
      FROM 'data/caller_family.parquet' cf
      LEFT JOIN 'data/families_classified.parquet' fc USING (family)
      LEFT JOIN cur ON cur.address = cf.address""")

    def group_metrics(member_sql: str, keys: list[str], match_cat: bool = False) -> pd.DataFrame:
        """member_sql yields (caller, <keys...>[, cat]); returns contracts, txs_y1, usd_tx_y1, usd_held_now per key.

        match_cat=True: member_sql also yields `cat` and only the member's txs in that category count.
        """
        k = ", ".join(keys)
        on = "caller, cat" if match_cat else "caller"
        return c.sql(f"""
          WITH g AS ({member_sql}),
               n AS (SELECT {k}, count(DISTINCT caller) contracts FROM g GROUP BY ALL),
               t AS (SELECT {k}, count(DISTINCT x.tx_hash) txs_y1 FROM g
                       JOIN (SELECT {on}, tx_hash FROM txcat) x USING ({on}) GROUP BY ALL),
               v AS (SELECT {k}, sum(tx_max_usd) / {fr} usd_tx_y1 FROM
                       (SELECT DISTINCT {k}, s.tx_hash, s.tx_max_usd FROM g
                        JOIN (SELECT {on}, tx_hash, tx_max_usd FROM stx) s USING ({on})) GROUP BY ALL),
               h AS (SELECT {k}, sum(H.usd) usd_held_now FROM (SELECT DISTINCT caller, {k} FROM g) gg
                       JOIN H ON H.address = gg.caller GROUP BY ALL)
          SELECT * FROM n LEFT JOIN t USING ({k}) LEFT JOIN v USING ({k}) LEFT JOIN h USING ({k})
          ORDER BY txs_y1 DESC NULLS LAST""").df()

    # ---------- table 1: per category ----------
    t1 = group_metrics("SELECT DISTINCT caller, cat FROM ycat", ["cat"], match_cat=True)
    alltime = c.sql("SELECT cat, count(DISTINCT caller) callers_alltime FROM cat_all GROUP BY 1").df()
    t1 = order_cats(alltime.merge(t1, on="cat", how="left").rename(columns={"contracts": "callers_y1"}))
    t1.insert(1, "group", t1.cat.map(GROUP))
    anyrow = group_metrics("SELECT DISTINCT caller, 'ANY pre-quantum' AS grp FROM ycat", ["grp"]).rename(columns={"grp": "cat"})
    anyrow = anyrow.rename(columns={"contracts": "callers_y1"})
    anyrow["callers_alltime"] = scalar("SELECT count(DISTINCT caller) FROM cat_all")
    t1 = pd.concat([t1, anyrow], ignore_index=True)
    save(t1, "t1_categories")
    save(pd.DataFrame([{"total_txs_y1_any": scalar("SELECT count(DISTINCT tx_hash) FROM txcat"),
                        "sample_fraction": fr, "transfers_in_sample": meta["transfers"],
                        "priced_share": meta["priced_share"]}]), "t1_meta")

    # ---------- table 2: role / mutability per category (y1-active callers) ----------
    t2 = c.sql("""
      SELECT y.cat, count(*) callers_y1,
        count(*) FILTER (WHERE role = 'account_7702_eoa') acct_7702_eoa,
        count(*) FILTER (WHERE role = 'account_contract') acct_contract,
        count(*) FILTER (WHERE role = 'application') applications,
        count(*) FILTER (WHERE role = 'application' AND mutability = 'immutable') app_immutable,
        count(*) FILTER (WHERE role = 'application' AND mutability = 'upgradeable') app_upgradeable,
        count(*) FILTER (WHERE role = 'application' AND mutability = 'proxy_unresolved') app_proxy_unresolved,
        count(*) FILTER (WHERE role IN ('no_code_now', 'unclassified')) other
      FROM (SELECT DISTINCT caller, cat FROM ycat) y JOIN cls USING (caller) GROUP BY 1""").df()
    save(order_cats(t2), "t2_roles_mutability")

    t3 = group_metrics("""SELECT DISTINCT y.caller, y.cat,
            CASE WHEN y.cat = 'ecrecover' THEN 'ecrecover' ELSE 'other EC / RSA' END catgroup, role, mutability
          FROM ycat y JOIN cls USING (caller)""", ["catgroup", "role", "mutability"], match_cat=True)
    save(t3.sort_values(["catgroup", "usd_tx_y1"], ascending=[True, False]), "t3_value_by_role")

    # ---------- curated contracts ----------
    c.sql("""CREATE TABLE curapps AS SELECT cur.* FROM cur JOIN cls ON cls.caller = cur.address
             WHERE cls.role = 'application'""")
    per = group_metrics("SELECT address caller, address addr FROM curapps", ["addr"])
    curm = cur.merge(per.drop(columns="contracts").rename(columns={"addr": "address"}), on="address", how="left")
    curm = curm.merge(c.sql("SELECT caller address, string_agg(cat || ':' || txs, ' ' ORDER BY txs DESC) cats FROM ycat GROUP BY 1").df(),
                      on="address", how="left")
    curm.to_csv(f"{OUT}/curated_contracts.csv", index=False)

    cov = group_metrics("SELECT caller, curated::VARCHAR curated FROM cls WHERE role = 'application' AND caller IN (SELECT caller FROM ycat)",
                        ["curated"])
    save(cov, "curated_coverage")

    for key in ["function", "reliance", "upgradeability", "ecdsa_order", "signer", "crypto_role"]:
        save(group_metrics(f"SELECT address caller, {key} FROM curapps", [key]), f"curated_by_{key}")
    save(group_metrics("SELECT address caller, reliance, upgradeability FROM curapps", ["reliance", "upgradeability"]),
         "curated_reliance_x_upgradeability")
    save(group_metrics("SELECT address caller, function, reliance FROM curapps", ["function", "reliance"]),
         "curated_function_x_reliance")
    cols = ["address", "protocol", "function", "signer", "reliance", "ecdsa_order", "upgradeability", "crypto_role",
            "txs_y1", "usd_tx_y1", "usd_held_now"]
    apps = curm[curm.address.isin(set(c.sql("SELECT address FROM curapps").df().address))]
    save(apps.sort_values("usd_tx_y1", ascending=False).head(40)[cols], "curated_top40_by_value")
    save(apps.sort_values("usd_held_now", ascending=False).head(25)[cols], "curated_top25_by_held")
    save(apps.sort_values("txs_y1", ascending=False).head(40)[cols], "curated_top40_by_txs")

    # ---------- permit tokens: market cap whose permit path is ECDSA ----------
    mc = []
    for a in apps[apps.function == "user_auth_permit"].address:
        p = f"data/blockscout/address/{a}.json"
        d = json.load(open(p)) if os.path.exists(p) else None
        t = (d or {}).get("token") or {}
        mc.append((a, t.get("symbol"), float(t.get("circulating_market_cap") or 0)))
    mc = pd.DataFrame(mc, columns=["address", "symbol", "market_cap_usd"]).merge(
        apps[["address", "protocol", "reliance", "ecdsa_order", "upgradeability"]], on="address")
    save(mc.sort_values("market_cap_usd", ascending=False), "permit_tokens_market_cap")

    # ---------- lattice (strong bytecode fingerprints; verified by hand) ----------
    scan = pd.read_parquet("data/code_scan.parquet")
    strong = scan[(scan.falcon_psi_rev > 0) | (scan.falcon_psi_inv_rev > 0) | (scan.mldsa_zetas > 0)]
    c.register("strong", strong)
    save(c.sql("""SELECT i.address, i.block_number, i.deployer,
                     CASE WHEN s.mldsa_zetas > 0 THEN 'ML-DSA' ELSE 'Falcon' END scheme, s.codesize
                   FROM 'data/contracts_index.parquet' i JOIN strong s USING (code_hash) ORDER BY block_number""").df(),
         "lattice_contracts")

    # ---------- rollups by proof system (L2BEAT) ----------
    T = pd.read_parquet("data/l2beat_tvs.parquet")
    g = T.groupby("sv", dropna=False)[["total", "canonical"]].sum().div(1e9).round(2)
    save(g.sort_values("total", ascending=False).reset_index(), "l2_tvs_by_state_validation")


if __name__ == "__main__":
    main()
