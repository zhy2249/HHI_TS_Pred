// Independent R5 rule checks; artificial q only, no CTC outcomes or tuning.
#include "TsR5Prediction.h"
#include <array>
#include <iostream>
#include <random>
#include <stdexcept>
#include <vector>
using namespace TsFixedPrediction;
#define require(ok) do { if (!(ok)) throw std::runtime_error("R5 design mismatch at line " + std::to_string(__LINE__)); } while (false)
struct Score { int g = 0, b = 0; int h() const { return g-b; } };
static Score score(int pc, int p, const std::vector<int> &a, unsigned rice, int range)
{
  Score s;
  for (int v : a)
  {
    int d=syntaxCost(remap(v,pc),rice,range)-syntaxCost(remap(v,p),rice,range);
    s.g+=d; s.b=std::max(s.b,d);
  }
  return s;
}
static int referenceMargin(int pc, const std::vector<int> &a, unsigned rice, int range)
{
  if (a.size()<3) return pc;
  std::vector<int> ps{0};
  for (int v:a) ps.push_back(v<=1?0:v);
  std::sort(ps.begin(),ps.end()); ps.erase(std::unique(ps.begin(),ps.end()),ps.end());
  int winner=pc; Score best;
  for (int p:ps)
  {
    const Score s=score(pc,p,a,rice,range);
    if (s.h()>0 && (s.h()>best.h() || (s.h()==best.h() && s.g>best.g))) { best=s; winner=p; }
  }
  return winner;
}
struct Grid
{
  static constexpr int width=8;
  std::array<int,width*width> q{};
  int at(int x,int y) const { return x<0 || y<0 ? 0:q[y*width+x]; }
};
static int current(const Grid &g,int x,int y) { return std::max(std::abs(g.at(x-1,y)),std::abs(g.at(x,y-1))); }
static int parent(const Grid &g,int x,int y,unsigned rice,int range)
{
  int v[5],n=0;
  for (int i=0;i<5;++i) { int a=std::abs(g.at(x+r4Dx[i],y+r4Dy[i])); if(a) v[n++]=a; }
  return guardedLocalPredict(current(g,x,y),v,n,rice,range).predictor;
}
static int referenceVeto(const Grid &g,int x,int y,unsigned rice,int range)
{
  const int base=parent(g,x,y,rice,range),pc=current(g,x,y);
  if (equivalentPredictors(base,pc)) return base;
  int n=0; Score s;
  for(int i=0;i<5;++i)
  {
    int xx=x+r4Dx[i],yy=y+r4Dy[i],a=std::abs(g.at(xx,yy));
    if(!a) continue;
    ++n;
    int d=syntaxCost(remap(a,parent(g,xx,yy,rice,range)),rice,range)-
          syntaxCost(remap(a,current(g,xx,yy)),rice,range);
    s.g+=d; s.b=std::max(s.b,d);
  }
  return n>=3 && s.h()>0?pc:base;
}
int main()
{
  uint64_t templates=0,reranked=0,rescued=0,grids=0,veto=0,vetoI=0,vetoM=0,gridRerank=0,r4Differences=0;
  for(int code=0;code<(1<<20);++code)
  {
    int v=code; std::array<int,5> a{}; std::vector<int> nz;
    for(int &x:a) { x=v%16; v/=16; if(x) nz.push_back(x); }
    auto read=[&](int x,int y) { for(int i=0;i<5;++i) if(x==2+r4Dx[i] && y==2+r4Dy[i]) return a[i]; return 0; };
    for(unsigned rice:{1u,2u,4u})
    {
      const auto r=r5Predict(23,read,2,2,rice,15);
      r4Differences+=!equivalentPredictors(r.predictor,r4Predict(19,read,2,2,rice,15).predictor);
      require(r.predictor==referenceMargin(std::max(a[0],a[1]),nz,rice,15));
      const bool active=!equivalentPredictors(r.parent,r.current),changed=!equivalentPredictors(r.parent,r.predictor);
      require(!r.accepted || (r.support>=3 && r.margin()>0));
      if(active) require(r.margin()>=r.original.margin());
      reranked+=active && changed; rescued+=!active && changed; ++templates;
      if(active && changed && reranked==1)
      {
        std::cout<<"RERANK template="; for(int x:a)std::cout<<x<<',';
        std::cout<<" rice="<<rice<<" Current="<<r.current<<" R3="<<r.parent<<" R5="<<r.predictor
                 <<" R3G/H="<<r.original.gain<<'/'<<r.original.margin()<<" R5G/H="<<r.gain<<'/'<<r.margin()<<'\n';
      }
    }
  }
  std::mt19937 rng(20260921);
  const int magnitudes[]={0,1,2,3,4,7,8,9,10,15,16,31,32,255,32767};
  for(int trial=0;trial<3000;++trial)
  {
    Grid g;
    for(auto &a:g.q) { a=magnitudes[rng()%15]; if(rng()%2) a=-a; }
    const unsigned rice=1+trial%4;
    for(int y=0;y<Grid::width;++y) for(int x=0;x<Grid::width;++x)
    {
      const auto read=[&](int xx,int yy) { require(xx<0 || yy<0 || yy*Grid::width+xx<y*Grid::width+x); return g.at(xx,yy); };
      for(int mode:{23,24})
      {
        const auto r=r5Predict(mode,read,x,y,rice,15);
        if(mode==23)
        {
          gridRerank+=!equivalentPredictors(r.parent,r.current) && !equivalentPredictors(r.parent,r.predictor);
          std::vector<int> nz;
          for(int k=0;k<5;++k) { int a=std::abs(g.at(x+r4Dx[k],y+r4Dy[k])); if(a) nz.push_back(a); }
          require(r.predictor==referenceMargin(current(g,x,y),nz,rice,15));
          r4Differences+=!equivalentPredictors(r.predictor,r4Predict(19,read,x,y,rice,15).predictor);
        }
        if(mode==24)
        {
          require(r.predictor==referenceVeto(g,x,y,rice,15));
          require(r.predictor==r.parent || r.predictor==r.current);
          if(r.accepted)
          {
            ++veto; vetoI+=r.parent<=1; vetoM+=r.parent>1;
            require(r.margin()>0 && !equivalentPredictors(r.parent,r.current));
            if(veto==1)
            {
              std::cout<<"VETO grid trial="<<trial<<" x="<<x<<" y="<<y<<" rice="<<rice
                <<" R3="<<r.parent<<" Current="<<r.current<<" G/H="<<r.gain<<'/'<<r.margin()<<'\n';
              for(int yy=0;yy<=y;++yy) { for(int xx=0;xx<Grid::width;++xx)std::cout<<g.at(xx,yy)<<','; std::cout<<'\n'; }
            }
          }
        }
        auto poison=g;
        for(int k=y*Grid::width+x;k<int(g.q.size());++k) poison.q[k]=int(rng()%65535)-32767;
        require(r5Predict(mode,[&](int xx,int yy){return poison.at(xx,yy);},x,y,rice,15).predictor==r.predictor);
        auto signs=g; for(auto &q:signs.q)q=-q;
        require(r5Predict(mode,[&](int xx,int yy){return signs.at(xx,yy);},x,y,rice,15).predictor==r.predictor);
        ++grids;
      }
      // The historical primitive never reads its own target, even though R5 can score that target afterwards.
      const auto strictPast=[&](int xx,int yy) { require(xx<0 || yy<0 || yy*Grid::width+xx<y*Grid::width+x); return g.at(xx,yy); };
      require(r4Parent(strictPast,x,y,rice,15).predictor==parent(g,x,y,rice,15));
    }
  }
  std::cout<<"COUNTS templates="<<templates<<" accepted-parent-reranked="<<reranked<<" rescued="<<rescued
           <<" grid-target-policies="<<grids<<" veto="<<veto<<" identity="<<vetoI<<" magnitude="<<vetoM
           <<" wide-grid-reranked="<<gridRerank<<" differences-vs-R4-3="<<r4Differences
           <<"; artificial coverage, NOT video activity or RD gain\n";
  require(rescued && vetoI && vetoM);
  std::cout<<"PASS formula, causality and sign-invariance checks. Zero reranking is a negative activity finding, not hidden.\n";
}
