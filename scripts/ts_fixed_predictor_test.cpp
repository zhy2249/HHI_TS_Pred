// Standalone structural test against the codec's actual grouped scan tables.
#include "CommonLib/Rom.h"
#include "CommonLib/Unit.h"
#include "CommonLib/TsFixedPrediction.h"
#include <iostream>
#include <stdexcept>
#include <vector>

static void require(bool value) { if (!value) { throw std::runtime_error("TS fixed predictor test failed"); } }

int main()
{
  using TsFixedPrediction::predict;
  using namespace TsFixedPrediction;
  const int sample[] = {8, 2, 2, 2, 3};
  require(localPredict(9, 8, sample, 5, 1, 15) == 2);
  require(localPredict(10, 8, sample, 5, 1, 15) == 2);
  require(localPredict(9, 8, sample, 2, 1, 15) == 8);
  const int tie[] = {2, 2, 8, 8, 3};
  require(localPredict(9, 8, tie, 5, 1, 15) == 8);
  const int costs[] = {0, 1, 3, 3, 4, 4, 5, 5, 6, 6, 8, 8};
  for (int a = 0; a < 12; ++a) { require(syntaxCost(a, 1, 15) == costs[a]); }
  const int guarded[] = {8, 2, 2, 2, 2}, identity[] = {4, 2, 1, 1, 1};
  require(guardedLocalPredict(8, sample, 5, 1, 15).predictor == 8);
  require(guardedLocalPredict(8, sample, 5, 1, 15).margin() == 0);
  require(guardedLocalPredict(8, guarded, 5, 1, 15).predictor == 2);
  require(guardedLocalPredict(4, identity, 5, 1, 15).predictor == 0);
  require(guardedLocalPredict(8, guarded, 2, 1, 15).predictor == 8);
  unsigned accepted = 0, rejected = 0;
  // Independent delete-each-fixed-contribution check (not the same max formula).
  for (int l = 1; l <= 8; ++l)
    for (int u = 1; u <= 8; ++u)
      for (int d = 1; d <= 8; ++d)
        for (int ll = 1; ll <= 8; ++ll)
          for (int uu = 1; uu <= 8; ++uu)
          {
            const int values[] = {l, u, d, ll, uu}, current = std::max(l, u);
            const auto result = guardedLocalPredict(current, values, 5, 1, 15);
            require(result.winner == localPredict(10, current, values, 5, 1, 15));
            bool survivesAll = true;
            for (int omit = 0; omit < 5; ++omit)
            {
              int costCurrent = 0, costOther = 0;
              for (int i = 0; i < 5; ++i)
                if (i != omit)
                {
                  costCurrent += syntaxCost(remap(values[i], current), 1, 15);
                  costOther += syntaxCost(remap(values[i], result.winner), 1, 15);
                }
              survivesAll &= costOther < costCurrent;
            }
            require((result.margin() > 0) == survivesAll);
            require(result.predictor == (survivesAll ? result.winner : current));
            accepted += survivesAll;
            rejected += !survivesAll && !equivalentPredictors(current, result.winner);
          }
  require(accepted > 0 && rejected > 0);
  for (int policy : {13, 14, 15, 16})
  {
    require(componentEnabled(policy, true));
    require(componentEnabled(policy, false) == (policy == 13 || policy == 15));
    if (r3Adaptive(policy))
    {
      require(selectedMode(policy, 37, 0, 4) == 1);
      require(selectedMode(policy, 37, 4, 0) == 1);
      require(selectedMode(policy, 37, 4, -2) == 1);
      require(selectedMode(policy, 37, 4, 2) == 0);
      require(selectedMode(policy, 37, 4, 2, false) == (policy == 15 ? 0 : 1));
      require(updateState(policy, 2, 0) == 2); // Certificate, not EWMA, handles stale tiny scores.
    }
  }
  for (int a = 0; a < 128; ++a)
    for (int p = 0; p < 128; ++p)
    {
      const int mapped = remap(a, p);
      const int restored = !mapped ? 0 : mapped == 1 && p > 0 ? p : mapped - (mapped <= p);
      require(restored == a);
      if (p < 2) { require(mapped == a); }
    }
  for (int mode : {11, 12})
  {
    require(selectedMode(mode, 37, 0) == 1 && selectedMode(mode, 37, 1) == 0);
    require(updateState(mode, -8, 1) == -5);
  }
  require(selectedMode(4, 31, 0) == 3 && selectedMode(4, 32, 0) == 3 && selectedMode(4, 33, 0) == 1);
  for (int mode : {6, 7, 8})
  {
    require(selectedMode(mode, 22, 0) == 1);
    require(selectedMode(mode, 22, -1) == 1);
    require(selectedMode(mode, 22, 1) == 3);
  }
  require(selectedMode(8, 33, 100) == 1);
  require(updateState(6, 100, -3) == -3 && updateState(6, -3, 0) == 0);
  require(updateState(7, 8, 0) == 6 && updateState(7, -8, 0) == -6);
  require(updateState(7, -3, 0) == -3 && updateState(7, 32767, 32767) == 32767);
  require(updateState(7, -32767, -32767) == -32767);
  require(proxyCost(0) == 0 && proxyCost(1) == 1 && proxyCost(2) == 3 && proxyCost(3) == 3 && proxyCost(4) == 5);
  require(remap(0, 8) == 0 && remap(8, 8) == 1 && remap(7, 8) == 8 && remap(9, 8) == 9);
  require(predict(5, 2, 2, 3, 8, 8, 3, 12) == 3); // EH=0
  require(predict(5, 2, 2, 3, 8, 8, 1, 8) == 3); // EH=2, EV=5
  require(predict(5, 2, 2, 3, 8, 8, 0, 8) == 8); // EH=3, EV=5 -> fallback
  require(predict(5, 2, 2, 3, 3, 3, 3, 3) == 3); // both zero
  require(predict(2, 2, 2, 3, 8, 8, 0, 0) == 3);
  require(predict(2, 2, 2, 3, 8, 5, 0, 0) == 6);
  require(predict(2, 2, 2, 3, 8, 2, 0, 0) == 8);
  require(predict(3, 2, 2, 3, 8, 8, 3, 12) == 3);
  require(predict(3, 1, 2, 3, 8, 8, 3, 12) == 8);
  require(predict(2, 0, 2, 0, 8, 8, 0, 12) == 8);
  for (int l = 0; l < 16; ++l)
    for (int u = 0; u < 16; ++u)
      for (int d = 0; d < 16; ++d)
        for (int mode = 0; mode < 4; ++mode)
        {
          const int p = predict(mode, 3, 3, l, u, d, (l * 7) % 16, (u * 3) % 16);
          require(p >= 0 && p <= std::max(l, u));
          if (mode) { require(p >= std::min(l, u)); }
        }
  initROM();
  int shapes = 0;
  long long checked = 0;
  for (unsigned wi = 0; wi < gp_sizeIdxInfo->numWidths(); ++wi)
    for (unsigned hi = 0; hi < gp_sizeIdxInfo->numHeights(); ++hi)
    {
      const int w = gp_sizeIdxInfo->sizeFrom(wi), h = gp_sizeIdxInfo->sizeFrom(hi);
      if (w < 2 || h < 2 || w > MAX_NONZERO_TU_SIZE || h > MAX_NONZERO_TU_SIZE) { continue; }
      const auto scan = g_scanOrder[SCAN_GROUPED_4x4][CoeffScanType::DIAG][wi][hi];
      std::vector<int> inverse(w * h, -1);
      bool valid = true;
      for (int s = 0; s < w * h; ++s)
      {
        const int pos = scan[s].idx;
        if (pos < 0 || pos >= w * h || inverse[pos] != -1) { valid = false; break; }
        inverse[pos] = s;
      }
      if (!valid) { continue; } // Not a complete coefficient-group shape.
      ++shapes;
      for (int s = 0; s < w * h; ++s)
      {
        const int pos = scan[s].idx, x = pos % w, y = pos / w;
        const auto before = [&](int dx, int dy) { require(inverse[pos + dx + dy * w] < s); ++checked; };
        if (x) { before(-1, 0); }
        if (y) { before(0, -1); }
        if (x && y) { before(-1, -1); }
        if (x >= 2) { before(-2, 0); }
        if (y >= 2) { before(0, -2); }
      }
    }
  destroyROM();
  require(shapes > 0 && checked > 0);
  std::cout << "PASS: predictor examples/ranges; " << shapes << " native scan shapes, "
            << checked << " causal neighbour checks\n";
}
