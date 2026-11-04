#!/usr/bin/env bash
# Systematic 1-in-10 sample of 1000-block partitions over the y1 window (22,100,000..24,699,999)
# for erc20 and native transfers. Partition p is sampled iff (p - 22100) % 10 == 0.
# Both tables are fetched per partition so complete (erc20, native) pairs accumulate in order.
set -euo pipefail
for p in $(seq 22100 10 24690); do
  for t in canonical_execution_erc20_transfers canonical_execution_native_transfers; do
    scripts/download_xatu.sh "$t" "$p" "$p" 1 &
  done
  while (( $(jobs -rp | wc -l) >= 8 )); do wait -n; done
done
wait
