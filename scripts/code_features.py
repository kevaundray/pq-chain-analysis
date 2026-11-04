"""EVM runtime-bytecode features: opcode presence (push-data aware) and crypto-constant fingerprints."""

PUSH1, PUSH32 = 0x60, 0x7F

OPS = {"delegatecall": 0xF4, "callcode": 0xF2, "selfdestruct": 0xFF, "create2": 0xF5, "create": 0xF0}


def opcodes(code: bytes) -> set[int]:
    seen = set()
    i, n = 0, len(code)
    while i < n:
        op = code[i]
        seen.add(op)
        i += 1 + (op - PUSH1 + 1 if PUSH1 <= op <= PUSH32 else 0)
    return seen


def h(x: str) -> bytes:
    return bytes.fromhex(x)


# Raw byte sequences searched anywhere in the code (constants appear as PUSH data or data tables).
FINGERPRINTS = {
    # elliptic curves
    "secp256k1_p": h("fffffffffffffffffffffffffffffffffffffffffffffffffffffffefffffc2f"),
    "secp256k1_n": h("fffffffffffffffffffffffffffffffebaaedce6af48a03bbfd25e8cd0364141"),
    "secp256k1_n_half": h("7fffffffffffffffffffffffffffffff5d576e7357a4501ddfe92f46681b20a0"),
    "p256_p": h("ffffffff00000001000000000000000000000000ffffffffffffffffffffffff"),
    "p256_n": h("ffffffff00000000ffffffffffffffffbce6faada7179e84f3b9cac2fc632551"),
    "bn254_p": h("30644e72e131a029b85045b68181585d97816a916871ca8d3c208c16d87cfd47"),
    "bn254_r": h("30644e72e131a029b85045b68181585d2833e84879b9709143e1f593f0000001"),
    "bls12381_p_hi": h("1a0111ea397fe69a4b1ba7b6434bacd7"),
    "bls12381_r": h("73eda753299d7d483339d80809a1d80553bda402fffe5bfeffffffff00000001"),
    "ed25519_p": h("7fffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffed"),
    "ed25519_l": h("1000000000000000000000000000000014def9dea2f79cd65812631a5cf5d3ed"),
    # STARK fields (hash-based proof systems)
    "stark252_p": h("0800000000000011000000000000000000000000000000000000000000000001"),
    # lattice (ZKNox / Kohaku / Fireblocks fingerprints, see local research notes)
    "falcon_psi_rev": h("16e40c7b04bc29930e25261022510dd61fdb166802d22ae80fcb1be72a3a0001"),
    "falcon_psi_inv_rev": h("222b0db009f121dc066e2b452386191d05192d2f19991026141a203605c70001"),
    "mldsa_zetas": h("003965690039756700495e0200000001"),
    "push3_mldsa_q": h("627fe001"),
    "push3_mldsa_ninv": h("627f6021"),
    "push2_falcon_q": h("613001"),
    "push2_falcon_ninv": h("612fe9"),
    # ecrecover called with a hard-coded 3000 gas stipend (breaks under EIP-8151's higher success cost):
    # PUSH1 0x01 (address) PUSH2 0x0bb8 (gas) STATICCALL / CALL
    "ecrecover_gas3000_staticcall": h("6001610bb8fa"),
    "ecrecover_gas3000_call": h("6001610bb8f1"),
}


def fingerprints(code: bytes) -> dict[str, int]:
    return {k: code.count(v) for k, v in FINGERPRINTS.items()}


def classify_lattice(fp: dict[str, int]) -> str | None:
    if fp["falcon_psi_rev"] or fp["falcon_psi_inv_rev"] or (fp["push2_falcon_q"] >= 5 and fp["push2_falcon_ninv"]):
        return "falcon"
    if fp["mldsa_zetas"] or (fp["push3_mldsa_q"] >= 5 and fp["push3_mldsa_ninv"]):
        return "mldsa"
    return None
