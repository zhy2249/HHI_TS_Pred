#!/usr/bin/env bash
# Stage I: 5*7*4=140 points. Shared pool, resume, per-mode workbook publication.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
unset TS_COND_TRACE TS_R8_TRACE TS_R9_TRACE TS_R10_TRACE TS_RATE_SHADOW TS_RATE_RDOQ_SHADOW
# Leave TS_R10_CACHE unset unless explicitly supplied: honor the TypeDef.h cache default.
export TS_R10_STATS="${TS_R10_STATS:-0}"
exec python3 -u scripts/batch_test.py \
  --preset LBeu --class C,E --qps 22,27,32,37 \
  --fixed-predictors r10_expert_axis_A,r10_expert_p1_A,r10_integer_then_fractional,r10_matched_state_weights,r10_axis_A_tiebreak \
  --encoder build/ts-r10/bin/EncoderApp --decoder build/ts-r10/bin/DecoderApp \
  --input-dir /home/zhy/videos --jobs 10 --decode-md5 --no-recon \
  --xlsm-report --xlsm-template scripts/JVET-hhi.xlsm \
  --out-dir runs/ts_r10_LB_CE_half "$@"
