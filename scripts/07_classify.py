"""Rule-based role / mutability per family -> data/families_classified.parquet.

role:
  account_7702_eoa   EIP-7702 delegated EOA (the EOA's secp256k1 key remains root authority)
  account_contract   smart-contract wallet: Safe-style execTransaction, ERC-4337 validateUserOp, Safe proxy,
                     or wallet-like Blockscout name on rep/logic (WalletSimple, Account, Kernel, ...)
  application        everything else
mutability:
  owner_controlled   accounts whose owners can change logic (7702 re-delegation, Safe singleton, UUPS/1967 wallets)
  upgradeable        application behind EIP-1967/beacon/1822/ZeppelinOS proxy, or diamond (diamondCut)
  proxy_unresolved   small DELEGATECALL forwarder (account or application) whose target slot is non-standard
  immutable          no proxy and no upgrade selector (includes EIP-1167 clones of fixed logic)
Curated rows (data/curation/out_*.jsonl) override these per address in the report.
"""

import re
import sys

import pandas as pd

sys.path.insert(0, "scripts")
import blockscout  # noqa: E402

WALLET_NAME = re.compile(
    r"(?i)(safe(proxy)?\b|gnosissafe|walletsimple|smartwallet|smart.?account|\baccount\b|kernel|nexus|msca|"
    r"lightaccount|simpleaccount|ambire|argent|multisig|wallet(core|proxy|impl)|qredowallet|dsproxy|instadapp|"
    r"dfnssmartaccount|delegator|accountfacet|cloneablewallet|bloctoaccount|managedaccount|\bidentity\b|cowshed)")
NOT_WALLET = re.compile(r"(?i)railgun|paymaster|relayer|kerneldao")
UPGRADEABLE_PROXIES = ("eip1967", "beacon", "eip1822", "zos")


def role(r, label: str) -> str:
    if r.proxy_kind == "eip7702":
        return "account_7702_eoa"
    if (r.sel_execTransaction or r.sel_validateUserOp_v06v07 or r.sel_validateUserOp_v08
            or r.proxy_kind == "safe_proxy"):
        return "account_contract"
    if WALLET_NAME.search(label) and not NOT_WALLET.search(label):
        return "account_contract"
    return "application"


def mutability(r, rl: str) -> str:
    if r.proxy_kind == "eip7702":
        return "owner_controlled"
    if rl == "account_contract":
        if (r.proxy_kind in UPGRADEABLE_PROXIES + ("safe_proxy",) or r.sel_upgradeToAndCall or r.sel_upgradeTo
                or r.sel_diamondCut):
            return "owner_controlled"
        if r.proxy_kind == "small_delegating_proxy":
            return "proxy_unresolved"
        return "immutable"
    if r.proxy_kind in UPGRADEABLE_PROXIES or r.sel_diamondCut:
        return "upgradeable"
    if r.proxy_kind == "small_delegating_proxy":
        return "proxy_unresolved"
    return "immutable"


def main():
    F = pd.read_parquet("data/families.parquet")
    bs = blockscout.load_addresses()
    names = dict(zip(bs.address, (bs.name.fillna("") + " " + bs.impl_name.fillna("")).str.strip()))

    def label(r):
        keys = [r.rep, r.logic, r.logic2 if "logic2" in F.columns else None]
        return " ".join(names.get(k, "") for k in keys if isinstance(k, str)).strip()

    F["label"] = [label(r) for r in F.itertuples()]
    F["role"] = [role(r, lb) for r, lb in zip(F.itertuples(), F.label)]
    F["mutability"] = [mutability(r, rl) for r, rl in zip(F.itertuples(), F.role)]
    F.to_parquet("data/families_classified.parquet", index=False)
    print(pd.crosstab(F.role, F.mutability))


if __name__ == "__main__":
    main()
