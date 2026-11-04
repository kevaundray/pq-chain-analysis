# Pre-quantum crypto dependencies of Ethereum mainnet contracts: PQ research notes (as of 2026-11-03)

Scope: web and on-chain research only. Quick reads of mainnet state used a public RPC (`ethereum-rpc.publicnode.com`, block ≈ 26,336,574) and Sepolia (`ethereum-sepolia-rpc.publicnode.com`). Anything inferred rather than read from a source is tagged **[INFERENCE]**. Anything I could not confirm is tagged **[UNVERIFIED]**.

---

## 1. PQ signature verifiers on Ethereum mainnet

### 1.1 Summary

Only one PQ-verifying contract family is confirmed live on mainnet: the **Pauli Group / Anchor Wallet Lamport wallets**, which use hash-based one-time signatures. Every lattice verifier found (Falcon, ML-DSA, SPHINCS variants) is on **testnets or devnets only**.

### 1.2 Confirmed mainnet deployments

| Project | Scheme | Mainnet address(es) | Evidence |
|---|---|---|---|
| Anchor Wallet v1 (Pauli Group) "LamportWalletFactory" | Lamport OTS (keccak) | Factory **`0x5D58355AeFa81AAD5672dd39d6D8C73fDbA237a9`** (14,722 B runtime, nonce 8) | Listed as `"ethereum"`, chainid 1, `isTestnet:false` in [LamportWalletManager/supportedBlockchains.json](https://github.com/Pauli-Group/LamportWalletManager/blob/master/supportedBlockchains.json). Code confirmed via `eth_getCode`. |
| Anchor Lamport wallets created by that factory | Lamport OTS | `0x753c54c23f5c1f9646aff4f48f3b60d7beab5700`, `0xc27f9f8ac2dfe10d67af6fea2f469a3b04631b01`, **`0xe1c67b7db6ea02125d4a2d4ec91d382dbf98e3d9`**, `0x70c006c4c9456ba14054e2b923fcffeba8513af2`, `0xdaadcae35c1335b6e8d1aac7b9ce03ca7ac4f8ce`, `0x9935a9a8b535c214dfcb7288f5a4afe5096fd4e0`, `0xaf2692c294311e16eafc31206ef2d067b1743c1c` | I derived these as CREATE addresses for factory nonces 1–7. Each has 6,038 B of identical runtime code (codehash `0x43c7153efb4fa3205195d1869fb18a330bf989ea128245dde68c9a41545dcfc1`). Balances are tiny: 0, 0, 0.01, 0.0501, 0, 0, 0.005 ETH. The Pauli founder independently names `0xE1C67B…E3d9` as a mainnet Lamport wallet holding CryptoKitty #1850 ([ethresear.ch reply #11](https://ethresear.ch/t/how-to-hard-fork-to-save-most-users-funds-in-a-quantum-emergency/18901/11)). |
| Anchor Vault (newer ERC-4337 Lamport account) | Lamport OTS | **Not found** on mainnet | The product page describes it ([anchorwallet.ca](https://anchorwallet.ca/)), but the only factory found is Sepolia `0x7AB1135013e119496a823e2E28C7CC9eA4A566EF` ([lambAAInteractions/blockchainOptions.ts](https://github.com/Pauli-Group/lambAAInteractions)). |

Two caveats on the Anchor v1 wallets:
- **They still accept ECDSA signatures.** The runtime contains the ERC-1271 `isValidSignature` selector `0x1626ba7e`, and Pauli's CLI documents "Sign Message With ECDSA Key on behalf of wallet (EIP1271 - **Not A Quantum Secure Signature**)" ([wallet_cli README](https://github.com/Pauli-Group/wallet_cli)). This is an instance of the hybrid-wallet weakness in §4.
- **Transactions are relayed by an EOA.** A connected EOA submits each call and pays gas ([anchorwallet.ca](https://anchorwallet.ca/)), so the PQ protection covers the assets only, not the submission path.

### 1.3 Lattice and hash-based verifiers found on testnets only

I checked every listed verifier, factory and account address on mainnet with `eth_getCode`; all returned `0x`.

| Project | Schemes | Where deployed | Gas (verify) | Source |
|---|---|---|---|---|
| ZKNox ETHFALCON | Falcon-512 (NIST), ETHFALCON (keccak instead of SHAKE), EPERVIER (key-recovery variant) | Sepolia, Arbitrum Sepolia, Base Sepolia (via the Kohaku deployments file); OP Sepolia example `0xD088Ede58BD1736477d66d114D842bDE279A41Fa` | main branch: Falcon 3.9M, ETHFALCON 1.5M, EPERVIER 1.6M. Experimental `ZKNOX_falcon8` branch: **447,047** execution (~500k as a full tx); Falcon-1024 845,839 | [README](https://github.com/ZKNoxHQ/ETHFALCON), [benchmarks](https://github.com/ZKNoxHQ/ETHFALCON/blob/main/doc/benchmarks.md) |
| ZKNox ETHDILITHIUM | ML-DSA-44 (NIST), MLDSA-ETH | Same testnets | main: 8.1M / 4.9M. `exp/packed-verifier` branch: **1,196,707** / 847,709; ML-DSA-65 1.54M | [README](https://github.com/ZKNoxHQ/ETHDILITHIUM) |
| EF Kohaku `pq-account` | Hybrid ERC-4337 account: ECDSA-k1 or P-256, combined with Falcon, ETHFALCON, ML-DSA or MLDSA-ETH | Sepolia (verifiers e.g. Falcon `0x9A8bD1cA6533E367CEA77f16eb116ed9A55029F2`, ETHFALCON `0x328C56D41FeEA925c718D1ebBEDd5481E363de9C`, ML-DSA `0x092c5d82069de997E34Ce2505CA7D5042f3721ef`, MLDSA-ETH `0xA7D6d8A62521F316a77372ebfCAdbb5B44be1C34`), Arbitrum Sepolia, Base Sepolia. Addresses are CREATE2 (salted) and empty on mainnet. | Account total: 8.39M (ML-DSA), 5.12M (MLDSA-ETH), 4.06M (Falcon), 1.69M (ETHFALCON), each including the ECDSA leg | [README](https://github.com/ethereum/kohaku/tree/master/packages/pq-account), [deployments.json](https://github.com/ethereum/kohaku/blob/master/packages/pq-account/deployments/deployments.json) |
| Fireblocks `evm-ml-dsa-verifier` | ML-DSA-44, FIPS 204 compliant | No deployments listed; repo labelled research code, unaudited | **1,226,311** per verify. Key registration ≈4.11M gas (20,545 B key stored as contract code). Needs a shared Keccak-f[1600] helper contract. | [repo](https://github.com/fireblocks-labs/evm-ml-dsa-verifier), [blog 2026-09-02](https://www.fireblocks.com/blog/post-quantum-signatures-ethereum-cheaper-gas) |
| nconsigny SPHINCs- | SLH-DSA variants: C7, C12, C13, SLH-DSA-SHA2/Keccak-128-24, leanSphincs(-s/-f) | Sepolia (e.g. C13 `0xc6f4009D4a8220527b849670431Cbde5FeD8A5F2`, SLH-DSA-SHA2-128-24 `0x12B712ad3ca6D81d4B3690B2f93420cd65EA0553`); ethrex EIP-8141 testnet (chain 8141) frame accounts | Verify execution 39k–204k. Full tx ≈178k–390k, dominated by the calldata floor of ≈64 gas per signature byte. | [README](https://github.com/nconsigny/SPHINCs-), [deployments.md](https://github.com/nconsigny/SPHINCs-/blob/main/docs/deployments.md), [ethresear.ch](https://ethresear.ch/t/sphincs-minus-efficient-stateless-post-quantum-signature-verification-on-the-evm/25165/1) |
| poqeth (academic) | WOTS+, XMSS, SPHINCS+, MAYO | Library only | Finds full on-chain verification "often prohibitively costly"; optimistic "Naysayer" verification mode is cheapest | [ePrint 2025/091](https://eprint.iacr.org/2025/091), [repo](https://github.com/ruslan-ilesik/poqeth) |
| Other demos (PQBEAT Falcon-Smart-Account, LimeChain FlyFlow, Tetration falcon-solidity, Silence Labs ML-DSA demo on Base Sepolia) | Falcon / ML-DSA | Testnets or local only, per their READMEs | Tetration's Falcon: 24M (per ZKNox benchmarks) | [PQBEAT](https://github.com/PQBEAT/Falcon-Smart-Account), [FlyFlow](https://github.com/LimeChain/FlyFlow), [Tetration](https://github.com/Tetration-Lab/falcon-solidity), [Silence Labs](https://docs.silencelaboratories.com/duo/cookbook/example-apps/react-native-boilerplate/code-walkthrough/post-quantum-signing) |

### 1.4 Searched with no mainnet result
- Mainnet `eth_getCode` on every ZKNox/Kohaku CREATE2 verifier, factory and account address in deployments.json, plus the OP-Sepolia example address: all empty.
- Kyber / ML-KEM verifiers in Solidity: none found. Search: "Kyber ML-KEM solidity smart contract Ethereum". A KEM has no on-chain verification role anyway [INFERENCE].
- XMSS or WOTS verifier wallets on mainnet, other than Anchor's Lamport: none found. Searches: "Lamport signature smart contract wallet Ethereum mainnet", "SPHINCS+ solidity verifier … WOTS+ XMSS", "post-quantum smart account Ethereum mainnet launch 2026".
- Mainnet deployments of SPHINCs-, Fireblocks, PQBEAT or FlyFlow: none listed in their repos.
- Not checked: whether any of the testnet bytecodes above also appear on mainnet. That needs a codehash or fingerprint scan, which the data team can run with §1.5.

### 1.5 Bytecode fingerprints

All values below were extracted from **Sepolia runtime bytecode** of the ZKNox/Kohaku verifiers and cross-checked against source.

| Scheme | Fingerprint | Notes |
|---|---|---|
| Falcon-512 (ZKNox `falcon`, `ethfalcon`) | `PUSH2 0x3001` (q = 12289), seen 15× | Modulus. Source: [ZKNOX_falcon_utils.sol](https://github.com/ZKNoxHQ/ETHFALCON/blob/main/src/ZKNOX_falcon_utils.sol); also EIP-8052 `q = 12289`. |
| | `PUSH2 0x2fe9` (12265 = 512⁻¹ mod q) | Inverse-NTT scaling constant, named `nm1modq` in source. |
| | 32-byte word `0x16e40c7b04bc29930e25261022510dd61fdb166802d22ae80fcb1be72a3a0001` | First word of the packed `psi_rev` twiddle table: 16×16-bit coefficients, little-endian within the uint256, coefficients 1, 10810, 7143, … ([ZKNOX_falcon_deploy.sol](https://github.com/ZKNoxHQ/ETHFALCON/blob/main/src/ZKNOX_falcon_deploy.sol)). Present in both Sepolia Falcon verifiers. |
| | `0x222b0db009f121dc066e2b452386191d05192d2f19991026141a203605c70001` | First word of the packed `psi_inv_rev` table (1, 1479, 8246, …). |
| | Packing format | Public keys and signature polynomials: 16 coefficients of 16 bits per uint256, so 32 words per 512-coefficient polynomial ([README](https://github.com/ZKNoxHQ/ETHFALCON)). Interface `verify(bytes h, bytes salt, uint256[] s2, uint256[] ntth)`. |
| ML-DSA / Dilithium (ZKNox `mldsa`, `mldsaeth`) | `PUSH3 0x7fe001` (q = 8380417), seen 16–18× | Modulus. Also EIP-8051 `q = 8380417`. |
| | `PUSH3 0x7f6021` (8347681 = 256⁻¹ mod q) | Inverse-NTT scaling. |
| | Byte run `003965690039756700495e0200000001` | Zetas 1753^brv(i) (1, 4808194, 3765607, 3761513, …) packed as descending 32-bit big-endian lanes inside PUSH words. Present in both Sepolia ML-DSA verifiers. |
| | 20,545-byte key-blob contracts | Expanded public key stored as contract code and read with EXTCODECOPY: ZKNox "PKContract" and the Fireblocks `pkBlob` ([Fireblocks README](https://github.com/fireblocks-labs/evm-ml-dsa-verifier)). |
| Shared SHAKE helper (Fireblocks, also used on ZKNox experimental branches) | Runtime `f1600_170.hex`, 21,622 B, keccak codehash `0x4afb4435879cdf8e50474c7aab2bc3a679caed432550ad6dba64f509309a817b` | The verifier pins this exact codehash via EXTCODEHASH ([helpers/README](https://github.com/fireblocks-labs/evm-ml-dsa-verifier/tree/main/helpers)). |
| Kyber / ML-KEM | `PUSH2 0x0d01` (q = 3329) | Listed in the [EIP-7885](https://eips.ethereum.org/EIPS/eip-7885) NTT moduli. 0x0d01 is a small constant, so expect false positives unless combined with other signals. |
| Other NTT moduli (EIP-7885) | BabyBear `0x78000001`, Goldilocks `0xffffffff00000001` | Indicate STARK/FRI verifiers rather than signature verifiers. |
| Hash-based (SPHINCs-, Lamport) | No modulus to match | Detect by codehash (Anchor wallet above; Sepolia C13 runtime 1,191 B, SLH-DSA-SHA2 1,284 B), by heavy KECCAK256 or SHA-256-precompile (`0x02`) loops, or by `verify(bytes32 pkSeed, bytes32 pkRoot, bytes32 message, bytes sig)`-style ABIs ([SPHINCs- README](https://github.com/nconsigny/SPHINCs-)). [INFERENCE] for the generic loop heuristics. |

### 1.6 Precompile proposals and their status

| Proposal | What | Status (Nov 2026) | Source |
|---|---|---|---|
| EIP-8051 | ML-DSA-44 verify at 0x12 (NIST) and 0x13 (ETH variant), 4,500 gas each; EIP-7932 alg type 0xD1 | Draft; not in Hegotá's tiered candidate set | [EIP-8051](https://eips.ethereum.org/EIPS/eip-8051) |
| EIP-8052 | Falcon-512 precompiles: hash-to-point ≈1,000 gas + core ≈2,000 gas; EIP-7932 alg type 0xFA; addresses TBD | Draft; not in Hegotá's candidate set | [EIP-8052](https://eips.ethereum.org/EIPS/eip-8052) |
| EIP-8355 | ML-DSA-44/65/87 verify at 0x12/0x13/0x14; 6,500 / 9,000 / 13,500 base gas + 6 gas per message word | Draft. EF tier list: C ("premature standardization"). **Declined for inclusion (DFI) in Hegotá at ACDE #247 (2026-10-08).** Disagreement over lattice assumptions vs hash-based; a compromise to reserve addresses for L2s was floated. | [EIP-8355](https://eips.ethereum.org/EIPS/eip-8355), [EF tier list](https://blog.ethereum.org/en/2026/09/07/protocol-hegota-eips), [ACDE #247 summary](https://etherworld.co/ethereum-protocol-update-acde-247/) |
| EIP-7885 | Generic NTT precompiles (FW/INV/VECMULMOD/VECADDMOD) for Falcon, Dilithium, Kyber, BabyBear, Goldilocks | Draft | [EIP-7885](https://eips.ethereum.org/EIPS/eip-7885) |
| EIP-7932 | Secondary signature algorithm registry and sig-recover precompile | Draft | [EIP-7932](https://eips.ethereum.org/EIPS/eip-7932) |
| EIP-8288 | EIP-8141 frame mode for in-mempool PQ-signature and STARK aggregation (leanVM recursive STARK) | Draft | [EIP-8288](https://eips.ethereum.org/EIPS/eip-8288) |
| RIPs (rollup precompiles) | PQ signature precompile | **Not found.** Searched [eip.tools/rips](https://eip.tools/rips) and "rollup RIP post-quantum signature precompile Falcon ML-DSA". EIP-8052 explicitly avoids the RIP range 0x0100–0x01FF. | — |
| EF roadmap | "PQ sig precompiles" at fork **J\***; MV-PQ adds "leanSPHINCS transactions" at J\* | Planning only | [pq.ethereum.org](https://pq.ethereum.org/), [EF priorities 2026-09-07](https://blog.ethereum.org/en/2026/09/07/protocol-priorities) |

---

## 2. Status of PQ account plans on Ethereum

| Item | Status and what it means for contracts | Source |
|---|---|---|
| **EIP-8141 Frame Transactions** | Draft spec, but **Scheduled for Inclusion as Hegotá's execution-layer headliner** (ACDE #245, Sept 2026). EF tier list grades it S. Hegotá mainnet is expected ~Q2 2027 (date unconfirmed). Built-in schemes are only SECP256K1 (0x1) and P256 (0x2); PQ schemes run as contract code in VERIFY frames, with witnesses in `ARBITRARY` signature entries read via SIGDATACOPY. Code-less EOAs get "default code" that still requires a SECP256K1 signature. The canonical paymaster authorizes with `ecrecover`. The spec states "the EIP-7702 authorization list heavily relies on ECDSA … does not satisfy the PQ goals". | [EIP-8141](https://eips.ethereum.org/EIPS/eip-8141), [ACDE #245](https://etherworld.co/ethereum-protocol-update-acde-245/), [ethereum.org Hegotá](https://ethereum.org/roadmap/hegota/) |
| **EIP-8151 Account Code Restricted ecRecover** | **This is the "make ecrecover fail for migrated accounts" proposal.** After recovery, the `0x01` precompile returns *empty output* unless the recovered address's raw code is empty or exactly a 7702 delegation indicator. Gas rises to 6,100 (cold) / 3,200 (warm). Rationale cited: immutable `permit` tokens. Caveats in the spec: (a) `staticcall(3000, 1, …)` callers will run out of gas; (b) pure-Solidity ECDSA libraries bypass it; (c) L2 fault proofs that assume ecrecover is pure are affected. Status: Draft; EF tier A; **CFI for Hegotá at ACDE #247**, paired with EIP-8298. Important: it does **not** protect an EOA that is still 7702-delegated, because delegation-indicator code is allowed through. | [EIP-8151](https://eips.ethereum.org/EIPS/eip-8151), [ACDE #247](https://etherworld.co/ethereum-protocol-update-acde-247/) |
| **EIP-8298 SETCODEFROM** | Lets a 7702-delegated EOA install real code, so EIP-3607 then blocks ECDSA-originated transactions and EIP-8151 blocks ecrecover. The EF calls 8151 + 8298 together "the account path for retiring secp256k1 as a master key". Draft; tier A; CFI at ACDE #247. | [EIP-8298](https://eips.ethereum.org/EIPS/eip-8298), [EF priorities](https://blog.ethereum.org/en/2026/09/07/protocol-priorities) |
| **EIP-7851 Code-Controlled EOA Delegation** (ECDSA-disabled `0xef0101` prefix) | **Declined for inclusion in Hegotá** (ACDE #245); EF tier DFI ("loses to the Frames approach"). | [EIP-7851](https://eips.ethereum.org/EIPS/eip-7851), [ACDE #245](https://etherworld.co/ethereum-protocol-update-acde-245/) |
| **EIP-7932** signature algorithm registry | Draft. Referenced by EIP-8051, EIP-8052 and EIP-8030 (P256 alg type). Not among Hegotá candidates. | [EIP-7932](https://eips.ethereum.org/EIPS/eip-7932) |
| **Vitalik, "How to hard-fork to save most users' funds in a quantum emergency"** (ethresear.ch, 2024-03-09) | Plan: roll back to before large-scale theft; **disable traditional EOA transactions**; add a smart-wallet tx type; let users move to new validation code by submitting a STARK proof of a hash preimage (BIP-32 seed) of their key. **The post says nothing about `ecrecover` or contract-level signatures.** Permits, orders and similar would remain forgeable under that plan unless something like EIP-8151 is added [INFERENCE]. | [ethresear.ch/t/18901](https://ethresear.ch/t/how-to-hard-fork-to-save-most-users-funds-in-a-quantum-emergency/18901) |
| EF roadmap ([pq.ethereum.org](https://pq.ethereum.org/), [ethereum.org](https://ethereum.org/roadmap/security/quantum-resistance/)) | EF PQ team formed January 2026. Milestones: I\* PQ key registry (consensus layer); J\* PQ sig precompiles (execution layer); L\* PQ attestations + leanVM; M\* PQ sig aggregation + PQ blobs. Target: **L1 quantum-resistant across all three layers by December 2029**. Plan assumes Q-day as early as 2030; "MV-PQ" contingency at J\* (leanSPHINCS transactions, leanDA). Execution-layer migration "without a flag day" via account abstraction. | [EF priorities](https://blog.ethereum.org/en/2026/09/07/protocol-priorities), [strawmap issue #6](https://github.com/ethereum/strawmap/issues/6) |
| Consensus layer: leanSig / leanXMSS / leanMultisig | BLS replaced by hash-based leanXMSS, aggregated with a minimal zkVM (leanVM). Executable spec (leanSpec) used by ~10 client teams in weekly PQ interop devnets. EIP-8365 (BLS withdrawal-credential retirement) is tier A / CFI for Hegotá. | [leanSig](https://github.com/leanEthereum/leanSig), [leanMultisig](https://github.com/leanEthereum/leanMultisig), [ePrint 2025/055](https://eprint.iacr.org/2025/055.pdf), [pq.ethereum.org](https://pq.ethereum.org/) |
| Dormant or unmigrated funds | Left as an open governance question; EF estimates long-dormant exposure at ≈0.1% of ETH. | [pq.ethereum.org FAQ](https://pq.ethereum.org/) |

---

## 3. PQ replacement options by use case

Reference costs of today's primitives, for comparison:

| Primitive | Gas |
|---|---|
| ecrecover | 3,000 (6,100 / 3,200 under EIP-8151) |
| P256VERIFY (0x100) | 6,900 ([EIP-7951](https://eips.ethereum.org/EIPS/eip-7951)) |
| KZG point evaluation (0x0a) | 50,000 ([EIP-4844](https://eips.ethereum.org/EIPS/eip-4844)) |
| BLS12-381 pairing | 32,600·k + 37,700 ([EIP-2537](https://eips.ethereum.org/EIPS/eip-2537)) |
| Groth16 / fflonk verify | ≈300k ([ethresear.ch WHIR post](https://ethresear.ch/t/on-the-gas-efficiency-of-the-whir-polynomial-commitment-scheme/21301)) |

PQ signature verification, in EVM bytecode today:

| Scheme | Verify gas | Status |
|---|---|---|
| SPHINCS- / leanSphincs | ≈40–200k execution, ≈180–390k as a tx (calldata-bound) | Research, unaudited |
| ETHFALCON (keccak) | ≈1.5M (main branch) | Research, unaudited |
| Falcon-512 (NIST) | ≈0.45M (experimental branch) to 3.9M (main) | Research, unaudited |
| ML-DSA-44 (NIST) | ≈1.2M, plus ≈4.1M one-time key deployment | Research, unaudited |
| Lamport | Production on mainnet, but one-time keys | Anchor (no audit report found) |

Costs with precompiles are proposal estimates only: ≈3–4.5k (EIP-8051/8052) or 6.5–13.5k (EIP-8355), and none is scheduled.

### 3.1 ECDSA `ecrecover` for user authorization

| Use | How it verifies today | Exposure if the user's EOA migrates | PQ path |
|---|---|---|---|
| EIP-2612 `permit` (OpenZeppelin ERC20Permit, UNI), DAI-style `permit` | `ECDSA.recover` / `ecrecover` only; no ERC-1271 ([EIP-2612](https://eips.ethereum.org/EIPS/eip-2612), [OZ ERC20Permit](https://github.com/OpenZeppelin/openzeppelin-contracts/blob/master/contracts/token/ERC20/extensions/ERC20Permit.sol)) | Old key still signs permits; immutable tokens cannot be patched. | Only protocol-level EIP-8151 (requires the account to carry real, non-7702 code), or users revoking and avoiding the token [INFERENCE]. |
| EIP-3009 (USDC `transferWithAuthorization`) | FiatToken `SignatureChecker`: ecrecover if `!isContract(signer)`, otherwise ERC-1271 ([source](https://github.com/circlefin/stablecoin-evm/blob/master/contracts/util/SignatureChecker.sol)) | A delegated or migrated account has code, so ERC-1271 is used and the account's own (possibly PQ) logic decides. | Already PQ-capable via ERC-1271 once the account has code. |
| Permit2 (`0x000000000022D473030F116dDEE9F6B43aC78BA3`) and UniswapX (built on Permit2) | `code.length == 0` → ecrecover, else ERC-1271 ([SignatureVerification.sol](https://github.com/Uniswap/permit2/blob/main/src/libraries/SignatureVerification.sol)) | Same as USDC: safe once the account has code. | ERC-1271 → PQ verifier. |
| Seaport (1.6 at `0x0000000000000068F116a894984e2DB1123eB395`) | **Tries ecrecover first for 64/65-byte signatures; ERC-1271 only as fallback** ([SignatureVerification.sol](https://github.com/ProjectOpenSea/seaport-core/blob/main/src/lib/SignatureVerification.sol)) | Old ECDSA key keeps working even after the account has code. | EIP-8151 makes ecrecover return empty for code-bearing accounts, closing this hole. |
| CoW Protocol GPv2 | Signer chooses the scheme (Eip712 / EthSign / Eip1271 / PreSign) ([GPv2Signing.sol](https://github.com/cowprotocol/contracts/blob/main/src/contracts/mixins/GPv2Signing.sol)) | An attacker simply picks the ECDSA scheme [INFERENCE from code]. | EIP-8151. |
| 0x Exchange Proxy | `LibSignature`: EIP712 / ETHSIGN via ecrecover ([source](https://github.com/0xProject/protocol/blob/development/contracts/zero-ex/contracts/src/features/libs/LibSignature.sol)) | ECDSA only. | EIP-8151, or a redeploy. |
| Meta-tx forwarders (OpenZeppelin ERC2771Forwarder) | `ECDSA.tryRecoverCalldata` only ([source](https://github.com/OpenZeppelin/openzeppelin-contracts/blob/master/contracts/metatx/ERC2771Forwarder.sol)) | ECDSA only. | Replace with an ERC-1271 / ERC-7913-aware forwarder, or rely on 8141 native sponsorship. |
| Safe multisig owners | Signature types: ECDSA, `eth_sign` (v+4), ERC-1271 contract signature, approved hash ([Safe docs](https://docs.safefoundation.org/smart-account/signatures)) | Each EOA owner is a quantum-breakable key. | Swap EOA owners for ERC-1271 contract owners that verify PQ signatures (e.g. the Kohaku pq-account pattern), or use approved-hash. Safe-specific PQ module: **not found** (searched "Safe smart account post-quantum owner signer ERC-1271 Falcon Safe module quantum"). |
| ERC-4337 accounts | Validator logic in the account; bundler transaction is ECDSA-signed | PQ validators exist on testnets (Kohaku, SPHINCs-, Anchor Vault on Sepolia). Bundlers' validation gas limits are a practical obstacle for ≈1M-gas verifiers, as raised at [ACDE #247](https://etherworld.co/ethereum-protocol-update-acde-247/). | Hash-based SPHINCs- (≈60k `validateUserOp`) fits the limits; Falcon / ML-DSA at ≈0.5–1.2M strains them. |
| EIP-7702 delegates | The delegated EOA's ECDSA key can always re-delegate; EIP-8151 deliberately lets ecrecover pass for 7702-indicator code | Residual root authority stays with ECDSA. | EIP-8298 (convert to real code) plus EIP-8151; EIP-7851 was declined. |

Standards for key-agnostic verification:
- [ERC-1271](https://eips.ethereum.org/EIPS/eip-1271): contract signatures.
- [ERC-7913](https://eips.ethereum.org/EIPS/eip-7913): **Final**; `verify(key, hash, signature)` on verifier contracts for address-less keys.
- OpenZeppelin `SignatureChecker` has an ERC-7913 overload ([source](https://github.com/OpenZeppelin/openzeppelin-contracts/blob/master/contracts/utils/cryptography/SignatureChecker.sol)).
- Kohaku already uses OpenZeppelin's `ERC7913P256Verifier`, and ZKNox verifiers follow the same "logic contract" model.

### 3.2 ECDSA for operator and committee attestations

| System | Today | PQ status found |
|---|---|---|
| Wormhole core (`0x98f3c9e6E3fAce36bAAd05FE09d375Ef1464288B`) | Guardian quorum of secp256k1 signatures checked with `ecrecover` in `Messages.sol` ([source](https://github.com/wormhole-foundation/wormhole/blob/main/ethereum/contracts/Messages.sol)) | **No PQ plan found.** Searched "Wormhole guardian signatures post-quantum migration plan". Guardian-set rotation via governance VAA is the upgrade lever [INFERENCE]. |
| Pyth (EVM) | Price updates arrive as "WormholeMerkle", so they inherit Wormhole guardian ECDSA ([Pyth.sol](https://github.com/pyth-network/pyth-crosschain/blob/main/target_chains/ethereum/contracts/contracts/pyth/Pyth.sol)) | Inherits Wormhole's status. |
| Chainlink OCR2 aggregators | `ecrecover` per oracle signature in `transmit` ([OCR2Aggregator.sol](https://github.com/smartcontractkit/libocr/blob/master/contract2/OCR2Aggregator.sol)) | **No official PQ plan found.** A third-party scorer says OCR signing is "exclusively classical ECDSA/EdDSA" ([qrindex](https://qrindex.org/projects/chainlink)) [UNVERIFIED third party]. |
| RedStone | `ecrecover` in `SignatureLib` ([source](https://github.com/redstone-finance/redstone-oracles-monorepo/blob/main/packages/evm-connector/contracts/libs/SignatureLib.sol)) | Not found. |
| Multisig bridges, sequencer/relayer keys, CEX hot wallets | EOA or Safe ECDSA keys | The EF ranks "high-value operational keys" (exchanges, bridges, custody) second and governance/upgrade multisigs third among priority risks ([pq.ethereum.org](https://pq.ethereum.org/)). |

PQ options for committees:
- Per-signer hash-based signatures (SPHINCS-: ≈100–200k gas each, so a 13-of-19 quorum costs ≈1.3–2.6M) [INFERENCE from per-sig cost].
- Off-chain aggregation of hash-based signatures into one STARK, the leanMultisig approach, verified on L1 at roughly STARK cost (§3.4).
- Native in-mempool aggregation via EIP-8288 (Draft).

### 3.3 `ecrecover` tricks: VRF and Schnorr

| Use | Detail | Source |
|---|---|---|
| Chainlink VRF v2/v2.5 | `VRF.sol` "abuses ECRECOVER" for secp256k1 scalar multiplication (ECVRF over secp256k1) | [VRF.sol @ v2.10.0](https://github.com/smartcontractkit/chainlink/blob/v2.10.0/contracts/src/v0.8/vrf/VRF.sol) |
| Chronicle Scribe oracle | Aggregated Schnorr over secp256k1, verified with one `ecrecover` | [Schnorr.md](https://github.com/chronicleprotocol/scribe/blob/main/docs/Schnorr.md) |
| Blockstream ecrecover-schnorr-verifier | Same trick | [repo](https://github.com/BlockstreamResearch/ecrecover-schnorr-verifier) |

PQ replacements and caveats:
- **No PQ VRF with an EVM verifier was found.** Searched "Chainlink post-quantum", plus the VRF trick searches.
- Options: hash-based commit-reveal or threshold randomness proven in a STARK, or the beacon chain's RANDAO (EIP-8321, hash-chain RANDAO, tier B) [INFERENCE].
- These tricks would **also break under EIP-8151 if the recovered "address" has code**. That is negligible here, since the "addresses" are pseudo-random points [INFERENCE].

### 3.4 BN254 SNARK verification (ecadd / ecmul / ecpairing)

Users:
- **Rollups:** zkSync, Linea, Scroll, Polygon zkEVM.
- **Privacy:** Tornado, Railgun, Aztec.
- **Identity:** Semaphore / World ID (Groth16 on BN254, per a [third-party scorer](https://qrindex.org/projects/worldcoin-wld) [UNVERIFIED]).
- **zkVM verifiers:** RISC Zero's STARK provers are rated quantum-safe but its "STARK-to-SNARK" Groth16/BN254 wrapper is "vulnerable to attacks from quantum computers" ([RISC Zero security model](https://dev.risczero.com/api/security-model)). SP1's on-chain verifier is likewise Groth16 / PLONK ([sp1-verifier](https://docs.rs/crate/sp1-verifier/latest)).
- **Restaking:** EigenLayer `BLSSignatureChecker` uses BN254 pairing ([source](https://github.com/Layr-Labs/eigenlayer-middleware/blob/dev/src/BLSSignatureChecker.sol)).

PQ replacements:

| Option | On-chain cost | Maturity |
|---|---|---|
| Groth16 / fflonk (status quo, for comparison) | ≈300k | Production; quantum-vulnerable |
| Direct STARK/FRI verification (Starknet SHARP, Cairo verifier) | Multi-million gas; proof splitting required ([zkSecurity](https://blog.zksecurity.xyz/posts/stark-evm-adapter/)) | Production on mainnet (Starknet) |
| WHIR PCS verifier | 1.09–1.49M at 2¹⁶–2²² variables with aggressive parameters ([ethresear.ch 2024](https://ethresear.ch/t/on-the-gas-efficiency-of-the-whir-polynomial-commitment-scheme/21301)); **5.65M** at provable 100-bit Johnson-bound soundness over KoalaBear, 4.33M with proposed extension-field precompiles ([ethresear.ch 2026](https://ethresear.ch/t/evm-verification-of-whir-over-a-31-bit-field/24902)) | Research |
| Native aggregation (EIP-8288 frame mode, leanVM recursive STARK) | Amortized; ≈3,000 gas per signature at the frame level per the SPHINCS- post | Draft |
| Lattice SNARKs | **No EVM verifier found.** Searched "lattice SNARK EVM verifier". | — |

The EF notes STARKs "are already quantum-resistant", and that for zk-rollups "the proof system itself" must be upgraded ([ethereum.org](https://ethereum.org/roadmap/security/quantum-resistance/), [pq.ethereum.org](https://pq.ethereum.org/)).

### 3.5 KZG point evaluation (0x0a) and BLS12-381 (EIP-2537)

**KZG (0x0a):** used by blob rollups to open blob commitments, 50k gas each.
- PQ path: replace KZG with hash-based (STARK/FRI) or lattice commitments.
- EF milestones: "PQ blobs" at M\*, "leanDA sampling" at J\*.
- The EF tier list declined EIP-8142 because it "deepens dependence on KZG structures against the path to J\*".
- Sources: [ethereum.org](https://ethereum.org/roadmap/security/quantum-resistance/), [pq.ethereum.org](https://pq.ethereum.org/), [EF tier list](https://blog.ethereum.org/en/2026/09/07/protocol-hegota-eips), [EF priorities](https://blog.ethereum.org/en/2026/09/07/protocol-priorities).
- Contracts verifying 0x0a proofs will need a new commitment-opening verifier and new blob versioned-hash semantics [INFERENCE].

**BLS12-381 (EIP-2537):** used for beacon-chain BLS signature checks, DVT and restaking.
- PQ path: hash-based signatures (leanXMSS) plus SNARK/STARK aggregation (leanMultisig/leanVM), at roughly "≈3,000 bytes vs 96 bytes" per signature, compressed "250x" via leanVM ([ethereum.org](https://ethereum.org/roadmap/security/quantum-resistance/)).
- **No EVM verifier for leanXMSS or leanMultisig aggregates was found.**

### 3.6 P-256 / WebAuthn (passkeys)

Users:
- Coinbase Smart Wallet owners can be "passkey (Secp256r1) public key owners" ([README](https://github.com/coinbase/smart-wallet)).
- Daimo, Clave and others use the 0x100 precompile or Solidity P256 verifiers.
- EIP-8141 enshrines P256 (scheme 0x2).

PQ WebAuthn status:
- IETF draft "ML-DSA for Web Authentication" is at -05 ([datatracker](https://datatracker.ietf.org/doc/draft-vitap-ml-dsa-webauthn/05)).
- 1Password shipped ML-DSA passkeys (v8.12.44, Oct 2026). It cites COSE ML-DSA encoding as RFC 9964 (May 2026) [RFC number UNVERIFIED], and says FIDO/W3C work on upgrading existing passkeys is ongoing ([blog](https://1password.com/blog/post-quantum-passkeys)).
- SimpleWebAuthn documents ML-DSA support ([docs](https://simplewebauthn.dev/docs/advanced/server/pqc-ml-dsa-support)).

On-chain implication: verifying an ML-DSA passkey costs ≈1.2M gas (Fireblocks) without a precompile, and EIP-8355 was declined [INFERENCE: no cheap path in Hegotá].

### 3.7 RSA via modexp (0x05)

Users:
- **zkEmail:** DKIM RSA, verified inside Groth16 circuits ([zk-email-verify](https://github.com/zkemail/zk-email-verify), [docs](https://docs.zk.email/zk-email-verifier)).
- **Passports:** ICAO eMRTD passive authentication.
- **Aadhaar:** Anon Aadhaar ([repo](https://github.com/anon-aadhaar/anon-aadhaar); RSA detail [UNVERIFIED in fetched text]).
- **JWT/OIDC:** zkEmail jwt-tx-builder ([docs](https://docs.zk.email/jwt-tx-builder/packages)).

These are **doubly exposed**: the off-chain issuer's RSA key, and the BN254 SNARK wrapping it [INFERENCE]. The replacement depends on the issuers:
- DKIM: **no PQ DKIM deployment found**. Searched "zk-email DKIM RSA-2048 post-quantum".
- ICAO: "in the process of specifying PQC for inclusion into Doc 9303"; options under study are dual, hybrid-linked or PQ-only PKI ([ICAO slides, May 2026](https://id4africa.com/2026/files/PS3-S2-1-ICAO-FINAL.pdf)).
- Aadhaar and Google/Apple OIDC: no PQ signing plans found.

Once issuers move, on-chain verification of ML-DSA or SLH-DSA would be needed: in-EVM ≈0.1–1.2M gas, or inside a STARK.

---

## 4. Quantum-vulnerable design patterns

1. **ecrecover tried before ERC-1271, or signer-selected scheme.** A migrated account with an exposed ECDSA key stays forgeable.
   - OpenZeppelin `SignatureChecker.isValidSignatureNow` in **v4.x through v5.0.x** did `tryRecover` first and fell back to ERC-1271 ([v4.9.6](https://github.com/OpenZeppelin/openzeppelin-contracts/blob/v4.9.6/contracts/utils/cryptography/SignatureChecker.sol), [v5.0.0](https://github.com/OpenZeppelin/openzeppelin-contracts/blob/v5.0.0/contracts/utils/cryptography/SignatureChecker.sol)).
   - **v5.1.0 onward** branches on `signer.code.length == 0` and never ecrecovers for code-bearing signers ([v5.1.0](https://github.com/OpenZeppelin/openzeppelin-contracts/blob/v5.1.0/contracts/utils/cryptography/SignatureChecker.sol)).
   - Contracts compiled against ≤5.0 remain vulnerable forever if immutable. The data team can split them by OZ version or bytecode.
   - Seaport (ecrecover first), CoW GPv2 and 0x (scheme chosen by signer) have the same property (§3.1).
   - Safer patterns that branch on code first: Solady `SignatureCheckerLib` (`extcodesize` check first, [source](https://github.com/Vectorized/solady/blob/main/src/utils/SignatureCheckerLib.sol)), Permit2, and USDC's checker.
2. **ECDSA-only permits in immutable tokens.**
   - DAI (`0x6B175474E89094C44Da98b954EedeAC495271d0F`) has the DAI-style `permit` (selector `0x8fcbaf0c`, present in its runtime).
   - UNI (`0x1f9840a85d5aF5bf1D1762F925BDADdC4201F984`) has EIP-2612 `permit` (`0xd505accf`).
   - Any OpenZeppelin `ERC20Permit` token uses `ECDSA.recover` only.
   - None can adopt ERC-1271. EIP-8151's motivation names exactly this case ([EIP-8151](https://eips.ethereum.org/EIPS/eip-8151)).
   - Selectors were confirmed in the mainnet runtimes via RPC.
3. **"Code-length gate" is not enough under EIP-7702.** A 7702-delegated EOA has 23-byte code, so code-first checkers route to ERC-1271. But the ECDSA key can still re-delegate or send transactions, and EIP-8151 intentionally still lets ecrecover succeed for delegation-indicator accounts. Full exit requires EIP-8298 or 8141-style real code [EIP-8151/8298 specs].
4. **Hard-coded gas for ecrecover.** `staticcall(3000, 1, …)` will out-of-gas on every valid signature after EIP-8151, which raises the cost to 3,200–6,100 ([EIP-8151 Backwards Compatibility](https://eips.ethereum.org/EIPS/eip-8151)). The data team can detect `PUSH2 0x0bb8` gas preceding a call to address `0x01` [INFERENCE heuristic].
5. **Pure-Solidity secp256k1 / ECDSA** implementations bypass EIP-8151 entirely (spec Security Considerations).
6. **Hybrid PQ wallets that keep an ECDSA ERC-1271 path.** Anchor v1 Lamport wallets expose ECDSA `isValidSignature`, so dApps accepting ERC-1271 from them accept a quantum-forgeable signature ([wallet_cli](https://github.com/Pauli-Group/wallet_cli)). Kohaku pq-account instead requires *both* ECDSA and PQ, which is safe as long as both are checked ([Kohaku README](https://github.com/ethereum/kohaku/tree/master/packages/pq-account)).
7. **ecrecover as an EC-math gadget** (Chainlink VRF, Chronicle Scribe Schnorr): the cryptography itself is Shor-breakable, and no drop-in PQ replacement exists (§3.3).
8. **Long-lived committee keys** (bridges, oracles, admin multisigs) concentrate value behind exposed public keys. The EF ranks these right after user EOAs ([pq.ethereum.org](https://pq.ethereum.org/)).
