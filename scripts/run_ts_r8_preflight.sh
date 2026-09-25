#!/usr/bin/env bash
# Registered real-content activity test: 4 sequences x 2 QPs x (8 new + 4 controls).
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
unset TS_COND_TRACE TS_R8_TRACE TS_RATE_SHADOW TS_RATE_RDOQ_SHADOW
export TS_R8_STATS=1
exec python3 -u scripts/batch_test.py \
  --preset LBeu --sequences PartyScene,BQMall,KristenAndSara,Johnny --qps 22,37 --frames 17 \
  --fixed-predictors current,r3_risk_guard,rate_raw,rate_guard,r8_raw_sparse_max,r8_guard_sparse_max,r8_reject_nopred,r8_mixed_raw,r8_complete_raw,r8_complete_sparse_max,r8_minimax,r8_smoothed_dense \
  --encoder build/ts-r8/bin/EncoderApp --decoder build/ts-r8/bin/DecoderApp \
  --input-dir /home/zhy/videos --jobs 10 --decode-md5 --no-recon --no-xlsm-report \
  --out-dir runs/ts_r8_preflight "$@"
