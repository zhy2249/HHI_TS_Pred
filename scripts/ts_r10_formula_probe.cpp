#include "CommonLib/TsR10Prediction.h"
#include <iostream>
int main()
{
  using namespace TsFixedPrediction;
  int mode;
  while(std::cin>>mode)
  {
    R10Decision d;
    std::cin>>d.validation>>d.distinct; d.count=mode==6?4:3;
    int64_t ci[5][4]{},cf[5][4]{}; int weights[5]{};
    for(int j=0;j<d.validation;++j)
    {
      std::cin>>weights[j];
      for(int e=0;e<d.count;++e) { std::cin>>ci[j][e]>>cf[j][e]; }
    }
    r10Select(mode,d,ci,cf,weights);
    std::cout<<d.expert<<' '<<d.rawExpert<<' '<<d.ciTies<<' '<<d.guardRejected<<'\n';
  }
}
