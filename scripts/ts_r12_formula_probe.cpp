#include "CommonLib/TsR12Prediction.h"
#include <iostream>
int main()
{
  using namespace TsFixedPrediction;
  char kind;
  while(std::cin>>kind)
  {
    if(kind=='S')
    {
      int mode; R12Decision d; std::cin>>mode>>d.validation; d.count=mode==3?4:3;
      for(int j=0;j<d.validation;++j)
      {
        int effective; std::cin>>d.slots[j]>>effective; d.informative[j]=effective;
        for(int e=0;e<d.count;++e) { std::cin>>d.ciRows[j][e]>>d.cfRows[j][e]; }
      }
      r12Select(mode,d); std::cout<<d.expert<<' '<<d.baseExpert<<' '<<d.ciTies<<' '<<d.legalDeletes<<'\n';
    }
    else
    {
      int mode,h[5],weights[5]; std::cin>>mode;
      for(int &v:h) { std::cin>>v; } for(int &v:weights) { std::cin>>v; }
      const auto ci=[](int a){return int64_t(syntaxCost(a,1,15))<<SCALE_BITS;};
      const auto d=r12Integer(h,ci,weights);
      std::cout<<d.predictor(mode)<<' '<<d.raw<<' '<<d.gain<<' '<<(mode==8?d.full:mode==11?d.soft:0)<<'\n';
    }
  }
}
