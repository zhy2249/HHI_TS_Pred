#include "CommonLib/TsMultiMapping.h"
#include <iostream>
#include <random>
#include <chrono>
#include <fstream>
using namespace TsMultiMapping;
static void equal(const Result &a,const Result &b)
{
  CHECK(a.action!=b.action || a.returned!=b.returned || a.searched!=b.searched || a.root!=b.root ||
    a.score!=b.score || a.trace!=b.trace || a.positive!=b.positive || a.neutral!=b.neutral || a.negative!=b.negative || a.zeroSteps!=b.zeroSteps,"Engine mismatch");
}
int main(int argc,char **argv)
{
  try {
    if(argc==4 && std::string(argv[1])=="--benchmark")
    {
      struct Row { std::array<int,5> h;unsigned rice;int range; };
      std::ifstream f(argv[2]);std::vector<Row> rows;Row row;
      while(f>>row.h[0]>>row.h[1]>>row.h[2]>>row.h[3]>>row.h[4]>>row.rice>>row.range) { rows.push_back(row);CHECK(rows.size()>20000,"Benchmark input cap"); }
      const int repeats=std::stoi(argv[3]);CHECK(rows.empty() || repeats<5 || repeats>20,"Need nonempty trace and 5..20 repeats");
      volatile uint64_t sink=0;
      for(const auto &m:methods()) for(int rep=-1;rep<repeats;++rep) for(int phase=0;phase<3;++phase)
      {
        const int e=(phase+rep+3)%3;const auto engine=Engine(e);Operations ops;uint64_t checksum=0;
        const auto start=std::chrono::steady_clock::now();
        for(const auto &r:rows) { auto a=select(r.h,m,r.rice,r.range,engine);checksum=checksum*1099511628211ULL+uint64_t(a.score);for(auto v:a.action.targets) { checksum=checksum*1099511628211ULL+v; }ops+=a.ops; }
        const auto ns=std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now()-start).count();sink=checksum;
        if(rep>=0) { std::cout<<"{\"mg\":"<<m.mg<<",\"engine\":"<<e<<",\"repeat\":"<<rep<<",\"positions\":"<<rows.size()<<",\"nanoseconds\":"<<ns<<",\"checksum\":\""<<checksum<<"\",\"operations\":["<<ops.candidates<<','<<ops.queries<<','<<ops.hits<<','<<ops.adds<<','<<ops.multiplies<<','<<ops.compares<<','<<ops.rankUpdates<<','<<ops.pruned<<','<<ops.loops<<"]}\n"; }
      }
      // Separate mapping/inverse costs; selector construction is outside timer.
      for(int rep=0;rep<repeats;++rep)
      {
        std::vector<Action> actions;for(const auto &r:rows) { actions.push_back(select(r.h,methods()[11],r.rice,r.range).action); }
        for(int inverse=0;inverse<2;++inverse)
        {
          const auto start=std::chrono::steady_clock::now();uint64_t sum=0;
          for(int loop=0;loop<64;++loop) for(size_t i=0;i<rows.size();++i) { const int value=(int(i)+loop)%255;sum+=inverse?unmap(value,actions[i]):map(value,actions[i]); }
          const auto ns=std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now()-start).count();sink=sum;
          std::cout<<"{\"mg\":11,\"engine\":"<<(inverse?4:3)<<",\"repeat\":"<<rep<<",\"positions\":"<<rows.size()*64<<",\"nanoseconds\":"<<ns<<",\"checksum\":\""<<sum<<"\",\"operations\":[]}\n";
        }
      }
      (void)sink;return 0;
    }
    if(argc>1 && std::string(argv[1])=="--cases")
    {
      std::array<int,5> h;unsigned rice;int range;
      while(std::cin>>h[0]>>h[1]>>h[2]>>h[3]>>h[4]>>rice>>range)
      {
        for(const auto &m:methods()) { auto r=select(h,m,rice,range);std::cout<<m.mg<<' '<<r.score<<' '<<r.action.count;for(int j=0;j<r.action.count;++j) { std::cout<<' '<<r.action.targets[j]; }std::cout<<'\n'; }
      }return 0;
    }
    uint64_t maps=0,cases=0,methodsChecked=0;std::mt19937 gen(20261026);
    // Full finite domains, every ordered prefix (including neutral suffixes).
    for(int max=1;max<=9;++max)
    {
      auto walk=[&](auto &&self,Action p)->void {
        validate(p,max);auto c=canonical(p);
        for(int a=0;a<=max;++a) { const int y=map(a,p);CHECK(y<0 || y>max || unmap(y,p)!=a || map(unmap(a,p),p)!=a || map(a,c)!=y,"Bijection/canonical failure");++maps; }
        if(p.count==std::min(max,4)) { return; }
        for(int q=1;q<=max;++q) if(std::find(p.targets.begin(),p.targets.begin()+p.count,q)==p.targets.begin()+p.count) { self(self,append(p,q)); }
      };walk(walk,{});
    }
    for(int range:{8,15,20}) for(int p:{0,1,2,9,255,1<<range}) if(p<=1<<range)
      for(int a=0;a<=1<<range;++a) { CHECK(map(a,single(p))!=TsFixedPrediction::remap(a,p),"Legacy single remap mismatch");++maps; }
    for(int range:{8,15,20})
    {
      const int max=1<<range;std::array<int,6> targets{{max,1,max/2,2,max-1,3}};
      for(int rotation=0;rotation<6;++rotation)
      {
        Action p;for(int j=0;j<6;++j) { p=append(p,targets[(rotation+j)%6]); }validate(p,max);
        for(int a=0;a<=max;++a) { int y=map(a,p);CHECK(y<0 || y>max || unmap(y,p)!=a || map(unmap(a,p),p)!=a,"Full large-domain six-target inverse failure");++maps; }
      }
    }
    for(int j=0;j<6;++j) { Action p;bool failed=false;try { if(j==0) { p.count=7; }else if(j==1) { p=single(0);p.count=1; }else if(j==2) { p=append(single(2),2); }else if(j==3) { p=single(257); }else if(j==4) { p.count=-1; }else { p.targets[5]=1; }validate(p,256); }catch(const std::exception &) { failed=true; }CHECK(!failed,"Malformed action accepted"); }
    for(int trial=0;trial<18000;++trial)
    {
      std::array<int,5> h{};const int range=trial%3==0?8:trial%3==1?15:20;unsigned rice=trial%9;
      for(int &v:h) { v=trial<3125?0:gen()%((trial%4)?32:((1<<range)+1)); }
      if(trial<3125) { int code=trial;for(int &v:h) { v=code%5;code/=5; } }
      const std::array<std::array<int,5>,5> examples={{{4,5,5,6,1},{1,2,2,6,8},{1,1,1,6,6},{0,2,1,0,1},{1<<range,2,3,4,5}}};
      if(trial>=3125 && trial<3130) { h=examples[trial-3125];rice=1; }
      for(const auto &m:methods())
      {
        const auto a=select(h,m,rice,range,Engine::NAIVE,true),b=select(h,m,rice,range,Engine::PREFIX,true),c=select(h,m,rice,range,Engine::FAST,true);
        equal(a,b);equal(a,c);++methodsChecked;
      }
      CHECK(select(h,methods()[4],rice,range).action!=select(h,methods()[8],rice,range).action,"G_K2/N_K2 invariant");++cases;
    }
    auto get=[&](std::array<int,5> h,int mg){for(const auto &m:methods()) if(m.mg==mg) { return select(h,m,1,15).score; }return int64_t(-1);};
    CHECK(get({4,5,5,6,1},1)!=18 || get({4,5,5,6,1},2)!=14 || get({4,5,5,6,1},4)!=13 || get({4,5,5,6,1},5)!=12,"Exact example 1");
    CHECK(get({1,2,2,6,8},5)!=15 || get({1,2,2,6,8},9)!=14,"Neutral placeholder regression");
    CHECK(get({1,1,1,6,6},2)!=11 || get({1,1,1,6,6},15)!=9 || get({0,2,1,0,1},2)!=5,"Protected root/CE01 regression");
    std::cout<<"{\"complete\":true,\"neighborhoods\":"<<cases<<",\"method_triples\":"<<methodsChecked<<",\"mapping_checks\":"<<maps<<",\"failures\":0}\n";
  }catch(const std::exception &e) { std::cerr<<e.what()<<'\n';return 1; }
}
