#include "DecoderLib/tsaudit/Budget.h"
#include <algorithm>
#include <array>
#include <cassert>
#include <iostream>
int main()
{
  using namespace TsAudit;
  unsigned cases=0;
  for(unsigned cap: {0u,1u,3u,7u,96u}) for(unsigned visits:{0u,1u,64u,125000u})
  for(int poc=0;poc<6;++poc) for(unsigned slots:{1u,2u})
  {
    std::array<int,3> order{{0,1,2}};
    std::array<std::array<Budget,2>,3> original{};
    for(int c=0;c<3;++c) for(unsigned i=0;i<slots;++i) { original[c][i]=tuBudget(cap,visits,poc,c,slots,i); }
    do
    {
      uint64_t r=0,v=0;
      for(int c:order) for(unsigned i=0;i<slots;++i)
      {
        const auto b=tuBudget(cap,visits,poc,c,slots,i);
        assert(b.maxReplays==original[c][i].maxReplays && b.maxVisits==original[c][i].maxVisits);
        r+=b.maxReplays;v+=b.maxVisits;
        assert(!b.fits(cap+1,16));
      }
      assert(r==cap && v==visits);++cases;
    } while(std::next_permutation(order.begin(),order.end()));
  }
  Budget b{5,1000,1,48};
  assert(b.fits(4,16));assert(!b.fits(5,16));
  std::cout<<"PASS allocation_permutations="<<cases<<" no_borrowing=true total_caps=true\n";
}
