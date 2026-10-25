// Independent complete TSRC CG replay for copied CABAC states; fixed final q.
#pragma once
#include "TsVirtualCoding.h"

namespace TsFixedPrediction
{
struct RateReplayPath { int pass1 = -1, pass2 = -1; };
template<class Sink> auto replayPosition(Sink &sink,int scan,int pass,int) -> decltype(sink.position(scan,pass),void())
{ sink.position(scan,pass); }
template<class Sink> void replayPosition(Sink &,int,int,...) {}
template<class Geometry, class Predictor, class Sink>
RateReplayPath replayRateCG(Geometry &cctx, const TCoeff *q, const Predictor &predict,
                           int &bins, unsigned rice, Sink &sink)
{
  RateReplayPath path;
  const int first = cctx.minSubPos(), last = cctx.maxSubPos();
  replayPosition(sink,-1,0,0);
  if (!cctx.isLastSubSet() || !cctx.only1stSigGroup())
  {
    sink.encodeBin(cctx.isSigGroup(), cctx.sigGroupCtxId(true));
    if (!cctx.isSigGroup()) { return path; }
  }
  const auto level = [&](int s, bool regular = true) {
    const int a = std::abs(int(q[cctx.blockPos(s)]));
    return !regular || cctx.bdpcm() != BdpcmMode::NONE ? a : remap(a, predict(s));
  };
  int nz = 0;
  for (int s = first; s <= last && bins >= 4; ++s)
  {
    replayPosition(sink,s,1,0);
    const int v = q[cctx.blockPos(s)];
    if (nz || s != last) { sink.encodeBin(v != 0, cctx.sigCtxIdAbsTS(s,q)); --bins; }
    if (v)
    {
      ++nz;
      sink.encodeBin(v < 0, cctx.signCtxIdAbsTS(s,q,cctx.bdpcm()));
      const int a = level(s);
      sink.encodeBin(a > 1, cctx.lrg1CtxIdAbsTS(s,q,cctx.bdpcm())); bins -= 2;
      if (a > 1) { sink.encodeBin((a - 2) & 1, cctx.parityCtxIdAbsTS()); --bins; }
    }
    path.pass1 = s;
  }
  for (int s = first; s <= last && bins >= 4; ++s)
  {
    replayPosition(sink,s,2,0);
    const int a = level(s);
    for (int c = 2; c <= 8; c += 2)
      if (a >= c) { sink.encodeBin(a >= c + 2, cctx.greaterXCtxIdAbsTS(c / 2)); --bins; }
    path.pass2 = s;
  }
  for (int s = first; s <= last; ++s)
  {
    replayPosition(sink,s,3,0);
    const int cutoff = s <= path.pass2 ? 10 : s <= path.pass1 ? 2 : 0;
    const int a = level(s, cutoff != 0);
    if (a >= cutoff)
    {
      sink.encodeRemAbsEP(s <= path.pass1 ? (a-cutoff) >> 1 : a,
                          rice, COEF_REMAIN_BIN_REDUCTION, cctx.maxLog2TrDRange());
      if (a && s > path.pass1) { sink.encodeBinEP(q[cctx.blockPos(s)] < 0); }
    }
  }
  return path;
}
inline int ratePredictor(CoeffCodingContext &cctx, int s, const TCoeff *q)
{
  const int p = cctx.magnitudePredictorTS(s,q);
  if (p >= 0) { return p; }
  int l,u; cctx.neighTS(l,u,s,q); return std::max(std::abs(l),std::abs(u));
}
inline MagnitudeAction rateAction(CoeffCodingContext &cctx,int s,const TCoeff *q)
{
  auto a=cctx.magnitudeActionTS(s,q);
  if(a.predictor<0) { int l,u; cctx.neighTS(l,u,s,q); a.predictor=std::max(std::abs(l),std::abs(u)); }
  return a;
}
}
