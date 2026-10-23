#!/usr/bin/env bash
# R14 v3, compact-15-v1: A=196 jobs; optional B=224 jobs. Shared pool, no anchor encoding.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
r14_phase=A
r14_args=()
while (($#)); do
  case "$1" in
    --phase)
      if (($# < 2)); then echo '--phase requires A, B, or all' >&2; exit 2; fi
      r14_phase="$2"; shift 2 ;;
    --phase=*) r14_phase="${1#*=}"; shift ;;
    *) r14_args+=("$1"); shift ;;
  esac
done
r14_a=r14_fixed_near_only,r14_g2_none_equal,r14_g2_pair2_equal,r14_fixed_quarter,r14_fixed_threequarter,r14_g4_none_equal,r14_g4_pair2_equal
r14_b=r14_g2_none_half,r14_g4_none_half,r14_g2_none_zero,r14_g4_none_zero,r14_g2_pair2_half,r14_g4_pair2_half,r14_g2_pair2_zero,r14_g4_pair2_zero
case "$r14_phase" in
  A|a) r14_modes="$r14_a" ;;
  B|b) r14_modes="$r14_b" ;;
  all) r14_modes="$r14_a,$r14_b" ;;
  *) echo "Unknown R14 phase: $r14_phase (expected A, B, or all)" >&2; exit 2 ;;
esac
# Old observers are unrelated to R14; explicit trace=0 is unsafe for legacy
# presence-based TS_COND_TRACE, so remove it rather than exporting zero.
unset TS_COND_TRACE TS_R8_TRACE TS_R9_TRACE TS_R10_TRACE TS_R11_TRACE TS_R12_TRACE
unset TS_R13_TRACE TS_R13_POC TS_R13_DETAIL_LIMIT
unset TS_RATE_SHADOW TS_RATE_RDOQ_SHADOW TS_R12_SHADOW_MODES TS_R12_DETAIL_LIMIT
for r14_round in 2 3 4 5 6 8 9 10 11 12 13; do
  export "TS_R${r14_round}_STATS=0"
done
export TS_R10_CACHE=0
export TS_R14_STATS="${TS_R14_STATS:-0}"
export TS_R14_TRACE="${TS_R14_TRACE:-0}"
export TS_R14_DETAIL_LIMIT="${TS_R14_DETAIL_LIMIT:-64}"
# TS_R14_POC stays absent unless explicitly supplied; zero means POC 0 only.
exec python3 -u scripts/batch_test.py \
  --preset LBeu --class C,E --qps 22,27,32,37 \
  --fixed-predictors "$r14_modes" \
  --encoder build/ts-r14/bin/EncoderApp --decoder build/ts-r14/bin/DecoderApp \
  --input-dir /home/zhy/videos --jobs 10 --decode-md5 --no-recon \
  --xlsm-report --xlsm-template scripts/JVET-hhi.xlsm \
  --out-dir runs/ts_r14_nf168_v3_n15_LB_CE_half "${r14_args[@]}"
