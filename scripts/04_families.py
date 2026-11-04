"""Resolve each caller family's logic code and upgradeability at head.

Family key (from the head probe): 7702:<delegate>, 1167:<impl>, code:<codehash>, nocode.
Representative = family member with most y1 pre-quantum precompile txs. For each representative:
  * read EIP-1967 impl/admin/beacon, EIP-1822, ZeppelinOS impl/admin and slot 0 (Safe singleton)
  * resolve the logic address (proxy impl, beacon impl, 1167 impl, 7702 delegate (+ its own proxy impl))
  * extract selector set / opcode flags / crypto fingerprints from the logic code.
Output: data/families.parquet
"""

import sys

import duckdb
import pandas as pd

sys.path.insert(0, "scripts")
import code_features as cf  # noqa: E402
import rpc  # noqa: E402

SAFE_MASTERCOPY_SELECTOR = bytes.fromhex("a619486e")
SELECTORS = {
    "isValidSignature": "1626ba7e",
    "validateUserOp_v06v07": "19822f7c",
    "validateUserOp_v08": "8f0a6f74",
    "execTransaction": "6a761202",
    "permit2612": "d505accf",
    "permitDAI": "8fcbaf0c",
    "transferWithAuthorization": "e3ee160e",
    "erc20_transfer": "a9059cbb",
    "upgradeTo": "3659cfe6",
    "upgradeToAndCall": "4f1ef286",
    "changeMasterCopy": "7de7edef",
    "diamondCut": "1f931c1c",
}


def word_addr(w):
    if not w or int(w, 16) == 0 or int(w, 16) >> 160:
        return None
    return "0x" + w[-40:]


def has_selector(code: bytes, sel: str) -> bool:
    return (b"\x63" + bytes.fromhex(sel)) in code


def main():
    c = duckdb.connect()
    fam = c.sql("""
      WITH y AS (SELECT caller, sum(txs) txs FROM 'data/agg/y1_caller.parquet'
                 WHERE precompile_name IN ('ecrecover','ecadd','ecmul','ecpairing','pointEval','p256verify','modexp')
                    OR precompile_name LIKE 'bls12%' GROUP BY 1)
      SELECT p.family, count(*) members, sum(y.txs) txs, arg_max(y.caller, y.txs) rep
      FROM y JOIN 'data/caller_family.parquet' p ON p.address = y.caller
      GROUP BY 1
    """).df()
    fam = fam[fam.family != "nocode"].reset_index(drop=True)
    print("families", len(fam), flush=True)

    reps = list(fam.rep)
    slots = rpc.read_slots(reps)
    codes = rpc.get_codes(reps)
    print("rep slots/codes", len(slots), len(codes), flush=True)

    rows = []
    for r in fam.itertuples():
        s = slots[r.rep]
        code = codes[r.rep]
        kind, target = "none", None
        if r.family.startswith("7702:"):
            kind, target = "eip7702", r.family[5:]
        elif r.family.startswith("1167:"):
            kind, target = "eip1167", r.family[5:]
        elif word_addr(s["eip1967_impl"]):
            kind, target = "eip1967", word_addr(s["eip1967_impl"])
        elif word_addr(s["eip1967_beacon"]):
            kind, target = "beacon", word_addr(s["eip1967_beacon"])
        elif word_addr(s["eip1822"]):
            kind, target = "eip1822", word_addr(s["eip1822"])
        elif word_addr(s["zos_impl"]):
            kind, target = "zos", word_addr(s["zos_impl"])
        elif len(code) < 1500 and SAFE_MASTERCOPY_SELECTOR in code and word_addr(s["slot0"]):
            kind, target = "safe_proxy", word_addr(s["slot0"])
        elif len(code) < 600 and cf.OPS["delegatecall"] in cf.opcodes(code):
            kind = "small_delegating_proxy"
        rows.append(dict(family=r.family, rep=r.rep, proxy_kind=kind, logic=target, rep_codesize=len(code),
                         admin=word_addr(s["eip1967_admin"]) or word_addr(s["zos_admin"])))

    for x in rows:
        if x["proxy_kind"] == "beacon":
            out = rpc._rpc("eth_call", [{"to": x["logic"], "data": "0x5c60da1b"}, "latest"])
            x["beacon"], x["logic"] = x["logic"], word_addr(out[2:])

    targets = sorted({x["logic"] for x in rows if x["logic"]})
    tslots = rpc.read_slots(targets)
    for x in rows:
        if x["logic"] and x["proxy_kind"] in ("eip7702", "eip1167"):
            x["logic2"] = word_addr(tslots[x["logic"]]["eip1967_impl"])
    logic_addrs = sorted(set(targets) | {x["logic2"] for x in rows if x.get("logic2")})
    lcodes = rpc.get_codes(logic_addrs)
    print("logic codes", len(lcodes), flush=True)

    for x in rows:
        la = x.get("logic2") or x["logic"]
        lc = lcodes[la] if la else codes[x["rep"]]
        x["logic_codesize"] = len(lc)
        ops = cf.opcodes(lc)
        for k, op in cf.OPS.items():
            x["op_" + k] = op in ops
        for k, sel in SELECTORS.items():
            x["sel_" + k] = has_selector(lc, sel)
        fp = cf.fingerprints(lc)
        for k, v in fp.items():
            x["fp_" + k] = v
        x["lattice"] = cf.classify_lattice(fp)
    out = fam.merge(pd.DataFrame(rows), on=["family", "rep"])
    out.to_parquet("data/families.parquet", index=False)
    print("done", len(out))


if __name__ == "__main__":
    main()
