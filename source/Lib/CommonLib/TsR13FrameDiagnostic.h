// Pure observation of final frame reconstruction at loop-filter boundaries.
// No reconstructed samples or coding state are changed. Hashes are diagnostic
// FNV-1a over signed Pel values represented as four little-endian bytes, not MD5.
#pragma once
#include "TsFixedPrediction.h"
#include "Picture.h"
#include <cinttypes>
#include <mutex>
#include <vector>

namespace TsFixedPrediction
{
struct R13FrameMetric
{
  uint64_t samples=0,sse=0;
  uint64_t originalHash=UINT64_C(14695981039346656037);
  uint64_t reconstructionHash=UINT64_C(14695981039346656037);
  static uint64_t hashPel(uint64_t hash,int value)
  {
    const uint32_t bits=static_cast<uint32_t>(value);
    for(unsigned shift=0;shift<32;shift+=8)
    {
      hash^=(bits>>shift)&255u;
      hash*=UINT64_C(1099511628211);
    }
    return hash;
  }
  void add(int original,int reconstruction)
  {
    const int64_t difference=int64_t(original)-int64_t(reconstruction);
    ++samples; sse+=uint64_t(difference*difference);
    originalHash=hashPel(originalHash,original);
    reconstructionHash=hashPel(reconstructionHash,reconstruction);
  }
};

inline void r13ObserveFrame(const char *stage,const Picture &picture,bool useTrueOriginal,bool clipPending)
{
  const auto &options=r13Observation();
  const int poc=picture.m_poc;
  if(!options.diagnostic || poc<0 || poc>options.diagnosticMaxPoc ||
     (options.poc>=0 && options.poc!=poc)) { return; }

  // This helper is called only AFTER inverse LMCS. Original selection follows
  // EncGOP's PSNR choice, including unfiltered TrueOrig when MCTF is enabled.
  // Metrics cover the coded buffer, including any padding: they are unweighted
  // raw internal-bit-depth SSE, not a claim of equality to cropped/WPSNR output.
  const CPelUnitBuf original=useTrueOriginal?picture.getTrueOrigBuf():picture.getOrigBuf();
  const CPelUnitBuf reconstruction=picture.getRecoBuf();
  static std::once_flag header;
  std::call_once(header,[] {
    std::fprintf(stderr,"TS_R13_FRAME_HEADER trajectory,poc,layer,stage,component,bitdepth,width,height,grid_size,clip_pending,true_original,samples,sse,original_hash,reconstruction_hash\n");
    std::fprintf(stderr,"TS_R13_FRAME_TILE_HEADER trajectory,poc,layer,stage,component,bitdepth,x,y,width,height,clip_pending,true_original,samples,sse,original_hash,reconstruction_hash\n");
  });
  static constexpr int gridSize=64; // Component-sample coordinates, not luma coordinates.
  for(unsigned comp=0;comp<getNumberValidComponents(reconstruction.chromaFormat);++comp)
  {
    if(options.diagnosticComponent>=0 && int(comp)!=options.diagnosticComponent) { continue; }
    const auto id=CompID(comp);
    const CPelBuf o=original.get(id),r=reconstruction.get(id);
    CHECK(o.width!=r.width || o.height!=r.height,"R13 frame diagnostic buffer dimensions differ");
    const int frameWidth=int(r.width),frameHeight=int(r.height);
    const int columns=(frameWidth+gridSize-1)/gridSize;
    const int rows=(frameHeight+gridSize-1)/gridSize;
    const int bitDepth=picture.m_cs->sps->m_bitDepths[toChannelType(id)];
    std::vector<R13FrameMetric> tiles(columns*rows);
    R13FrameMetric frame;
    for(int y=0;y<frameHeight;++y)
      for(int x=0;x<frameWidth;++x)
      {
        const int a=o.buf[y*o.stride+x],b=r.buf[y*r.stride+x];
        frame.add(a,b);
        tiles[(y/gridSize)*columns+x/gridSize].add(a,b);
      }
    std::fprintf(stderr,"TS_R13_FRAME %d,%d,%d,%s,%u,%d,%d,%d,%d,%d,%d,%" PRIu64 ",%" PRIu64 ",%" PRIu64 ",%" PRIu64 "\n",
      mode(),poc,picture.m_layerId,stage,comp,bitDepth,frameWidth,frameHeight,gridSize,int(clipPending),int(useTrueOriginal),
      frame.samples,frame.sse,frame.originalHash,frame.reconstructionHash);
    for(int by=0;by<rows;++by)
      for(int bx=0;bx<columns;++bx)
      {
        const int x=bx*gridSize,y=by*gridSize;
        const int width=std::min(gridSize,frameWidth-x),height=std::min(gridSize,frameHeight-y);
        const auto &tile=tiles[by*columns+bx];
        std::fprintf(stderr,"TS_R13_FRAME_TILE %d,%d,%d,%s,%u,%d,%d,%d,%d,%d,%d,%d,%" PRIu64 ",%" PRIu64 ",%" PRIu64 ",%" PRIu64 "\n",
          mode(),poc,picture.m_layerId,stage,comp,bitDepth,x,y,width,height,int(clipPending),int(useTrueOriginal),
          tile.samples,tile.sse,tile.originalHash,tile.reconstructionHash);
      }
  }
}
}
