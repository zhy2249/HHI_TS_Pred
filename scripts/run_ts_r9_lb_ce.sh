#!/usr/bin/env bash
# Stage I by default. One shared task pool; existing per-mode workbook writing.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
unset TS_COND_TRACE TS_R8_TRACE TS_R9_TRACE TS_RATE_SHADOW TS_RATE_RDOQ_SHADOW
export TS_R9_STATS="${TS_R9_STATS:-0}"
exec python3 -u scripts/batch_test.py \
  --preset LBeu --class C,E --qps 22,27,32,37 \
  --fixed-predictors r9_p10,r9_p12,r9_axis_sparse,r9_half_penalty,r9_feature_penalty,r9_unit_risk,r9_axis_feature \
  --encoder build/ts-r9/bin/EncoderApp --decoder build/ts-r9/bin/DecoderApp \
  --input-dir /home/zhy/videos --jobs 10 --decode-md5 --no-recon \
  --xlsm-report --xlsm-template scripts/JVET-hhi.xlsm \
  --out-dir runs/ts_r9_stage1_LB_CE_half "$@"
