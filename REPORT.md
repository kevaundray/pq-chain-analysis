# Pre-quantum cryptography in Ethereum mainnet contracts

*Snapshot of contract state at block ≈26.33M (2026-11-03). Usage window ("the year"): blocks 22,100,000–24,699,999 (2025-03-22 → 2026-03-18), the most recent full year of the precompile trace corpus.*

**Question.** Suppose user accounts become post-quantum (PQ), for example via EIP-8141 frame transactions with PQ verification. How much of what users rely on still sits on contracts that verify pre-quantum cryptography? How many such contracts are there, can they change, do they have an alternative path, and how much value moves through them?

---

## TL;DR

- **Activity.** In one year, **787k addresses** made **32.2M transactions** (≈5.2% of the ≈613M mainnet transactions) that invoked pre-quantum signature or curve operations inside the EVM. That excludes the transaction signature itself. The 787k are ≈277k real contracts plus 510k EIP-7702-delegated EOAs. Those transactions moved roughly **$1.3T**, measured as the largest transfer per transaction.
- **ecrecover dominates.** It covers 678k of the 787k addresses, 30.8M transactions and essentially all the value. Other elliptic-curve use is small in count (≈111k addresses, mostly passkey wallets) but secures rollups and bridges. RSA is negligible.
- **Lattice is almost absent.** Six lattice verifiers exist on mainnet (ZKNox Falcon/ETHFALCON/EPERVIER, three ML-DSA). Together they have about 13 calls and dust balances.
- **Most ecrecover callers are accounts, not applications.** 75% are EIP-7702-delegated EOAs, 18% are contract wallets, and **≈41k (6%) are applications**. Those applications carry most of the activity: 28.2M of the 30.8M transactions and ≈$1.07T of the value.
- **I curated the 346 largest applications by reading their source.** They cover 86% of application transactions, 91% of application value and 99.5% of value held.
  - **Only 34 offer a real alternative path** to the pre-quantum check (ERC-1271, a signer-selected scheme, or pre-sign). Those 34 carry 11.2M transactions and $484B.
  - **117 can only rotate keys** while the scheme stays ECDSA: market-maker quote signers, bridges, oracles, paymasters. They carry 13.9M transactions and $511B.
  - **96 depend on it exclusively** ("sole"). They carry 3.6M transactions, $131B, and $28.5B currently held.
  - **99 have a verifier the consumer can repoint** (89 SNARK verifiers, 2 KZG, plus a few bridge, order and RSA verifiers).
- **Immutability, in the curated set:**
  - 160 contracts are fully immutable (11.6M transactions, $459B).
  - 98 have immutable code with configurable keys or verifiers ($472B).
  - 88 sit behind an admin-upgradeable proxy ($168B, $18.8B held).
  - 43 are **both immutable and sole**: $104B per year and $15.6B held. Almost all the held funds are in 14 ECDSA-only `permit` tokens (wstETH, DAI, USDe…); most of the value moved ($73B) goes through 4 trading contracts (UniswapX cosigner, KyberSwap RFQ, Clipper, AirSwap).
- **Who signs matters more than whether the user is PQ:**
  - **End-user signatures:** 63 contracts, $457B, $32B held. These need ERC-1271 or ERC-7913 support so PQ accounts can sign, plus EIP-8151 so that migrated EOAs' old keys stop working.
  - **Single operator keys:** 88 contracts, $385B (RFQ quotes, cosigners, paymasters, vouchers).
  - **Committees:** 54 contracts, $159B (bridges, oracles).
  - **Proofs:** 119 contracts, SNARK/KZG/BLS. They secure ≈$3.0B of SNARK-verified rollup value and ≈$15.3B of optimistic rollups that settle disputes with ZK proofs.
- **Token supply behind ECDSA-only `permit`:** ≈$34B (wstETH, DAI, USDe, weETH, aWETH, GHO, …), of which $22B is in immutable contracts. A further ≈$107B (USDC, stETH, USDS, sUSDS) has an ERC-1271 path, with caveats.

---

## 1. Method in one paragraph

