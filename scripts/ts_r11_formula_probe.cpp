#include "CommonLib/TsR11Prediction.h"
#include <iostream>
int main()
{
  using namespace TsFixedPrediction;
  int mode;
  while(std::cin>>mode)
  {
    R11Decision d; d.count=r11ExpertCount(mode);
    std::cin>>d.targets.count>>d.effective;
    for(int e=0;e<d.count;++e) { int p; std::cin>>p; d.actions[e]=canonicalAction(p); }
    for(int e=1;e<d.count;++e)
    { bool unique=true; for(int k=0;k<e;++k) { unique &= d.actions[e]!=d.actions[k]; } d.distinct+=unique; }
    R11Loss ci{},cf{};
    for(int j=0;j<d.targets.count;++j)
      for(int e=0;e<d.count;++e) { std::cin>>ci[j][e]>>cf[j][e]; }
    r11Select(mode,d,ci,cf);
    std::cout<<d.expert<<' '<<d.rawExpert<<' '<<d.ciTies<<' '<<d.fallback<<'\n';
  }
}
