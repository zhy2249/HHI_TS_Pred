// Frozen R5-20260921-v1. Two independent changes to the unchanged R3-1 parent.
#pragma once
#include "TsR4Prediction.h" // Reuse only the frozen causal R3 primitive/offsets.

namespace TsFixedPrediction
{
struct R5Result
{
  int predictor = 0, current = 0, parent = 0, support = 0;
  int gain = 0, bestPositive = 0;
  bool attempted = false, accepted = false;
  LocalGuardResult original{0, 0};
  int margin() const { return gain - bestPositive; }
};

// read must expose only earlier positions; out-of-TU top/left positions return 0.
// Never reads the current target, uses CABAC state, or persists search-branch q.
template<class Read> inline R5Result r5Predict(int policy, const Read &read, int x, int y, unsigned rice, int range)
{
  CHECK(!r5(policy), "Invalid R5 policy");
  R5Result out;
  int values[5], n = 0;
  for (int i = 0; i < 5; ++i)
  {
    const int a = std::abs(read(x + r4Dx[i], y + r4Dy[i]));
    if (a) { values[n++] = a; }
  }
  out.current = std::max(std::abs(read(x - 1, y)), std::abs(read(x, y - 1)));
  out.original = guardedLocalPredict(out.current, values, n, rice, range);
  out.parent = out.predictor = out.original.predictor;
  out.support = n;
  if (n < 3) { return out; }
  if (policy == 23)
  {
    out.attempted = true;
    out.predictor = out.current;
    int candidates[6] = {0};
    std::copy_n(values, n, candidates + 1);
    std::sort(candidates, candidates + n + 1);
    for (int c = 0; c <= n; ++c)
    {
      const int p = candidates[c] <= 1 ? 0 : candidates[c];
      if (equivalentPredictors(p, out.current)) { continue; }
      int gain = 0, best = 0;
      for (int i = 0; i < n; ++i)
      {
        const int d = syntaxCost(remap(values[i], out.current), rice, range) -
                      syntaxCost(remap(values[i], p), rice, range);
        gain += d; best = std::max(best, d);
      }
      const int h = gain - best;
      // Strict H>0; H then G; sorted candidates retain identity then smaller p ties.
      // Unlike R4-3, this also reranks already ACCEPTED parent predictions.
      if (h > 0 && (h > out.margin() || (h == out.margin() && gain > out.gain)))
      {
        out.predictor = p; out.gain = gain; out.bestPositive = best;
      }
    }
    out.accepted = out.margin() > 0; // Means a non-Current robust winner for mode 1.
    return out;
  }
  // Mode 2: no replacement experts. Output can ONLY be the original R3 or Current.
  if (equivalentPredictors(out.parent, out.current)) { return out; }
  out.attempted = true;
  for (int i = 0; i < 5; ++i)
  {
    const int jx = x + r4Dx[i], jy = y + r4Dy[i];
    const int a = std::abs(read(jx, jy));
    if (!a) { continue; }
    // Predict historical target j from ITS predecessors, never including q_j.
    // Fixed R3 primitive, not recursive R5; same immutable TU Rice/range proxy.
    const auto past = r4Parent(read, jx, jy, rice, range);
    const int pastCurrent = std::max(std::abs(read(jx - 1, jy)), std::abs(read(jx, jy - 1)));
    const int d = syntaxCost(remap(a, past.predictor), rice, range) -
                  syntaxCost(remap(a, pastCurrent), rice, range);
    out.gain += d; out.bestPositive = std::max(out.bestPositive, d);
  }
  out.accepted = out.margin() > 0; // Means an accepted Current veto for mode 2.
  if (out.accepted) { out.predictor = out.current; }
  return out;
}
}
