// Decoder-only read-only R13 diagnostics. The decoded picture remains untouched.
// Original-file comparison is optional and never participates in decoding.
#pragma once
#include "TsFixedPrediction.h"
#include "Picture.h"
#include <cinttypes>
#include <climits>
#include <cstdlib>
#include <cstdio>
#include <fstream>
#include <mutex>
#include <string>
#include <vector>

namespace TsR13DecodeObservation
{
constexpr uint64_t hashSeed = UINT64_C(14695981039346656037);
inline uint64_t hashValue(uint64_t hash, int value)
{
  const uint32_t bits = static_cast<uint32_t>(value);
  for (unsigned shift=0; shift<32; shift+=8)
  {
    hash ^= (bits>>shift)&255u;
    hash *= UINT64_C(1099511628211);
  }
  return hash;
}
inline uint64_t hashBuffer(const CPelBuf &buffer)
{
  uint64_t hash=hashSeed;
  for (unsigned y=0; y<buffer.height; ++y)
    for (unsigned x=0; x<buffer.width; ++x)
      hash=hashValue(hash,buffer.buf[y*buffer.stride+x]);
  return hash;
}
struct Options
{
  bool enabled=false;
  int poc=-1,maxPoc=31,ctu=-1,limit=200000,originalBits=-1,originalFrameSkip=0;
  std::string original;
};
inline int envInteger(const char *name,int fallback,int minimum,int maximum)
{
  const char *value=std::getenv(name);
  if (!value || !*value) return fallback;
  char *end=nullptr;
  const long parsed=std::strtol(value,&end,10);
  CHECK(*end || parsed<minimum || parsed>maximum,"Invalid R13 decoder diagnostic integer option");
  return int(parsed);
}
inline const Options &options()
{
  static const Options value=[] {
    Options o;
    o.enabled=envInteger("TS_R13_DECODE_DIAG",0,0,1)!=0;
    if (!o.enabled) return o;
    o.poc=envInteger("TS_R13_DECODE_POC",-1,-1,INT_MAX);
    o.maxPoc=envInteger("TS_R13_DECODE_MAX_POC",31,0,INT_MAX);
    CHECK(o.poc>o.maxPoc,"R13 decoder target POC exceeds TS_R13_DECODE_MAX_POC");
    o.ctu=envInteger("TS_R13_DECODE_CTU",-1,-1,INT_MAX);
    o.limit=envInteger("TS_R13_DECODE_LIMIT",200000,1,INT_MAX);
    const char *path=std::getenv("TS_R13_DECODE_ORIGINAL");
    if (path && *path)
    {
      o.original=path;
      o.originalBits=envInteger("TS_R13_DECODE_ORIGINAL_BITS",-1,8,16);
      CHECK(o.originalBits<8,"TS_R13_DECODE_ORIGINAL requires explicit TS_R13_DECODE_ORIGINAL_BITS");
      o.originalFrameSkip=envInteger("TS_R13_DECODE_ORIGINAL_FRAME_SKIP",0,0,INT_MAX);
    }
    return o;
  }();
  return value;
}
inline bool selected(int poc,int ctu=-1)
{
  const auto &o=options();
  return o.enabled && poc>=0 && poc<=o.maxPoc && (o.poc<0 || o.poc==poc) && (ctu<0 || o.ctu<0 || o.ctu==ctu);
}

// Only DecLib's loop-filter scope activates CommonLib hooks. Encoder use of
// CommonLib ALF cannot accidentally create decoder observations.
inline bool &loopActive() { static thread_local bool value=false; return value; }
struct LoopScope
{
  bool previous;
  explicit LoopScope(int poc):previous(loopActive()) { loopActive()=selected(poc); }
  ~LoopScope() { loopActive()=previous; }
};

struct OriginalFrame
{
  int poc=-1,width=0,height=0;
  std::vector<int> plane[MAX_NUM_COMP];
};
inline const OriginalFrame *originalFrame(const Picture &picture)
{
  const auto &o=options();
  if (o.original.empty()) return nullptr;
  const CPelUnitBuf rec=picture.getRecoBuf();
  CHECK(picture.m_layerId!=0,"R13 decoder external original currently supports layer 0 only");
  CHECK(rec.chromaFormat!=ChromaFormat::_420,"R13 decoder original comparison currently requires planar 4:2:0");
  const int width=rec.Y().width,height=rec.Y().height;
  CHECK(width%2 || height%2,"R13 decoder original comparison requires even frame dimensions");
  static thread_local OriginalFrame frame;
  if (frame.poc==picture.m_poc && frame.width==width && frame.height==height) return &frame;
  frame.poc=picture.m_poc; frame.width=width; frame.height=height;
  const uint64_t samples=uint64_t(width)*height*3/2;
  const unsigned bytesPerSample=o.originalBits>8?2:1;
  const uint64_t frameBytes=samples*bytesPerSample;
  std::ifstream file(o.original,std::ios::binary|std::ios::ate);
  CHECK(!file,"Cannot open R13 decoder diagnostic original");
  const auto fileBytes=file.tellg();
  const uint64_t index=uint64_t(picture.m_poc)+unsigned(o.originalFrameSkip);
  CHECK(fileBytes<0 || uint64_t(fileBytes)%frameBytes || uint64_t(fileBytes)<(index+1)*frameBytes,
        "R13 decoder original file size/frame index is inconsistent with decoded geometry");
  file.seekg(std::streamoff(index*frameBytes));
  std::vector<unsigned char> data(frameBytes);
  file.read(reinterpret_cast<char *>(data.data()),std::streamsize(data.size()));
  CHECK(!file,"Cannot read R13 decoder diagnostic original frame");
  uint64_t pos=0;
  for (unsigned c=0;c<MAX_NUM_COMP;++c)
  {
    const auto id=CompID(c);
    const auto &buf=rec.get(id);
    const int shift=picture.m_cs->sps->m_bitDepths[toChannelType(id)]-o.originalBits;
    CHECK(shift<0,"R13 diagnostic original bit depth must not exceed internal bit depth");
    frame.plane[c].resize(buf.width*buf.height);
    for (auto &sample:frame.plane[c])
    {
      unsigned raw=data[pos++];
      if (bytesPerSample==2) raw|=unsigned(data[pos++])<<8;
      CHECK(raw>=(1u<<o.originalBits),"R13 diagnostic original sample exceeds declared bit depth");
      sample=int(raw<<shift);
    }
  }
  return &frame;
}
struct Metric
{
  uint64_t samples=0,sse=0,originalHash=hashSeed,reconstructionHash=hashSeed;
  void add(int value,int original,bool hasOriginal)
  {
    ++samples; reconstructionHash=hashValue(reconstructionHash,value);
    if (hasOriginal)
    {
      const int64_t delta=int64_t(value)-original;
      sse+=uint64_t(delta*delta); originalHash=hashValue(originalHash,original);
    }
  }
};

// Full-frame rows and complete component-coordinate 64x64 tile grids remain
// global even with a CTU filter. That filter applies to block/filter detail.
// SSE/original_hash use -1 when no original was explicitly supplied.
inline void observe(const char *stage,const Picture &picture,const CPelUnitBuf &rec,
                    bool clipPending=false,bool clipOnly=false)
{
  if (!loopActive() || !selected(picture.m_poc)) return;
  const OriginalFrame *original=originalFrame(picture);
  static std::once_flag header;
  std::call_once(header,[] {
    std::fprintf(stderr,"TS_R13_DEC_FRAME_HEADER trajectory,poc,layer,stage,component,bitdepth,width,height,grid_size,clip_pending,has_original,samples,sse,original_hash,reconstruction_hash\n");
    std::fprintf(stderr,"TS_R13_DEC_TILE_HEADER trajectory,poc,layer,stage,component,bitdepth,x,y,width,height,clip_pending,has_original,samples,sse,original_hash,reconstruction_hash\n");
  });
  constexpr int grid=64;
  for (unsigned c=0;c<getNumberValidComponents(rec.chromaFormat);++c)
  {
    const auto id=CompID(c);
    const auto &r=rec.get(id);
    const int w=r.width,h=r.height,columns=(w+grid-1)/grid,rows=(h+grid-1)/grid;
    const int bits=picture.m_cs->sps->m_bitDepths[toChannelType(id)];
    const auto &range=picture.m_cs->slice->clpRng(id);
    Metric frame;
    std::vector<Metric> tiles(columns*rows);
    for (int y=0;y<h;++y) for (int x=0;x<w;++x)
    {
      const int raw=r.buf[y*r.stride+x];
      const int value=clipOnly?std::min(range.max,std::max(range.min,raw)):raw;
      const int source=original?original->plane[c][y*w+x]:0;
      frame.add(value,source,original!=nullptr);
      tiles[(y/grid)*columns+x/grid].add(value,source,original!=nullptr);
    }
    const auto sse=original?std::to_string(frame.sse):"-1";
    const auto oh=original?std::to_string(frame.originalHash):"-1";
    std::fprintf(stderr,"TS_R13_DEC_FRAME %d,%d,%d,%s,%u,%d,%d,%d,%d,%d,%d,%" PRIu64 ",%s,%s,%" PRIu64 "\n",
      TsFixedPrediction::mode(),picture.m_poc,picture.m_layerId,stage,c,bits,w,h,grid,int(clipPending),int(original!=nullptr),
      frame.samples,sse.c_str(),oh.c_str(),frame.reconstructionHash);
    for (int by=0;by<rows;++by) for (int bx=0;bx<columns;++bx)
    {
      const auto &tile=tiles[by*columns+bx];
      const auto tsse=original?std::to_string(tile.sse):"-1";
      const auto toh=original?std::to_string(tile.originalHash):"-1";
      std::fprintf(stderr,"TS_R13_DEC_TILE %d,%d,%d,%s,%u,%d,%d,%d,%d,%d,%d,%d,%" PRIu64 ",%s,%s,%" PRIu64 "\n",
        TsFixedPrediction::mode(),picture.m_poc,picture.m_layerId,stage,c,bits,bx*grid,by*grid,
        std::min(grid,w-bx*grid),std::min(grid,h-by*grid),int(clipPending),int(original!=nullptr),
        tile.samples,tsse.c_str(),toh.c_str(),tile.reconstructionHash);
    }
  }
}
inline void observe(const char *stage,const Picture &picture,bool clipPending=false,bool clipOnly=false)
{ observe(stage,picture,picture.getRecoBuf(),clipPending,clipOnly); }

inline void filterSummary(const Picture &picture)
{
  if (!loopActive()) return;
  const auto &cs=*picture.m_cs;
  for (int ctu=0;ctu<picture.m_ctuNums;++ctu)
  {
    if (!selected(picture.m_poc,ctu)) continue;
    const auto &pcv=*cs.pcv;
    const unsigned columns=(pcv.lumaWidth+pcv.maxCUWidth-1)/pcv.maxCUWidth;
    const auto *cu=cs.getCU(Position((ctu%columns)*pcv.maxCUWidth,(ctu/columns)*pcv.maxCUHeight),ChannelType::LUMA);
    const auto &slice=*cu->slice;
    for (unsigned c=0;c<getNumberValidComponents(picture.getRecoBuf().chromaFormat);++c)
    {
      const auto id=CompID(c);
      const auto &modes=picture.getAlfModes(id);
      const int alfMode=unsigned(ctu)<modes.size()?modes[ctu]:-1;
      const int saoSet=(slice.m_ccSaoEnabledFlag[c] && slice.m_ccSaoControl[c])?slice.m_ccSaoControl[c][ctu]:0;
      const bool ccAlfEnabled=c && (c==1?slice.m_ccAlfCbEnabledFlag:slice.m_ccAlfCrEnabledFlag);
      const int ccAlfFilter=ccAlfEnabled && slice.m_ccAlfFilterControl[c-1]?slice.m_ccAlfFilterControl[c-1][ctu]:0;
      uint64_t saoHash=hashSeed,ccHash=hashSeed;
      const auto &sao=slice.m_ccSaoComParam;
      saoHash=hashValue(saoHash,sao.enabled[c]); saoHash=hashValue(saoHash,sao.extChroma[c]);
      saoHash=hashValue(saoHash,sao.setNum[c]);
      for (unsigned s=0;s<sao.setNum[c];++s)
      {
        saoHash=hashValue(saoHash,sao.setEnabled[c][s]); saoHash=hashValue(saoHash,sao.setType[c][s]);
        for (unsigned k=0;k<MAX_NUM_COMP;++k)
        {
          saoHash=hashValue(saoHash,sao.candPos[c][s][k]); saoHash=hashValue(saoHash,sao.bandNum[c][s][k]);
        }
        for (unsigned k=0;k<MAX_CCSAO_CLASS_NUM;++k) saoHash=hashValue(saoHash,sao.offset[c][s][k]);
      }
      if (c && ccAlfFilter>0 && cs.sps->m_alfImprovementsEnabledFlag)
      {
        const auto &coeff=slice.m_ccAlfFilterParam.getEcmParamNoCheck().ccAlfCoeff[c-1][ccAlfFilter-1];
        for (const auto value:coeff) ccHash=hashValue(ccHash,value);
      }
      std::fprintf(stderr,"TS_R13_DEC {\"kind\":\"filter\",\"poc\":%d,\"ctu\":%d,\"component\":%u,\"alf_enabled\":%d,\"alf_mode\":%d,\"alf_chroma_aps\":%d,\"ccalf_enabled\":%d,\"ccalf_filter\":%d,\"ccalf_aps\":%d,\"ccalf_coeff_hash\":\"%" PRIu64 "\",\"ccsao_enabled\":%d,\"ccsao_set\":%d,\"ccsao_params_hash\":\"%" PRIu64 "\",\"lfcccm_enabled\":%d}\n",
        picture.m_poc,ctu,c,int(slice.m_alfEnabledFlag[c]),alfMode,slice.m_alfApsIdChroma,
        int(ccAlfEnabled),ccAlfFilter,
        c?(c==1?slice.m_ccAlfCbApsId:slice.m_ccAlfCrApsId):-1,ccHash,
        int(slice.m_ccSaoEnabledFlag[c]),saoSet,saoHash,int(slice.m_lfCccmEnabledFlag));
    }
  }
}
}
