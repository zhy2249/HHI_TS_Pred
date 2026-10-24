// Optional decoder-derived CCP evidence. Read-only snapshots of live reference
// samples and returned models; never invoked for encoder search trials.
#pragma once
#include "TsR13DecodeObservation.h"
#include "UnitTools.h"
#include <sstream>

namespace TsR13CcpDiagnostic
{
inline bool selected(const CodingUnit &cu)
{
  if(cu.cs->pcv->isEncoder || !TsR13DecodeObservation::selected(cu.cs->picture->m_poc,int(CU::getCtuAddr(cu))))
    return false;
  static const bool enabled=TsR13DecodeObservation::envInteger("TS_R13_DECODE_CCP",0,0,1)!=0;
  return enabled;
}
struct State
{
  uint64_t rows=0,omitted=0;
  std::mutex mutex;
  ~State()
  {
    if(rows||omitted)
      std::fprintf(stderr,"TS_R13_DEC {\"schema\":1,\"kind\":\"ccp_summary\",\"rows\":%" PRIu64
        ",\"omitted\":%" PRIu64 ",\"truncated\":%d}\n",rows,omitted,int(omitted!=0));
  }
};
inline State &state() { static State value; return value; }
inline uint64_t regionHash(const CPelBuf &ref,int x0,int y0,int x1,int y1)
{
  uint64_t hash=TsR13DecodeObservation::hashSeed;
  for(int y=y0;y<y1;++y)
    for(int x=x0;x<x1;++x)
      hash=TsR13DecodeObservation::hashValue(hash,ref.at(x,y));
  return hash;
}
inline void model(std::ostringstream &out,const CrossCompModels &m)
{
  out << "{\"valid\":" << int(m.valid);
  if(m.valid)
  {
    out << ",\"dual\":" << int(m.dualModel) << ",\"filter\":" << int(m.filter)
        << ",\"luma_threshold\":" << m.lumaThres << ",\"luma_offset\":" << m.lumaOffset
        << ",\"ref_size_x\":" << m.refSizeX << ",\"ref_size_y\":" << m.refSizeY;
    for(int c=0;c<2;++c)
    {
      out << (c==0?",\"cb\":[":",\"cr\":[");
      for(int d=0;d<(m.dualModel?2:1);++d)
      {
        if(d) out << ',';
        const auto &p=c==0?m.modelCb[d]:m.modelCr[d];
        out << "{\"type\":" << int(p.modelType) << ",\"bd\":" << p.bd << ",\"mid\":" << p.midVal << ",\"params\":[";
        for(size_t i=0;i<p.params.size();++i)
        {
          if(i) out << ',';
          out << p.params[i];
        }
        out << "]}";
      }
      out << ']';
    }
  }
  out << '}';
}
inline void observe(const CodingUnit &cu,const CPelBuf &ref,int width,int height,int left,int top,
                    int posX,int posY,const CrossCompModels &first,const CrossCompModels &second,
                    const std::vector<int> &costs,int bestIndex,int bestCost)
{
  if(!selected(cu)) return;
  State &s=state();
  std::lock_guard<std::mutex> lock(s.mutex);
  const int poc=cu.cs->picture->m_poc,ctu=int(CU::getCtuAddr(cu));
  if(s.rows>=uint64_t(TsR13DecodeObservation::options().limit))
  {
    if(++s.omitted==1)
      std::fprintf(stderr,"TS_R13_DEC {\"schema\":1,\"kind\":\"ccp_truncated\",\"poc\":%d,\"ctu\":%d}\n",poc,ctu);
    return;
  }
  ++s.rows;
  const int bx=left+int(cu.Cb().width),by=top+int(cu.Cb().height);
  std::ostringstream out;
  out << "TS_R13_DEC {\"schema\":1,\"kind\":\"ccp\",\"revision\":\"R13-DEC-CCP-v1\",\"poc\":" << poc
      << ",\"ctu\":" << ctu << ",\"x\":" << cu.Cb().x << ",\"y\":" << cu.Cb().y
      << ",\"w\":" << cu.Cb().width << ",\"h\":" << cu.Cb().height
      << ",\"ref_x\":" << posX << ",\"ref_y\":" << posY << ",\"ref_w\":" << width << ",\"ref_h\":" << height
      << ",\"left\":" << left << ",\"top\":" << top
      << ",\"ref_domain\":\"downsampled_luma_minus_offset\",\"top_hash\":" << regionHash(ref,0,0,width,top)
      << ",\"left_hash\":" << regionHash(ref,0,top,left,height)
      << ",\"below_left_hash\":" << regionHash(ref,0,by,left,height)
      << ",\"below_left_east_hash\":" << regionHash(ref,left,by,left+1,height)
      << ",\"below_left_east_samples\":" << height-by
      << ",\"below_left_east_x\":" << posX+left << ",\"below_left_east_y\":" << posY+by
      << ",\"block_hash\":" << regionHash(ref,left,top,bx,by)
      << ",\"block_top_hash\":" << regionHash(ref,left,top-1,bx,top)
      << ",\"block_left_hash\":" << regionHash(ref,left-1,top,left,by)
      << ",\"block_right_hash\":" << regionHash(ref,bx,top,bx+1,by)
      << ",\"block_bottom_hash\":" << regionHash(ref,left,by,bx,by+1)
      << ",\"nonfused_best_index\":" << bestIndex << ",\"nonfused_best_cost\":" << bestCost
      << ",\"candidate_costs\":[";
  for(size_t i=0;i<costs.size();++i) { if(i) out << ','; out << costs[i]; }
  out << "],\"selected_models\":[";
  model(out,first); out << ','; model(out,second); out << "]}";
  std::fprintf(stderr,"%s\n",out.str().c_str());
}
}
