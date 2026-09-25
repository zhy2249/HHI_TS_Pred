#!/usr/bin/env bash
# R7 shadow (legacy script/env names retained): unchanged old R3, not BD-rate.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
unset TS_COND_TRACE
export TS_RATE_SHADOW=1
# Optional expensive encoder-search probe; still does not change decisions.
export TS_RATE_RDOQ_SHADOW="${TS_RATE_RDOQ_SHADOW:-0}"
exec python3 -u scripts/batch_test.py \
  --preset LBeu --sequences PartyScene,BQMall,KristenAndSara --qps 22,37 --frames 3 \
  --fixed-predictors r3_risk_guard --encoder build/ts-rate/bin/EncoderApp \
  --decoder build/ts-rate/bin/DecoderApp --jobs 3 --decode-md5 --no-recon \
  --no-xlsm-report --out-dir runs/ts_rate_shadow "$@"
