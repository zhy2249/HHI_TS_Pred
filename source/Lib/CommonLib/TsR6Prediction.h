// Frozen R6-20260923-v1: independent dense-bias and sparse-support experiments.
#pragma once
#include "TsFixedPrediction.h"

namespace TsFixedPrediction
{
struct R6Result
{
  int predictor = 0, current = 0, parent = 0, support = 0;
  bool luOnly = false, proposed = false, parentAccepted = false;
  bool attempted = false, scoreTieCurrent = false;
  int currentHits = 0, scoreCurrent = 0, scoreSelected = 0;
  LocalGuardResult original{0, 0};
};

// Lower is better. Mode 27 deletes each predictor's minimum absolute cost.
// Mode 28 adds its largest positive saving vs identity back to total cost:
// this equals a constant minus (sum(savings)-max(0,max(saving))).
inline int r6Score(int policy, int p, const int *a, int n, unsigned rice, int range)
{
  CHECK((policy != 27 && policy != 28) || n < 3, "Invalid R6 score request");
  int sum = 0, minimum = 0x7fffffff, bestSaving = 0;
  for (int i = 0; i < n; ++i)
  {
    const int c = syntaxCost(remap(a[i], p), rice, range);
    sum += c; minimum = std::min(minimum, c);
    bestSaving = std::max(bestSaving, syntaxCost(a[i], rice, range) - c);
  }
  return policy == 27 ? sum - minimum : sum + bestSaving;
}

// Only L,U,D,LL,UU magnitudes; zeros absent/out-of-TU are not samples.
// Repeated values at distinct positions remain separate samples. No q_i read.
template<class Read> inline R6Result r6Predict(int policy, const Read &read, int x, int y, unsigned rice, int range)
{
  CHECK(!r6(policy), "Invalid R6 policy");
  const int a[5] = {std::abs(read(x-1,y)), std::abs(read(x,y-1)),
                   std::abs(read(x-1,y-1)), std::abs(read(x-2,y)), std::abs(read(x,y-2))};
  int nz[5], n = 0;
  for (int v : a) { if (v) { nz[n++] = v; } }
  R6Result out;
  out.current = std::max(a[0], a[1]);
  out.support = n;
  out.luOnly = n == 2 && a[0] && a[1];
  for (int i = 0; i < n; ++i) { out.currentHits += nz[i] == out.current; }
  out.original = guardedLocalPredict(out.current, nz, n, rice, range);
  out.predictor = out.parent = out.original.predictor;
  out.proposed = !equivalentPredictors(out.original.winner, out.current);
  out.parentAccepted = out.proposed && out.original.margin() > 0;
  if (policy >= 29)
  {
    if (n >= 3) { return out; } // Dense R3 is bit-for-bit unchanged.
    out.attempted = true;
    out.predictor = 0;
    if (out.luOnly)
      out.predictor = policy == 29 ? out.current : policy == 30 ?
        int((int64_t(a[0]) + a[1] + 1) / 2) : std::min(a[0], a[1]);
    return out;
  }
  if (n < 3) { return out; } // Dense experiments do not alter sparse fallback.
  out.attempted = true;
  if (policy == 25 || policy == 26)
  {
    // 25 includes winner==Current; 26 isolates a strictly better raw candidate
    // rejected by the guard. Accepted R3 predictions are preserved in both.
    if (!out.parentAccepted && (policy == 25 || out.proposed)) { out.predictor = 0; }
    return out;
  }
  int candidates[6] = {0};
  std::copy_n(nz, n, candidates + 1);
  std::sort(candidates, candidates + n + 1);
  out.predictor = out.current;
  out.scoreCurrent = out.scoreSelected = r6Score(policy, out.current, nz, n, rice, range);
  for (int i = 0; i <= n; ++i)
  {
    const int p = candidates[i] <= 1 ? 0 : candidates[i];
    if (equivalentPredictors(p, out.current)) { continue; }
    const int score = r6Score(policy, p, nz, n, rice, range);
    out.scoreTieCurrent |= score == out.scoreCurrent;
    // Retain the original tie convention to isolate the scoring change.
    if (score < out.scoreSelected) { out.predictor = p; out.scoreSelected = score; }
  }
  return out; // No additional asymmetric R3 guard after symmetric scoring.
}
}
