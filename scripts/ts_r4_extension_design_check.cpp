// Independent frozen R4-4/5/6 prototypes compared against codec implementation.
// Uses artificial coefficient grids, never real CTC data or unquantized samples.
#include "TsFixedPrediction.h"
#include "TsR4Prediction.h"
#include <array>
#include <iostream>
#include <random>
#include <stdexcept>
#include <vector>

using namespace TsFixedPrediction;
static void check(bool ok) { if (!ok) { throw std::runtime_error("R4 extension property failed"); } }
struct Grid
{
  static constexpr int w = 8, h = 8;
  std::array<int,w*h> q{};
  int value(int x,int y) const { return x < 0 || y < 0 ? 0 : q[y*w+x]; }
};
static constexpr int dx[5] = {-1,0,-1,-2,0};
static constexpr int dy[5] = {0,-1,-1,0,-2};
static int current(const Grid &g,int x,int y)
{ return std::max(std::abs(g.value(x-1,y)),std::abs(g.value(x,y-1))); }
static int r3(const Grid &g,int x,int y,unsigned rice)
{
  int a[5],n=0;
  for(int i=0;i<5;++i) { int v=std::abs(g.value(x+dx[i],y+dy[i])); if(v) a[n++]=v; }
  return guardedLocalPredict(current(g,x,y),a,n,rice,15).predictor;
}
// 0=R3, 1=Current, 2=NoPred, 3=original directional, 4=signed plane.
static int expert(const Grid &g,int x,int y,unsigned rice,int mode)
{
  if(mode==0) return r3(g,x,y,rice);
  if(mode==1) return current(g,x,y);
  if(mode==2) return 0;
  if(mode==3) return predict(3,x,y,std::abs(g.value(x-1,y)),std::abs(g.value(x,y-1)),
    std::abs(g.value(x-1,y-1)),std::abs(g.value(x-2,y)),std::abs(g.value(x,y-2)));
  check(mode==4);
  if(!x || !y) return r3(g,x,y,rice);
  const int l=g.value(x-1,y),u=g.value(x,y-1),d=g.value(x-1,y-1);
  const long long pred=std::max<long long>(std::min(l,u),std::min<long long>(std::max(l,u),(long long)l+u-d));
  return int(std::abs(pred));
}
static int directionalRisk(const Grid &g,int x,int y,unsigned rice)
{
  if(x<2 || y<2) return r3(g,x,y,rice);
  int a[5],n=0;
  for(int i=0;i<5;++i) { a[i]=std::abs(g.value(x+dx[i],y+dy[i])); n += a[i]>0; }
  const int pc=current(g,x,y);
  if(n<3) return pc;
  const int eh=std::abs(a[0]-a[3])+std::abs(a[1]-a[2]);
  const int ev=std::abs(a[1]-a[4])+std::abs(a[0]-a[2]);
  const int wh=1+(eh<ev),wv=1+(ev<eh);
  const int weights[5]={wh,wv,1,wh,wv};
  std::vector<int> candidates{0};
  for(int v:a) if(v) candidates.push_back(v<=1?0:v);
  std::sort(candidates.begin(),candidates.end());
  candidates.erase(std::unique(candidates.begin(),candidates.end()),candidates.end());
  int best=pc,bg=0,bb=0;
  for(int p:candidates)
  {
    int gain=0,b=0;
    for(int i=0;i<5;++i) if(a[i])
    {
      const int d=weights[i]*(syntaxCost(remap(a[i],pc),rice,15)-syntaxCost(remap(a[i],p),rice,15));
      gain+=d; b=std::max(b,d); // Remove the ENTIRE weighted observation.
    }
    if(gain>bg) { best=p; bg=gain; bb=b; }
  }
  if(eh==ev) check((bg-bb>0?best:pc)==r3(g,x,y,rice));
  return bg-bb>0?best:pc;
}
struct Backtest { int predictor,mode=0,gain=0,bestPositive=0,valid=0; };
static Backtest backtest(const Grid &g,int x,int y,unsigned rice,bool signedOnly)
{
  Backtest out{r3(g,x,y,rice)};
  if(signedOnly && (!x || !y)) return out;
  for(int i=0;i<5;++i) out.valid += g.value(x+dx[i],y+dy[i])!=0;
  if(out.valid<3) return out;
  for(int m:signedOnly?std::vector<int>{4}:std::vector<int>{1,2,3})
  {
    int gain=0,b=0;
    for(int i=0;i<5;++i)
    {
      const int xx=x+dx[i],yy=y+dy[i],a=std::abs(g.value(xx,yy));
      if(!a) continue;
      const int base=expert(g,xx,yy,rice,0),p=expert(g,xx,yy,rice,m);
      const int d=syntaxCost(remap(a,base),rice,15)-syntaxCost(remap(a,p),rice,15);
      gain+=d; b=std::max(b,d);
    }
    if(gain>out.gain) { out.mode=m; out.gain=gain; out.bestPositive=b; }
  }
  if(out.gain-out.bestPositive>0) out.predictor=expert(g,x,y,rice,out.mode);
  else out.mode=0;
  return out;
}
int main()
{
  std::mt19937 rng(20260920);
  std::array<uint64_t,3> changes{},mapped{};
  std::array<uint64_t,4> selectedModels{};
  uint64_t selectedSigned=0;
  uint64_t targets=0;
  for(int trial=0;trial<500;++trial)
  {
    Grid g;
    for(int y=0;y<Grid::h;++y) for(int x=0;x<Grid::w;++x)
      g.q[y*Grid::w+x]=trial%3==0?2*x-3*y+trial%7:trial%3==1?(int(rng()%17)-8):(rng()%3?int(rng()%511)-255:0);
    for(int y=0;y<Grid::h;++y) for(int x=0;x<Grid::w;++x)
    {
      const unsigned rice=1+trial%4;
      const int base=r3(g,x,y,rice);
      const auto l=backtest(g,x,y,rice,false),s=backtest(g,x,y,rice,true);
      ++selectedModels[l.mode]; selectedSigned += s.mode==4;
      const std::array<int,3> p={directionalRisk(g,x,y,rice),l.predictor,s.predictor};
      const auto read = [&](int xx, int yy) { return g.value(xx, yy); };
      for (int m = 0; m < 3; ++m) check(p[m] == r4Predict(20 + m, read, x, y, rice, 15).predictor);
      check(!l.mode || (l.valid>=3 && l.gain-l.bestPositive>0));
      check(!s.mode || (s.valid>=3 && s.gain-s.bestPositive>0));
      check(expert(g,x,y,rice,4)<=current(g,x,y) || !x || !y);
      Grid poisoned=g;
      // Every position not in the strict causal northwest rectangle is poisoned.
      // All implemented primitive offsets are componentwise nonpositive.
      for(int yy=0;yy<Grid::h;++yy) for(int xx=0;xx<Grid::w;++xx)
        if(xx>x || yy>y || (xx==x && yy==y)) poisoned.q[yy*Grid::w+xx]=int(rng()%1023)-511;
      const std::array<int,3> p2={directionalRisk(poisoned,x,y,rice),
        backtest(poisoned,x,y,rice,false).predictor,backtest(poisoned,x,y,rice,true).predictor};
      check(p==p2);
      // Each primitive expert at a historical target must not read its own q.
      Grid self=g; self.q[y*Grid::w+x]=int(rng()%1023)-511;
      for(int m=0;m<=4;++m) check(expert(g,x,y,rice,m)==expert(self,x,y,rice,m));
      for(int m=0;m<3;++m)
      {
        check(p[m]>=0);
        changes[m]+=!equivalentPredictors(base,p[m]);
        mapped[m]+=remap(std::abs(g.value(x,y)),base)!=remap(std::abs(g.value(x,y)),p[m]);
      }
      ++targets;
    }
  }
  for(int m=0;m<3;++m)
  { check(mapped[m]>0); std::cout<<"R4-"<<m+4<<" changed="<<changes[m]<<" mapped="<<mapped[m]<<'\n'; }
  Grid example;
  example.q[3*Grid::w+2]=5; example.q[2*Grid::w+3]=-1; example.q[2*Grid::w+2]=1;
  check(expert(example,3,3,1,4)==3);
  std::cout<<"CB selected R3/Current/NoPred/directional=";
  for(auto n:selectedModels) std::cout<<n<<',';
  std::cout<<" SP-selected="<<selectedSigned<<'\n';
  std::cout<<"PASS "<<targets<<" artificial targets: guard, future/self poison, signed bounds; NOT codec or RD validation\n";
}
