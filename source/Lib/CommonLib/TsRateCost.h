// CG-entry frozen fractional costs. No coefficient, CABAC or probability writes.
#pragma once
#include "TsFixedPrediction.h"
#include "Contexts.h"

namespace TsFixedPrediction
{
struct RateTable
{
  BinFracBits gt1{}, parity{}, gt[4]{};
  int64_t cost(unsigned a, unsigned rice, int range, int cutoff = 10) const
  {
    CHECK(cutoff != 2 && cutoff != 10, "Magnitude model requires a regular path");
    if (!a) { return 0; } // Significance/sign cancel for fixed nonzero samples.
    int64_t bits = gt1.intBits[a > 1];
    if (a <= 1) { return bits; }
    bits += parity.intBits[(a - 2) & 1];
    if (cutoff == 10)
      for (unsigned c = 2; c <= 8; c += 2)
        if (a >= c) { bits += gt[c / 2 - 1].intBits[a >= c + 2]; }
    if (a >= unsigned(cutoff))
      bits += int64_t(riceLength((a - cutoff) >> 1, rice, range)) << SCALE_BITS;
    return bits;
  }
};
struct RateSnapshot
{
  RateTable byDirectNonzero[3];
  bool ready = false;
};
struct RateDecision
{
  int current = 0, winner = 0, predictor = 0, n = 0;
  int count = 0, candidates[6]{};
  int64_t scores[6]{}, currentScore = 0, gain = 0, bestPositive = 0;
  int64_t margin() const { return gain - bestPositive; }
  bool proposed() const { return !equivalentPredictors(current, winner); }
  bool accepted() const { return proposed() && margin() > 0; }
};
// Same candidate set, Current-first ties, support and fixed-winner guard as R3.
template<class Cost>
RateDecision rateDecision(int current, const int *nz, int n, const Cost &cost)
{
  RateDecision d;
  d.current = d.winner = d.predictor = current; d.n = n;
  const auto sum = [&](int p) {
    int64_t s = 0;
    for (int i = 0; i < n; ++i) { s += cost(remap(nz[i], p)); }
    return s;
  };
  d.currentScore = sum(current);
  d.candidates[d.count] = current; d.scores[d.count++] = d.currentScore;
  if (n < 3) { return d; }
  int sorted[6] = {0};
  std::copy_n(nz, n, sorted + 1); std::sort(sorted, sorted + n + 1);
  int64_t best = d.currentScore;
  for (int i = 0; i <= n; ++i)
  {
    const int p = sorted[i] <= 1 ? 0 : sorted[i];
    bool duplicate = false;
    for (int k = 0; k < d.count; ++k) { duplicate |= equivalentPredictors(p, d.candidates[k]); }
    if (duplicate) { continue; }
    CHECK(d.count >= 6, "Too many local magnitude candidates");
    const auto value = sum(p);
    d.candidates[d.count] = p; d.scores[d.count++] = value;
    if (value < best) { best = value; d.winner = p; }
  }
  if (d.proposed())
  {
    for (int i = 0; i < n; ++i)
    {
      const int64_t v = cost(remap(nz[i], current)) - cost(remap(nz[i], d.winner));
      d.gain += v; d.bestPositive = std::max(d.bestPositive, v);
    }
    if (d.margin() > 0) { d.predictor = d.winner; }
  }
  return d;
}
}
