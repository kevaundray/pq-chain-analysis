"""Per-address lookup index for the site -> docs/lookup/<shard>.json.gz (1024 shards), families.json, meta.json.

One record per address that ever made a pre-quantum precompile call (cat_all), plus records for the implementation
contracts behind proxy / clone / 7702 families.
Shard = (first 3 hex chars after 0x) >> 2, as 3-digit hex. Key = first 16 hex chars after 0x (64 bits; a random
address falsely matching a record in its shard has probability ~1e-13; collisions inside the data are checked).
Shards are gzip files (GitHub Pages deploys time out on the uncompressed index); the page decompresses them with
DecompressionStream.

Record (keys omitted when empty):
  u   {cat: [txs_y1, calls_alltime, first_block, last_block]}   usage per category (codes in meta.cats)
  t   distinct y1 transactions using any category (percentile via meta.t_quantiles)
  f   index into families.json (rule-based classification of the address's code family)
  x   1 if the address has no code at the probe block (destroyed contract or EOA caller)
  n   name (curated protocol, else Blockscout name)
  v   [usd_tx_y1, sampled_txs]   value estimate from the 1-in-10 sample (sum of largest transfer per tx, x10)
  h   usd held now (only for addresses in the holdings fetch)
  c   1 if hand-classified (details live in docs/data.json)
  im  [n_families, members, txs_y1, roles]   when the address is the implementation behind proxy/clone/7702 families

families.json: [[role, mutability, proxy_kind, logic, members, label], ...]
"""

import glob
import gzip
import json
import os
import shutil
import sys
from collections import defaultdict

import duckdb
import pandas as pd

sys.path.insert(0, "scripts")
import blockscout  # noqa: E402
from pqdefs import AT, PRECOMPILE_CAT, base_tables  # noqa: E402

OUT = "docs/lookup"
CAT_CODE = {"ecrecover": "e", "bn254": "b", "kzg": "k", "bls12381": "l", "p256": "p", "sw_p256": "sp",
            "sw_secp256k1": "sk", "sw_bn254": "sb", "sw_ed25519": "se", "sw_bls12381": "sl", "rsa": "r"}
ROLE_CODE = {"application": "a", "account_contract": "w", "account_7702_eoa": "d", "no_code_now": "n"}
MUT_CODE = {"immutable": "i", "upgradeable": "u", "owner_controlled": "o", "proxy_unresolved": "x"}
KEY_HEX = 16


def shard_of(addr: str) -> str:
    return f"{int(addr[2:5], 16) >> 2:03x}"


