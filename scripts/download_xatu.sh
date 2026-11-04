#!/usr/bin/env bash
# Resumable download of Xatu canonical_execution_* parquet partitions (1000 blocks each).
# Usage: scripts/download_xatu.sh <table> <start_partition> <end_partition> [parallel]
# Partitions are block_number/1000, e.g. 22100 -> 22100000.parquet.
set -euo pipefail

TABLE="$1"
START="$2"
END="$3"
PARALLEL="${4:-8}"
DEST="${DEST_ROOT:-$PWD/data/xatu}/$TABLE"
BASE_URL="https://data.ethpandaops.io/xatu/mainnet/databases/default/$TABLE/1000"
mkdir -p "$DEST"

fetch() {
  local out="$DEST/${1}000.parquet"
  [[ -f "$out" ]] && return
  curl --fail --silent --show-error --location --retry 8 --retry-all-errors \
    --connect-timeout 30 --continue-at - --output "$out.part" "$BASE_URL/${1}000.parquet" \
    || { echo "failed: $1" >&2; return 0; }
  # Empty bodies (zero-byte placeholder partitions) leave no .part file behind.
  if [[ -f "$out.part" ]]; then mv "$out.part" "$out"; else : > "$out.empty"; fi
}
export -f fetch
export DEST BASE_URL

seq "$START" "$END" | xargs -r -n 1 -P "$PARALLEL" bash -c 'fetch "$1"' _
