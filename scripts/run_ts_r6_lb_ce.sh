#!/usr/bin/env bash
# Default: three primary independent hypotheses, shared queue, half-frame LB CE.
# Diagnostics and LU ablations can be selected with --fixed-predictors override.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
unset TS_COND_TRACE
export TS_R6_STATS=1
exec python3 -u scripts/batch_test.py \
  --preset LBeu --class C,E --qps 22,27,32,37 \
  --fixed-predictors r6_reject_nopred,r6_trim_saving,r6_sparse_max \
  --encoder build/ts-r6/bin/EncoderApp --decoder build/ts-r6/bin/DecoderApp \
  --input-dir /home/zhy/videos --jobs 10 --decode-md5 --no-recon \
  --xlsm-report --xlsm-template scripts/JVET-hhi.xlsm \
  --out-dir runs/ts_r6_LB_CE_half "$@"
