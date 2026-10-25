#pragma once
#include <cstdint>
#include <array>

namespace TsAudit
{
// Immutable component allocations. Remainders rotate with POC; no component
// borrows an absent/later component's allowance. Each retained TU has its own
// share, assigned by sampling priority, not decoding or policy execution order.
inline uint64_t equalShare(uint64_t total,unsigned count,unsigned rank)
{ return count?total/count+(rank<total%count):0; }
struct Budget
{
  uint64_t maxReplays=0,maxVisits=0,replays=0,visits=0;
  bool fits(uint64_t branches,uint64_t coefficients) const
  { return replays+branches<=maxReplays && visits+branches*3*coefficients<=maxVisits; }
};
inline Budget tuBudget(uint64_t replays,uint64_t visits,int poc,int component,unsigned slots,unsigned rank)
{
  const unsigned componentRank=(component+3-(poc%3))%3;
  return {equalShare(equalShare(replays,3,componentRank),slots,rank),
          equalShare(equalShare(visits,3,componentRank),slots,rank),0,0};
}
}
