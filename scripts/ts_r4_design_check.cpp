// Independent frozen algebra oracle, now also compared against R4 implementation.
// Reuses the actual R3 remapping, cost and tie-break; no CTC data are read.
#include "TsFixedPrediction.h"
#include "TsR4Prediction.h"
#include <array>
#include <iostream>
#include <stdexcept>
#include <vector>

using namespace TsFixedPrediction;
struct Score { int gain = 0, best = 0; int margin() const { return gain - best; } };
static Score score(int current, int p, const int *values, int n, unsigned rice, int range)
{
  Score s;
  for (int i = 0; i < n; ++i)
  {
    const int d = syntaxCost(remap(values[i], current), rice, range) - syntaxCost(remap(values[i], p), rice, range);
    s.gain += d;
    s.best = std::max(s.best, d);
  }
  return s;
}
// Maximize H, then G; Current wins H=0, then identity/smaller-p wins a tie.
static int robustWinner(int current, const int *values, int n, unsigned rice, int range)
{
  if (n < 3) { return current; }
  std::vector<int> candidates{0};
  for (int i = 0; i < n; ++i) { candidates.push_back(values[i] <= 1 ? 0 : values[i]); }
  std::sort(candidates.begin(), candidates.end());
  candidates.erase(std::unique(candidates.begin(), candidates.end()), candidates.end());
  int best = current;
  Score bs;
  for (int p : candidates)
  {
    const auto s = score(current, p, values, n, rice, range);
    if (s.margin() > 0 && (s.margin() > bs.margin() ||
        (s.margin() == bs.margin() && s.gain > bs.gain)))
    { best = p; bs = s; }
  }
  return best;
}
static void check(bool ok) { if (!ok) { throw std::runtime_error("R4 design property failed"); } }
int main()
{
  uint64_t samples = 0, rescued = 0, reranked = 0, identity = 0, magnitude = 0;
  bool rescueExample = false, rerankExample = false;
  // L,U,D,LL,UU magnitudes; zeros do not count as nonzero samples.
  for (int code = 0; code < 1048576; ++code)
  {
    std::array<int,5> t{};
    int v = code, nz[5], n = 0;
    for (int &a : t) { a = v % 16; v /= 16; if (a) { nz[n++] = a; } }
    const int current = std::max(t[0],t[1]);
    for (unsigned rice : {1u, 2u, 4u})
    {
      const auto r3 = guardedLocalPredict(current,nz,n,rice,15);
      const bool active3 = !equivalentPredictors(r3.predictor,current);
      // Frozen proposal: preserve ALL R3 accepted predictions. Only complete
      // its fallback search, instead of reranking already accepted choices.
      const int r4 = active3 ? r3.predictor : robustWinner(current,nz,n,rice,15);
      const bool active4 = !equivalentPredictors(r4,current);
      const auto s4 = score(current,r4,nz,n,rice,15);
      check(!active3 || r4 == r3.predictor);
      check(!active4 || (n >= 3 && s4.margin() > 0));
      if (active3) { check(s4.margin() >= r3.margin()); }
      // Two branch ablations retain the original proposal/guard (NO re-search).
      const int onlyIdentity = active3 && r3.predictor <= 1 ? 0 : current;
      const int onlyMagnitude = active3 && r3.predictor > 1 ? r3.predictor : current;
      const auto read = [&](int x, int y) {
        for (int k = 0; k < 5; ++k) if (x == 2 + r4Dx[k] && y == 2 + r4Dy[k]) return t[k];
        return 0;
      };
      check(r4Predict(17, read, 2, 2, rice, 15).predictor == onlyIdentity);
      check(r4Predict(18, read, 2, 2, rice, 15).predictor == onlyMagnitude);
      check(r4Predict(19, read, 2, 2, rice, 15).predictor == r4);
      const bool i = !equivalentPredictors(onlyIdentity,current);
      const bool m = !equivalentPredictors(onlyMagnitude,current);
      check(int(i)+int(m)==int(active3));
      identity += i; magnitude += m;
      const bool rescue = !active3 && active4;
      const bool rerank = active3 && active4 && !equivalentPredictors(r3.predictor,r4);
      rescued += rescue; reranked += rerank; ++samples;
      if ((rescue && !rescueExample) || (rerank && !rerankExample))
      {
        std::cout << (rescue ? "RESCUE" : "RERANK") << " template=";
        for (int a : t) { std::cout << a << ','; }
        std::cout << " rice=" << rice << " Current=" << current << " R2winner=" << r3.winner
                  << " R3H=" << r3.margin() << " R3=" << r3.predictor << " R4=" << r4
                  << " R4G=" << s4.gain << " R4H=" << s4.margin() << '\n';
        rescueExample |= rescue; rerankExample |= rerank;
      }
    }
  }
  std::cout << "COUNTS algebra templates/rice=" << samples << " rescued=" << rescued << " reranked=" << reranked
            << " R3-identity=" << identity << " R3-magnitude=" << magnitude
            << "; artificial enumeration, NOT measured activity or RD gain\n" << std::flush;
  check(rescued && !reranked && identity && magnitude);
  std::cout << "PASS\n";
}
