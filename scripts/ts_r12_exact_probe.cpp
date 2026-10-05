// Pure R12 exact-path regression and microbenchmark; never runs video coding.
#include "CommonLib/TsR12Exact.h"
#include <chrono>
#include <cstdlib>
#include <iomanip>
#include <iostream>
#include <random>
#include <stdexcept>
#include <string>
#include <vector>

namespace
{
using namespace TsFixedPrediction;
using Clock = std::chrono::steady_clock;
uint64_t checks = 0;

void require(bool ok, const std::string &where)
{
  if (!ok) { throw std::runtime_error(where); }
}

uint64_t mix(uint64_t x)
{
  x ^= x >> 30; x *= UINT64_C(0xbf58476d1ce4e5b9);
  x ^= x >> 27; x *= UINT64_C(0x94d049bb133111eb);
  return x ^ (x >> 31);
}

// Nonnegative, nonmonotonic integer costs, including values well above int32.
// Headroom covers all five samples, W22111 and identity-trim without overflow.
int64_t arbitraryCost(int a, uint64_t seed)
{
  return a ? int64_t((mix(uint64_t(a) ^ seed) & ((UINT64_C(1) << 43) - 1)) +
                    (UINT64_C(1) << 38)) : 0;
}

template<class CF, class CI>
void compareExperts(const int (&h)[5], int limit, const CF &cf, const CI &ci)
{
  for (int mode = 0; mode <= 12; ++mode)
  {
    const auto reference = r12Experts(mode, h, limit, cf, ci);
    int cfCalls = 0, ciCalls = 0;
    const auto fast = r12FastExperts(mode, h, limit,
      [&](int a) { ++cfCalls; return cf(a); },
      [&](int a) { ++ciCalls; return ci(a); });
    for (int e = 0; e < (mode == 3 ? 4 : 3); ++e)
    {
      require(fast[e] == reference[e], "expert/action mismatch mode=" + std::to_string(mode) +
              " expert=" + std::to_string(e) + " case=" + std::to_string(checks));
    }
    int nonzero = 0; for (int v : h) { nonzero += v != 0; }
    require(cfCalls <= 11 && ciCalls <= 11, "bounded cost-call regression");
    if (nonzero < 3) { require(!cfCalls && !ciCalls, "sparse expert unexpectedly evaluated cost"); }
    ++checks;
  }
}

void expertsSmall()
{
  for (int input = 0; input < 7776; ++input)
  {
    int h[5]{}, x = input;
    for (int &v : h) { v = x % 6; x /= 6; }
    const auto integer = [](int a) { return int64_t(syntaxCost(a, 1, 15)) << SCALE_BITS; };
    compareExperts(h, 6, integer, integer);
    // A fully tied model stresses canonical 0/1 and Current-first ordering.
    const auto flat = [](int a) { return a ? INT64_C(1) << 40 : 0; };
    compareExperts(h, 6, flat, flat);
    compareExperts(h, 6,
      [&](int a) { return arbitraryCost(a, UINT64_C(0xabc) + input); },
      [&](int a) { return arbitraryCost(a, UINT64_C(0xdef) + input); });
  }
}

void expertsRandom()
{
  std::mt19937_64 random(1203100301);
  const int limits[] = {1, 2, 3, 6, 15, 255, 1023, 32768};
  for (int input = 0; input < 20000; ++input)
  {
    const int limit = limits[input % 8];
    int h[5]{};
    for (int &v : h)
    {
      const auto kind = random() % 5;
      v = kind == 0 ? 0 : kind == 1 ? 1 : kind == 2 ? limit : int(random() % (limit + 1));
    }
    const auto cfSeed = random(), ciSeed = random();
    compareExperts(h, limit,
      [&](int a) { require(a >= 0 && a <= limit, "CF out of magnitude range"); return arbitraryCost(a, cfSeed); },
      [&](int a) { require(a >= 0 && a <= limit, "CI out of magnitude range"); return arbitraryCost(a, ciSeed); });
  }
  // Exhaustive extremes also cover repeated largest value and identity at limit=1.
  const int values[] = {0, 1, 2, 32767, 32768};
  for (int input = 0; input < 3125; ++input)
  {
    int h[5]{}, x = input; for (int &v : h) { v = values[x % 5]; x /= 5; }
    const auto cf = [](int a) { return arbitraryCost(a, 77); };
    const auto ci = [](int a) { return int64_t(syntaxCost(a, 8, 15)) << SCALE_BITS; };
    compareExperts(h, 32768, cf, ci);
  }
}

// Independent legal CF mask, used to verify *which* callbacks occur, not only
// the returned winner. Zero means no CF is needed, including singleton pools.
int expectedCFMask(int mode, const R12Decision &d)
{
  if (!d.validation) { return 0; }
  std::array<int64_t, 4> scores{};
  for (int j = 0; j < d.validation; ++j)
    for (int e = 0; e < d.count; ++e)
      scores[e] += d.ciRows[j][e] * ((mode == 9 || mode == 12) ? R12_WEIGHTS[d.slots[j]] : 1);
  if (mode == 5)
  {
    std::array<int64_t, 3> direct{}; bool present = false;
    for (int j = 0; j < d.validation; ++j) if (d.slots[j] == 0 || d.slots[j] == 1)
    {
      present = true;
      for (int e = 0; e < 3; ++e) { direct[e] += d.ciRows[j][e]; }
    }
    const auto minimum = *std::min_element(direct.begin(), direct.end());
    if (present && std::count(direct.begin(), direct.end(), minimum) == 1) { return 0; }
  }
  const auto minimum = *std::min_element(scores.begin(), scores.begin() + 3);
  int pool = 0, ties = 0;
  for (int e = 0; e < 3; ++e) { if (scores[e] == minimum) { pool |= 1 << e; ++ties; } }
  if (ties == 1 && (mode == 1 || mode == 2 || mode == 3 || mode == 4 || mode == 6))
  {
    if (mode == 1 || mode == 2 || mode == 6)
      for (int e = mode == 1 ? 0 : 2; e < 3; ++e)
        if (scores[e] > minimum && scores[e] - minimum <= R12_Q) { pool |= 1 << e; }
    if (mode == 3 && scores[3] >= minimum && scores[3] - minimum <= R12_Q) { pool |= 8; }
    int effective = 0;
    for (int j = 0; j < d.validation; ++j) { effective += d.informative[j]; }
    if ((mode == 4 || mode == 6) && effective >= 2)
      for (int deleted = 0; deleted < d.validation; ++deleted) if (d.informative[deleted])
      {
        std::array<int64_t, 3> remaining{};
        for (int j = 0; j < d.validation; ++j) if (j != deleted)
          for (int e = 0; e < 3; ++e) { remaining[e] += d.ciRows[j][e]; }
        const auto best = *std::min_element(remaining.begin(), remaining.end());
        for (int e = 0; e < 3; ++e) { if (remaining[e] == best) { pool |= 1 << e; } }
      }
  }
  return (pool & (pool - 1)) ? pool : 0;
}

void compareSelector(int mode, R12Decision d, int expected = -1)
{
  d.count = mode == 3 ? 4 : 3;
  const int legalMask = expectedCFMask(mode, d);
  int calls[4]{};
  const int selected = r12FastSelect(mode, d.validation, d.ciRows, d.slots.data(), d.informative.data(),
    [&](int e) {
      require(e >= 0 && e < d.count && (legalMask & (1 << e)), "excluded expert CF evaluated");
      ++calls[e];
      int64_t total = 0;
      for (int j = 0; j < d.validation; ++j)
        total += d.cfRows[j][e] * ((mode == 9 || mode == 10 || mode == 12) ? R12_WEIGHTS[d.slots[j]] : 1);
      return total;
    });
  r12Select(mode, d);
  require(selected == d.expert, "selector mismatch mode=" + std::to_string(mode) +
          " case=" + std::to_string(checks));
  if (expected >= 0) { require(selected == expected, "specified selector edge case failed"); }
  for (int e = 0; e < 4; ++e)
    require(calls[e] == int(bool(legalMask & (1 << e))), "missing/repeated lazy CF call");
  ++checks;
}

void selectorsRandom()
{
  std::mt19937_64 random(1203100302);
  for (int input = 0; input < 16000; ++input)
  {
    R12Decision d; d.validation = int(random() % 6);
    std::array<int, 5> slots{{0, 1, 2, 3, 4}}; std::shuffle(slots.begin(), slots.end(), random);
    for (int j = 0; j < d.validation; ++j)
    {
      d.slots[j] = slots[j]; d.informative[j] = random() % 2;
      for (int e = 0; e < 4; ++e)
      {
        const int64_t offset = input % 3 ? 0 : INT64_C(1) << 42;
        d.ciRows[j][e] = offset + int64_t(random() % 6) * R12_Q + (input % 5 ? 0 : int64_t(random() % 3));
        d.cfRows[j][e] = offset + int64_t(random() % 8) * 17000;
      }
    }
    for (int mode = 0; mode <= 12; ++mode) { compareSelector(mode, d); }
  }
}

R12Decision oneRow(std::array<int64_t, 4> ci, std::array<int64_t, 4> cf, int slot = 2)
{
  R12Decision d; d.validation = 1; d.slots[0] = slot; d.ciRows[0] = ci; d.cfRows[0] = cf;
  return d;
}

void selectorsEdges()
{
  for (int mode = 0; mode <= 12; ++mode) { compareSelector(mode, {}, 0); }
  // Exact boundary Q is eligible, Q+1 is not. Mode 2 does not admit B.
  const auto near = oneRow({{0, R12_Q, R12_Q + 1, 0}}, {{100, 20, 1, 1}});
  compareSelector(1, near, 1); compareSelector(2, near, 0);
  compareSelector(3, near, 3);
  auto d = near; d.ciRows[0][3] = -1;
  compareSelector(3, d, 0); // Negative D gap is outside the specified pool.
  d.ciRows[0][3] = R12_Q + 1; compareSelector(3, d, 0);
  d.ciRows[0][3] = R12_Q; compareSelector(3, d, 3);
  // An original CI tie is protected against C near/LOO and D admission.
  d = oneRow({{0, 0, R12_Q, 0}}, {{100, 50, 0, 0}});
  for (int mode : {1, 2, 3, 4, 6}) { compareSelector(mode, d, 1); }
  d = oneRow({{2 * R12_Q, 0, R12_Q, 0}}, {{5, 10, 5, 0}});
  compareSelector(1, d, 2); // Candidate A outside near pool, C wins.
  d.ciRows[0][0] = R12_Q; compareSelector(1, d, 0); // Improving challenger tie: A first.
  d.cfRows[0] = {{10, 10, 10, 0}}; compareSelector(1, d, 1); // CF tie keeps incumbent.
  // CI collision still forms an informative mapped row; only the supplied
  // mapped-difference flag controls whether a row participates in deletion.
  d = {}; d.validation = 2; d.slots = {{2, 3, 0, 0, 0}};
  d.ciRows[0] = {{0, 4 * R12_Q, 4 * R12_Q, 0}};
  d.ciRows[1] = {{2 * R12_Q, 0, 3 * R12_Q, 0}};
  d.cfRows[0] = {{1, 50, 100, 0}}; d.cfRows[1] = {{100, 1, 100, 0}};
  d.informative[0] = d.informative[1] = true;
  compareSelector(4, d, 1); // Full-V0 CF picks B, not per-deletion CF.
  d.informative[1] = false; compareSelector(4, d, 0); // neff<2 protects A.
  // Direct unique ignores the otherwise-favoured full-V0 and all CF.
  d = {}; d.validation = 2; d.slots = {{0, 3, 0, 0, 0}};
  d.ciRows[0] = {{3, 1, 2, 0}}; d.ciRows[1] = {{0, 100, 0, 0}};
  d.cfRows[0] = {{0, 999, 0, 0}}; compareSelector(5, d, 1);
  d.ciRows[0][2] = 1; compareSelector(5, d, 2); // direct tie reverts to full CI.
  // W22111 applies to spatial slots, not the compact row index.
  d = {}; d.validation = 2; d.slots = {{3, 0, 0, 0, 0}};
  d.ciRows[0] = {{0, 6, 30, 0}}; d.ciRows[1] = {{4, 0, 30, 0}};
  compareSelector(0, d, 0); compareSelector(9, d, 1); compareSelector(12, d, 1);
  d.ciRows[0] = {{0, 4, 30, 0}}; d.cfRows[0] = {{0, 6, 0, 0}}; d.cfRows[1] = {{4, 0, 0, 0}};
  compareSelector(0, d, 0); compareSelector(10, d, 1);
  // Random tests assert entire callback masks; these edges explicitly pin all
  // zero-call exits: empty, singleton, direct unique, protected tie to singleton.
  for (int mode : {0, 2, 4, 6, 7, 8, 9, 10, 11, 12})
    compareSelector(mode, oneRow({{0, 4 * R12_Q, 5 * R12_Q, 0}}, {{100, 0, 0, 0}}), 0);
}

struct BenchInput
{
  int h[5]{};
  uint64_t seed = 0;
  R12Decision selector;
};

void benchmark()
{
  std::mt19937_64 random(1203100303);
  std::vector<BenchInput> inputs(4096);
  for (auto &input : inputs)
  {
    for (int &v : input.h) { v = random() % 4 ? int(random() % 40) : 0; }
    input.seed = random(); input.selector.validation = 5;
    for (int j = 0; j < 5; ++j)
    {
      input.selector.slots[j] = j; input.selector.informative[j] = random() % 2;
      for (int e = 0; e < 4; ++e)
      {
        input.selector.ciRows[j][e] = (random() % 5) * R12_Q;
        input.selector.cfRows[j][e] = random() % (8 * R12_Q);
      }
    }
  }
  std::cout << "{\"scope\":\"pure_function_microbenchmark_not_encoding_speed\","
               "\"fractional_cost_model\":\"synthetic_nonmonotone_hash_not_RateTable\",\"modes\":[";
  for (int mode : {1, 3, 5, 9, 11, 12})
  {
    const auto run = [&](bool exact, bool experts) {
      uint64_t hash = UINT64_C(1469598103934665603); const auto start = Clock::now();
      for (int repeat = 0; repeat < 8; ++repeat)
        for (const auto &input : inputs)
        {
          if (experts)
          {
            const auto cf = [&](int a) { return arbitraryCost(a, input.seed); };
            const auto ci = [](int a) { return int64_t(syntaxCost(a, 1, 15)) << SCALE_BITS; };
            const auto actions = exact ? r12FastExperts(mode, input.h, 32768, cf, ci) :
                                         r12Experts(mode, input.h, 32768, cf, ci);
            for (int e = 0; e < (mode == 3 ? 4 : 3); ++e)
              hash = (hash ^ uint64_t(actions[e].predictor)) * UINT64_C(1099511628211);
          }
          else
          {
            auto d = input.selector; d.count = mode == 3 ? 4 : 3;
            int winner = 0;
            if (exact)
              winner = r12FastSelect(mode, d.validation, d.ciRows, d.slots.data(), d.informative.data(), [&](int e) {
                int64_t sum = 0;
                for (int j = 0; j < d.validation; ++j)
                  sum += d.cfRows[j][e] * ((mode == 9 || mode == 10 || mode == 12) ? R12_WEIGHTS[d.slots[j]] : 1);
                return sum;
              });
            else { r12Select(mode, d); winner = d.expert; }
            hash = (hash ^ uint64_t(winner)) * UINT64_C(1099511628211);
          }
        }
      return std::make_pair(std::chrono::duration<double>(Clock::now() - start).count(), hash);
    };
    if (mode != 1) { std::cout << ','; }
    std::cout << "{\"mode\":" << mode;
    for (bool experts : {true, false})
    {
      const auto warmOld = run(false, experts), warmNew = run(true, experts);
      require(warmOld.second == warmNew.second, "benchmark warmup output mismatch");
      std::array<double, 4> oldTimes{}, newTimes{};
      for (int trial = 0; trial < 4; ++trial)
      {
        const auto first = run(trial % 2, experts), second = run(!(trial % 2), experts);
        require(first.second == second.second && first.second == warmOld.second, "benchmark output mismatch");
        oldTimes[trial] = trial % 2 ? second.first : first.first;
        newTimes[trial] = trial % 2 ? first.first : second.first;
      }
      std::sort(oldTimes.begin(), oldTimes.end()); std::sort(newTimes.begin(), newTimes.end());
      const double oldMedian = (oldTimes[1] + oldTimes[2]) / 2, newMedian = (newTimes[1] + newTimes[2]) / 2;
      std::cout << ",\"" << (experts ? "experts" : "selector") << "\":{\"reference_s\":" << oldMedian
                << ",\"optimized_s\":" << newMedian << ",\"optimized_over_reference\":" << newMedian / oldMedian
                << ",\"checksum\":\"" << warmOld.second << "\"}";
    }
    std::cout << '}';
  }
  std::cout << "]}\n";
}
}

int main(int argc, char **argv)
{
  try
  {
    require(argc == 2, "usage: ts_r12_exact_probe --experts-small|--experts-random|--selectors-random|--selectors-edges|--benchmark");
    const std::string task = argv[1];
    if (task == "--benchmark") { benchmark(); return 0; }
    if (task == "--experts-small") { expertsSmall(); }
    else if (task == "--experts-random") { expertsRandom(); }
    else if (task == "--selectors-random") { selectorsRandom(); }
    else if (task == "--selectors-edges") { selectorsEdges(); }
    else { throw std::runtime_error("unknown task " + task); }
    std::cout << "{\"task\":\"" << task << "\",\"comparisons\":" << checks << ",\"pass\":true}\n";
    return 0;
  }
  catch (const std::exception &error) { std::cerr << error.what() << '\n'; return 1; }
}
