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
