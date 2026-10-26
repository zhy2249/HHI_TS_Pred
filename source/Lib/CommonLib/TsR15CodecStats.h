// Bounded aggregate observations only. Never feeds the R15 decisions.
#pragma once
#include "TsMultiMapping.h"
#include <atomic>
#include <cinttypes>

namespace TsMultiMapping
{
struct CodecStats
{
  std::atomic<uint64_t> trials{0},upPossible{0},upAllowed{0},gateChanged{0},tested{0};
  std::atomic<uint64_t> writerNZ{0},writerChanged{0};
  std::array<std::atomic<uint64_t>,7> trialTargets{},writerTargets{};
  ~CodecStats()
  {
    if(trials.load())
      std::printf("TS_R15_QUANT_STATS population=RDOQ-trials-not-final-TUs; positions=%" PRIu64
        "; up-possible=%" PRIu64 "; up-added=%" PRIu64 "; up-gate-vs-current=%" PRIu64
        "; listed-levels=%" PRIu64 "\n",trials.load(),upPossible.load(),upAllowed.load(),gateChanged.load(),tested.load());
    if(writerNZ.load())
      std::printf("TS_R15_WRITER_STATS population=final-Writer-regular-nonzero; positions=%" PRIu64
        "; map-vs-current=%" PRIu64 "\n",writerNZ.load(),writerChanged.load());
    if(trials.load() || writerNZ.load())
      for(int k=0;k<=6;++k)
        std::printf("TS_R15_TARGETS k=%d; RDOQ-trial=%" PRIu64 "; final-Writer-regular-nonzero=%" PRIu64 "\n",
          k,trialTargets[k].load(),writerTargets[k].load());
  }
};
inline CodecStats &codecStats() { static CodecStats s; return s; }
inline void recordQuant(const Action &p,bool possible,bool allowed,bool currentAllowed,int levels)
{
  if(!TsFixedPrediction::r15StatsEnabled()) { return; }
  auto &s=codecStats(); constexpr auto order=std::memory_order_relaxed;
  s.trials.fetch_add(1,order); s.trialTargets[p.count].fetch_add(1,order);
  s.upPossible.fetch_add(possible,order); s.upAllowed.fetch_add(possible && allowed,order);
  s.gateChanged.fetch_add(possible && allowed!=currentAllowed,order); s.tested.fetch_add(levels,order);
}
inline void recordWriter(const Action &p,int a,int current)
{
  if(!TsFixedPrediction::r15StatsEnabled()) { return; }
  auto &s=codecStats(); constexpr auto order=std::memory_order_relaxed;
  s.writerNZ.fetch_add(1,order); s.writerTargets[p.count].fetch_add(1,order);
  s.writerChanged.fetch_add(map(a,p)!=TsFixedPrediction::remap(a,current),order);
}
} // namespace TsMultiMapping
