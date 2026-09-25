#!/usr/bin/env bash
# One shared pool across all eight modes; LB half frames from LBeu INI.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
unset TS_COND_TRACE TS_R8_TRACE TS_RATE_SHADOW TS_RATE_RDOQ_SHADOW
export TS_R8_STATS=1
exec python3 -u scripts/batch_test.py \
  --preset LBeu --class C,E --qps 22,27,32,37 \
  --fixed-predictors r8_raw_sparse_max,r8_guard_sparse_max,r8_reject_nopred,r8_mixed_raw,r8_complete_raw,r8_complete_sparse_max,r8_minimax,r8_smoothed_dense \
  --encoder build/ts-r8/bin/EncoderApp --decoder build/ts-r8/bin/DecoderApp \
  --input-dir /home/zhy/videos --jobs 10 --decode-md5 --no-recon \
  --xlsm-report --xlsm-template scripts/JVET-hhi.xlsm \
  --out-dir runs/ts_r8_LB_CE_half "$@"
