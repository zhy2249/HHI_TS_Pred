#!/usr/bin/env bash
# Five experiments, ONE shared task pool. HHI LBeu uses CTC half frames.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
unset TS_COND_TRACE
exec python3 -u scripts/batch_test.py \
  --preset LBeu --class C,E --qps 22,27,32,37 \
  --fixed-predictors q32,conf2,prev,ewma,q32_ewma \
  --encoder build/ts-conditional/bin/EncoderApp \
  --decoder build/ts-conditional/bin/DecoderApp \
  --input-dir /home/zhy/videos \
  --jobs 10 --decode-md5 --no-recon \
  --xlsm-report --xlsm-template scripts/JVET-hhi.xlsm \
  --out-dir runs/ts_conditional_LB_CE_half \
  "$@"
