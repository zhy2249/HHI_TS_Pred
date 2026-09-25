// Frozen R4-20260920-v2 policies. Pure causal functions, no state or RDO caches.
#pragma once
#include "TsFixedPrediction.h"

namespace TsFixedPrediction
{
// During Reader pass 3, current-CG magnitudes are restored progressively but
// signs are written back only at CG end. Never mutate that working buffer.
struct R4SignView
{
  const TCoeff *coeff;
  const int *positions;
  int count;
  unsigned signs;
  int at(int pos) const
  {
    for (int k = 0; k < count; ++k)
      if (positions[k] == pos)
      {
        const int a = std::abs(int(coeff[pos]));
        return (signs >> k) & 1u ? -a : a;
      }
    return int(coeff[pos]); // Earlier CG already has its final signs.
  }
};

struct R4Result
{
  int predictor = 0, current = 0, parent = 0, support = 0;
  int gain = 0, bestPositive = 0;
  int model = 0; // CB: 0=R3,1=Current,2=NoPred,3=directional; SP:4=plane.
  int direction = 0; // 0=tie, 1=horizontal, 2=vertical; -1=boundary.
  bool attempted = false, accepted = false, rescue = false, suppressed = false;
  LocalGuardResult original{0, 0};
  int margin() const { return gain - bestPositive; }
};

inline constexpr int r4Dx[5] = {-1, 0, -1, -2, 0};
inline constexpr int r4Dy[5] = {0, -1, -1, 0, -2};

// read(x,y) returns signed q, zero for absent top/left neighbors. It must only
// expose earlier positions. Actual grouped scan is checked by native tests.
template<class Read> inline LocalGuardResult r4Parent(const Read &read, int x, int y, unsigned rice, int range)
{
  int values[5], n = 0;
  for (int i = 0; i < 5; ++i)
  {
    const int a = std::abs(read(x + r4Dx[i], y + r4Dy[i]));
    if (a) { values[n++] = a; }
  }
  const int current = std::max(std::abs(read(x - 1, y)), std::abs(read(x, y - 1)));
  return guardedLocalPredict(current, values, n, rice, range);
}

template<class Read> inline int r4Expert(const Read &read, int x, int y, unsigned rice, int range, int expert)
{
  if (expert == 0) { return r4Parent(read, x, y, rice, range).predictor; }
  if (expert == 2) { return 0; }
  const int l = read(x - 1, y), u = read(x, y - 1);
  if (expert == 1) { return std::max(std::abs(l), std::abs(u)); }
  if (expert == 3)
    return predict(3, x, y, std::abs(l), std::abs(u), std::abs(read(x - 1, y - 1)),
                   std::abs(read(x - 2, y)), std::abs(read(x, y - 2)));
  CHECK(expert != 4, "Invalid R4 expert");
  if (!x || !y) { return r4Parent(read, x, y, rice, range).predictor; }
  const int64_t plane = int64_t(l) + u - read(x - 1, y - 1);
  return int(std::abs(std::max<int64_t>(std::min(l, u), std::min<int64_t>(std::max(l, u), plane))));
}

template<class Read> inline R4Result r4Predict(int policy, const Read &read, int x, int y, unsigned rice, int range)
{
  CHECK(!r4(policy), "Invalid R4 policy");
  R4Result out;
  int a[5], nz[5], n = 0;
  for (int i = 0; i < 5; ++i)
  {
    a[i] = std::abs(read(x + r4Dx[i], y + r4Dy[i]));
    if (a[i]) { nz[n++] = a[i]; }
  }
  out.current = std::max(a[0], a[1]);
  out.original = guardedLocalPredict(out.current, nz, n, rice, range);
  out.predictor = out.parent = out.original.predictor;
  out.support = n;
  const bool active = !equivalentPredictors(out.parent, out.current);
  if (policy == 17 || policy == 18)
  {
    const bool keep = active && ((out.parent <= 1) == (policy == 17));
    out.predictor = keep ? (policy == 17 ? 0 : out.parent) : out.current;
    out.suppressed = active && !keep;
    return out; // NO search after deleting a candidate class.
  }
  if (policy == 19 || policy == 20)
  {
    if (policy == 19 && (active || equivalentPredictors(out.original.winner, out.current))) { return out; }
    if (policy == 20 && (x < 2 || y < 2)) { out.direction = -1; return out; }
    int weights[5] = {1, 1, 1, 1, 1};
    if (policy == 20)
    {
      const int64_t eh = std::abs(int64_t(a[0]) - a[3]) + std::abs(int64_t(a[1]) - a[2]);
      const int64_t ev = std::abs(int64_t(a[1]) - a[4]) + std::abs(int64_t(a[0]) - a[2]);
      weights[0] = weights[3] = 1 + (eh < ev);
      weights[1] = weights[4] = 1 + (ev < eh);
      out.direction = eh < ev ? 1 : ev < eh ? 2 : 0;
    }
    if (n < 3) { out.predictor = out.current; return out; }
    out.attempted = true;
    int candidates[6] = {0};
    std::copy_n(nz, n, candidates + 1);
    std::sort(candidates, candidates + n + 1);
    int winner = out.current;
    for (int c = 0; c <= n; ++c)
    {
      const int p = candidates[c] <= 1 ? 0 : candidates[c];
      int gain = 0, best = 0;
      for (int i = 0; i < 5; ++i) if (a[i])
      {
        const int d = weights[i] * (syntaxCost(remap(a[i], out.current), rice, range) - syntaxCost(remap(a[i], p), rice, range));
        gain += d; best = std::max(best, d);
      }
      const int h = gain - best;
      const bool better = policy == 19 ? h > 0 && (h > out.margin() || (h == out.margin() && gain > out.gain)) : gain > out.gain;
      if (better) { winner = p; out.gain = gain; out.bestPositive = best; }
    }
    out.accepted = out.margin() > 0;
    out.predictor = out.accepted ? winner : out.current;
    out.rescue = policy == 19 && out.accepted;
    return out;
  }
  // CB/SP: predict each past target using THAT target's earlier neighbors.
  // Same immutable TU Rice/range surrogate for every target, not syntax replay.
  if (n < 3 || (policy == 22 && (!x || !y))) { return out; }
  out.attempted = true;
  int gains[5] = {}, maxima[5] = {};
  const int first = policy == 22 ? 4 : 1, last = policy == 22 ? 4 : 3;
  for (int i = 0; i < 5; ++i) if (a[i])
  {
    const int jx = x + r4Dx[i], jy = y + r4Dy[i];
    const int base = r4Expert(read, jx, jy, rice, range, 0);
    const int baseCost = syntaxCost(remap(a[i], base), rice, range);
    for (int m = first; m <= last; ++m)
    {
      const int p = r4Expert(read, jx, jy, rice, range, m);
      const int d = baseCost - syntaxCost(remap(a[i], p), rice, range);
      gains[m] += d; maxima[m] = std::max(maxima[m], d);
    }
  }
  int winner = 0;
  for (int m = first; m <= last; ++m)
    if (gains[m] > out.gain) { winner = m; out.gain = gains[m]; out.bestPositive = maxima[m]; }
  out.accepted = out.margin() > 0;
  if (out.accepted)
  {
    out.model = winner;
    out.predictor = r4Expert(read, x, y, rice, range, winner);
  }
  return out;
}
}
