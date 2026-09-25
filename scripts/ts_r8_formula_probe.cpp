// Line protocol for comparison with the independently frozen Python reference.
#include "CommonLib/TsR8Prediction.h"
#include <iostream>
#include <vector>
int main()
{
  int mode, limit;
  while (std::cin >> mode >> limit)
  {
    int a[5]; for (auto &v : a) { std::cin >> v; }
    std::vector<int64_t> cf(limit+1), ci(limit+1);
    for (auto &v : cf) { std::cin >> v; }
    for (auto &v : ci) { std::cin >> v; }
    const auto d = TsFixedPrediction::r8Decision(mode,a,limit,[&](int v) { return cf.at(v); },[&](int v) { return ci.at(v); });
    std::cout << d.current << ' ' << d.predictor << ' ' << d.n << ' ' << d.rawWinner << ' ' << d.gain << ' ' << d.margin << ' ' << d.count;
    for (int k = 0; k < d.count; ++k) { std::cout << ' ' << d.candidates[k] << ' ' << d.scores[k] << ' ' << d.regrets[k]; }
    std::cout << '\n';
  }
}
