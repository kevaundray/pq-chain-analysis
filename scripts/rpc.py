"""Batched mainnet state probes over a public RPC.

probe(addresses) -> {addr: (codehash, codesize, code_head32, balance_wei)} at `latest`, using one
eth_call per chunk against a hand-assembled helper injected with a state override:

  for each 32-byte word a in calldata:
      mem[4i..] = extcodehash(a), extcodesize(a), extcodecopy(a,0,32), balance(a)
  return mem[0 : 4*calldatasize]

read_slots(addresses) -> {addr: {slot_name: word}}  (proxy/admin slots, via stubbed-code state override)
get_codes(addresses)  -> {addr: runtime code}       (EXTCODECOPY of many contracts per eth_call)
See evm_helpers.py for the helper programs.
"""

import json
import os
import time
from concurrent.futures import ThreadPoolExecutor

import requests

RPCS = [
    os.environ.get("ETH_RPC_URL", "https://ethereum-rpc.publicnode.com"),
]
HELPER = "0x00000000000000000000000000000000000c0de1"
HELPER_CODE = (
    "0x60005b80361115603357803581600402813f8152813b81602001526020600082604001843c81319060600152"
    "506020016002565b50366004026000f3"
)

session = requests.Session()


def _rpc(method, params, url=None):
    body = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    for attempt in range(10):
        try:
            r = session.post(url or RPCS[0], json=body, timeout=120)
            j = r.json()
        except (requests.RequestException, json.JSONDecodeError):
            time.sleep(1 + attempt)
            continue
        if "error" in j:
            if attempt == 9:
                raise RuntimeError(j["error"])
            time.sleep(1 + attempt)
            continue
        return j["result"]
    raise RuntimeError(f"rpc failed: {method}")


def block_number() -> int:
    return int(_rpc("eth_blockNumber", []), 16)


def _probe_chunk(args):
    chunk, block = args
    data = "0x" + "".join(a[2:].rjust(64, "0") for a in chunk)
    res = _rpc(
        "eth_call",
        [{"to": HELPER, "data": data, "gas": hex(30_000_000)}, block, {HELPER: {"code": HELPER_CODE}}],
    )[2:]
    out = {}
    for i, a in enumerate(chunk):
        w = res[i * 256:(i + 1) * 256]
        out[a] = (w[0:64], int(w[64:128], 16), w[128:192], int(w[192:256], 16))
    return out


def probe(addresses, block="latest", chunk=400, workers=4):
    addrs = [a.lower() for a in addresses]
    chunks = [(addrs[i:i + chunk], block) for i in range(0, len(addrs), chunk)]
    result = {}
    with ThreadPoolExecutor(workers) as ex:
        for i, part in enumerate(ex.map(_probe_chunk, chunks)):
            result.update(part)
            if i % 100 == 0:
                print(f"probe {i}/{len(chunks)}", flush=True)
    return result


HELPER2 = "0x00000000000000000000000000000000000c0de2"


def _enc(addrs):
    return "0x" + "".join(a[2:].rjust(64, "0") for a in addrs)


def _chunks(seq, n):
    return [seq[i:i + n] for i in range(0, len(seq), n)]


def read_slots(addresses, block="latest", chunk=150, workers=3):
    """{addr: {slot_name: 32-byte hex word}} via stubbed-code state override (storage preserved)."""
    import evm_helpers as eh

    def run(ch):
        ov = {HELPER2: {"code": eh.CALLER}}
        ov.update({a: {"code": eh.STUB} for a in ch})
        r = _rpc("eth_call", [{"to": HELPER2, "data": _enc(ch), "gas": hex(30_000_000)}, block, ov])[2:]
        w = 64 * eh.NSLOTS
        return {a: dict(zip(eh.SLOTS, (r[i * w + j * 64:i * w + (j + 1) * 64] for j in range(eh.NSLOTS))))
                for i, a in enumerate(ch)}

    out = {}
    with ThreadPoolExecutor(workers) as ex:
        for part in ex.map(run, _chunks([a.lower() for a in addresses], chunk)):
            out.update(part)
    return out


def get_codes(addresses, block="latest", chunk=40, workers=3):
    """{addr: runtime code bytes} via the DUMP helper (EXTCODECOPY of many contracts per eth_call)."""
    import evm_helpers as eh

    def run(ch):
        b = bytes.fromhex(_rpc("eth_call", [{"to": HELPER2, "data": _enc(ch), "gas": hex(60_000_000)}, block,
                                            {HELPER2: {"code": eh.DUMP}}])[2:])
        res, off = {}, 0
        for a in ch:
            n = int.from_bytes(b[off:off + 32], "big")
            res[a] = b[off + 32:off + 32 + n]
            off += 32 + ((n + 31) // 32) * 32
        return res

    out = {}
    with ThreadPoolExecutor(workers) as ex:
        for part in ex.map(run, _chunks([a.lower() for a in addresses], chunk)):
            out.update(part)
    return out
