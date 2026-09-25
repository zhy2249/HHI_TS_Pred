// Native CABAC round trips on artificial TUs; not an RD or CTC test.
#include "CommonLib/ContextModelling.h"
#include "CommonLib/Rom.h"
#include "EncoderLib/CABACWriter.h"
#include "DecoderLib/CABACReader.h"
#include <iostream>
#include <random>
#include <stdexcept>

#define require(ok) do { if (!(ok)) throw std::runtime_error("R5 codec test mismatch at line " + std::to_string(__LINE__)); } while (false)
int main()
{
  using namespace TsFixedPrediction;
  require(r5(mode()));
  initROM();
  std::mt19937 rng(20260921);
  XuPool pool;
  CodingStructure cs(pool);
  SPS sps;
  Slice slice;
  cs.sps = &sps; slice.m_sps = &sps;
  sps.m_dualITree = false;
  sps.m_bitDepths[ChannelType::LUMA] = sps.m_bitDepths[ChannelType::CHROMA] = 10;
  uint64_t predictions = 0, cgs = 0, mapped = 0, signedViews = 0, parentMapped = 0;
  for (int trial = 0; trial < 240; ++trial)
  {
    const int w = trial == 0 ? 4 : trial == 1 ? 8 : 1 << (1 + trial % 5);
    const int h = trial <= 1 ? 16 : 1 << (1 + (trial / 5) % 5);
    const CompID comp = CompID(trial % 3);
    const int scale = comp == COMP_Y ? 1 : 2;
    CodingUnit cu(ChromaFormat::_420, Area(0, 0, w * scale, h * scale));
    TransformUnit tu(ChromaFormat::_420, Area(0, 0, w * scale, h * scale));
    cu.cs = &cs; cu.slice = &slice; cu.qp = rng() % 64;
    cu.predMode = trial % 2 ? MODE_INTRA : MODE_INTER;
    tu.cs = &cs; tu.cu = &cu; tu.mtsIdx[comp] = MtsType::SKIP;
    const auto bdpcm = trial == 0 ? BdpcmMode::NONE : trial % 11 == 0 ? BdpcmMode::HOR : trial % 13 == 0 ? BdpcmMode::VER : BdpcmMode::NONE;
    const unsigned rice = 1 + trial % 4;
    sps.m_spsRangeExtension.m_tsrcRicePresentFlag = true;
    slice.m_tsrcIndex = rice - 1;
    CoeffCodingContext enc(tu, comp, false, bdpcm), dec(tu, comp, false, bdpcm);
    enc.remRegBins = dec.remRegBins = (w * h * 7) >> 2;
    std::vector<TCoeff> q(w * h), decoded(w * h), inverse(w * h);
    for (int s = 0; s < w * h; ++s) { inverse[enc.blockPos(s)] = s; }
    for (int y = 0; y < h; ++y) for (int x = 0; x < w; ++x)
      q[y*w+x] = trial % 4 == 0 ? 2*x-3*y : trial % 4 == 1 ? int(rng()%17)-8 : rng()%3 ? int(rng()%32767)-16383 : 0;
    if (trial % 9 == 0) { std::fill(q.begin(), q.end(), 0); }
    if (trial == 0)
    {
      // Frozen rescue counterexample, now through actual native CABAC too.
      q[2*w+1] = 2; q[w+2] = 1; q[w+1] = 10; q[2*w] = 1; q[2] = 1; q[2*w+2] = 2;
    }
    if (trial == 1)
    {
      // Independent artificial-grid witness: only the causal read closure is nonzero.
      // At (7,2), R3=8, Current=9; Current veto has G=8,H=3 (Rice=2).
      std::fill(q.begin(), q.end(), 0);
      q[5]=-16; q[6]=32; q[7]=8;
      q[w+5]=32; q[w+6]=2; q[w+7]=-9;
      q[2*w+3]=255; q[2*w+4]=-10; q[2*w+5]=8; q[2*w+6]=-8; q[2*w+7]=8;
    }
    q[0] = q[0] ? q[0] : -3; // TU has CBF; other groups may be all zero.
    OutputBitstream bits;
    BinEncoder_Std binEnc;
    CABACWriter writer(binEnc, nullptr);
    writer.initBitstream(&bits); binEnc.reset(cu.qp, I_SLICE);
    std::vector<int> budgets;
    for (int g = 0; g <= enc.lastSubSet(); ++g)
    {
      enc.initSubblock(g);
      bool significant = false;
      for (int s = enc.minSubPos(); s <= enc.maxSubPos(); ++s)
      {
        significant |= q[enc.blockPos(s)] != 0;
        const int pos = enc.blockPos(s), x = pos % w, y = pos / w;
        const auto causalRead = [&](int xx, int yy) {
          if (xx < 0 || yy < 0) { return 0; }
          require(xx < w && yy < h && inverse[xx + yy * w] < s);
          return int(q[xx + yy * w]);
        };
        const auto result = r5Predict(mode(), causalRead, x, y, rice, enc.maxLog2TrDRange());
        if (mode() == 23 && trial == 0 && x == 2 && y == 2)
          require(result.accepted && result.parent == 2 && result.predictor == 0 && result.margin() == 2);
        if (mode() == 24 && trial == 1 && x == 7 && y == 2)
        {
          std::cerr << "VETO witness parent=" << result.parent << " current=" << result.current << " pred=" << result.predictor
                    << " G=" << result.gain << " H=" << result.margin() << " range=" << enc.maxLog2TrDRange() << '\n';
          require(result.accepted && result.parent == 8 && result.current == 9 && result.predictor == 9 && result.margin() == 3);
        }
        require(result.predictor == enc.magnitudePredictorTS(s, q.data()));
        auto poison = q;
        for (int k = s; k < w * h; ++k) { poison[enc.blockPos(k)] = int(rng()%511)-255; }
        require(result.predictor == enc.magnitudePredictorTS(s, poison.data()));
        mapped += remap(std::abs(int(q[pos])), result.predictor) != remap(std::abs(int(q[pos])), result.current);
        parentMapped += remap(std::abs(int(q[pos])), result.predictor) != remap(std::abs(int(q[pos])), result.parent);
        // Simulate Reader's magnitude-only current CG with full decoded signs.
        auto partial = q;
        int positions[1 << MLS_CG_SIZE], count = 0;
        unsigned signs = 0;
        for (int k = enc.minSubPos(); k <= enc.maxSubPos(); ++k)
        {
          const int at = enc.blockPos(k);
          if (q[at]) { positions[count] = at; signs |= unsigned(q[at] < 0) << count; ++count; }
          partial[at] = std::abs(int(q[at]));
        }
        const R4SignView view{partial.data(), positions, count, signs};
        require(result.predictor == enc.magnitudePredictorModeTS(mode(), s, partial.data(), &view));
        ++signedViews; ++predictions;
      }
      if (significant) { enc.setSigGroup(); }
      unsigned riceBits[8] = {};
      writer.residual_coding_subblockTS(enc, q.data(), riceBits, rice, false);
      const int witness = trial == 0 ? 2*w+2 : 2*w+7;
      if (trial <= 1 && enc.minSubPos() <= inverse[witness] && inverse[witness] <= enc.maxSubPos())
        require(enc.remRegBins >= 4); // Witness really went through regular remapping, not bypass.
      enc.finishTsPredictorCG(q.data(), true, true);
      require(enc.tsPredictorState() == 0 && enc.tsPredictorRecentMargin() == 0);
      budgets.push_back(enc.remRegBins);
    }
    binEnc.encodeBinTrm(1); binEnc.finish(); bits.writeByteAlignment();
    InputBitstream input;
    input.getFifo() = bits.getFifo();
    BinDecoder_Std binDec;
    CABACReader reader(binDec, nullptr);
    reader.initBitstream(&input); binDec.reset(cu.qp, I_SLICE);
    for (int g = 0; g <= dec.lastSubSet(); ++g)
    {
      dec.initSubblock(g);
      reader.residual_coding_subblockTS(dec, decoded.data(), rice);
      require(dec.remRegBins == budgets[g]);
      for (int s = dec.minSubPos(); s <= dec.maxSubPos(); ++s)
        require(decoded[dec.blockPos(s)] == q[dec.blockPos(s)]);
      dec.finishTsPredictorCG(decoded.data(), true, true);
      require(dec.tsPredictorState() == 0 && dec.tsPredictorRecentMargin() == 0);
      ++cgs;
    }
    require(binDec.decodeBinTrm() == 1);
    binDec.finish();
    require(q == decoded);
  }
  require(mapped > 0);
  require(parentMapped > 0);
  destroyROM();
  std::cout << "PASS " << name() << ": 240 native TU roundtrips, CG=" << cgs << " causal=" << predictions
            << " signed-views=" << signedViews << " artificial mapped=" << mapped << " vs-parent=" << parentMapped << '\n';
}