A contract counts as relying on pre-quantum logic if, as the **execution context**, it made a *successful* call to one of the following, observed in a geth `callTracer` trace of every mainnet transaction:
- an EC precompile: `ecrecover` 0x01, BN254 0x06–0x08, KZG 0x0a, BLS12-381 0x0b–0x11, P-256 0x100;
- or `modexp` 0x05 with an elliptic-curve field/order modulus or an RSA-size (≥1024-bit) modulus.

"Execution context" means the proxy address for proxies, and the EOA for 7702 delegations. The corpus is [precompile-usage](https://github.com/CPerezz/precompile-tracer), blocks 2.4M–24.7M.

**Lattice detection** is static: I fingerprinted 2.48M unique runtime bytecodes deployed since block 18M (Xatu `canonical_execution_contracts`), looking for Falcon/ML-DSA NTT tables and moduli.

**Current state** (code, proxy slots, ETH, ERC-20 balances) comes from mainnet RPC (`eth_call` with state overrides) and Blockscout.

**Value**, unless stated otherwise:
- `tx value` is the sum, over distinct transactions, of the **largest single ERC-20/ETH transfer in each transaction**. It comes from a systematic 1-in-10 block sample of Xatu transfer tables, priced with DefiLlama; 99.2% of transfers were priced.
- `held` is ETH plus the first 50 ERC-20s currently held by the contract.

Each code family (contracts sharing logic) was classified by rules: 7702 / contract-wallet / application; immutable / upgradeable. The 433 largest contracts were then classified by reading verified source (Sourcify, Blockscout) or bytecode: 346 applications and 87 wallets. Section 9 has the caveats.

---

## 2. How many contracts, by category

| Category | What it is | Contracts ever | Active in year | Tx in year | Tx value in year | Held now |
|---|---|---:|---:|---:|---:|---:|
| **1. ecrecover** | secp256k1 ECDSA recovery (0x01) | 1,463,133 | 678,009 | 30,792,126 | $1,300.6B | $45.1B |
| **2. EC precompiles** | | | | | | |
| BN254 (ecadd/ecmul/ecpairing) | Groth16/PLONK/fflonk verifiers, BN254-BLS | 898 | 416 | 883,578 | $2.34B | $0.11B |
| KZG point evaluation | blob openings (BLS12-381 KZG) | 28 | 24 | 359,716 | ≈$0 | $1.10B |
| BLS12-381 (EIP-2537) | BLS signatures | 17 | 17 | 125 | ≈$0 | ≈$0 |
| P-256 (0x100, since Fusaka) | passkeys / WebAuthn | 24,505 | 24,505 | 95,452 | $0.12B | ≈$0 |
| **3. EC in software (via modexp)** | | | | | | |
| P-256 | pre-Fusaka passkey verifiers (FCL/Daimo/Solady) | 126,036 | 95,012 | 373,541 | $0.98B | ≈$0 |
| BN254 field inversions | SNARK verifiers | 321 | 142 | 593,845 | $0.02B | ≈$0 |
| secp256k1 | software secp256k1 | 6 | 5 | 14,547 | ≈$0 | ≈$0 |
| ed25519 | | 3 | 0 | 0 | – | – |
| BLS12-381 | | 3 | 3 | 7 | – | – |
| **4. RSA (modexp ≥1024-bit)** | DKIM / identity / Keyring | 34 | 18 | 1,071 | ≈$0 | ≈$0 |
| **Any pre-quantum** | | **1,603,560** | **787,419** | **32,178,616** | **$1,303.6B** | **$46.3B** |
| *5. Lattice* | Falcon / ML-DSA verifiers (static scan) | *6* | *≈13 calls* | – | – | *dust* |

**Notes**
- **Not counted:** 103 contracts use the STARK prime field (2²⁵¹+17·2¹⁹²+1) in `modexp`. These are StarkWare verifiers, which are hash-based (FRI), so not pre-quantum.
- **Static lower bound for ECDSA in code:** 44,085 unique bytecodes (52,817 contracts) deployed since Aug 2023 embed the secp256k1 `n/2` malleability constant used by the OZ/Solady ECDSA libraries. The equivalent counts are 3,803 contracts for BN254, 230 for P-256 and 220 for BLS12-381.
- **Hard-coded `staticcall(3000, 0x01, …)`:** the exact pattern appears in only 3 unique codes since block 18M. EIP-8151 would break it.

### Lattice (and other PQ) on mainnet

| Address | Scheme | Deployed | Use |
|---|---|---|---|
| `0xe758…3f55` ZKNOX_ethfalcon | Falcon (keccak variant) | block 24,670,293 | 5 static calls from one contract (`0x23da…`) |
| `0xa964…5994` ZKNOX_ethepervier | Falcon (EPERVIER, key-recovery variant) | 24,670,269 | none |
| `0x4c09…fe4c` (same deployer) | Falcon | 24,670,293 | none |
| `0x4c1e…2278` MLDSA44Verifier | ML-DSA-44 | 26,266,136 | 2 wallet calls (1167 clones) |
| `0xc263…13e7` | ML-DSA | 26,174,776 | ≈5 calls from `BunkerVault` |
| `0x6c6e…8145` | ML-DSA | 26,107,269 | none |

- **Hash-based:** the only mainnet PQ wallets found are 7 Anchor Lamport wallets from 2022, which still accept ECDSA via ERC-1271 (research notes §1.2).
- **Detection rule:** confirmed contracts carry the twiddle-table words or zeta tables. Small-constant matches (q = 12289 or 8380417 alone) were false positives: `VaultMarketHub`, `FarmStrategy`, `HeraldiaS5Engine`.

---

## 3. Accounts vs applications

Of the addresses active in the year, by role:

| Category | Active | 7702-delegated EOAs | Contract wallets | Applications | …immutable | …upgradeable proxy | …unresolved proxy |
|---|---:|---:|---:|---:|---:|---:|---:|
| ecrecover | 678,009 | 510,639 | 122,740 | 41,121 | 18,671 | 2,853 | 19,597 |
| BN254 | 416 | 1 | 1 | 394 | 330 | 64 | 0 |
| KZG | 24 | 0 | 0 | 23 | 15 | 8 | 0 |
| BLS12-381 | 17 | 0 | 0 | 17 | 16 | 1 | 0 |
| P-256 precompile | 24,505 | 87 | 24,392 | 24 | 24 | 0 | 0 |
| P-256 software | 95,012 | 0 | 94,191 | 820 | 12 | 1 | 807 |
| RSA | 18 | 0 | 3 | 15 | 13 | 2 | 0 |

How these were classified:
- **Contract wallets:** Safe, BitGo WalletSimple, ERC-4337 accounts (Coinbase Smart Wallet, Kernel, LightAccount…), Infinex diamonds, Dapper/Blocto/Ambire. They were identified by Safe/4337 selectors and Blockscout names.
- **Mutability is per code family:** an EIP-1967, beacon, 1822 or ZeppelinOS slot, or a diamond, counts as upgradeable. "Unresolved" means a small `DELEGATECALL` forwarder whose target sits in a non-standard slot, mostly deposit/forwarder proxies.

Value by role (ecrecover only; groups overlap at the transaction level):

| Role | Mutability | Contracts | Tx in year | Tx value | Held now* |
|---|---|---:|---:|---:|---:|
| application | immutable | 18,671 | 22.5M | $889B | $15.9B |
| application | upgradeable | 2,853 | 6.6M | $182B | $17.7B |
| application | unresolved proxy | 19,597 | 0.24M | $4.8B | ≈$0 |
| contract wallet | owner-controlled (Safe, UUPS wallets) | 100,885 | 1.02M | $201B | $9.3B |
| contract wallet | immutable (e.g. BitGo WalletSimple clones) | 21,854 | 1.27M | $101B | $1.8B |
| 7702 EOA | re-delegatable by the ECDSA key | 510,639 | 2.05M | $17.6B | $0.18B |

\*ERC-20 holdings were fetched only for the ≈3.9k addresses that matter most by usage or ETH balance. ETH is complete: contract wallets on this list hold 1.24M ETH (≈$2.9B) and 7702 EOAs hold 63k ETH.

---

## 4. Curated applications: function, reliance, immutability

The 346 applications cover 86% of application transactions and 91% of application tx value. Each was read at the source or bytecode level for:
- what the check is *for*;
- who holds the key;
- whether a non-pre-quantum path exists;
- whether the code can change.

The output, with an evidence string per contract, is in `data/report/curated_contracts.csv`. Confidence: 209 high, 75 medium, 62 low (mostly unverified market-maker or executor contracts).

### By function

| Function | Contracts | Tx in year | Tx value | Held now |
|---|---:|---:|---:|---:|
| Operator-signed RFQ quote / cosigner | 42 | 6.54M | $372.7B | $0.08B |
| User-signed intent / order (CoW, 1inch, Seaport, UniswapX orders…) | 20 | 5.93M | $368.8B | $0.13B |
| User `permit` / Permit2 / EIP-3009 | 36 | 5.11M | $122.0B | $31.8B |
| Oracle / keeper report signatures (Chainlink Automation & OCR, RedStone) | 7 | 0.53M | $96.3B | ≈$0 |
| Bridge / committee attestation (CCTP, Wormhole, LayerZero DVNs, CCIP, Peggy, Polygon PoS…) | 41 | 4.67M | $64.4B | $1.39B |
| Unidentified executors / other | 17 | 1.67M | $13.5B | ≈$0 |
| Paymaster / sponsor signer | 9 | 1.52M | $4.5B | ≈$0 |
| SNARK proof verification | 111 | 0.78M | $2.3B | $0.11B |
| Sequencer / relayer signature | 9 | 0.50M | $2.0B | ≈$0 |
| Operator-signed claim / mint / voucher | 21 | 1.31M | $1.7B | $0.03B |
| Blob KZG opening | 11 | 0.24M | ≈$0 | $1.10B |
| BLS aggregate signature (EigenDA, Aztec, Aligned…) | 10 | 0.10M | ≈$0 | ≈$0 |
| Passkey / WebAuthn verifier | 3 | 18k | ≈$0 | – |
| VRF / randomness | 3 | 14k | ≈$0 | ≈$0 |
| RSA (Keyring) | 1 | 383 | ≈$0 | – |

On how to read these values:
- **Bridge attestation** usually happens in a different transaction from the value transfer, so its tx value understates what it secures.
- **"Held" for permit tokens** is the underlying asset held by the token contract, e.g. stETH inside wstETH. The permit feature itself is auxiliary to the token.

### Reliance × who can change it

| Reliance | Immutable | Immutable code, configurable keys/verifier | Upgradeable proxy |
|---|---|---|---|
| **sole** (no alternative path) | **43 contracts · 1.64M tx · $104B · $15.6B held** | 8 · 0.25M · $11.6B | 45 · 1.74M · $16.1B · $12.9B held |
| **key rotation only** (scheme fixed) | 6 · 1.13M · $57.6B | 78 · 9.57M · $391B | 33 · 3.70M · $109B · $1.4B held |
| **alternative exists** (1271 / scheme choice / pre-sign) | 20 · 9.32M · $344B | 8 · 0.87M · $105B | 6 · 1.09M · $45.2B · $4.5B held |
| **configurable verifier** (consumer can repoint) | 91 · 0.59M · $0.5B | 4 · 31k · $1.2B | 4 · 36k · ≈$0 |

**Immutable, sole, and core to the contract's purpose (29 contracts).** These cannot be fixed in place:
- the UniswapX V2 reactor (cosigner checked with raw `ecrecover`);
- KyberSwap RFQ (`tryRecover` must succeed before ERC-1271 is tried, so PQ-length signatures fail);
- Clipper, AirSwap, Aztec L1 rollup/slashing and its epoch-proof verifier;
- Tornado Cash ETH pools, 0xbow Privacy Pools, FOOM;
- the Daimo/Solady P-256 fallback verifiers;
- the Infinex meta-tx forwarder;
- several unverified executors.

The other 14 immutable-sole contracts are auxiliary features, mostly ECDSA-only `permit` on tokens and vaults: wstETH, DAI, USDe, sUSDe, GHO, osETH, MetaMorpho vaults, Morpho Blue.

### How user signatures are checked (ecrecover users)

| Order | Contracts | Tx in year | Tx value | Held | Meaning for PQ users |
|---|---:|---:|---:|---:|---|
| `ecrecover` only | 165 | 16.5M | $569B | $28.7B | A new PQ account cannot use the feature. A migrated EOA's old key still works. |
| Signer selects scheme (CoW, 1inch, Bebop, Angstrom, Tokenlon RFQ, Safe-style) | 11 | 3.58M | $308B | $0.13B | PQ accounts can use ERC-1271 or pre-sign. An attacker holding the old ECDSA key simply picks the ECDSA scheme. |
| `ecrecover` first, then ERC-1271 (Seaport 1.6, USDS/sUSDS, Pendle, Tokenlon PMM, KyberSwap DSLO, AirSwap, ParaSwap RFQ) | 12 | 2.79M | $160B | $4.6B | PQ accounts work via the fallback. The old key still works for the same address. |
| Account code checked first (Permit2, USDC, stETH, Relay, TokenTable, Velora) | 10 | 4.95M | $86B | ≈$0 | Safe once the account has code. Exceptions: stETH and the Curve stableswap-ng LP pass only 65 bytes (r, s, v) to ERC-1271, which a PQ signature cannot fit. |

### Token supply behind `permit`

| Token | Market cap | Permit path | Code |
|---|---:|---|---|
| USDC | $70.8B | code check first → ERC-1271; EIP-3009 likewise | upgradeable |
| stETH | $22.2B | code first, but ERC-1271 receives only 65 bytes | upgradeable |
| wstETH | $10.7B | ecrecover only | immutable |
| USDS / sUSDS | $9.6B / $4.5B | ecrecover first, then ERC-1271 | upgradeable |
| aWETH (+ other Aave v3 aTokens) | $5.4B | ecrecover only | upgradeable |
| weETH | $5.1B | ecrecover only | upgradeable |
| DAI | $4.5B | ecrecover only (DAI-style permit) | immutable |
| USDe / sUSDe | $4.5B / $1.1B | ecrecover only | immutable |
| GHO, bUSD0, osETH, Liquid ETH, eETH, sENA, … | ≈$2.3B | ecrecover only | mixed |

ECDSA-only permit totals ≈$34B, ≈$22B of it immutable. Wrappers overlap with their underlying (wstETH/stETH, weETH/eETH). Beyond the curated tokens, **10,960 contracts with a `permit` selector called ecrecover during the year.**

### Top applications by tx value

| Contract | Function | Who signs | Reliance / code | Tx in year | Tx value |
|---|---|---|---|---:|---:|
| 1inch LOP v4 / Router v6 | intent orders | user | alternative (scheme choice) / immutable | 1.24M | $207B |
| KyberSwap executor `0x6324…` *(low confidence)* | quote signature | operator | key rotation / configurable | 1.09M | $195B |
| Native RFQ (`0xa540…`, `0x5d1a…`) | quote signature | operator | key rotation / configurable | 0.46M | $112B |
| Chainlink Automation v2.1 | report signatures | committee | key rotation / configurable | 63k | $96B |
| Unknown PMM `0xbee3…` *(low)* | quote signature | operator | key rotation / upgradeable | 1.41M | $69B |
| KyberSwap RFQ | quote signature | user/maker | **sole** / immutable | 139k | $61B |
| CoW Protocol GPv2 | intent orders | user | alternative / immutable | 1.30M | $55B |
| OKX market maker `0x51c7…` *(low)* | quote signature | operator | key rotation / immutable | 552k | $54B |
| Permit2 | permits | user | alternative (code first) / immutable | 3.84M | $50B |
| KyberSwap Limit Order | orders | mixed | alternative (ecrecover first) | 23k | $50B |
| KyberSwap KEM hook | quote signature | operator | alternative / configurable | 74k | $37B |
| USDC | permit / 3009 | user | alternative (code first) / upgradeable | 921k | $30B |
| Circle CCTP V2 / V1 | attester signatures | committee | key rotation | 249k / 262k | $28B / $22B |
| Wormhole Core | guardian quorum (19 secp256k1) | committee | key rotation / upgradeable | 1.03M | $4.4B |

Largest holdings where the crypto is *core*:
- **KZG + SNARK:** zkLighter $1.05B, Linea $46M (upgradeable).
- **Committees:** Injective Peggy $0.70B, Polygon PoS StakeManager $0.37B, Aster vault $0.16B, NEAR Omni $61M, Circle Gateway $58M, Gnosis xDAI bridge $48M.
- **SNARK:** Railgun $0.11B.

### Rollups whose L1 contracts verify pre-quantum proofs

L2BEAT summary (via [ethbeat.org](https://ethbeat.org/api/scaling/summary)), 2026-11-03, grouped by state validation. "Canonical" means escrowed on L1.

| State validation | TVS | Canonical (L1 escrow) | Proof crypto on L1 |
|---|---:|---:|---|
| Validity proofs, SNARK (`SN`) | $1.39B | $1.17B | BN254 (Groth16/PLONK/fflonk) |
| Validity proofs, STARK wrapped in SNARK (`ST, SN`) | $1.62B | $0.81B | BN254 wrapper |
| Validity proofs, STARK only (`ST`, e.g. Starknet) | $0.37B | $0.27B | FRI (hash-based); blobs via KZG |
| Fraud proofs, single-round ZK (`1R, ZK`, e.g. Base) | $15.26B | $2.80B | ZK proof in disputes. **[INFERENCE]** SP1/RISC Zero Groth16 on BN254 |
| Fraud proofs, interactive (`INT`) | $14.61B | $5.51B | no EC in the proof path |

All blob-posting rollups also depend on KZG commitments at the protocol level. Every rollup's upgrade keys are ECDSA multisigs.

---

## 5. What these contracts want, and PQ replacements

| What the contract needs | Today | PQ replacement | Cost / maturity | Who can migrate |
|---|---|---|---|---|
| **User authorizes offline**: permit, signed order, meta-tx | `ecrecover` of the EOA | Verify through the account: [ERC-1271](https://eips.ethereum.org/EIPS/eip-1271) (account code decides) or [ERC-7913](https://eips.ethereum.org/EIPS/eip-7913) `verify(key, hash, sig)` against a PQ verifier. Remove ECDSA-first ordering. For immutable legacy code, [EIP-8151](https://eips.ethereum.org/EIPS/eip-8151) makes `ecrecover` return empty for accounts with real code. Frame transactions' atomic batching removes much of the need for `permit` **[INFERENCE]**. | In-EVM verification: Falcon-512 ≈0.45–3.9M gas, ML-DSA-44 ≈1.2M (+4.1M one-off key registration), SPHINCS-variants ≈40–200k execution (≈180–390k as a transaction). Precompiles are drafts only (EIP-8051/8052 ≈3–4.5k gas; EIP-8355 declined for Hegotá). | Protocol, for routers/settlement contracts. Users route around immutable ECDSA-only paths. |
| **Operator authorizes execution**: RFQ quote, cosigner, voucher, paymaster | Single ECDSA key | Replace the inner check with a PQ verifier or an ERC-1271 signer contract (many maker contracts are already 1271 wrappers). Signatures grow from 65 B to ≈666 B (Falcon-512), 2,420 B (ML-DSA-44) or ≈8–17 KB (SLH-DSA). | Same verifier costs, paid on every fill | Operator. The 78 "configurable" contracts can swap the signer but not the scheme without new code. |
| **Committee attests to an external fact**: bridges, oracles, DVNs | m-of-n secp256k1 | Per-signer hash-based signatures (≈1.3–2.6M gas for a 13-of-19 quorum **[INFERENCE]**), or aggregate off-chain into one STARK (leanMultisig-style). ZK light clients with STARK verification. | No production PQ committee found | Governance upgrade, or app-level verifier choice (LayerZero DVN set, Hyperlane ISM) |
| **Verify a SNARK** (rollups, zkVMs, privacy, identity) | BN254 pairing | STARK/FRI verifier on L1 (Starknet SHARP in production), WHIR, or recursive aggregation into a PQ proof | ≈1.1–5.6M gas vs ≈300k for Groth16 | Consumer repoints the verifier (89 of 111 curated verifiers are swappable) |
| **Aggregate signatures** (BLS on BN254 / BLS12-381) | pairing | Hash-based signatures (leanSig/XMSS) aggregated in a SNARK/STARK (leanMultisig) | No EVM verifier yet | Protocol team |
| **Open blob commitments** | KZG (0x0a) | Protocol PQ data availability (EF roadmap "PQ blobs" at M\*, leanDA); rollup contracts adopt the new opening verifier | Roadmap | L1 protocol, then rollups |
| **Randomness / Schnorr** via the ecrecover trick | secp256k1 algebra | No PQ VRF EVM verifier found; commit-reveal or threshold randomness proven in a STARK; RANDAO | – | Protocol |
| **Passkeys** | P-256 (0x100 / FCL) | ML-DSA WebAuthn (IETF draft; 1Password shipped ML-DSA passkeys) | ≈1.2M gas without a precompile | Wallet vendor (Coinbase Smart Wallet, Infinex: upgradeable by owner) |
| **RSA identity** (DKIM, JWT, passports) | RSA via modexp | Issuer-side PQ first (no PQ DKIM; ICAO still specifying); then ML-DSA/SLH-DSA verification on-chain or inside a STARK | – | Off-chain issuers |
| **Account owners** (Safe, BitGo, 7702) | EOA owners | Safe: replace EOA owners with ERC-1271 PQ signer contracts. BitGo WalletSimple: immutable, signers fixed, so funds must move. 7702: convert to real code (EIP-8298 / 8141). | – | Owners |

---

## 6. Implications for "PQ accounts, legacy contracts"

1. **A fresh PQ account (new address) mostly loses features rather than funds.**
   - Every `ecrecover_only` user path is unusable: 165 contracts, $569B per year. That includes ECDSA-only `permit` on ≈$34B of tokens, many order protocols, and the meta-tx forwarders.
   - Routers that check account code first (Permit2, USDC) or offer ERC-1271 or pre-sign (CoW, 1inch `fillContractOrder`, Seaport fallback) keep working.
   - Watch for interfaces that pin 65-byte signatures (stETH, Curve stableswap-ng, AirSwap `v,r,s`) or require `tryRecover` to succeed first (KyberSwap RFQ).
2. **A migrated EOA (same address, new PQ authority) stays forgeable everywhere `ecrecover` is accepted.**
   - Affected: ecrecover-only paths ($569B), scheme selection by the signer ($308B) and ECDSA-before-1271 ordering ($160B).
   - The fix is protocol-level: EIP-8151 makes `ecrecover` fail when the recovered address has real code.
   - It only protects once the account holds **real** code. The EIP explicitly lets 7702 delegation indicators through, so EIP-8298 or EIP-8141's account conversion is also needed.
   - It does not cover pure-Solidity ECDSA. Only the 6 secp256k1 software users seen here would be affected, plus any library code that is never exercised.
3. **Operator and committee keys are independent of user PQ-ness.**
   - About $385B (single operator key) and $159B (committees) per year flows through checks where a quantum attacker would target the *operator's* key: market-maker quote signers, CCTP attesters, Wormhole guardians, LayerZero DVNs, Chainlink OCR/Automation signers.
   - 117 of these contracts can rotate keys but not the scheme.
   - Moving them to PQ requires new code: 33 are upgradeable proxies; the 78 with "configurable params" need a redeploy or a verifier indirection.
4. **Proof systems have the cleanest migration lever.** Most SNARK verifiers are standalone contracts the consumer can repoint. The cost is the gas premium of PQ verification and the rollup's admin process. KZG is a protocol dependency of all blob rollups.
5. **Immutable and sole is the residual risk.** 43 contracts: $104B per year, $15.6B held.
   - **Core trading paths:** UniswapX cosigner, KyberSwap RFQ, Clipper, AirSwap. Users can route around them.
   - **Privacy pools:** Tornado, Privacy Pools. Funds exit only through BN254 proofs.
   - **Immutable `permit` tokens:** wstETH, DAI, USDe and others. Protection depends entirely on EIP-8151.
6. **Custody contracts.** About 21.9k immutable contract wallets (BitGo WalletSimple clones and similar) hold 390k ETH plus tokens behind fixed ECDSA signer sets. Owners must move funds; the code cannot be changed.

---

## 7. Protocol context (as of 2026-11)

Details and sources are in `research/pq-research.md`.

| Item | Status | Relevance |
|---|---|---|
| [EIP-8141](https://eips.ethereum.org/EIPS/eip-8141) frame transactions | Draft. Reported scheduled for Hegotá. | Built-in tx schemes are SECP256K1 and P256 only; PQ schemes run as contract code in VERIFY frames (`ARBITRARY` signatures). |
| [EIP-8151](https://eips.ethereum.org/EIPS/eip-8151) account-code-restricted ecRecover | Draft. Reported CFI for Hegotá. | Neutralises old ECDSA keys in legacy contracts for accounts with real code. Raises successful-recovery gas to 3,200 warm / 6,100 cold. |
| EIP-8298 SETCODEFROM | Draft. Reported CFI, paired with 8151. | Lets 7702 accounts install real code. |
| EIP-8051 / 8052 (ML-DSA / Falcon precompiles), EIP-7932, EIP-7885 | Draft | Would cut PQ verification to a few thousand gas. |
| EIP-8355 (ML-DSA precompiles) | Reported declined for Hegotá | No cheap PQ verification in the next fork. |
| EF PQ roadmap | L1 quantum-resistant target Dec 2029; PQ signature precompiles at J\*, PQ blobs at M\* | – |

---

## 8. Files

| Path | Content |
|---|---|
| `data/report/*.csv` | Every table above, plus the full curated list (`curated_contracts.csv`: protocol, function, signer, reliance, ECDSA order, upgradeability, admin, PQ replacement, evidence, confidence) |
| `data/curation/out_*.jsonl` | Per-contract classifications, with evidence |
| `research/pq-research.md` | PQ verifier landscape, EIP status, replacement options and gas, vulnerable patterns (with sources) |
| `scripts/` | Pipeline: `01_precompile_agg` → `02_contracts_pass` → `03_probe_callers` → `03b_caller_family` → `04_families` → `05_code_scan` → `06_value_flows` → `07_classify` → `08_holdings` → `09_report_tables` |

---

## 9. Caveats

- **Runtime observation.** Contracts that verify ECDSA/EC in pure Solidity, or that were not called in the window, are missed by the runtime count; §2 gives static lower bounds. Caller = execution context, so libraries and verifiers reached via `DELEGATECALL` are attributed to the calling proxy. Calls that failed are not in the corpus.
- **Window and state are at different times.** The usage window ends 2026-03-18, where the corpus ends. Code, proxy and holdings are at 2026-11-03. The 6 lattice contracts were found by bytecode scan; their activity comes from Blockscout internal transactions.
- **Value.**
  - Tx value is the largest transfer per transaction, so it measures economic size, not net flow. Group values overlap.
  - It comes from a 1-in-10 sample: the estimated ecrecover transaction count, 30.78M, matches the exact 30.79M.
  - Committee attestations often run in a different transaction from the value movement, so bridges are understated.
  - Holdings cover ≈3.9k addresses and the first 50 tokens each. ETH balances are complete.
- **Classification.**
  - Roles and mutability for the long tail are heuristic (selectors, proxy slots, names).
  - The 433 curated rows were produced by agents reading verified source or bytecode; 65 are low confidence.
  - "Immutable" means the code cannot change. Keys or verifier addresses may still be settable; that case is the separate column "immutable code, configurable".
- **Protocol status.** Fork-schedule statements (Hegotá) come from secondary sources cited in the research notes and were not independently verified. The text of EIP-8141 and EIP-8151 was checked.
- **Market sizes** use Blockscout prices on 2026-11-03 (ETH ≈ $2,300).
