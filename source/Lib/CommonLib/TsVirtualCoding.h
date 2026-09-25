// Deterministic research-only TS syntax replay. No EncoderLib dependency.
#pragma once
#include "ContextModelling.h"

namespace TsFixedPrediction
{
struct FractionalSink
{
  CtxStore<BinProbModel_Std> &contexts;
  uint64_t bits = 0;
  void encodeBin(unsigned bin, unsigned id) { contexts[id].estFracBitsUpdate(bin, bits); }
  void encodeBinEP(unsigned) { bits += BinProbModelBase::estFracBitsEP(); }
  void encodeRemAbsEP(unsigned value, unsigned rice, unsigned cutoff, int range)
  {
    CHECK(cutoff != COEF_REMAIN_BIN_REDUCTION, "Unexpected TS Rice cutoff");
    bits += BinProbModelBase::estFracBitsEP(riceLength(value, rice, range));
  }
};

// Native CABACWriter::residual_coding_subblockTS is retained independently and
// serves as the validation oracle for this replay (including final contexts).
// Only bins and sink are mutated. Context geometry/group flags and q are read-only.
template<class Sink>
void replayCG(CoeffCodingContext &cctx, const TCoeff *coeff, int predictor, int &bins, int rice, Sink &sink)
{
  CHECK(predictor != 0 && predictor != 1, "Virtual R2 branches must be Current or NoPred");
  const int first = cctx.minSubPos(), last = cctx.maxSubPos();
  if (!cctx.isLastSubSet() || !cctx.only1stSigGroup())
  {
    sink.encodeBin(cctx.isSigGroup(), cctx.sigGroupCtxId(true));
    if (!cctx.isSigGroup()) { return; }
  }
  const auto mapped = [&](int s, bool enabled = true) {
    const int a = std::abs(int(coeff[cctx.blockPos(s)]));
    if (!enabled || cctx.bdpcm() != BdpcmMode::NONE || predictor == 0) { return a; }
    int l, u;
    cctx.neighTS(l, u, s, coeff);
    return remap(a, std::max(std::abs(l), std::abs(u)));
  };
  int nonzero = 0, pass1 = -1, pass2 = -1;
  for (int s = first; s <= last && bins >= 4; ++s)
  {
    const auto q = coeff[cctx.blockPos(s)];
    if (nonzero || s != last)
    {
      sink.encodeBin(q != 0, cctx.sigCtxIdAbsTS(s, coeff));
      --bins;
    }
    if (q)
    {
      ++nonzero;
      sink.encodeBin(q < 0, cctx.signCtxIdAbsTS(s, coeff, cctx.bdpcm()));
      const int level = mapped(s);
      sink.encodeBin(level > 1, cctx.lrg1CtxIdAbsTS(s, coeff, cctx.bdpcm()));
      bins -= 2;
      if (level > 1) { sink.encodeBin((level - 2) & 1, cctx.parityCtxIdAbsTS()); --bins; }
    }
    pass1 = s;
  }
  for (int s = first; s <= last && bins >= 4; ++s)
  {
    const int level = mapped(s);
    for (int cutoff = 2; cutoff <= 8; cutoff += 2)
      if (level >= cutoff)
      {
        sink.encodeBin(level >= cutoff + 2, cctx.greaterXCtxIdAbsTS(cutoff >> 1));
        --bins;
      }
    pass2 = s;
  }
  for (int s = first; s <= last; ++s)
  {
    const int cutoff = s <= pass2 ? 10 : s <= pass1 ? 2 : 0;
    const int level = mapped(s, cutoff != 0);
    if (level >= cutoff)
    {
      const unsigned rem = s <= pass1 ? (level - cutoff) >> 1 : level;
      sink.encodeRemAbsEP(rem, rice, COEF_REMAIN_BIN_REDUCTION, cctx.maxLog2TrDRange());
      if (level && s > pass1) { sink.encodeBinEP(coeff[cctx.blockPos(s)] < 0); }
    }
  }
}
}
