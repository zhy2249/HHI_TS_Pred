// Read-only final-decoder block observations. This is not a codec experiment:
// no predictor, coefficient, context, search state or reconstruction is changed.
#pragma once

#include "CommonLib/TsR13DecodeObservation.h"
#include "CommonLib/UnitTools.h"
#include "CommonLib/Quant.h"
#include <cinttypes>
#include <mutex>
#include <sstream>

namespace TsR13DecoderDiagnostic
{
using TsR13DecodeObservation::hashValue;
using TsR13DecodeObservation::hashBuffer;
static constexpr uint64_t hashSeed = UINT64_C(14695981039346656037);

struct State
{
  uint64_t rows=0, omitted=0, cuRows=0, tuRows=0, ctuRows=0;
  bool started=false;
  std::mutex mutex;
  ~State()
  {
    if(started)
    {
      std::fprintf(stderr,"TS_R13_DEC {\"schema\":1,\"kind\":\"syntax_summary\",\"rows\":%" PRIu64
        ",\"cu_rows\":%" PRIu64 ",\"tu_rows\":%" PRIu64 ",\"ctu_rows\":%" PRIu64
        ",\"omitted\":%" PRIu64 ",\"truncated\":%d}\n",rows,cuRows,tuRows,ctuRows,omitted,int(omitted!=0));
    }
  }
};
inline State &state() { static State value; return value; }

// Caller holds the local mutex. All numbers are exact integer fields; hashes
// cover named semantic values, never object representations/pointers/padding.
inline bool reserveRow(State &s,const char *kind,int poc,int ctu)
{
  const auto &o=TsR13DecodeObservation::options();
  if(!s.started)
  {
    s.started=true;
    std::fprintf(stderr,"TS_R13_DEC {\"schema\":1,\"kind\":\"syntax_identity\",\"revision\":\"R13-DEC-BLOCK-v1\","
      "\"poc_filter\":%d,\"ctu_filter\":%d,\"limit\":%" PRIu64
      ",\"hash\":\"fnv1a64-int32le\",\"reconstruction_domain\":\"before_inverse_lmcs\"}\n",
      o.poc,o.ctu,uint64_t(o.limit));
  }
  if(s.rows>=uint64_t(o.limit))
  {
    ++s.omitted;
    if(s.omitted==1)
      std::fprintf(stderr,"TS_R13_DEC {\"schema\":1,\"kind\":\"syntax_truncated\",\"poc\":%d,\"ctu\":%d,\"next_kind\":\"%s\"}\n",poc,ctu,kind);
    return false;
  }
  ++s.rows;
  return true;
}

inline std::string prefix(const char *kind,int poc,int ctu,uint64_t order)
{
  std::ostringstream out;
  out << "TS_R13_DEC {\"schema\":1,\"kind\":\"" << kind << "\",\"poc\":" << poc
      << ",\"ctu\":" << ctu << ",\"order\":" << order;
  return out.str();
}

inline void areaFields(std::ostringstream &out,const CompArea &area)
{
  out << ",\"x\":" << area.x << ",\"y\":" << area.y << ",\"w\":" << area.width << ",\"h\":" << area.height;
}

inline uint64_t motionHash(const CodingUnit &cu)
{
  uint64_t hash=hashSeed;
  const CMotionBuf mb=cu.getMotionBuf();
  for(unsigned y=0;y<mb.height;++y)
    for(unsigned x=0;x<mb.width;++x)
    {
      const auto &mi=mb.at(x,y);
      for(int value:{int(mi.isInter),int(mi.isIBCmot),int(mi.interDir),int(mi.useAltHpelIf),
                    int(mi.sliceIdx),int(mi.bcwIdx),int(mi.usesLIC)})
        hash=hashValue(hash,value);
      for(unsigned l=0;l<NUM_RPL01;++l)
      {
        const bool active=(mi.interDir&(1<<l))!=0;
        hash=hashValue(hash,active?int(mi.refIdx[l]):-1);
        hash=hashValue(hash,active?mi.mv[l].getHor():0);
        hash=hashValue(hash,active?mi.mv[l].getVer():0);
      }
      hash=hashValue(hash,mi.isIBCmot?mi.bv.getHor():0);
      hash=hashValue(hash,mi.isIBCmot?mi.bv.getVer():0);
    }
  return hash;
}

inline void observeCu(const CodingUnit &cu,bool lmcsCtuFlag)
{
  if(!TsR13DecodeObservation::options().enabled || cu.cs->pcv->isEncoder) { return; }
  const int poc=cu.cs->picture->m_poc,ctu=int(CU::getCtuAddr(cu));
  if(!TsR13DecodeObservation::selected(poc,ctu)) { return; }
  State &s=state();
  std::lock_guard<std::mutex> lock(s.mutex);
  const bool intra=CU::isIntra(cu),palette=CU::isPLT(cu),inter=!intra&&!palette;
  const auto &slice=*cu.slice;
  if(reserveRow(s,"CU",poc,ctu))
  {
    ++s.cuRows;
    std::ostringstream out;
    out << prefix("CU",poc,ctu,s.rows);
    areaFields(out,cu.block(cu.chType)); // native channel coordinates
    out << ",\"channel\":" << int(cu.chType) << ",\"dual_tree\":" << int(CS::isDualITree(*cu.cs))
        << ",\"depth\":" << int(cu.depth) << ",\"qt_depth\":" << int(cu.qtDepth)
        << ",\"bt_depth\":" << int(cu.btDepth) << ",\"mt_depth\":" << int(cu.mtDepth)
        << ",\"split_series\":" << uint64_t(cu.splitSeries) << ",\"pred_mode\":" << int(cu.predMode)
        << ",\"qp\":" << int(cu.qp) << ",\"root_cbf\":" << int(cu.rootCbf)
        << ",\"skip\":" << int(cu.skip) << ",\"sbt\":" << (inter?int(cu.sbtInfo):0)
        << ",\"lmcs_slice\":" << int(slice.m_lmcsEnabledFlag) << ",\"lmcs_ctu\":" << int(lmcsCtuFlag)
        << ",\"lmcs_chroma_scale\":" << int(slice.m_picHeader->m_lmcsChromaResidualScaleFlag)
        << ",\"intra_y\":" << (intra&&cu.Y().valid()?int(cu.intraDir[ChannelType::LUMA]):-1)
        << ",\"intra_uv\":" << (intra&&cu.Cb().valid()?int(cu.intraDir[ChannelType::CHROMA]):-1)
        << ",\"luma_mode_idx\":" << (intra&&cu.Y().valid()?int(cu.lumaModeIdx):-1)
        << ",\"chroma_mode_idx\":" << (intra&&cu.Cb().valid()?int(cu.chromaModeIdx):-1)
        << ",\"mip\":" << int(intra&&cu.mipFlag) << ",\"dimd\":" << int(intra&&cu.dimdFlag)
        << ",\"dimd_chroma\":" << int(intra&&cu.dimdChromaFlag) << ",\"timd\":" << int(intra&&cu.timdFlag)
        << ",\"eip\":" << int(intra&&cu.eipFlag) << ",\"sgpm\":" << int(intra&&cu.sgpm)
        << ",\"cclm\":" << int(intra&&cu.Cb().valid()&&PU::isLMCMode(cu.intraDir[ChannelType::CHROMA]))
        << ",\"cccm\":" << (intra&&cu.Cb().valid()?int(cu.cccmFlag):0)
        << ",\"cccm_type\":" << (intra&&cu.Cb().valid()&&cu.cccmFlag?int(cu.cccmType):-1)
        << ",\"ccp_derived\":" << int(intra&&cu.Cb().valid()&&cu.decDerivedCcpMode)
        << ",\"ccp_nonlocal\":" << (intra&&cu.Cb().valid()?cu.idxNonLocalCCP:0)
        << ",\"ccp_fusion\":" << (intra&&cu.Cb().valid()?cu.ccMergeFusionIdx:0)
        << ",\"cc_filter\":" << int(intra&&cu.Cb().valid()&&cu.ccFilterFlag)
        << ",\"bdpcm_y\":" << (intra?int(cu.bdpcmMode[0]):0)
        << ",\"bdpcm_uv\":" << (intra?int(cu.bdpcmMode[1]):0)
        << ",\"merge\":" << int(inter&&cu.mergeFlag)
        << ",\"merge_idx\":" << (inter&&cu.mergeFlag?int(cu.mergeIdx):-1)
        << ",\"merge_type\":" << (inter&&cu.mergeFlag?int(cu.mergeType):-1)
        << ",\"inter_dir\":" << (inter?int(cu.interDir):0)
        << ",\"affine\":" << int(inter&&cu.affine) << ",\"geo\":" << int(inter&&cu.geoFlag)
        << ",\"ciip\":" << int(inter&&cu.ciipFlag) << ",\"obmc\":" << int(inter&&cu.obmcFlag)
        << ",\"lic\":" << int(inter&&cu.licFlag) << ",\"bdmvr\":" << int(inter&&cu.bdmvrRefine)
        << ",\"imv\":" << (inter?int(cu.imv):0) << ",\"bcw\":" << (inter?int(cu.bcwIdx):0);
    for(unsigned l=0;l<NUM_RPL01;++l)
    {
      const bool active=inter&&(cu.interDir&(1<<l));
      const int ref=active?int(cu.refIdx[l]):-1;
      const bool validRef=ref>=0 && ref<slice.m_numRefIdx[RefPicList(l)] && !CU::isIBC(cu);
      out << ",\"ref" << l << "\":" << ref
          << ",\"ref_poc" << l << "\":" << (validRef?slice.getRefPOC(RefPicList(l),ref):-1)
          << ",\"mvx" << l << "\":" << (active?cu.mv[l].getHor():0)
          << ",\"mvy" << l << "\":" << (active?cu.mv[l].getVer():0);
    }
    out << ",\"motion_hash\":" << (inter&&cu.Y().valid()?motionHash(cu):0) << "}";
    std::fprintf(stderr,"%s\n",out.str().c_str());
  }

  // Palette coefficients are escape values, not transform coefficients.
  if(palette) { return; }
  unsigned tuIndex=0;
  for(const auto &tu:CU::traverseTUs(cu))
  {
    for(unsigned comp=0;comp<getNumberValidComponents(cu.chromaFormat);++comp)
    {
      const auto id=CompID(comp);
      const auto &a=tu.blocks[id];
      if(!a.valid()) { continue; }
      if(!reserveRow(s,"TU",poc,ctu)) { continue; }
      ++s.tuRows;
      const bool cbf=TU::getCbf(tu,id);
      uint64_t coeffHash=hashSeed,nonzero=0,absSum=0;
      const CCoeffBuf coeff=tu.getCoeffs(id);
      for(unsigned y=0;y<a.height;++y)
        for(unsigned x=0;x<a.width;++x)
        {
          // A zero CBF implies zero levels; do not read an irrelevant buffer.
          const int q=cbf?coeff.at(x,y):0;
          coeffHash=hashValue(coeffHash,q);
          nonzero+=(q!=0);
          absSum+=uint64_t(q<0?-int64_t(q):int64_t(q));
        }
      // Decoder scratch buffers wrap at CTU boundaries. This hook runs before
      // the next CU, while all non-overlapping TUs of this CU are still live.
      // Intra prediction is overwritten by reconstruction in other builds.
      const bool predValid=!intra || KEEP_PRED_AND_RESI_SIGNALS || ENABLE_NNLF;
      // rootCbf=0 inter initializes only Y residual; UV is stale, not evidence.
      const bool resiValid=intra||cu.rootCbf||id==COMP_Y;
      const bool scaleApplied=isChroma(id)&&slice.m_lmcsEnabledFlag&&
        slice.m_picHeader->m_lmcsChromaResidualScaleFlag&&(cbf||tu.jointCbCr)&&a.area()>4&&
        (!intra||slice.isIntra()||lmcsCtuFlag);
      const bool lmcsDomain=id==COMP_Y&&slice.m_lmcsEnabledFlag&&(lmcsCtuFlag||slice.isIntra());
      std::ostringstream out;
      out << prefix("TU",poc,ctu,s.rows);
      areaFields(out,a);
      out << ",\"component\":" << comp << ",\"channel\":" << int(cu.chType)
          << ",\"cu_x\":" << cu.block(cu.chType).x << ",\"cu_y\":" << cu.block(cu.chType).y
          << ",\"cu_w\":" << cu.block(cu.chType).width << ",\"cu_h\":" << cu.block(cu.chType).height
          << ",\"tu_index\":" << tuIndex << ",\"depth\":" << int(tu.depth)
          << ",\"cbf\":" << int(cbf) << ",\"mts\":" << int(tu.mtsIdx[id])
          << ",\"ts\":" << int(cbf&&tu.mtsIdx[id]==MtsType::SKIP)
          << ",\"joint_cbcr\":" << int(tu.jointCbCr) << ",\"qp\":" << int(cu.qp)
          << ",\"qp_effective\":" << QpParam(tu,id).Qp(tu.mtsIdx[id]==MtsType::SKIP)
          << ",\"nonzero\":" << nonzero << ",\"abs_sum\":" << absSum << ",\"coeff_hash\":" << coeffHash
          << ",\"chroma_scale_applied\":" << int(scaleApplied)
          << ",\"chroma_adj\":" << (scaleApplied?tu.getChromaAdj():-1)
          << ",\"pred_valid\":" << int(predValid) << ",\"resi_valid\":" << int(resiValid)
          << ",\"pred_hash\":" << (predValid?hashBuffer(cu.cs->getPredBuf(a)):0)
          << ",\"resi_hash\":" << (resiValid?hashBuffer(cu.cs->getResiBuf(a)):0)
          << ",\"reco_hash\":" << hashBuffer(cu.cs->getRecoBuf(a))
          << ",\"reco_lmcs_domain\":" << int(lmcsDomain) << "}";
      std::fprintf(stderr,"%s\n",out.str().c_str());
    }
    ++tuIndex;
  }
}

inline void observeCtu(const CodingStructure &cs,const UnitArea &ctuArea)
{
  if(!TsR13DecodeObservation::options().enabled || cs.pcv->isEncoder) { return; }
  const int poc=cs.picture->m_poc,ctu=int(getCtuAddr(ctuArea.lumaPos(),*cs.pcv));
  if(!TsR13DecodeObservation::selected(poc,ctu)) { return; }
  State &s=state();
  std::lock_guard<std::mutex> lock(s.mutex);
  for(unsigned comp=0;comp<getNumberValidComponents(ctuArea.chromaFormat);++comp)
  {
    const auto id=CompID(comp);
    const auto a=clipArea(ctuArea.blocks[id],cs.area.blocks[id]);
    if(!a.valid()||!reserveRow(s,"CTU",poc,ctu)) { continue; }
    ++s.ctuRows;
    std::ostringstream out;
    out << prefix("CTU",poc,ctu,s.rows);
    areaFields(out,a);
    out << ",\"component\":" << comp << ",\"reco_hash\":" << hashBuffer(cs.getRecoBuf(a)) << "}";
    std::fprintf(stderr,"%s\n",out.str().c_str());
  }
}
}
