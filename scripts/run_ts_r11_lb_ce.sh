#!/usr/bin/env bash
# Eight CE groups, one shared pool; no B tasks or extra Current encoding.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
unset TS_COND_TRACE TS_R8_TRACE TS_R9_TRACE TS_R10_TRACE TS_RATE_SHADOW TS_RATE_RDOQ_SHADOW
export TS_R10_CACHE=0
export TS_R11_TRACE=0
export TS_R11_STATS="${TS_R11_STATS:-0}"
exec python3 -u scripts/batch_test.py \
  --preset LBeu --class C,E --qps 22,27,32,37 \
  --fixed-predictors r11_no_evidence_r3,r11_query_context_tie,r11_same_cg_local8,r11_same_tu_local8,r11_add_native_current,r11_add_identity,r11_no_evidence_query,r11_no_evidence_tu8 \
  --encoder build/ts-r11/bin/EncoderApp --decoder build/ts-r11/bin/DecoderApp \
  --input-dir /home/zhy/videos --jobs 10 --decode-md5 --no-recon \
  --xlsm-report --xlsm-template scripts/JVET-hhi.xlsm \
  --out-dir runs/ts_r11_LB_CE_half "$@"
