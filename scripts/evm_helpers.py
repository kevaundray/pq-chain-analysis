"""Hand-assembled EVM helpers used with eth_call state overrides (one call covers many addresses).

DUMP:   calldata = abi-packed addresses (32-byte words). Returns for each address:
        word(size) || code padded to 32 bytes.
STUB:   installed as the code of each *target* via state override; storage is preserved, so it returns
        the target's own values of SLOTS (7 x 32 bytes).
CALLER: calldata = addresses; staticcalls each (stubbed) target and returns the concatenated 7-word outputs.
"""

OPC = dict(ADD=0x01, MUL=0x02, GT=0x11, ISZERO=0x15, SHL=0x1B, SHR=0x1C, CALLDATALOAD=0x35, CALLDATASIZE=0x36,
           EXTCODESIZE=0x3B, EXTCODECOPY=0x3C, POP=0x50, MSTORE=0x52, SLOAD=0x54, JUMP=0x56, JUMPI=0x57, GAS=0x5A,
           JUMPDEST=0x5B, DUP1=0x80, DUP2=0x81, DUP4=0x83, DUP5=0x84, SWAP1=0x90, RETURN=0xF3, STATICCALL=0xFA)

SLOTS = {
    "eip1967_impl": 0x360894A13BA1A3210667C828492DB98DCA3E2076CC3735A920A3CA505D382BBC,
    "eip1967_admin": 0xB53127684A568B3173AE13B9F8A6016E243E63B6E8EE1178D6A717850B5D6103,
    "eip1967_beacon": 0xA3F0AD74E5423AEBFD80D3EF4346578335A9A72AEAEE59FF6CB3582B35133D50,
    "eip1822": 0xC5F16F0FCC639FA48A6947836D9850F504798523BF8C9A3A87D5876CF622BCF7,
    "zos_impl": 0x7050C9E0F4CA769C69BD3A8EF740BC37934F8E2C036E5A723FD8EE048ED3F8C3,
    "zos_admin": 0x10D6A54A4754C8869D6886B5F5D7FBFA5B4522237EA5C60D11BC4E7A1FF9390B,
    "slot0": 0,
}
NSLOTS = len(SLOTS)


def P(n, v):
    return ("PUSH", n, v)


def asm(prog) -> str:
    """Tokens: opcode names, P(n, value), ("PUSHL", label) (PUSH2 of a label), "LABEL:name"."""
    def size(t):
        if isinstance(t, tuple):
            return 1 + (t[1] if t[0] == "PUSH" else 2)
        return 0 if t.startswith("LABEL:") else 1

    labels, pc = {}, 0
    for t in prog:
        if isinstance(t, str) and t.startswith("LABEL:"):
            labels[t[6:]] = pc
        pc += size(t)
    out = bytearray()
    for t in prog:
        if isinstance(t, tuple):
            if t[0] == "PUSH":
                out += bytes([0x5F + t[1]]) + int(t[2]).to_bytes(t[1], "big")
            else:
                out += bytes([0x61]) + labels[t[1]].to_bytes(2, "big")
        elif not t.startswith("LABEL:"):
            out.append(OPC[t])
    return "0x" + out.hex()


# stack comments list the top of stack first
DUMP = asm([
    P(1, 0), P(1, 0),                                    # [ptr, i]
    "LABEL:loop", "JUMPDEST",
    "DUP2", "CALLDATASIZE", "GT", "ISZERO", ("PUSHL", "end"), "JUMPI",
    "DUP2", "CALLDATALOAD",                              # [addr, ptr, i]
    "DUP1", "EXTCODESIZE",                               # [size, addr, ptr, i]
    "DUP1", "DUP4", "MSTORE",                            # mem[ptr] = size
    "DUP1", P(1, 0), "DUP5", P(1, 32), "ADD", "DUP5", "EXTCODECOPY",   # extcodecopy(addr, ptr+32, 0, size)
    P(1, 31), "ADD", P(1, 5), "SHR", P(1, 5), "SHL", P(1, 32), "ADD",  # [inc, addr, ptr, i]
    "SWAP1", "POP", "ADD",                               # [ptr', i]
    "SWAP1", P(1, 32), "ADD", "SWAP1",                   # [ptr', i+32]
    ("PUSHL", "loop"), "JUMP",
    "LABEL:end", "JUMPDEST", P(1, 0), "RETURN",          # return(0, ptr)
])

_stub = []
for k, s in enumerate(SLOTS.values()):
    _stub += [P(32, s) if s else P(1, 0), "SLOAD", P(1, 32 * k), "MSTORE"]
STUB = asm(_stub + [P(1, 32 * NSLOTS), P(1, 0), "RETURN"])

CALLER = asm([
    P(1, 0),                                             # [i]
    "LABEL:loop", "JUMPDEST",
    "DUP1", "CALLDATASIZE", "GT", "ISZERO", ("PUSHL", "end"), "JUMPI",
    P(1, 32 * NSLOTS), "DUP2", P(1, NSLOTS), "MUL",      # [i*N, retSize, i]
    P(1, 0), P(1, 0), "DUP5", "CALLDATALOAD", "GAS",     # [gas, addr, 0, 0, i*N, retSize, i]
    "STATICCALL", "POP", P(1, 32), "ADD",
    ("PUSHL", "loop"), "JUMP",
    "LABEL:end", "JUMPDEST", P(1, NSLOTS), "MUL", P(1, 0), "RETURN",
])
