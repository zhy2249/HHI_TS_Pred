// R8 frozen specification. Pure causal function; no CABAC writes.
#pragma once
#include "TsRateCost.h"

namespace TsFixedPrediction
{
struct R8Decision
{
  int current = 0, predictor = 0, n = 0, count = 0, rawWinner = 0;
  int candidates[21]{};
  int64_t scores[21]{}, regrets[21]{}, gain = 0, margin = 0;
};
inline int r8Canonical(int p) { return p <= 1 ? 0 : p; }
inline bool r8TieLess(int a, int b, int current)
{
  const auto rank = [&](int p) { return p == current ? 0 : p == 0 ? 1 : 2; };
  return rank(a) != rank(b) ? rank(a) < rank(b) : a < b;
}
// publicMode, not the internal policy ID. All candidates share immutable costs.
template<class FractionalCost, class IntegerCost>
R8Decision r8Decision(int publicMode, const int (&a)[5], int limit,
                      const FractionalCost &fractional, const IntegerCost &integer)
{
  CHECK(!r8Name(publicMode), "Unimplemented R8 decision");
  R8Decision d;
  int nz[5]{};
  for (int v : a)
  {
    CHECK(v < 0 || v > limit, "R8 magnitude out of range");
    if (v) { nz[d.n++] = v; }
  }
  d.current = d.predictor = d.rawWinner = r8Canonical(std::max(a[0], a[1]));
  if (d.n < 3 && !(publicMode == 20 && d.n))
  {
    const bool s0 = (publicMode >= 7 && publicMode <= 10) || publicMode == 15 || publicMode == 23;
    if (!s0)
    {
      d.predictor = 0;
      if (d.n == 2 && a[0] && a[1])
        d.predictor = r8Canonical(publicMode == 2 || publicMode == 5 ? (a[0] + a[1] + 1) / 2 :
                                 publicMode == 3 || publicMode == 6 ? std::min(a[0],a[1]) : std::max(a[0],a[1]));
    }
    return d;
  }
  const bool smoothed = publicMode == 19 || publicMode == 20;
  const bool complete = publicMode == 15 || publicMode == 16 || publicMode == 18 || smoothed || publicMode == 21 || publicMode == 22;
  const auto clip = [&](int v) { return std::max(0, std::min(limit, v)); };
  const auto add = [&](int v) {
    v = r8Canonical(v);
    for (int i = 0; i < d.count; ++i) { if (d.candidates[i] == v) { return; } }
    CHECK(d.count >= 21, "R8 candidate capacity exceeded");
    d.candidates[d.count++] = v;
  };
  add(0);
  for (int i = 0; i < d.n; ++i)
    for (int delta = smoothed ? -1 : 0; delta <= (smoothed ? 1 : 0); ++delta)
    {
      const int v = clip(nz[i] + delta);
      if (!v) { continue; }
      add(v);
      if (complete) { add(clip(v + 1)); }
    }
  std::sort(d.candidates, d.candidates + d.count);
  // The caller supplies the immutable CF10/CF2 mixture for C01/C02.
  const auto cost = [&](int v) -> int64_t {
    return publicMode == 23 ? integer(v) : fractional(v) + (publicMode == 13 || publicMode == 14 ? integer(v) : 0);
  };
  // M(v,p) has only three possible costs: C(1), C(v), C(v+1).
  // Precompute per support position: <=11 cost calls for empirical, <=31
  // for smoothing, instead of up to 21*5*3 repeated CABAC/Rice evaluations.
  const int terms = smoothed ? 3 : 1;
  const int64_t hitCost = cost(1);
  int values[5][3]{};
  int64_t same[5][3]{}, incremented[5][3]{};
  for (int i = 0; i < d.n; ++i)
    for (int t = 0; t < terms; ++t)
    {
      const int v = values[i][t] = clip(nz[i] + (smoothed ? t - 1 : 0));
      same[i][t] = cost(v);
      incremented[i][t] = v && v < limit ? cost(v + 1) : same[i][t];
    }
  int64_t loss[21][5]{};
  int cur = -1, raw = 0;
  for (int k = 0; k < d.count; ++k)
  {
    if (d.candidates[k] == d.current) { cur = k; }
    for (int i = 0; i < d.n; ++i)
    {
      const int p = d.candidates[k];
      for (int t = 0; t < terms; ++t)
      {
        const int v = values[i][t], weight = smoothed && t == 1 ? 2 : 1;
        loss[k][i] += weight * (!v ? 0 : v == p ? hitCost : v < p ? incremented[i][t] : same[i][t]);
      }
      d.scores[k] += loss[k][i];
    }
    if (d.scores[k] < d.scores[raw] ||
        (d.scores[k] == d.scores[raw] && r8TieLess(d.candidates[k], d.candidates[raw], d.current))) { raw = k; }
  }
  CHECK(cur < 0, "R8 candidates must include Current-equivalent");
  d.rawWinner = d.predictor = d.candidates[raw];
  d.gain = d.scores[cur] - d.scores[raw];
  int64_t bestPositive = 0;
  for (int i = 0; i < d.n; ++i) { bestPositive = std::max(bestPositive, loss[cur][i] - loss[raw][i]); }
  d.margin = d.gain - bestPositive;
  if (((publicMode >= 4 && publicMode <= 6) || publicMode == 14 || publicMode == 23) && d.margin <= 0) { d.predictor = d.current; }
  if (publicMode == 7 && d.margin <= 0) { d.predictor = 0; }
  if ((publicMode == 8 || publicMode == 11) && d.rawWinner != d.current && d.margin <= 0) { d.predictor = 0; }
  if (publicMode == 9 || publicMode == 10 || publicMode == 12)
  {
    int chosen = 0;
    int64_t robust[21]{};
    for (int k = 0; k < d.count; ++k)
    {
      int64_t adjustment = publicMode == 9 ? loss[k][0] : 0;
      for (int i = 0; i < d.n; ++i)
        adjustment = publicMode == 9 ? std::min(adjustment,loss[k][i]) : std::max(adjustment,loss[0][i]-loss[k][i]);
      robust[k] = d.scores[k] + (publicMode == 9 ? -adjustment : adjustment);
      if (robust[k] < robust[chosen] || (robust[k] == robust[chosen] &&
          r8TieLess(d.candidates[k],d.candidates[chosen],d.current))) { chosen = k; }
    }
    d.predictor = d.candidates[chosen];
  }
  if (publicMode == 17 || publicMode == 18)
  {
    // Scenario -1=full; 0..n-1=delete one original nonzero position.
    // Keep P0 FIXED across scenarios (including a uniquely occurring magnitude).
    for (int deleted = -1; deleted < d.n; ++deleted)
    {
      int64_t best = d.scores[0] - (deleted < 0 ? 0 : loss[0][deleted]);
      for (int k = 1; k < d.count; ++k)
        best = std::min(best, d.scores[k] - (deleted < 0 ? 0 : loss[k][deleted]));
      for (int k = 0; k < d.count; ++k)
        d.regrets[k] = std::max(d.regrets[k], d.scores[k] - (deleted < 0 ? 0 : loss[k][deleted]) - best);
    }
    int chosen = 0;
    for (int k = 1; k < d.count; ++k)
      if (d.regrets[k] < d.regrets[chosen] || (d.regrets[k] == d.regrets[chosen] &&
          (d.scores[k] < d.scores[chosen] || (d.scores[k] == d.scores[chosen] &&
           r8TieLess(d.candidates[k], d.candidates[chosen], d.current))))) { chosen = k; }
    d.predictor = d.candidates[chosen];
  }
  return d;
}
}
