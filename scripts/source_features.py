"""Regex features over Sourcify verified sources (data/sourcify/*.json) -> data/source_features.parquet.

Heuristics only; they feed manual/agent classification and are not ground truth.
"""

import glob
import json
import os
import re

import pandas as pd

PATTERNS = {
    "ecrecover": r"\becrecover\s*\(",
    "oz_ecdsa": r"\bECDSA\.(?:try)?[Rr]ecover",
    "solady_sigchecker": r"SignatureCheckerLib\.",
    "oz_sigchecker": r"SignatureChecker\.isValidSignatureNow",
    "calls_1271": r"(?:IERC1271|ERC1271)\s*\([^)]*\)\s*\.isValidSignature|0x1626ba7e",
    "implements_1271": r"function\s+isValidSignature\s*\(",
    "code_length_gate": r"\.code\.length\s*(?:==|>|!=)\s*0|extcodesize|isContract\s*\(",
    "permit_2612": r"function\s+permit\s*\(",
    "eip3009": r"function\s+(?:transferWithAuthorization|receiveWithAuthorization)\s*\(",
    "eip712": r"EIP712|_hashTypedDataV4|DOMAIN_SEPARATOR",
    "uups": r"UUPSUpgradeable|function\s+upgradeTo(?:AndCall)?\s*\(",
    "initializable": r"\bInitializable\b",
    "delegatecall_src": r"\.delegatecall\s*\(|delegatecall\s*\(\s*gas",
    "selfdestruct_src": r"\bselfdestruct\s*\(",
    "groth16": r"(?i)groth16|verifyProof\s*\(",
    "plonk": r"(?i)plonk|fflonk|honk",
    "pairing": r"(?i)\bpairing\b|ecPairing|staticcall\([^)]*,\s*(?:0x)?0?8\s*,",
    "bn254": r"(?i)bn254|bn128|alt_bn128",
    "bls": r"(?i)\bbls\b|BLSSignatureChecker|bls12",
    "kzg": r"(?i)kzg|point_?evaluation|blobhash",
    "p256": r"(?i)p256|secp256r1|webauthn|FCL_",
    "rsa": r"(?i)\brsa\b|pkcs1",
    "ed25519": r"(?i)ed25519|curve25519",
    "schnorr": r"(?i)schnorr",
    "vrf": r"(?i)\bvrf\b",
    "lattice": r"(?i)falcon|dilithium|ml-?dsa|kyber|lattice|\bntt\b",
    "hash_based_sig": r"(?i)lamport|winternitz|\bwots\b|xmss|sphincs",
    "role_guardian": r"(?i)guardian",
    "role_oracle": r"(?i)\boracle|transmitter|aggregator",
    "role_signer": r"(?i)\b(?:trusted)?signer\b|signers\b|validatorSet|committee|quorum|threshold",
    "role_relayer": r"(?i)relayer|operator|sequencer|attester",
}
OZ_HEADER = re.compile(r"OpenZeppelin Contracts(?: \(last updated v([0-9.]+)\))?(?: v([0-9.]+))?")


def features(addr: str, d: dict) -> dict:
    sources = d.get("sources") or {}
    text = "\n".join(s.get("content", "") for s in sources.values())
    comp = d.get("compilation") or {}
    pr = d.get("proxyResolution") or {}
    row = {
        "address": addr,
        "name": comp.get("name"),
        "compiler": comp.get("compilerVersion"),
        "is_proxy": pr.get("isProxy"),
        "proxy_type": pr.get("proxyType"),
        "implementations": ";".join(i.get("address", "").lower() for i in pr.get("implementations") or []),
        "deploy_block": (d.get("deployment") or {}).get("blockNumber"),
        "n_files": len(sources),
    }
    for k, p in PATTERNS.items():
        row[k] = len(re.findall(p, text))
    sc = [s.get("content", "") for path, s in sources.items() if path.endswith("SignatureChecker.sol")]
    vers = []
    for content in sc:
        m = OZ_HEADER.search(content)
        if m:
            vers.append(m.group(1) or m.group(2) or "?")
    row["oz_sigchecker_version"] = ";".join(vers)
    row["source_files"] = ";".join(sorted(os.path.basename(p) for p in sources))[:2000]
    return row


rows = []
for f in glob.glob("data/sourcify/*.json"):
    with open(f) as fh:
        d = json.load(fh)
    if d:
        rows.append(features(os.path.basename(f)[:-5], d))
df = pd.DataFrame(rows)
df.to_parquet("data/source_features.parquet", index=False)
print(len(df), "verified")
