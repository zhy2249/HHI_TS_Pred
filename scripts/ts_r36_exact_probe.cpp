// Pure integer predictor checks. Never invokes EncoderApp/DecoderApp or I/O coding.
#include "CommonLib/TsR6Prediction.h"
#include "CommonLib/TsR36Exact.h"
#include <algorithm>
#include <array>
#include <cstdint>
#include <iostream>
#include <random>
#include <stdexcept>
#include <string>

namespace
{
using namespace TsFixedPrediction;
struct Counts
{
  uint64_t patterns = 0, guards = 0, predictors = 0;
  uint64_t sparseCurrentOne = 0, denseCanonicalZero = 0;
  uint64_t guardAccepted = 0, identityRejected = 0, nonzeroRejected = 0;
  uint64_t duplicateAccepted = 0, rawTieCurrent = 0, tieCurrentRetained = 0;
  uint64_t rejectionFallback = 0;
};

[[noreturn]] void fail(const char *what, int current, const int *nz, int n, unsigned rice, int range)
{
  std::cerr << what << " current=" << current << " n=" << n << " rice=" << rice << " range=" << range << " nz=";
  for (int j = 0; j < n; ++j) { std::cerr << nz[j] << ','; }
  std::cerr << '\n';
  throw std::runtime_error("R3/R6 exact predictor mismatch");
}

LocalGuardResult checkGuard(Counts &counts, int current, const int *nz, int n, unsigned rice, int range)
{
  const auto old = guardedLocalPredict(current, nz, n, rice, range);
  const auto now = r36Guard(current, nz, n, rice, range);
  ++counts.guards;
  if (now.predictor != old.predictor || now.winner != old.winner || now.gain != old.gain ||
      now.bestPositive != old.bestPositive || now.margin() != old.margin())
    fail("guard fields", current, nz, n, rice, range);
  counts.sparseCurrentOne += n < 3 && current == 1 && now.predictor == 1 && now.winner == 1;
  counts.denseCanonicalZero += n >= 3 && current == 1 && now.predictor == 1 && now.winner == 0;
  return old;
}

void checkPattern(Counts &counts, const int (&h)[5], unsigned rice, int range)
{
  ++counts.patterns;
  const int current = std::max(h[0], h[1]);
  int nz[5], n = 0;
  for (int value : h) { if (value) { nz[n++] = value; } }
  const auto guard = checkGuard(counts, current, nz, n, rice, range);
  const bool proposed = !equivalentPredictors(current, guard.winner);
  const bool rejected = n >= 3 && proposed && guard.margin() <= 0;
  counts.guardAccepted += proposed && guard.margin() > 0;
  counts.identityRejected += rejected && guard.winner <= 1;
  counts.nonzeroRejected += rejected && guard.winner > 1;
  bool duplicate = false;
  for (int i = 0; i < n; ++i)
    for (int j = i + 1; j < n; ++j) { duplicate |= nz[i] == nz[j]; }
  counts.duplicateAccepted += duplicate && proposed && guard.margin() > 0;

  const auto cost = [&](int p) {
    int total = 0;
    for (int i = 0; i < n; ++i) { total += syntaxCost(remap(nz[i], p), rice, range); }
    return total;
  };
  bool rawTie = false;
  if (n >= 3 && !proposed)
  {
    const int score = cost(current);
    for (int i = -1; i < n; ++i)
    {
      const int p = i < 0 || nz[i] <= 1 ? 0 : nz[i];
      rawTie |= !equivalentPredictors(current, p) && cost(p) == score;
    }
  }
  counts.rawTieCurrent += rawTie;
  // A signed spatial reference exercises abs() in the unchanged R6 wrapper.
  // Query is (2,2), with h = L,U,D,LL,UU. No current coefficient is read.
  const auto read = [&](int x, int y) {
    if (x == 1 && y == 2) { return -h[0]; }
    if (x == 2 && y == 1) { return h[1]; }
    if (x == 1 && y == 1) { return -h[2]; }
    if (x == 0 && y == 2) { return h[3]; }
    if (x == 2 && y == 0) { return -h[4]; }
    return 0;
  };
  for (int policy : {13, 14, 25, 26, 27, 28, 29, 30, 31})
  {
    const int expected = policy < 25 ? guard.predictor : r6Predict(policy, read, 2, 2, rice, range).predictor;
    const int actual = r36Predict(policy, h, rice, range);
    ++counts.predictors;
    if (actual != expected)
    {
      std::cerr << "policy=" << policy << " actual=" << actual << " expected=" << expected << '\n';
      fail("predictor", current, nz, n, rice, range);
    }
    if (policy == 26)
    {
      counts.rejectionFallback += rejected && actual == 0;
      counts.tieCurrentRetained += rawTie && current > 1 && actual == current;
    }
  }
}

void exhaustive(Counts &counts)
{
  // 8^5 supports retain repeated positions, zero slots and every sparse L/U case.
  for (int code = 0; code < 32768; ++code)
  {
    int h[5], v = code;
    for (int &a : h) { a = v % 8; v /= 8; }
    checkPattern(counts, h, 1, 15);
  }
}

void randomPatterns(Counts &counts)
{
  std::mt19937 rng(3612026);
  for (int trial = 0; trial < 40000; ++trial)
  {
    const int range = (trial & 1) ? 20 : 15;
    const unsigned rice = 1 + ((trial / 2) % 8);
    const int limit = 1 << range;
    const int edge[] = {0, 1, 2, 3, 4, 7, 8, 9, 10, 11, 12, 13, 31, 32, 33,
                       255, 256, 257, limit - 1, limit};
    int h[5];
    for (int &a : h)
      a = (rng() & 3) ? edge[rng() % (sizeof(edge) / sizeof(edge[0]))] : int(rng() % (limit + 1));
    checkPattern(counts, h, rice, range);
  }
  // Exact boundaries in the limited Golomb-Rice escape domain and both parities.
  for (int range : {15, 20})
    for (unsigned rice = 1; rice <= 8; ++rice)
    {
      for (int a : {1, 2, 9, 10, 11, 12, 10 + (10 << rice), (1 << range) - 1, 1 << range})
      {
        const int h[5] = {a, a, std::max(0, a - 1), std::min(1 << range, a + 1), a};
        checkPattern(counts, h, rice, range);
      }
      const unsigned maxPrefix = 32 - COEF_REMAIN_BIN_REDUCTION - range;
      const int cappedLevel = 10 + 2 * (((1 << maxPrefix) - 1 + COEF_REMAIN_BIN_REDUCTION) << rice);
      for (int delta : {-2, -1, 0, 1, 2})
      {
        const int a = cappedLevel + delta;
        if (a <= (1 << range))
        {
          const int h[5] = {a, a, a - 1, a + 1, 1};
          checkPattern(counts, h, rice, range);
        }
      }
    }
}

void independentGuards(Counts &counts)
{
  std::mt19937 rng(3600126);
  for (int trial = 0; trial < 80000; ++trial)
  {
    const int range = (trial & 1) ? 20 : 15;
    const unsigned rice = 1 + ((trial / 2) % 8);
    const int limit = 1 << range;
    const int n = (trial / 16) % 6;
    int nz[5];
    for (int j = 0; j < n; ++j)
      nz[j] = (rng() & 1) ? 1 + int(rng() % 8) : 1 + int(rng() % limit);
    // Current is intentionally not required to occur in nz; this tests the API,
    // not only the more constrained caller where Current=max(L,U).
    const int current = trial % 7 == 0 ? 1 : trial % 7 == 1 ? 0 : int(rng() % (limit + 1));
    checkGuard(counts, current, nz, n, rice, range);
  }
  for (int n : {0, 1, 2, 3, 4, 5})
  {
    const int nz[] = {1, 1, 1, 1, 1};
    checkGuard(counts, 1, nz, n, 1, 15);
  }
}

void output(const Counts &c)
{
  std::cout << "{\"patterns\":" << c.patterns << ",\"guards\":" << c.guards
            << ",\"predictors\":" << c.predictors
            << ",\"sparse_current_one\":" << c.sparseCurrentOne
            << ",\"dense_canonical_zero\":" << c.denseCanonicalZero
            << ",\"guard_accepted\":" << c.guardAccepted
            << ",\"identity_rejected\":" << c.identityRejected
            << ",\"nonzero_rejected\":" << c.nonzeroRejected
            << ",\"duplicate_accepted\":" << c.duplicateAccepted
            << ",\"raw_tie_current\":" << c.rawTieCurrent
            << ",\"tie_current_retained\":" << c.tieCurrentRetained
            << ",\"rejection_fallback\":" << c.rejectionFallback << "}\n";
}
}

int main(int argc, char **argv)
{
  try
  {
    if (argc != 2) { throw std::runtime_error("Expected exhaustive, random or guards"); }
    Counts counts;
    const std::string action(argv[1]);
    if (action == "exhaustive") { exhaustive(counts); }
    else if (action == "random") { randomPatterns(counts); }
    else if (action == "guards") { independentGuards(counts); }
    else { throw std::runtime_error("Unknown probe action"); }
    output(counts);
    return 0;
  }
  catch (const std::exception &e)
  {
    std::cerr << e.what() << '\n';
    return 1;
  }
}
