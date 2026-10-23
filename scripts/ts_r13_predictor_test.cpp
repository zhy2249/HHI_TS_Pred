// R13 pure-function reference probe: no video, quantizer, Writer or Reader I/O.
#include "CommonLib/TsR13Prediction.h"
#include <algorithm>
#include <array>
#include <cstdint>
#include <iostream>
#include <limits>
#include <random>
#include <stdexcept>
#include <string>
#include <vector>

namespace
{
using namespace TsFixedPrediction;

void require(bool condition, const char *message)
{
  if (!condition) { throw std::runtime_error(message); }
}

// Independent limited-escape bin length. It deliberately does not call the
// production syntaxCost/riceLength, score table, or candidate construction.
int referenceCost(unsigned magnitude, unsigned rice, int range)
{
  if (magnitude < 2) { return int(magnitude); }
  int cost = 2;
  for (unsigned threshold : {2u, 4u, 6u, 8u}) { cost += magnitude >= threshold; }
  if (magnitude < 10) { return cost; }
  const uint64_t value = (uint64_t(magnitude) - 10) / 2;
  const uint64_t cutoff = COEF_REMAIN_BIN_REDUCTION;
  if (value < (cutoff << rice)) { return cost + int((value >> rice) + 1 + rice); }
  const unsigned cap = 32 - unsigned(cutoff) - unsigned(range);
  const uint64_t code = (value >> rice) - cutoff;
  if (code >= (UINT64_C(1) << cap) - 1) { return cost + int(cutoff + cap + range); }
  unsigned prefix = 0;
  while (code + 2 > (UINT64_C(1) << (prefix + 1))) { ++prefix; }
  return cost + int(cutoff + 2 * prefix + rice + 1);
}

int64_t referenceLoss(int magnitude, int predictor, unsigned rice, int range)
{
  const auto cost = [&](unsigned value) { return int64_t(referenceCost(value, rice, range)); };
  if (predictor <= 1) { return 168 * cost(unsigned(magnitude)); }
  if (magnitude == predictor) { return 168; }
  const int64_t distance = int64_t(predictor) - magnitude;
  if (distance == -1)
  {
    const int64_t c = cost(unsigned(magnitude));
    return c <= 22 ? 168 * c - 4 * (c - 1) * (c - 1) : 1932;
  }
  if (distance == 1)
  {
    const int64_t c = cost(unsigned(magnitude) + 1);
    return c <= 11 ? 168 * c - 4 * (c - 1) * (c - 1) : 84 * c + 525;
  }
  return 168 * cost(unsigned(magnitude) + unsigned(predictor > magnitude));
}

struct Reference
{
  int n = 0, weightSum = 0, current = 0, predictor = 0;
  int hit = 0, down = 0, up = 0, weightedHit = 0, weightedDown = 0, weightedUp = 0;
  std::vector<int> candidates;
  std::vector<int64_t> scores;
  int64_t best = -1, second = -1;
  bool tied = false;
};

Reference reference(const int (&h)[5], const int (&weights)[5], unsigned rice, int range)
{
  Reference r;
  r.current = r.predictor = std::max(h[0], h[1]);
  for (int j = 0; j < 5; ++j)
  {
    if (h[j]) { ++r.n; r.weightSum += weights[j]; }
  }
  if (r.n >= 3)
  {
    std::vector<int> ordered{0};
    for (int m : h) { if (m > 1) { ordered.push_back(m); } }
    std::sort(ordered.begin(), ordered.end());
    ordered.erase(std::unique(ordered.begin(), ordered.end()), ordered.end());
    const int current = r.current <= 1 ? 0 : r.current;
    r.candidates.push_back(current);
    for (int p : ordered) { if (p != current) { r.candidates.push_back(p); } }
    int bestIndex = 0;
    for (int p : r.candidates)
    {
      int64_t score = 0;
      for (int j = 0; j < 5; ++j)
        if (h[j]) { score += weights[j] * referenceLoss(h[j], p, rice, range); }
      r.scores.push_back(score);
      if (score < r.scores[bestIndex]) { bestIndex = int(r.scores.size()) - 1; }
    }
    r.predictor = r.candidates[bestIndex]; r.best = r.scores[bestIndex];
    for (int i = 0; i < int(r.scores.size()); ++i) if (i != bestIndex)
      if (r.second < 0 || r.scores[i] < r.second) { r.second = r.scores[i]; }
    r.tied = r.second >= 0 && r.second == r.best;
  }
  if (r.predictor > 1)
    for (int j = 0; j < 5; ++j) if (h[j])
    {
      const int64_t distance = int64_t(r.predictor) - h[j];
      if (!distance) { ++r.hit; r.weightedHit += weights[j]; }
      if (distance == -1) { ++r.down; r.weightedDown += weights[j]; }
      if (distance == 1) { ++r.up; r.weightedUp += weights[j]; }
    }
  return r;
}

uint64_t cases = 0, dense = 0, sparse = 0, ties = 0, oldNewDisagree = 0, weightedDisagree = 0;

void check(const int (&h)[5], unsigned rice, int range)
{
  int picks[2]{};
  for (int mode = 1; mode <= 2; ++mode)
  {
    const int weights[5] = {mode == 2 ? 2 : 1, mode == 2 ? 2 : 1, 1, 1, 1};
    const auto expected = reference(h, weights, rice, range);
    const auto actual = r13Decision(mode, h, rice, range);
    require(actual.n == expected.n && actual.weightSum == expected.weightSum, "support/physical weights");
    require(actual.current == expected.current && actual.predictor == expected.predictor, "predictor reference");
    require(r13Predict(mode, h, rice, range) == expected.predictor, "fast predictor vs decision");
    require(actual.scored == (expected.n >= 3), "sparse scoring gate");
    if (actual.scored)
    {
      ++dense;
      require(actual.candidateCount == int(expected.candidates.size()), "candidate count/canonicalization");
      for (int c = 0; c < actual.candidateCount; ++c)
      {
        require(actual.candidates[c] == expected.candidates[c], "candidate order/tie priority");
        require(actual.scores[c] == expected.scores[c], "candidate score");
      }
      require(actual.bestScore == expected.best && actual.secondScore == expected.second, "best/second score");
      require(actual.tiedBest == expected.tied, "tie flag");
      ties += actual.tiedBest;
    }
    else { ++sparse; require(actual.secondScore == -1, "sparse margin must be undefined"); }
    require(actual.hit == expected.hit && actual.down == expected.down && actual.up == expected.up,
            "selected predictor support counts");
    require(actual.weightedHit == expected.weightedHit && actual.weightedDown == expected.weightedDown &&
            actual.weightedUp == expected.weightedUp, "selected predictor weighted support");
    picks[mode - 1] = actual.predictor;
    ++cases;
  }
  weightedDisagree += picks[0] != picks[1];
  int nz[5]{}, n = 0; for (int m : h) { if (m) { nz[n++] = m; } }
  const int old = localPredict(10, std::max(h[0], h[1]), nz, n, rice, range);
  if (n >= 3 && old > 1) { require(picks[0] > 1, "uniform identity selection unexpectedly increased"); }
  oldNewDisagree += old != picks[0];
  // An independently parameterised weighted reference reduces exactly to the
  // production Uniform when all physical weights are one, including sparse.
  const int ones[5] = {1, 1, 1, 1, 1};
  require(reference(h, ones, rice, range).predictor == picks[0], "11111 reduction");
}

void outputCounts()
{
  std::cout << "{\"pass\":true,\"decisions\":" << cases << ",\"dense\":" << dense
            << ",\"sparse\":" << sparse << ",\"ties\":" << ties
            << ",\"old_new_disagree\":" << oldNewDisagree
            << ",\"weighted_disagree\":" << weightedDisagree << "}\n";
}

void query()
{
  int mode, range, h[5]{}; unsigned rice;
  while (std::cin >> mode >> rice >> range >> h[0] >> h[1] >> h[2] >> h[3] >> h[4])
  {
    const auto d = r13Decision(mode, h, rice, range);
    std::cout << "{\"n\":" << d.n << ",\"weight_sum\":" << d.weightSum
              << ",\"current\":" << d.current << ",\"predictor\":" << d.predictor
              << ",\"scored\":" << int(d.scored) << ",\"best\":" << d.bestScore
              << ",\"second\":" << d.secondScore << ",\"tied\":" << int(d.tiedBest)
              << ",\"candidates\":[";
    for (int i = 0; i < d.candidateCount; ++i) { std::cout << (i ? "," : "") << d.candidates[i]; }
    std::cout << "],\"scores\":[";
    for (int i = 0; i < d.candidateCount; ++i) { std::cout << (i ? "," : "") << d.scores[i]; }
    std::cout << "]}\n";
  }
}
}

