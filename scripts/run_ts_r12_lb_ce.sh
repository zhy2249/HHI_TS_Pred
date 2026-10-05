#!/usr/bin/env bash
# Six priority CE groups share one pool; no automatic B or Current re-encoding.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
unset TS_COND_TRACE TS_R8_TRACE TS_R9_TRACE TS_R10_TRACE TS_R11_TRACE TS_RATE_SHADOW TS_RATE_RDOQ_SHADOW
export TS_R10_CACHE=0 TS_R10_STATS=0 TS_R11_STATS=0
export TS_R12_STATS="${TS_R12_STATS:-0}"
export TS_R12_TRACE="${TS_R12_TRACE:-0}"
exec python3 -u scripts/batch_test.py \
  --preset LBeu --class C,E --qps 22,27,32,37 \
  --fixed-predictors r12_ci_near1,r12_r3_near1,r12_loo_unstable_cf,r12_c_distance_raw,r12_c_distance_fulltrim,r12_validation_distance \
  --encoder build/ts-r12/bin/EncoderApp --decoder build/ts-r12/bin/DecoderApp \
  --input-dir /home/zhy/videos --jobs 10 --decode-md5 --no-recon \
  --xlsm-report --xlsm-template scripts/JVET-hhi.xlsm \
  --out-dir runs/ts_r12_pos01_LB_CE_half "$@"
