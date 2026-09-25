// Compare independent CommonLib replay against native CABACWriter + BitEstimator.
#include "CommonLib/TsVirtualCoding.h"
#include "CommonLib/Rom.h"
#include "EncoderLib/CABACWriter.h"
#include <iostream>
#include <random>
#include <stdexcept>

static void require(bool ok) { if (!ok) { throw std::runtime_error("R2 rate test mismatch"); } }

int main()
{
  using namespace TsFixedPrediction;
  require(mode() == 0 || mode() == 1 || mode() == 11 || mode() == 12);
  initROM();
  std::mt19937 rng(20260918);
  XuPool pool;
  CodingStructure cs(pool);
  SPS sps;
  Slice slice;
  cs.sps = &sps;
  slice.m_sps = &sps;
  sps.m_dualITree = false;
  sps.m_bitDepths[ChannelType::LUMA] = 10;
  sps.m_bitDepths[ChannelType::CHROMA] = 10;
  uint64_t cgs = 0, riceCases = 0;
  for (int trial = 0; trial < 600; ++trial)
  {
    const int w = 1 << (1 + rng() % 5), h = 1 << (1 + rng() % 5);
    if (w * h < 16) { continue; }
    const CompID comp = CompID(trial % 3);
    const int scale = comp == COMP_Y ? 1 : 2;
    CodingUnit cu(ChromaFormat::_420, Area(0, 0, w * scale, h * scale));
    TransformUnit tu(ChromaFormat::_420, Area(0, 0, w * scale, h * scale));
    sps.m_spsRangeExtension.m_extendedPrecisionProcessingFlag = trial % 5 == 0;
    sps.m_bitDepths[ChannelType::LUMA] = sps.m_bitDepths[ChannelType::CHROMA] = 14;
    cu.cs = &cs;
    cu.slice = &slice;
    cu.qp = rng() % 64;
    cu.predMode = trial % 3 == 0 ? MODE_INTER : MODE_INTRA;
    slice.m_eSliceType = trial % 2 ? I_SLICE : B_SLICE;
    tu.cs = &cs;
    tu.cu = &cu;
    tu.mtsIdx[comp] = MtsType::SKIP;
    const auto bdpcm = trial % 7 == 0 ? BdpcmMode::HOR : trial % 11 == 0 ? BdpcmMode::VER : BdpcmMode::NONE;
    CoeffCodingContext native(tu, comp, false, bdpcm);
    CoeffCodingContext replay(tu, comp, false, bdpcm);
    std::vector<TCoeff> q(w * h);
    for (auto &v : q)
    {
      const int size = trial % 4 == 0 ? 32767 : trial % 4 == 1 ? 2 : 35;
      v = rng() % 3 ? int(rng() % size) - size / 2 : 0;
    }
    // Explicit empty CGs, inferred last CG, high levels and limited budgets.
    if (trial % 9 == 0)
    {
      std::fill(q.begin(), q.end(), 0);
      q[replay.blockPos(w * h - 1)] = 1;
    }
    int bins = trial % 3 ? (w * h * 7) >> 2 : int(rng() % 30);
    native.remRegBins = bins;
    BitEstimator_Std estimator;
    estimator.reset(cu.qp, I_SLICE);
    CABACWriter writer(estimator, nullptr);
    Ctx virtualCtx(estimator.getCtx());
    FractionalSink sink{static_cast<CtxStore<BinProbModel_Std> &>(virtualCtx)};
    const int rice = 1 + rng() % 8;
    for (int g = 0; g <= native.lastSubSet(); ++g)
    {
      native.initSubblock(g);
      replay.initSubblock(g);
      bool sig = false;
      for (int s = native.minSubPos(); s <= native.maxSubPos(); ++s) { sig |= q[native.blockPos(s)] != 0; }
      if (sig) { native.setSigGroup(); replay.setSigGroup(); }
      if (mode() >= 11)
      {
        // q after this CG is unavailable to the decoder. Poison it independently
        // and verify both histories remain equal, including after empty groups.
        auto causal = replay;
        auto poisoned = q;
        for (int s = replay.maxSubPos() + 1; s < w * h; ++s) { poisoned[replay.blockPos(s)] = int(rng() % 65535) - 32767; }
        const auto before = replay.tsPredictorState();
        if (!g) { require(before == 0); }
        replay.finishTsPredictorCG(q.data());
        causal.finishTsPredictorCG(poisoned.data());
        require(replay.tsPredictorState() == causal.tsPredictorState());
        require(selectedMode(mode(), cu.qp, replay.tsPredictorState()) == selectedMode(mode(), cu.qp, causal.tsPredictorState()));
        if (!sig && bdpcm == BdpcmMode::NONE)
          require(replay.tsPredictorState() == updateState(mode(), before, 0));
        ++cgs;
        continue;
      }
      unsigned riceBits[8] = {};
      writer.residual_coding_subblockTS(native, q.data(), riceBits, rice, false);
      replayCG(replay, q.data(), mode(), bins, rice, sink);
      require(bins == native.remRegBins);
      require(sink.bits == estimator.getEstFracBits());
      const auto &a = static_cast<const CtxStore<BinProbModel_Std> &>(virtualCtx);
      const auto &b = static_cast<const CtxStore<BinProbModel_Std> &>(estimator.getCtx());
      for (unsigned id = 0; id < ContextSetCfg::NumberOfContexts; ++id)
      {
        // Compare internal probability pairs, used-state estimates and adaptation parameters.
        require(a[id].getState() == b[id].getState());
        require(a[id].estFracBits(0) == b[id].estFracBits(0));
        require(a[id].getWinSizes() == b[id].getWinSizes());
        require(a[id].getAdaptRateWeight() == b[id].getAdaptRateWeight());
        require(a[id].getAdaptRateOffset(0) == b[id].getAdaptRateOffset(0));
        require(a[id].getAdaptRateOffset(1) == b[id].getAdaptRateOffset(1));
      }
      ++cgs;
    }
  }
  BitEstimator_Std estimator;
  for (int range : {15, 20})
    for (unsigned rice = 1; rice <= 8; ++rice)
      for (unsigned value = 0; value < (1u << range); value += 1 + value / 97)
      {
        estimator.resetBits();
        estimator.encodeRemAbsEP(value, rice, COEF_REMAIN_BIN_REDUCTION, range);
        require(estimator.getEstFracBits() == (uint64_t(riceLength(value, rice, range)) << SCALE_BITS));
        ++riceCases;
      }
  destroyROM();
  std::cout << "PASS " << name() << ": " << cgs << (mode() >= 11 ? " causal CG state/clone checks; " : " CGs match native fractional cost/context/budget exactly; ")
            << riceCases << " Rice lengths\n";
}