int main(int argc, char **argv)
{
  try
  {
    const std::string action = argc == 2 ? argv[1] : "";
    if (action == "query") { query(); return 0; }
    if (action == "table")
    {
      for (int c = 1; c <= 512; ++c)
        std::cout << '[' << c << ',' << r13DownScore(c) << ',' << r13UpScore(c) << "]\n";
      return 0;
    }
    if (action == "loss")
    {
      int m, p, range; unsigned rice;
      while (std::cin >> m >> p >> rice >> range) { std::cout << r13Loss168(m, p, rice, range) << '\n'; }
      return 0;
    }
    if (action == "exhaustive")
    {
      for (int input = 0; input < 32768; ++input)
      {
        int h[5]{}, value = input;
        for (int &m : h) { m = value % 8; value /= 8; }
        for (unsigned rice : {0u, 1u, 4u, 8u})
          for (int range : {15, 20}) { check(h, rice, range); }
      }
    }
    else if (action == "random")
    {
      std::mt19937_64 random(130120261022ULL);
      for (int i = 0; i < 20000; ++i)
      {
        const int range = i % 2 ? 15 : 20, limit = 1 << range;
        int h[5]{};
        for (int &m : h)
        {
          const unsigned kind = unsigned(random() % 6);
          m = kind == 0 ? 0 : kind == 1 ? 1 : kind == 2 ? limit :
              kind == 3 ? limit - 1 : int(random() % (limit + 1));
        }
        check(h, unsigned(i % 9), range);
      }
      for (int range : {15, 20})
      {
        const int limit = 1 << range;
        const int values[] = {0, 1, 2, limit - 1, limit};
        for (int input = 0; input < 3125; ++input)
        {
          int h[5]{}, value = input;
          for (int &m : h) { m = values[value % 5]; value /= 5; }
          check(h, unsigned(input % 9), range);
        }
      }
    }
    else { throw std::runtime_error("expected exhaustive, random, query, table or loss"); }
    outputCounts(); return 0;
  }
  catch (const std::exception &e) { std::cerr << e.what() << '\n'; return 1; }
}
