// Experimental out-of-band mode: encoder and decoder MUST use the same setting.
#pragma once
#include "CommonDef.h" // Loads TypeDef.h experiment defaults before testing macros.
#include <algorithm>
#include <cstdlib>
#include <cstring>
#include <cstdio>

namespace TsFixedPrediction
{
// Public R8 numbers are deliberately distinct from internal dispatch IDs.
inline int r8PublicMode(int policy)
{
  // Append new policies: preserve every previously recorded internal ID.
  static const int ids[] = {1, 4, 8, 13, 15, 16, 17, 19, 2, 3, 5, 6, 7, 9, 10, 11, 12, 14, 18, 20, 21, 22, 23, 24};
  return policy >= 34 && policy <= 57 ? ids[policy - 34] : 0;
}
inline const char *r8Name(int publicMode)
{
  switch (publicMode)
  {
  case 1: return "r8_raw_sparse_max";
  case 2: return "r8_raw_sparse_mean";
  case 3: return "r8_raw_sparse_min";
  case 4: return "r8_guard_sparse_max";
  case 5: return "r8_guard_sparse_mean";
  case 6: return "r8_guard_sparse_min";
  case 7: return "r8_dense_nopred";
  case 8: return "r8_reject_nopred";
  case 9: return "r8_trim_cost";
  case 10: return "r8_trim_saving";
  case 11: return "r8_reject_sparse_max";
  case 12: return "r8_trim_sparse_max";
  case 13: return "r8_mixed_raw";
  case 14: return "r8_mixed_guard";
  case 15: return "r8_complete_raw";
  case 16: return "r8_complete_sparse_max";
  case 17: return "r8_minimax";
  case 18: return "r8_minimax_complete";
  case 19: return "r8_smoothed_dense";
  case 20: return "r8_smoothed_all_support";
  case 21: return "r8_dual_path";
  case 22: return "r8_causal_path";
  case 23: return "r8_r3_dual_quant";
  case 24: return "r8_raw_dual_quant";
  default: return nullptr;
  }
}
inline int r8Policy(const char *name)
{
  for (int p = 34; p <= 57; ++p)
    if (!std::strcmp(name, r8Name(r8PublicMode(p)))) { return p; }
  return 0;
}
inline bool r8(int policy) { return r8PublicMode(policy) != 0; }
inline bool r8DualQuant(int policy) { return r8PublicMode(policy) >= 23; }
inline const char *defaultName()
{
#if JVET_BJUT_TS_FIXED_PREDICTOR && JVET_BJUT_TS_FIXED_NOPRED
  return "nopred";
#elif JVET_BJUT_TS_FIXED_PREDICTOR && JVET_BJUT_TS_FIXED_GRADIENT
  return "gradient";
#elif JVET_BJUT_TS_FIXED_PREDICTOR && JVET_BJUT_TS_FIXED_DIRECTIONAL
  return "directional";
#else
  return JVET_BJUT_TS_R8_MODE ? r8Name(JVET_BJUT_TS_R8_MODE) :
         JVET_BJUT_TS_R7_MODE == 1 ? "rate_raw" :
         JVET_BJUT_TS_R7_MODE == 2 ? "rate_guard" :
         JVET_BJUT_TS_R6_MODE == 1 ? "r6_dense_nopred" :
         JVET_BJUT_TS_R6_MODE == 2 ? "r6_reject_nopred" :
         JVET_BJUT_TS_R6_MODE == 3 ? "r6_trim_cost" :
         JVET_BJUT_TS_R6_MODE == 4 ? "r6_trim_saving" :
         JVET_BJUT_TS_R6_MODE == 5 ? "r6_sparse_max" :
         JVET_BJUT_TS_R6_MODE == 6 ? "r6_sparse_mean" :
         JVET_BJUT_TS_R6_MODE == 7 ? "r6_sparse_min" :
         JVET_BJUT_TS_R5_MODE == 1 ? "r5_margin_first" :
         JVET_BJUT_TS_R5_MODE == 2 ? "r5_current_veto" :
         JVET_BJUT_TS_R4_MODE == 1 ? "r4_identity_only" :
         JVET_BJUT_TS_R4_MODE == 2 ? "r4_magnitude_only" :
         JVET_BJUT_TS_R4_MODE == 3 ? "r4_guard_rescue" :
         JVET_BJUT_TS_R4_MODE == 4 ? "r4_directional_risk" :
         JVET_BJUT_TS_R4_MODE == 5 ? "r4_causal_models" :
         JVET_BJUT_TS_R4_MODE == 6 ? "r4_signed_plane" :
         JVET_BJUT_TS_R3_MODE == 1 ? "r3_risk_guard" :
         JVET_BJUT_TS_R3_MODE == 2 ? "r3_risk_guard_y" :
         JVET_BJUT_TS_R3_MODE == 3 ? "r3_cn_guard" :
         JVET_BJUT_TS_R3_MODE == 4 ? "r3_cn_guard_y" :
         JVET_BJUT_TS_R2_MODE == 1 ? "r2_modal" :
         JVET_BJUT_TS_R2_MODE == 2 ? "r2_risk" :
         JVET_BJUT_TS_R2_MODE == 3 ? "r2_cn_log" :
         JVET_BJUT_TS_R2_MODE == 4 ? "r2_cn_frac" :
         JVET_BJUT_TS_CONDITIONAL_MODE == 1 ? "q32" :
         JVET_BJUT_TS_CONDITIONAL_MODE == 2 ? "conf2" :
         JVET_BJUT_TS_CONDITIONAL_MODE == 3 ? "prev" :
         JVET_BJUT_TS_CONDITIONAL_MODE == 4 ? "ewma" :
         JVET_BJUT_TS_CONDITIONAL_MODE == 5 ? "q32_ewma" : "current";
#endif
}
inline const char *name()
{
#if JVET_BJUT_TS_FIXED_PREDICTOR
  static const char *value = []() {
    const char *v = std::getenv("TS_FIXED_PREDICTOR");
    if (!v) { return defaultName(); }
    if (std::strcmp(v, "current") && std::strcmp(v, "nopred") &&
        std::strcmp(v, "gradient") && std::strcmp(v, "directional") &&
        std::strcmp(v, "q32") && std::strcmp(v, "conf2") && std::strcmp(v, "prev") &&
        std::strcmp(v, "ewma") && std::strcmp(v, "q32_ewma") &&
        std::strcmp(v, "r2_modal") && std::strcmp(v, "r2_risk") &&
        std::strcmp(v, "r2_cn_log") && std::strcmp(v, "r2_cn_frac") &&
        std::strcmp(v, "r3_risk_guard") && std::strcmp(v, "r3_risk_guard_y") &&
        std::strcmp(v, "r3_cn_guard") && std::strcmp(v, "r3_cn_guard_y") &&
        std::strcmp(v, "r4_identity_only") && std::strcmp(v, "r4_magnitude_only") &&
        std::strcmp(v, "r4_guard_rescue") && std::strcmp(v, "r4_directional_risk") &&
        std::strcmp(v, "r4_causal_models") && std::strcmp(v, "r4_signed_plane") &&
        std::strcmp(v, "r5_margin_first") && std::strcmp(v, "r5_current_veto") &&
        std::strcmp(v, "r6_dense_nopred") && std::strcmp(v, "r6_reject_nopred") &&
        std::strcmp(v, "r6_trim_cost") && std::strcmp(v, "r6_trim_saving") &&
        std::strcmp(v, "r6_sparse_max") && std::strcmp(v, "r6_sparse_mean") && std::strcmp(v, "r6_sparse_min") &&
        std::strcmp(v, "rate_raw") && std::strcmp(v, "rate_guard") && !r8Policy(v))
    {
      std::fprintf(stderr, "Invalid TS_FIXED_PREDICTOR: %s\n", v);
      std::exit(EXIT_FAILURE);
    }
    return v;
  }();
  return value;
#else
  const char *v = std::getenv("TS_FIXED_PREDICTOR");
  if (v && std::strcmp(v, "current"))
  {
    std::fprintf(stderr, "TS experiment requested (%s), but TypeDef.h master is OFF\n", v);
    std::exit(EXIT_FAILURE);
  }
  return "current";
#endif
}
inline int mode()
{
  static const int value = !std::strcmp(name(), "nopred") ? 0 :
                          !std::strcmp(name(), "gradient") ? 2 :
                          !std::strcmp(name(), "directional") ? 3 :
                          !std::strcmp(name(), "q32") ? 4 :
                          !std::strcmp(name(), "conf2") ? 5 :
                          !std::strcmp(name(), "prev") ? 6 :
                          !std::strcmp(name(), "ewma") ? 7 :
                          !std::strcmp(name(), "q32_ewma") ? 8 :
                          !std::strcmp(name(), "r2_modal") ? 9 :
                          !std::strcmp(name(), "r2_risk") ? 10 :
                          !std::strcmp(name(), "r2_cn_log") ? 11 :
                          !std::strcmp(name(), "r2_cn_frac") ? 12 :
                          !std::strcmp(name(), "r3_risk_guard") ? 13 :
                          !std::strcmp(name(), "r3_risk_guard_y") ? 14 :
                          !std::strcmp(name(), "r3_cn_guard") ? 15 :
                          !std::strcmp(name(), "r3_cn_guard_y") ? 16 :
                          !std::strcmp(name(), "r4_identity_only") ? 17 :
                          !std::strcmp(name(), "r4_magnitude_only") ? 18 :
                          !std::strcmp(name(), "r4_guard_rescue") ? 19 :
                          !std::strcmp(name(), "r4_directional_risk") ? 20 :
                          !std::strcmp(name(), "r4_causal_models") ? 21 :
                          !std::strcmp(name(), "r4_signed_plane") ? 22 :
                          !std::strcmp(name(), "r5_margin_first") ? 23 :
                          !std::strcmp(name(), "r5_current_veto") ? 24 :
                          !std::strcmp(name(), "r6_dense_nopred") ? 25 :
                          !std::strcmp(name(), "r6_reject_nopred") ? 26 :
                          !std::strcmp(name(), "r6_trim_cost") ? 27 :
                          !std::strcmp(name(), "r6_trim_saving") ? 28 :
                          !std::strcmp(name(), "r6_sparse_max") ? 29 :
                          !std::strcmp(name(), "r6_sparse_mean") ? 30 :
                          !std::strcmp(name(), "r6_sparse_min") ? 31 :
                          !std::strcmp(name(), "rate_raw") ? 32 :
                          !std::strcmp(name(), "rate_guard") ? 33 :
                          r8Policy(name()) ? r8Policy(name()) : 1;
  return value;
}
inline void announce()
{
  (void)name(); // Validate explicit requests even in master-OFF builds.
  const bool wantShadow = std::getenv("TS_RATE_SHADOW") && std::strcmp(std::getenv("TS_RATE_SHADOW"), "0");
  const bool wantSearch = std::getenv("TS_RATE_RDOQ_SHADOW") && std::strcmp(std::getenv("TS_RATE_RDOQ_SHADOW"), "0");
  CHECK((wantShadow || wantSearch) && !JVET_BJUT_TS_R7_SHADOW,
        "Rebuild with TypeDef.h JVET_BJUT_TS_R7_SHADOW=1 (legacy JVET_BJUT_TS_RATE_SHADOW=1)");
  CHECK((wantShadow || wantSearch) && mode() != 13, "Rate shadow requires unchanged r3_risk_guard");
#if JVET_BJUT_TS_FIXED_PREDICTOR
  std::printf("EXPERIMENT: TS_FIXED_PREDICTOR=%s; syntax=experimental-v1\n", name());
  std::printf("TS predictor default: %s; selection: %s\n", defaultName(),
              std::getenv("TS_FIXED_PREDICTOR") ? "environment override" : "TypeDef.h default");
  if (mode() >= 4 && mode() <= 8)
    std::printf("TS conditional revision=1; CU-QP<=32; confidence=2:1; decay=2; TU-local; integer-proxy\n");
  if (mode() >= 9 && mode() <= 12)
    std::printf("TS R2 revision=2; anchor=current; template=L,U,D,LL,UU; support>=3; decay=2; TU-local; virtual-init=I/CU-QP; canonical=current\n");
  if (mode() >= 13 && mode() <= 16)
    std::printf("TS R3 revision=R3-20260919-v1; anchor=current; guard=G-max-positive>0; recent=immediately-previous-CG; scope=%s; TU-local\n",
                mode() == 14 || mode() == 16 ? "Y-only" : "YUV");
  if (mode() >= 17 && mode() <= 22)
    std::printf("TS R4 revision=R4-20260920-v2; mode=%d; anchor=current; scope=YUV; TU-local; stateless; cost=syntax-proxy; signed-view=1\n", mode() - 16);
  if (mode() == 23 || mode() == 24)
    std::printf("TS R5 revision=R5-20260921-v1; mode=%d; anchor=current; parent=r3_risk_guard; scope=YUV; TU-local; stateless; cost=syntax-proxy; rule=%s\n",
                mode() - 22, mode() == 23 ? "max-H-then-G" : "Current-only-causal-veto");
  if (mode() >= 25 && mode() <= 31)
    std::printf("TS R6 revision=R6-20260923-v1; mode=%d; anchor=current; parent=r3_risk_guard; scope=YUV; TU-local; stateless; cost=syntax-proxy; n=nonzero-positions; tie=Current-identity-smallest; stats=stderr\n", mode() - 24);
  if (mode() == 32 || mode() == 33)
  {
    std::printf("TS R7 experiment=R7-%d; parent=%s; runtime=%s; algorithm=RATE-20260924-v1\n",
                mode() - 31, mode() == 32 ? "R2-2" : "R3-1-YUV", name());
    // Retain legacy identity/schema for existing log readers and results.
    std::printf("TS RATE revision=RATE-20260924-v1; mode=%d; CG-entry-frozen-CABAC; full-regular-local-model; anchor=current\n", mode() - 31);
  }
  if (r8(mode()))
  {
    const int m = r8PublicMode(mode());
    std::printf("TS R8 revision=R8-DESIGN-20260925-v2; mode=%d; runtime=%s; anchor=current; scope=YUV; %s; n=nonzero-positions; stats=final-Writer-only\n", m, name(),
      m == 23 ? "integer-proxy-R3" : m == 21 || m == 22 ? "CG-entry-frozen-CABAC; dual-regular-path-model" :
      "CG-entry-frozen-CABAC; full-regular-local-model");
    if (m >= 21)
      std::printf("TS R8 extension=R8-ALL-20260926-v1; path=%s; owner-search=%s; search-stats=separate-from-final-Writer\n",
        m == 22 ? "TU-local-final-CG-weights" : m == 21 ? "fixed-1:1" : "parent",
        m >= 23 ? "paired-q0-q1-tie-q0" : "native");
  }
  if (wantShadow)
  {
    std::printf("TS R7 observation-only; parent=R3-1; actual-runtime=r3_risk_guard\n");
    std::printf("TS RATE shadow=RATE-20260924-v1; actual-decisions=R3-old; frozen-CG-context; no-bitstream-change\n");
  }
#endif
}
// Magnitudes are bounded by codec transform dynamic range. Use wider arithmetic
// for extrapolation/edge scores; the returned predictor stays within [min,max].
inline int predict(int mode, int x, int y, int l, int u, int d, int ll, int uu)
{
  const int hi = std::max(l, u), lo = std::min(l, u);
  if (mode == 0) { return 0; }
  if (mode == 2 && x > 0 && y > 0)
  {
    return int(std::max<long long>(lo, std::min<long long>(hi, (long long)l + u - d)));
  }
  if ((mode == 3 || mode == 5) && x >= 2 && y >= 2)
  {
    const auto eh = std::abs((long long)l - ll) + std::abs((long long)u - d);
    const auto ev = std::abs((long long)u - uu) + std::abs((long long)l - d);
    if (mode == 5 && (std::max(eh, ev) == 0 || std::max(eh, ev) < 2 * std::min(eh, ev)))
      return hi;
    return eh < ev ? l : ev < eh ? u : hi;
  }
  return hi;
}

inline bool r3Local(int mode) { return mode == 13 || mode == 14; }
inline bool r3Adaptive(int mode) { return mode == 15 || mode == 16; }
inline bool r3(int mode) { return r3Local(mode) || r3Adaptive(mode); }
inline bool r4(int mode) { return mode >= 17 && mode <= 22; }
inline bool r5(int mode) { return mode == 23 || mode == 24; }
inline bool r6(int mode) { return mode >= 25 && mode <= 31; }
inline bool rateMode(int mode) { return mode == 32 || mode == 33; }
inline bool needsTsRateContext(int mode) { return rateMode(mode) || (r8(mode) && r8PublicMode(mode) != 23); }
inline bool componentEnabled(int mode, bool luma) { return luma || (mode != 14 && mode != 16); }
inline bool equivalentPredictors(int a, int b) { return a == b || (a <= 1 && b <= 1); }
inline bool adaptive(int mode) { return (mode >= 6 && mode <= 8) || mode == 11 || mode == 12 || r3Adaptive(mode); }
inline int selectedMode(int mode, int qp, int64_t state, int64_t recentMargin = 0, bool luma = true)
{
  if (!componentEnabled(mode, luma)) { return 1; }
  if (r3Adaptive(mode)) { return state > 0 && recentMargin > 0 ? 0 : 1; }
  if (mode == 4) { return qp <= 32 ? 3 : 1; }
  if (mode == 11 || mode == 12) { return state > 0 ? 0 : 1; }
  if (adaptive(mode)) { return state > 0 && (mode != 8 || qp <= 32) ? 3 : 1; }
  return mode;
}
inline int64_t updateState(int mode, int64_t state, int64_t gain)
{
  if (mode == 6) { return gain; }
  const int64_t decay = state / 4; // C++ signed division truncates towards zero.
  const int64_t limit = int64_t(32767) << (mode == 12 ? SCALE_BITS : 0);
  return std::max(-limit, std::min(limit, state - decay + gain));
}
inline int remap(int a, int p) { return !a ? 0 : a == p ? 1 : a < p ? a + 1 : a; }
// Integer proxy only; NOT TSRC bits. Final effectiveness is measured by closed-loop BD-rate.
inline int proxyCost(unsigned a)
{
  if (!a) { return 0; }
  int cost = 1;
  while (a >>= 1) { cost += 2; }
  return cost;
}
// Identical length to BitEstimatorBase::encodeRemAbsEP, including limited escape.
inline unsigned riceLength(unsigned value, unsigned rice, int dynamicRange)
{
  const unsigned cutoff = COEF_REMAIN_BIN_REDUCTION;
  if (value < (cutoff << rice)) { return (value >> rice) + 1 + rice; }
  const unsigned maxPrefix = 32 - cutoff - dynamicRange;
  const unsigned code = (value >> rice) - cutoff;
  if (code >= ((1u << maxPrefix) - 1)) { return cutoff + maxPrefix + dynamicRange; }
  unsigned prefix = 0;
  while (code > ((2u << prefix) - 2)) { ++prefix; }
  return cutoff + 2 * prefix + rice + 1;
}
inline int syntaxCost(unsigned level, unsigned rice, int dynamicRange)
{
  if (level < 2) { return int(level); }
  return 2 + (level >= 2) + (level >= 4) + (level >= 6) + (level >= 8) +
         (level >= 10 ? riceLength((level - 10) >> 1, rice, dynamicRange) : 0);
}
inline int localPredict(int mode, int current, const int *nonzero, int n, unsigned rice, int dynamicRange)
{
  if (n < 3) { return current; }
  if (mode == 9)
  {
    for (int i = 0; i < n; ++i)
    {
      int count = 0;
      for (int j = 0; j < n; ++j) { count += nonzero[i] == nonzero[j]; }
      if (2 * count > n) { return nonzero[i]; }
    }
    return current;
  }
  const auto cost = [&](int p) {
    int sum = 0;
    for (int i = 0; i < n; ++i) { sum += syntaxCost(remap(nonzero[i], p), rice, dynamicRange); }
    return sum;
  };
  int best = current <= 1 ? 0 : current, score = cost(best);
  int candidates[6] = {0};
  std::copy_n(nonzero, n, candidates + 1);
  std::sort(candidates, candidates + n + 1);
  for (int i = 0; i <= n; ++i)
  {
    const int p = candidates[i] <= 1 ? 0 : candidates[i];
    const int value = cost(p);
    if (value < score) { best = p; score = value; }
  }
  return best; // Strict comparison preserves Current, then identity, then smallest p ties.
}

struct LocalGuardResult
{
  int predictor, winner;
  int gain = 0, bestPositive = 0;
  int margin() const { return gain - bestPositive; }
};
// Fixed-candidate delete-one-contribution sensitivity, not cross-validation.
inline LocalGuardResult guardedLocalPredict(int current, const int *nonzero, int n, unsigned rice, int dynamicRange)
{
  LocalGuardResult result{current, current};
  if (n < 3) { return result; }
  result.winner = localPredict(10, current, nonzero, n, rice, dynamicRange);
  if (equivalentPredictors(current, result.winner)) { return result; }
  for (int i = 0; i < n; ++i)
  {
    const int contribution = syntaxCost(remap(nonzero[i], current), rice, dynamicRange) -
                             syntaxCost(remap(nonzero[i], result.winner), rice, dynamicRange);
    result.gain += contribution;
    result.bestPositive = std::max(result.bestPositive, contribution);
  }
  if (result.margin() > 0) { result.predictor = result.winner; }
  return result;
}
}
