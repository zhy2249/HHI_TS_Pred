#!/usr/bin/env bash
# R13-1/2: 56 LB CE half-frame jobs in one shared pool; no anchor re-encoding.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
unset TS_COND_TRACE TS_R8_TRACE TS_R9_TRACE TS_R10_TRACE TS_R11_TRACE TS_R12_TRACE
unset TS_RATE_SHADOW TS_RATE_RDOQ_SHADOW TS_R12_SHADOW_MODES TS_R12_DETAIL_LIMIT
for r13_round in 2 3 4 5 6 8 9 10 11 12; do
  export "TS_R${r13_round}_STATS=0"
done
export TS_R10_CACHE=0
export TS_R13_STATS="${TS_R13_STATS:-0}"
export TS_R13_TRACE="${TS_R13_TRACE:-0}"
export TS_R13_DETAIL_LIMIT="${TS_R13_DETAIL_LIMIT:-64}"
# TS_R13_POC is optional; absent means all POCs. Do not default it to zero.
exec python3 -u scripts/batch_test.py \
  --preset LBeu --class C,E --qps 22,27,32,37 \
  --fixed-predictors r13_keep_hit_uniform,r13_keep_hit_spatial \
  --encoder build/ts-r13/bin/EncoderApp --decoder build/ts-r13/bin/DecoderApp \
  --input-dir /home/zhy/videos --jobs 10 --decode-md5 --no-recon \
  --xlsm-report --xlsm-template scripts/JVET-hhi.xlsm \
  --out-dir runs/ts_r13_kh168_LB_CE_half "$@"
