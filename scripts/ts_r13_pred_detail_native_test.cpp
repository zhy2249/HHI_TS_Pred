// Synthetic TU-only verification of the labeled full-TS replay against the
// native fractional estimator. No EncoderApp/DecoderApp or video is launched.
// Run separately with TS_FIXED_PREDICTOR=current/r13_keep_hit_uniform/
// r13_keep_hit_spatial and a temporary TS_R13_PRED_DETAIL output prefix.
#include "CommonLib/TsR13PredDetail.h"
#include "CommonLib/Rom.h"
#include "EncoderLib/CABACWriter.h"
#include <iostream>
#include <random>

int main()
{
  using namespace TsFixedPrediction;
  CHECK(mode()!=1 && mode()!=98 && mode()!=99,"Choose Current, R13-EQ, or R13-SP");
  CHECK(!TsR13PredDetail::enabled(),"Set a temporary TS_R13_PRED_DETAIL prefix");
  initROM();
  XuPool pool; CodingStructure cs(pool); SPS sps; PPS pps; Slice slice;
  cs.sps=&sps; cs.slice=&slice; slice.m_sps=&sps;
  slice.m_poc=16; slice.m_eSliceType=P_SLICE; slice.m_tsResidualCodingDisabledFlag=false;
  sps.m_chromaFormatIdc=ChromaFormat::_420; sps.m_dualITree=false;
  sps.m_bitDepths[ChannelType::LUMA]=sps.m_bitDepths[ChannelType::CHROMA]=10;
  sps.m_maxCuWidth=sps.m_maxCuHeight=64;
  pps.m_picWidthInLumaSamples=pps.m_picHeightInLumaSamples=64;
  PreCalcValues pcv(sps,pps,true); cs.pcv=&pcv; cs.pps=&pps; slice.m_pps=&pps;
  std::mt19937 rng(20261025);
  for(int trial=0;trial<12;++trial)
  {
    const int w=trial%3==0?8:16,h=trial%2==0?32:8;
    CodingUnit cu(ChromaFormat::_420,Area(0,0,w,h));
    TransformUnit tu(static_cast<const UnitArea&>(cu));
    cu.cs=&cs; cu.slice=&slice; cu.qp=33; cu.predMode=MODE_INTER;
    cu.bdpcmMode[0]=cu.bdpcmMode[1]=BdpcmMode::NONE;
    tu.cs=&cs; tu.cu=&cu; tu.mtsIdx[COMP_Y]=MtsType::SKIP;
    sps.m_spsRangeExtension.m_tsrcRicePresentFlag=true; slice.m_tsrcIndex=trial%4;
    std::vector<TCoeff> y(w*h),cb(w*h/4),cr(w*h/4);
    std::vector<uint8_t> sy(y.size()),sb(cb.size()),sr(cr.size());
    TCoeff *q[]={y.data(),cb.data(),cr.data()}; uint8_t *signs[]={sy.data(),sb.data(),sr.data()};
    EnumArray<Pel*,ChannelType> plt{}; EnumArray<bool*,ChannelType> run{};
    tu.init(q,signs,plt,run);
    for(auto &v:y) { v=trial%4==0?(rng()%90?0:1):int(rng()%31)-15; }
    y[0]=3;
    const auto input=y;
    Ctx entry(static_cast<const BinProbModel_Std*>(nullptr)); entry.init(cu.qp,P_SLICE);
    const Ctx originalEntry(entry);
    BitEstimator_Std estimator; estimator.getCtx()=entry; estimator.resetBits();
    CABACWriter writer(estimator,nullptr); writer.residual_coding_coef(tu,COMP_Y);
    const Ctx nativeAfter(estimator.getCtx());
    const uint64_t nativeBits=estimator.getEstFracBits();
    TsR13PredDetail::observe(tu,COMP_Y,entry,nativeBits);
    CHECK(y!=input || estimator.getEstFracBits()!=nativeBits,"Diagnostic mutated native inputs/rate");
    TsR13PredDetail::requireEqualContext(originalEntry,entry);
    TsR13PredDetail::requireEqualContext(nativeAfter,estimator.getCtx());
  }
  destroyROM();
  std::cout<<"PASS "<<name()<<" detail_native_replay TU=12; sequence_encode_decode=false\n";
}
