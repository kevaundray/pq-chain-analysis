"""Assign every probed caller to a code family -> data/caller_family.parquet (address, family).

Family keys:
  7702:<delegate>         EIP-7702 delegated EOA (code = 0xef0100 || delegate)
  1167:<impl>             EIP-1167 minimal proxy
  ptr:<kind>:<addr>       small (<1500 B) proxy code whose behaviour is set by storage; split by the stored
                          pointer (EIP-1967 impl, beacon, EIP-1822, ZeppelinOS impl, Safe singleton in slot 0), because
                          one generic proxy bytecode (e.g. ERC-1967/ERC-7760 minimal proxy) fronts unrelated logic
  code:<codehash>         everything else, by runtime code hash
  nocode                  no code at head (EOA callers or destroyed contracts)
"""

import sys

import duckdb
import pandas as pd

sys.path.insert(0, "scripts")
import code_features as cf  # noqa: E402
import rpc  # noqa: E402

SMALL = 1500


def base_family(code_head: str, codesize: int, codehash: str) -> str:
    if codesize == 0:
        return "nocode"
    if code_head.startswith("ef0100"):
        return "7702:0x" + code_head[6:46]
    if code_head.startswith("363d3d373d3d3d363d73"):
        return "1167:0x" + code_head[20:60]
    return "code:0x" + codehash


def word_addr(w):
    if not w or int(w, 16) == 0 or int(w, 16) >> 160:
        return None
    return "0x" + w[-40:]


def main():
    pr = pd.read_parquet("data/probe_latest.parquet")
    pr["family"] = [base_family(h, s, ch) for h, s, ch in zip(pr.code_head, pr.codesize, pr.codehash)]

    c = duckdb.connect()
    active = {r[0] for r in c.sql("""SELECT DISTINCT caller FROM 'data/agg/y1_caller.parquet'
        WHERE precompile_name IN ('ecrecover','ecadd','ecmul','ecpairing','pointEval','p256verify','modexp')
           OR precompile_name LIKE 'bls12%'""").fetchall()}
    small = pr[pr.family.str.startswith("code:") & (pr.codesize < SMALL) & pr.address.isin(active)]
    # only bytecodes that can forward calls (DELEGATECALL present) are candidate proxies
    reps = small.groupby("family").address.first()
    rep_codes = rpc.get_codes(list(reps))
    proxy_fams = {f for f, a in reps.items() if cf.OPS["delegatecall"] in cf.opcodes(rep_codes[a])}
    members = list(small[small.family.isin(proxy_fams)].address)
    print("proxy families", len(proxy_fams), "members", len(members), flush=True)

    slots = rpc.read_slots(members, workers=4)
    newfam = {}
    for a in members:
        s = slots[a]
        for kind in ("eip1967_impl", "eip1967_beacon", "eip1822", "zos_impl", "slot0"):
            p = word_addr(s[kind])
            if p:
                newfam[a] = f"ptr:{kind}:{p}"
                break
    pr["family"] = [newfam.get(a, f) for a, f in zip(pr.address, pr.family)]
    pr[["address", "family"]].to_parquet("data/caller_family.parquet", index=False)
    print("split", len(newfam), "families", pr.family.nunique())


if __name__ == "__main__":
    main()