def main():
    c = duckdb.connect()
    c.sql("SET memory_limit='30GB'; SET threads=16; SET temp_directory='data/tmp'")
    base_tables(c)
    meta = json.load(open("data/flows_meta.json"))
    fr, plist = meta["fraction"], ",".join(map(str, meta["partitions"]))

    print("usage", flush=True)
    usage = c.sql(f"""
      WITH pre AS (SELECT caller, {PRECOMPILE_CAT} cat, sum(calls) calls, min(first_block) fb, max(last_block) lb
                   FROM '{AT}' WHERE {PRECOMPILE_CAT} IS NOT NULL GROUP BY ALL),
           mx AS (SELECT caller, cls cat, calls, first_block fb, last_block lb FROM modcls),
           u AS (SELECT * FROM pre UNION ALL SELECT * FROM mx)
      SELECT u.caller, u.cat, coalesce(y.txs, 0) txs, u.calls, u.fb, u.lb
      FROM u LEFT JOIN ycat y USING (caller, cat)""").df()
    tot = c.sql("SELECT caller, count(DISTINCT tx_hash) t FROM txcat GROUP BY 1").df()
    t_quantiles = [int(x) for x in tot.t.quantile([i / 1000 for i in range(1001)], interpolation="lower")]

    print("value", flush=True)
    val = c.sql(f"""
      SELECT s.caller, sum(f.tx_max_usd) / {fr} usd, count(*) n
      FROM (SELECT DISTINCT caller, tx_hash FROM txcat WHERE block_number // 1000 IN ({plist})) s
      JOIN (SELECT tx_hash::VARCHAR tx_hash, tx_max_usd FROM 'data/flows_tx.parquet') f USING (tx_hash)
      GROUP BY 1""").df()

    print("families", flush=True)
    fc = pd.read_parquet("data/families_classified.parquet")
    fc["impl"] = fc.logic2.where(fc.logic2.notna(), fc.logic) if "logic2" in fc else fc.logic

    def clean_label(s):
        """Blockscout labels join rep/logic names; drop 'None' placeholders and repeats."""
        if not isinstance(s, str):
            return None
        words = [w for w in s.replace(";", " ").split() if w != "None"]
        out = [w for i, w in enumerate(words) if w not in words[:i]]
        return " ".join(out) or None

    # members / txs recomputed over pre-quantum callers and distinct transactions (families.parquet counts
    # include modexp-only callers and sum per-precompile tx counts)
    fam = c.sql("""SELECT cf.address caller, cf.family FROM 'data/caller_family.parquet' cf
                   SEMI JOIN cat_all ca ON ca.caller = cf.address""").df()
    c.register("fam", fam)
    c.register("fcimpl", fc[["family", "impl"]])
    fam_members = dict(c.sql("SELECT family, count(*) FROM fam GROUP BY 1").fetchall())
    impl_stats = c.sql("""
      SELECT fi.impl, count(DISTINCT f.family) n, count(DISTINCT f.caller) members, count(DISTINCT t.tx_hash) txs
      FROM fcimpl fi JOIN fam f USING (family) LEFT JOIN txcat t ON t.caller = f.caller
      WHERE fi.impl IS NOT NULL GROUP BY 1""").df().set_index("impl")

    fam_rows, fam_idx = [], {}
    for r in fc.itertuples(index=False):
        fam_idx[r.family] = len(fam_rows)
        fam_rows.append([ROLE_CODE.get(r.role, "?"), MUT_CODE.get(r.mutability, "?"), r.proxy_kind,
                         r.impl if isinstance(r.impl, str) else None, int(fam_members.get(r.family, 0)),
                         clean_label(r.label)])

    bs = blockscout.load_addresses()
    bs_name = {r.address: (r.name or "") for r in bs.itertuples() if isinstance(r.name, str) and r.name}
    hold = pd.read_parquet("data/holdings.parquet")
    cur = {}
    for f in glob.glob("data/curation/out_*.jsonl"):
        for line in open(f):
            if line.strip():
                d = json.loads(line)
                cur[d["address"].lower()] = d["protocol"]

    rec = defaultdict(dict)
    for r in usage.itertuples(index=False):
        rec[r.caller].setdefault("u", {})[CAT_CODE[r.cat]] = [int(r.txs), int(r.calls), int(r.fb), int(r.lb)]
    for r in tot.itertuples(index=False):
        rec[r.caller]["t"] = int(r.t)
    for r in val.itertuples(index=False):
        if r.usd > 0:
            rec[r.caller]["v"] = [round(float(r.usd)), int(r.n)]
    for r in fam.itertuples(index=False):
        if r.family in fam_idx:
            rec[r.caller]["f"] = fam_idx[r.family]
        elif r.family == "nocode":
            rec[r.caller]["x"] = 1
    for a, name in bs_name.items():
        if a in rec:
            rec[a]["n"] = name
    for a, name in cur.items():
        if a in rec:
            rec[a]["n"] = name
            rec[a]["c"] = 1
    for r in hold.itertuples(index=False):
        if r.address in rec and r.usd > 0:
            rec[r.address]["h"] = round(float(r.usd))

    # implementation contracts behind proxy / clone / 7702 families
    impl_roles = fc[fc.impl.notna()].groupby("impl").role.agg(lambda s: sorted(set(s)))
    for a, r in impl_stats.iterrows():
        rec[a]["im"] = [int(r.n), int(r.members), int(r.txs), [ROLE_CODE.get(x, "?") for x in impl_roles[a]]]
        if a in bs_name and "n" not in rec[a]:
            rec[a]["n"] = bs_name[a]

    print("records", len(rec), flush=True)
    shards = defaultdict(dict)
    for a, r in rec.items():
        key = a[2:2 + KEY_HEX]
        if key in shards[shard_of(a)]:
            raise RuntimeError(f"{KEY_HEX}-hex key collision at {a}")
        shards[shard_of(a)][key] = r
    shutil.rmtree(OUT, ignore_errors=True)
    os.makedirs(OUT)
    for k, d in shards.items():
        with gzip.open(f"{OUT}/{k}.json.gz", "wt", compresslevel=9) as fh:
            json.dump(d, fh, separators=(",", ":"))

    # block -> unix time anchors (min per 100k-block file of the precompile corpus)
    anchors = c.sql("""SELECT (block_number // 100000) * 100000 b, min(block_timestamp) ts
                       FROM read_parquet('~/work/xatu/precompile-usage/blocks_*.parquet', filename=false)
                       GROUP BY 1 ORDER BY 1""").fetchall()
    json.dump(fam_rows, open(f"{OUT}/families.json", "w"), separators=(",", ":"))
    m = {"cats": {v: k for k, v in CAT_CODE.items()}, "roles": {v: k for k, v in ROLE_CODE.items()},
         "muts": {v: k for k, v in MUT_CODE.items()}, "anchors": [[int(b), int(t)] for b, t in anchors],
         "y1": [22_100_000, 24_699_999], "sample_fraction": fr, "records": len(rec), "t_quantiles": t_quantiles}
    json.dump(m, open(f"{OUT}/meta.json", "w"), separators=(",", ":"))
    print("shards", len(shards))


if __name__ == "__main__":
    main()
