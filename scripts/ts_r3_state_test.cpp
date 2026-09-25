// Independent final-CG score/budget oracle + native writer + future-poison tests.
#include "CommonLib/ContextModelling.h"
#include "CommonLib/Rom.h"
#include "CommonLib/TsFixedPrediction.h"
#include "EncoderLib/CABACWriter.h"
#include <iostream>
#include <random>
#include <stdexcept>

static void require(bool ok) { if (!ok) { throw std::runtime_error("R3 state test mismatch"); } }
static int remapped(int a, int p) { return a == 0 ? 0 : a == p ? 1 : a + (a < p); }
static int logCost(int a)
{
  if (!a) { return 0; }
  int power = 0;
  while ((uint64_t(1) << (power + 1)) <= unsigned(a)) { ++power; }
  return 1 + 2 * power;
}

int main()
{
  using namespace TsFixedPrediction;
  require(r3(mode()));
  initROM();
  std::mt19937 rng(20260919);
  XuPool pool;
  CodingStructure cs(pool);
  SPS sps;
  Slice slice;
  cs.sps = &sps;
  slice.m_sps = &sps;
  sps.m_dualITree = false;
  sps.m_bitDepths[ChannelType::LUMA] = sps.m_bitDepths[ChannelType::CHROMA] = 10;
  uint64_t cgs = 0, predictions = 0, scopeSkipped = 0, selectedN = 0, emptyReset = 0, cg1N = 0;
  for (int trial = 0; trial < 600; ++trial)
  {
    const int w = trial % 5 == 0 ? 16 : 1 << (1 + rng() % 5);
    const int h = trial % 5 == 0 ? 16 : 1 << (1 + rng() % 5);
    const CompID comp = CompID(trial % 3);
    const int scale = comp == COMP_Y ? 1 : 2;
    CodingUnit cu(ChromaFormat::_420, Area(0, 0, w * scale, h * scale));
    TransformUnit tu(ChromaFormat::_420, Area(0, 0, w * scale, h * scale));
    cu.cs = &cs; cu.slice = &slice; cu.qp = rng() % 64;
    cu.predMode = trial % 3 == 0 ? MODE_INTER : MODE_INTRA;
    slice.m_eSliceType = trial % 2 ? I_SLICE : B_SLICE;
    tu.cs = &cs; tu.cu = &cu; tu.mtsIdx[comp] = MtsType::SKIP;
    const auto bdpcm = trial % 7 == 0 ? BdpcmMode::HOR : trial % 11 == 0 ? BdpcmMode::VER : BdpcmMode::NONE;
    const bool enabled = componentEnabled(mode(), comp == COMP_Y) && bdpcm == BdpcmMode::NONE;
    CoeffCodingContext native(tu, comp, false, bdpcm);
    std::vector<TCoeff> q(w * h);
    for (auto &v : q)
    {
      const int size = trial % 4 == 0 ? 16383 : trial % 4 == 1 ? 3 : 16;
      v = rng() % 3 ? int(rng() % size) - size / 2 : 0;
    }
    native.initSubblock(0);
    if (trial % 5 == 0)
    {
      // CG0 supplies two +2 contributions, CG1 empty clears the certificate
      // while positive tiny EWMA remains. This exercises CG1 eligibility too.
      std::fill(q.begin(), q.end(), 0);
      for (int s = native.minSubPos(); s <= native.maxSubPos(); ++s) { q[native.blockPos(s)] = 1; }
      q[native.blockPos(0)] = 4;
    }
    q[native.blockPos(0)] = q[native.blockPos(0)] ? q[native.blockPos(0)] : 1;
    native.remRegBins = (w * h * 7) >> 2;
    BitEstimator_Std estimator;
    estimator.reset(cu.qp, I_SLICE);
    CABACWriter writer(estimator, nullptr);
    for (int g = 0; g <= native.lastSubSet(); ++g)
    {
      native.initSubblock(g);
      const int64_t oldState = native.tsPredictorState(), oldMargin = native.tsPredictorRecentMargin();
      const int selected = selectedMode(mode(), cu.qp, oldState, oldMargin, comp == COMP_Y);
      if (r3Adaptive(mode()))
      {
        require(selected == (componentEnabled(mode(), comp == COMP_Y) && oldState > 0 && oldMargin > 0 ? 0 : 1));
        if (!g) { require(oldState == 0 && oldMargin == 0 && selected == 1); }
        selectedN += enabled && selected == 0;
        cg1N += enabled && g == 1 && selected == 0;
      }
      bool significant = false;
      for (int s = native.minSubPos(); s <= native.maxSubPos(); ++s)
      {
        significant |= q[native.blockPos(s)] != 0;
        auto poisoned = q;
        for (int future = s; future < w * h; ++future)
          poisoned[native.blockPos(future)] = int(rng() % 1023) - 511;
        const int p = native.magnitudePredictorTS(s, q.data());
        require(p == native.magnitudePredictorTS(s, poisoned.data()));
        if (!componentEnabled(mode(), comp == COMP_Y)) { require(p == -1); ++scopeSkipped; }
        ++predictions;
      }
      if (significant) { native.setSigGroup(); }
      // Independent reference: regular budget excludes CG flag and bypass bins.
      const auto currentP = [&](int s) {
        const int pos = native.blockPos(s), x = pos % w, y = pos / w;
        return std::max(x ? std::abs(q[pos - 1]) : 0, y ? std::abs(q[pos - w]) : 0);
      };
      const auto actualLevel = [&](int s) {
        const int a = std::abs(q[native.blockPos(s)]);
        if (bdpcm != BdpcmMode::NONE) { return a; }
        const int p = native.magnitudePredictorTS(s, q.data());
        return remapped(a, p < 0 ? currentP(s) : p);
      };
      int budget = native.remRegBins, seenNZ = 0;
      int64_t gain = 0, maximum = 0;
      if (significant)
      {
        for (int s = native.minSubPos(); s <= native.maxSubPos() && budget >= 4; ++s)
        {
          const int a = std::abs(q[native.blockPos(s)]);
          if (seenNZ || s != native.maxSubPos()) { --budget; }
          if (a) { ++seenNZ; budget -= actualLevel(s) > 1 ? 3 : 2; }
          if (r3Adaptive(mode()) && enabled)
          {
            const int d = logCost(remapped(a, currentP(s))) - logCost(a);
            require(d <= 0 || d == 2);
            gain += d; maximum = std::max(maximum, int64_t(d));
          }
        }
        for (int s = native.minSubPos(); s <= native.maxSubPos() && budget >= 4; ++s)
          for (int threshold : {2, 4, 6, 8}) { budget -= actualLevel(s) >= threshold; }
      }
      unsigned riceBits[8] = {};
      writer.residual_coding_subblockTS(native, q.data(), riceBits, 1, false);
      require(native.remRegBins == budget);
      auto cloned = native;
      auto poisoned = q;
      for (int s = native.maxSubPos() + 1; s < w * h; ++s) { poisoned[native.blockPos(s)] = 123; }
      native.finishTsPredictorCG(q.data(), false, true);
      cloned.finishTsPredictorCG(poisoned.data(), false, true);
      require(native.tsPredictorState() == cloned.tsPredictorState());
      require(native.tsPredictorRecentMargin() == cloned.tsPredictorRecentMargin());
      if (r3Adaptive(mode()) && enabled)
      {
        const int64_t expected = std::max<int64_t>(-32767, std::min<int64_t>(32767, oldState - oldState / 4 + gain));
        require(native.tsPredictorState() == expected);
        require(native.tsPredictorRecentMargin() == gain - maximum);
        if (!significant)
        {
          require(native.tsPredictorRecentMargin() == 0);
          if (oldMargin > 0 && expected > 0) { ++emptyReset; }
        }
      }
      else { require(native.tsPredictorState() == 0 && native.tsPredictorRecentMargin() == 0); }
      ++cgs;
    }
  }
  if (r3Adaptive(mode())) { require(selectedN > 0 && emptyReset > 0 && cg1N > 0); }
  if (mode() == 14 || mode() == 16) { require(scopeSkipped > 0); }
  destroyROM();
  std::cout << "PASS " << name() << ": CGs=" << cgs << " causal predictions=" << predictions
            << " scope-skipped=" << scopeSkipped << " NoPred-CGs=" << selectedN
            << " CG1-NoPred=" << cg1N << " empty-positive-reset=" << emptyReset << '\n';
}
