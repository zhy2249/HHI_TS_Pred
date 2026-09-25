// Independent scoring and scope checks; artificial templates, not video tuning.
#include "TsR6Prediction.h"
#include <array>
#include <iostream>
#include <random>
#include <stdexcept>
#include <vector>
using namespace TsFixedPrediction;
#define require(ok) do { if (!(ok)) throw std::runtime_error("R6 design mismatch line " + std::to_string(__LINE__)); } while(false)
static int reference(int mode, const std::array<int,5> &a, unsigned rice, int range)
{
  std::vector<int> nz, ps{0};
  for(int v:a) if(v) { nz.push_back(v); ps.push_back(v<=1?0:v); }
  const int pc=std::max(a[0],a[1]),n=int(nz.size());
  const auto parent=guardedLocalPredict(pc,nz.data(),n,rice,range);
  const bool proposed=!equivalentPredictors(parent.winner,pc),accepted=proposed && parent.margin()>0;
  if(mode>=29) return n>=3?parent.predictor:n==2 && a[0] && a[1]?
    (mode==29?pc:mode==30?int((int64_t(a[0])+a[1]+1)/2):std::min(a[0],a[1])):0;
  if(n<3) return pc;
  if(mode<=26) return !accepted && (mode==25 || proposed)?0:parent.predictor;
  const auto score=[&](int p) {
    std::vector<int> costs, gains;
    for(int v:nz) { const int c=syntaxCost(remap(v,p),rice,range); costs.push_back(c); gains.push_back(syntaxCost(v,rice,range)-c); }
    int total=0;
    if(mode==27) { std::sort(costs.begin(),costs.end()); for(int i=1;i<n;++i)total+=costs[i]; }
    else { for(int g:gains)total-=g; total+=std::max(0,*std::max_element(gains.begin(),gains.end())); }
    return total;
  };
  int winner=pc,best=score(pc);
  std::sort(ps.begin(),ps.end()); ps.erase(std::unique(ps.begin(),ps.end()),ps.end());
  for(int p:ps) if(score(p)<best) { winner=p; best=score(p); }
  return winner;
}
int main()
{
  constexpr int dx[5]={-1,0,-1,-2,0},dy[5]={0,-1,-1,0,-2};
  {
    const int a[5]={3,2,2,0,0};
    const auto read=[&](int x,int y){for(int k=0;k<5;++k)if(x==2+dx[k]&&y==2+dy[k])return a[k];return 0;};
    const auto r=r6Predict(28,read,2,2,1,15);
    require(r.current==3 && r.parent==3 && r.original.winner==2 && r.original.margin()==0 && r.predictor==2);
  }
  uint64_t tested=0,changed[7]={},mapped[7]={},luMapped[7]={};
  for(int code=0;code<32768;++code)
  {
    int c=code; std::array<int,5>a{}; for(int &v:a){v=c%8;c/=8;}
    const auto read=[&](int x,int y){for(int k=0;k<5;++k)if(x==2+dx[k]&&y==2+dy[k])return a[k]; require(false);return 0;};
    for(unsigned rice:{1u,4u}) for(int mode=25;mode<=31;++mode)
    {
      const auto r=r6Predict(mode,read,2,2,rice,15);
      require(equivalentPredictors(r.predictor,reference(mode,a,rice,15)));
      require(!r.current || r.currentHits>0);
      require(r.support>=0 && r.support<=5);
      if(mode<=28 && r.support<3)require(r.predictor==r.parent);
      if(mode>=29 && r.support>=3)require(r.predictor==r.parent);
      if(mode<=26 && r.parentAccepted)require(r.predictor==r.parent);
      if(mode==26 && !r.proposed)require(r.predictor==r.parent);
      if(!r.support)require(equivalentPredictors(r.predictor,r.current));
      if(mode==29 && r.luOnly)require(r.predictor==r.current);
      changed[mode-25]+=!equivalentPredictors(r.predictor,r.parent);
      bool effective=false;
      for(int target=0;target<=10;++target)
      {
        const int mod=remap(target,r.predictor);
        const int inverse=!mod?0:mod==1 && r.predictor>0?r.predictor:mod-(mod<=r.predictor);
        require(inverse==target);
        effective|=mod!=remap(target,r.parent);
      }
      if(effective && !mapped[mode-25])
      { std::cout<<"witness mode="<<mode-24<<" a=";for(int v:a)std::cout<<v<<',';
        std::cout<<" current="<<r.current<<" parent="<<r.parent<<" pred="<<r.predictor<<'\n'; }
      mapped[mode-25]+=effective;luMapped[mode-25]+=effective && r.luOnly;
      // If sample 1 exists, every candidate has minimum cost 1, so raw trim
      // is just unguarded R2-risk. Otherwise matching p>1 still removes 1.
      if(mode==27 && r.support>=3 && *std::min_element(a.begin(),a.end())>=1)
      {
        for(int p:a)
        {
          int total=0;for(int v:a)total+=syntaxCost(remap(v,p),rice,15);
          require(r6Score(27,p,a.data(),5,rice,15)==total-1);
        }
        if(*std::min_element(a.begin(),a.end())==1)
          require(equivalentPredictors(r.predictor,localPredict(10,r.current,a.data(),5,rice,15)));
      }
      ++tested;
    }
  }
  std::mt19937 rng(20260923);
  for(int trial=0;trial<200;++trial)
  {
    int q[64]; const int levels[]={0,1,2,7,8,9,16,255,32767};
    for(int &v:q) {v=levels[rng()%9];if(rng()%2)v=-v;}
    for(int i=0;i<64;++i)for(int mode=25;mode<=31;++mode)
    {
      const auto read=[&](int x,int y){if(x<0||y<0)return 0;require(x<8&&y<8&&y*8+x<i);return q[y*8+x];};
      const auto r=r6Predict(mode,read,i%8,i/8,1+trial%4,15+trial%2*5);
      std::array<int,5> a{};
      for(int k=0;k<5;++k)a[k]=std::abs(read(i%8+dx[k],i/8+dy[k]));
      require(equivalentPredictors(r.predictor,reference(mode,a,1+trial%4,15+trial%2*5)));
      const auto signs=[&](int x,int y){return -read(x,y);};
      require(r.predictor==r6Predict(mode,signs,i%8,i/8,1+trial%4,15+trial%2*5).predictor);
    }
  }
  for(int i=0;i<7;++i)
  {
    require(mapped[i]>0);
    if(i<=4)require(luMapped[i]==0);
    else require(luMapped[i]>0);
    std::cout<<"mode="<<i+1<<" changed_templates="<<changed[i]<<" effective_templates="<<mapped[i]<<" lu_effective="<<luMapped[i]<<'\n';
  }
  std::cout<<"PASS "<<tested<<" template-policy checks; 89600 causal/sign checks; no BD inference\n";
}
