#pragma once
#include "CommonLib/CommonDef.h"
#include <vector>
namespace TsAudit
{
struct Event { int id=-1; unsigned value=0,cost=0; int scan=-1,pass=0; };
struct Path { int p1=-1,p2=-1,end=0; };
struct Native
{
  std::vector<Event> events;
  std::vector<Path> paths;
  uint64_t bits=0;
  void bin(int id,unsigned b,unsigned cost)
  { CHECK(events.size()>=131072,"Audit TU bin limit exceeded"); events.push_back({id,b,cost,-1,0}); bits+=cost; }
  void ep(unsigned value,unsigned n)
  { for(int i=int(n)-1;i>=0;--i) { bin(-1,(value>>i)&1,32768); } }
};
}
