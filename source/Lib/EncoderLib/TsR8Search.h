// C03/C04: paired local OWNER-RD trials. Not a decoder decision or RDOQ proxy.
#pragma once
#include "CommonLib/TsFixedPrediction.h"
#if JVET_BJUT_TS_FIXED_PREDICTOR
#include "CommonLib/CodingStructure.h"
#include "CommonLib/Picture.h"
#include <array>
#include <cmath>
#include <map>
#include <mutex>
#include <tuple>
#include <vector>

namespace TsFixedPrediction
{
struct R8SearchStats
{
  using Key = std::tuple<int,int,int,int,int,int,int,int>;
  struct Row { uint64_t pairs=0, extra=0, changed=0, chosen1=0, ties=0, valid=0; double j0=0,j1=0,gain=0; };
  std::map<Key,Row> rows;
  std::mutex mutex;
  void add(const TransformUnit &tu, CompID comp, int owner, unsigned extra, bool changed, double j0, double j1)
  {
    static const bool enabled = !std::getenv("TS_R8_STATS") || std::strcmp(std::getenv("TS_R8_STATS"),"0");
    if (!enabled) { return; }
    std::lock_guard<std::mutex> lock(mutex);
    auto &r = rows[{r8PublicMode(mode()),int(comp),int(tu.blocks[comp].width),int(tu.blocks[comp].height),
                    tu.cu->qp,tu.cu->predMode == MODE_INTRA,int(tu.jointCbCr),owner}];
    ++r.pairs; r.extra += extra; r.changed += changed; r.chosen1 += j1 < j0; r.ties += j0 == j1;
    if (j0 < MAX_DOUBLE / 4 && j1 < MAX_DOUBLE / 4)
    { ++r.valid; r.j0 += j0; r.j1 += j1; r.gain += j0 - std::min(j0,j1); }
  }
  ~R8SearchStats()
  {
    if (rows.empty()) { return; }
    std::fprintf(stderr,"TS_R8_SEARCH_HEADER mode,component,width,height,cu_qp,intra,joint,owner,pairs,extra_up_candidates,q_changed,chosen_q1,ties,both_valid,j0_sum,j1_sum,local_gain_sum\n");
    for (const auto &v:rows)
    {
      const auto &k=v.first; const auto &r=v.second;
      std::fprintf(stderr,"TS_R8_SEARCH %d,%d,%d,%d,%d,%d,%d,%d,%llu,%llu,%llu,%llu,%llu,%llu,%.17g,%.17g,%.17g\n",
        std::get<0>(k),std::get<1>(k),std::get<2>(k),std::get<3>(k),std::get<4>(k),std::get<5>(k),std::get<6>(k),std::get<7>(k),
        (unsigned long long)r.pairs,(unsigned long long)r.extra,(unsigned long long)r.changed,
        (unsigned long long)r.chosen1,(unsigned long long)r.ties,(unsigned long long)r.valid,r.j0,r.j1,r.gain);
    }
  }
};
inline R8SearchStats &r8SearchStats() { static R8SearchStats s; return s; }

// One checkpoint per TS trial only. Owned coefficient/sign storage, no aliased
// "copy" of q. CodingStructure/CU topology is not changed by these callbacks.
class R8SearchEntry
{
  TransformUnit saved;
  std::array<std::vector<TCoeff>,MAX_NUM_TBLOCKS> coeff;
  std::array<std::vector<uint8_t>,MAX_NUM_TBLOCKS> signs;
  std::array<std::array<std::vector<Pel>,5>,MAX_NUM_TBLOCKS> pixels;
public:
  R8SearchEntry(TransformUnit &tu, CompID first, CompID last): saved(static_cast<const UnitArea&>(tu))
  {
    saved.cs=tu.cs; saved.cu=tu.cu;
    TCoeff *cp[MAX_NUM_TBLOCKS]{}; uint8_t *sp[MAX_NUM_TBLOCKS]{};
    EnumArray<Pel*,ChannelType> plt{}; EnumArray<bool*,ChannelType> run{};
    for (int c=0;c<int(tu.blocks.size());++c)
      if (tu.blocks[c].valid())
      {
        coeff[c].resize(tu.blocks[c].area()); cp[c]=coeff[c].data();
        if (tu.getSignsPredArea(CompID(c))) { signs[c].resize(tu.blocks[c].area()); sp[c]=signs[c].data(); }
      }
    saved.init(cp,sp,plt,run); saved=tu;
    for (int c=first;c<=last;++c)
      if (tu.blocks[c].valid())
      {
        const auto &a=tu.blocks[c];
        const CPelBuf src[] = {tu.cs->getRecoBuf(a),tu.cs->getResiBuf(a),tu.cs->getPredBuf(a),
                              tu.cs->getOrgResiBuf(a),tu.cs->picture->getRecoBuf(a)};
        for (int b=0;b<5;++b) { pixels[c][b].resize(a.area()); PelBuf(pixels[c][b].data(),a).copyFrom(src[b]); }
      }
  }
  void restore(TransformUnit &tu)
  {
    tu=saved;
    for (int c=0;c<int(tu.blocks.size());++c)
      if (!pixels[c][0].empty())
      {
        const auto &a=tu.blocks[c];
        PelBuf dst[] = {tu.cs->getRecoBuf(a),tu.cs->getResiBuf(a),tu.cs->getPredBuf(a),
                        tu.cs->getOrgResiBuf(a),tu.cs->picture->getRecoBuf(a)};
        for (int b=0;b<5;++b) { dst[b].copyFrom(CPelBuf(pixels[c][b].data(),a)); }
      }
  }
};

// evaluate() must reset its scalar outputs and owner auxiliary context each
// invocation, then return the UNCHANGED owner's full relevant local RD cost.
// The unchosen output is discarded; if q0 wins, deterministically rerun it to
// retain all native scratch/filter/quantizer outputs without partial restore.
template<class Evaluate>
void r8OwnerSearch(TransformUnit &tu, CompID comp, bool joint, MtsType tr,
                   CABACWriter &estimator, int owner, const Evaluate &evaluate)
{
  if (!r8DualQuant(mode()) || tr != MtsType::SKIP || tu.cu->getBdpcmMode(comp) != BdpcmMode::NONE || tu.noResidual)
  { evaluate(); return; }
  CHECK(tu.tsR8ExtendedSearch,"Nested R8 paired search");
  R8SearchEntry entry(tu,joint ? COMP_Cb : comp,joint ? COMP_Cr : comp);
  const Ctx initial(estimator.getCtx());
  tu.tsR8ExtraCandidates=0;
  const double j0=evaluate();
  std::vector<TCoeff> q0;
  for (int c=joint ? COMP_Cb : comp;c<=int(joint ? COMP_Cr : comp);++c)
  { auto q=tu.getCoeffs(CompID(c)); q0.insert(q0.end(),q.buf,q.buf+q.area()); }
  entry.restore(tu); estimator.getCtx()=initial;
  tu.tsR8ExtendedSearch=true;
  const double j1=evaluate();
  const unsigned extra=tu.tsR8ExtraCandidates;
  tu.tsR8ExtendedSearch=false;
  bool changed=false; size_t offset=0;
  for (int c=joint ? COMP_Cb : comp;c<=int(joint ? COMP_Cr : comp);++c)
  {
    auto q=tu.getCoeffs(CompID(c));
    changed |= !std::equal(q.buf,q.buf+q.area(),q0.begin()+offset); offset+=q.area();
  }
  CHECK(std::isnan(j0) || std::isnan(j1),"NaN R8 owner cost");
  r8SearchStats().add(tu,comp,owner,extra,changed,j0,j1);
  if (!(j1 < j0))
  {
    entry.restore(tu); estimator.getCtx()=initial;
    const double repeated=evaluate();
    CHECK(repeated != j0,"R8 q0 owner state was not restored exactly");
    offset=0;
    for (int c=joint ? COMP_Cb : comp;c<=int(joint ? COMP_Cr : comp);++c)
    { auto q=tu.getCoeffs(CompID(c)); CHECK(!std::equal(q.buf,q.buf+q.area(),q0.begin()+offset),"R8 q0 changed on replay"); offset+=q.area(); }
  }
  tu.tsR8ExtraCandidates=0;
}
}
#endif
