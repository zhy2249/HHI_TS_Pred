#include "CommonLib/TsR9Prediction.h"
#include <iostream>
int main()
{
  int mode,limit;
  while(std::cin>>mode>>limit)
  {
    int a[5]; for(int &v:a) { std::cin>>v; }
    std::vector<int64_t> cost(limit+1); for(auto &v:cost) { std::cin>>v; }
    const auto d=TsFixedPrediction::r9Decision(mode,a,limit,[&](int v){return cost.at(v);});
    std::cout<<d.action.predictor<<' '<<d.action.protect<<' '<<d.score<<' '<<d.n<<' '<<d.axis<<' '<<d.axisCost<<'\n';
  }
}
