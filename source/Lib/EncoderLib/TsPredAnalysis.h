// Research observer, included only by CABACWriter.cpp with the analysis macro enabled.
// No state here is written back to the real writer, slice, or coefficients.
#pragma once
#include <array>
#include <cstdlib>
#include <fstream>
#include <iomanip>
#include <mutex>
#include <sstream>

namespace TsPred
{
constexpr int modes = 6;
constexpr int selectors = 5;
inline int predict(int mode, int l, int u)
{
  switch (mode)
  {
  case 0: return 0; // Identity remapping; significance/sign syntax remains intact.
  case 1: return std::max(l, u);
  case 2: return l;
  case 3: return u;
  case 4: return std::min(l, u);
  default: return std::min(l, u) + std::abs(l - u) / 2; // floor mean, no sum overflow
  }
}
inline int remap(int a, int p, bool disabled)
{
  return disabled || a == 0 ? a : a == p ? 1 : a < p ? a + 1 : a;
}
template<class T> int best(const std::array<T, modes> &s, bool maximum = false)
{
  int b = 1; // Exact ties always prefer Current, then ascending candidate index.
  for (int m = 0; m < modes; ++m)
    if (maximum ? s[m] > s[b] : s[m] < s[b]) b = m;
  return b;
}
inline int64_t decay(int64_t s) // Explicit arithmetic right shift, portable for negative scores.
{
  return s >= 0 ? s / 8 : -((-s + 7) / 8);
}
struct CostScope
{
  BinEncIf &bin;
  std::vector<uint64_t> *cost;
  int pos;
  uint64_t before;
  CostScope(BinEncIf &b, std::vector<uint64_t> *c, int p)
    : bin(b), cost(c), pos(p), before(c ? b.getEstFracBits() : 0) {}
  ~CostScope() { if (cost) (*cost)[pos] += bin.getEstFracBits() - before; }
};
inline std::string env(const char *key, const char *fallback)
{
  const char *v = std::getenv(key);
  return v ? v : fallback;
}
inline std::string quoted(const std::string &s)
{
  std::string r = "\"";
  for (char c : s) { if (c == '"') r += '"'; r += c; }
  return r + '"';
}
struct Sink
{
  std::mutex mutex;
  std::ofstream csv, debug, census;
  uint64_t tuId = 0, debugCount = 0;
  int debugLimit = 0;
  Sink()
  {
    csv.open(env("TS_PRED_STATS", "ts_pred_cg_stats.csv"), std::ios::trunc);
    CHECK(!csv, "Cannot open TS_PRED_STATS");
    census.open(env("TS_PRED_STATS", "ts_pred_cg_stats.csv") + ".tu.csv", std::ios::trunc);
    CHECK(!census, "Cannot open TS census");
    census << "sequence,configuration,QP,POC,component,prediction_type,TU_x,TU_y,TU_width,TU_height,tsrc_enabled,bdpcm,ts_max_size\n";
    csv << "sequence,configuration,QP,POC,component,prediction_type,TU_id,TU_x,TU_y,TU_width,TU_height,"
           "CG_index,CG_count_in_TU,num_coeff,num_nonzero,bdpcm,ts_max_size,rice_param,anchor_rem_bins,"
           "cu_qp,history_cg,history_nonzero,confidence_margin,oracle_mode,oracle_tie_mask,oracle_rate,current_pred_rate,"
           "previous_winner_mode,cumulative_mode,recency_mode,confidence_mode,simple_mode";
    for (int s = 0; s < selectors; ++s) csv << ",selector" << s << "_rate,selector" << s << "_path_rate";
    for (int m = 0; m < modes; ++m)
    {
      const std::string p = ",pred" + std::to_string(m);
      for (const char *field : {"rate", "path_rate", "hit_count", "under_count", "over_count", "abs_error_sum",
                                "active_count", "nz_hit_count", "nz_under_count", "nz_over_count",
                                "modified_level_0_count", "modified_level_1_count", "modified_level_2_count",
                                "modified_level_3_4_count", "modified_level_5_9_count", "modified_level_10plus_count",
                                "hit_gain", "under_gain", "over_gain", "simple_gain"}) csv << p << '_' << field;
    }
    csv << '\n';
    if (std::getenv("TS_PRED_DEBUG"))
    {
      debug.open(env("TS_PRED_DEBUG", ""));
      CHECK(!debug, "Cannot open TS_PRED_DEBUG");
      debugLimit = std::stoi(env("TS_PRED_DEBUG_CGS", "2"));
      debug << "TU_id,POC,CG_index,scan_pos,block_pos,q,L,U,mode,p,modified,active,frac_bits\n";
    }
  }
};
inline Sink &sink() { static Sink value; return value; }
inline void census(const TransformUnit &tu, CompID compID)
{
  auto &s = sink();
  std::lock_guard<std::mutex> lock(s.mutex);
  const auto &a = tu.blocks[compID];
  s.census << quoted(env("TS_PRED_SEQUENCE", "unspecified")) << ',' << quoted(env("TS_PRED_CONFIGURATION", "unspecified"))
    << ',' << env("TS_PRED_QP", std::to_string(int(tu.cu->qp)).c_str()) << ',' << tu.cu->slice->m_poc
    << ',' << int(to_underlying(compID)) << ',' << (CU::isIntra(*tu.cu) ? "intra" : CU::isInter(*tu.cu) ? "inter" : "other")
    << ',' << a.x << ',' << a.y << ',' << a.width << ',' << a.height
    << ',' << !tu.cs->slice->m_tsResidualCodingDisabledFlag << ',' << int(to_underlying(tu.cu->getBdpcmMode(compID)))
    << ',' << (1 << tu.cs->sps->m_log2MaxTransformSkipBlockSize) << '\n';
  CHECK(!s.census, "TS census write failed");
}
} // namespace TsPred

void CABACWriter::analyseTsPrediction(const TransformUnit &tu, CompID compID)
{
  using namespace TsPred;
  auto &sink = TsPred::sink();
  // The encoder is normally single-threaded per process; protect output if that changes.
  std::lock_guard<std::mutex> lock(sink.mutex);
  const uint64_t tuId = sink.tuId++;
  const TCoeff *coeff = tu.getCoeffs(compID).buf;
  CoeffCodingContext anchor(tu, compID, false, tu.cu->getBdpcmMode(compID));
  anchor.remRegBins = (anchor.maxNumCoeff() * 7) >> 2;
  const int n = anchor.maxNumCoeff(), cgSize = 1 << anchor.log2CGSize(), count = n / cgSize;
  std::bitset<MLS_GRP_NUM> sig;
  std::vector<int> inverse(n);
  for (int i = 0; i < n; ++i)
  {
    inverse[anchor.blockPos(i)] = i;
    if (coeff[anchor.blockPos(i)]) sig.set(i / cgSize);
  }
  const auto &area = tu.blocks[compID];
  // Assert neighbour causality for every actual scan/shape, not just square blocks.
  for (int i = 0; i < n; ++i)
  {
    int pos = anchor.blockPos(i), x = pos % area.width, y = pos / area.width;
    CHECK((x && inverse[pos - 1] >= i) || (y && inverse[pos - area.width] >= i), "Noncausal TS neighbour");
  }
  const int rice = 1 + (tu.cs->sps->m_spsRangeExtension.m_tsrcRicePresentFlag ? tu.cu->slice->m_tsrcIndex : 0);
  BitEstimator_Std shadow;
  shadow.getCtx() = getCtx();
  shadow.countWithUpdate(true);
  CABACWriter writer(shadow, nullptr);
  std::array<Ctx, modes + selectors> pathCtx;
  std::vector<CoeffCodingContext> pathCoding(modes + selectors, anchor);
  for (auto &ctx : pathCtx) ctx = getCtx();
  Ctx anchorCtx = getCtx();
  std::array<int64_t, modes> cumulative{}, recency{}, simple{};
  std::array<uint64_t, modes> previous{};
  int historyNonzero = 0;
  uint64_t anchorTotal = 0;
  for (int g = 0; g < count; ++g)
  {
    // Choose before accessing ANY current-group rates or observations.
    std::array<int, selectors> chosen {{g ? best(previous) : 1, best(cumulative, true), best(recency, true), 1,
                                       best(simple, true)}};
    auto ranked = recency;
    std::sort(ranked.begin(), ranked.end(), std::greater<int64_t>());
    const int64_t margin = ranked[0] - ranked[1];
    // Preregistered untuned probe. Export inputs for later held-out calibration.
    chosen[3] = g >= 2 && historyNonzero >= 8 && margin >= (1 << SCALE_BITS) ? chosen[2] : 1;
    anchor.initSubblock(g, sig[g]);
    const int entryBudget = anchor.remRegBins;
    std::array<uint64_t, modes> rates{}, pathRates{};
    std::array<std::vector<uint64_t>, modes> costs;
    std::array<std::vector<int>, modes> levels, active;
    int nextBudget = anchor.remRegBins;
    Ctx nextCtx = anchorCtx;
    for (int m = 0; m < modes; ++m)
    {
      CoeffCodingContext branch = anchor;
      shadow.getCtx() = anchorCtx;
      shadow.resetBits();
      writer.m_tsAnalysisMode = m;
      costs[m].assign(n, 0); levels[m].assign(n, 0); active[m].assign(n, 0);
      writer.m_tsAnalysisCosts = &costs[m];
      writer.m_tsAnalysisLevels = &levels[m];
      writer.m_tsAnalysisActive = &active[m];
      unsigned riceBits[8] = {};
      writer.residual_coding_subblockTS(branch, coeff, riceBits, rice, false);
      rates[m] = shadow.getEstFracBits();
      if (m == 1) { nextBudget = branch.remRegBins; nextCtx = shadow.getCtx(); }
    }
    writer.m_tsAnalysisCosts = nullptr;
    writer.m_tsAnalysisLevels = nullptr;
    writer.m_tsAnalysisActive = nullptr;
    std::array<uint64_t, selectors> selectorPath{};
    for (int j = 0; j < modes + selectors; ++j)
    {
      shadow.getCtx() = pathCtx[j]; shadow.resetBits();
      writer.m_tsAnalysisMode = j < modes ? j : chosen[j - modes];
      pathCoding[j].initSubblock(g, sig[g]);
      unsigned riceBits[8] = {};
      writer.residual_coding_subblockTS(pathCoding[j], coeff, riceBits, rice, false);
      pathCtx[j] = shadow.getCtx();
      if (j < modes) pathRates[j] = shadow.getEstFracBits();
      else selectorPath[j - modes] = shadow.getEstFracBits();
    }
    CHECK(pathRates[1] != rates[1], "Current counterfactual differs from continuous native TS estimator");
    anchorTotal += rates[1];
    const int oracle = best(rates);
    unsigned ties = 0;
    for (int m = 0; m < modes; ++m) if (rates[m] == rates[oracle]) ties |= 1u << m;
    int nz = 0;
    for (int i = g * cgSize; i < (g + 1) * cgSize; ++i) nz += coeff[anchor.blockPos(i)] != 0;
    std::ostringstream row;
    row << quoted(env("TS_PRED_SEQUENCE", "unspecified")) << ',' << quoted(env("TS_PRED_CONFIGURATION", "unspecified"))
        << ',' << env("TS_PRED_QP", std::to_string(int(tu.cu->qp)).c_str()) << ',' << tu.cu->slice->m_poc << ',' << int(to_underlying(compID))
        << ',' << (CU::isIntra(*tu.cu) ? "intra" : CU::isInter(*tu.cu) ? "inter" : "other")
        << ',' << tuId << ',' << area.x << ',' << area.y << ',' << area.width << ',' << area.height
        << ',' << g << ',' << count << ',' << cgSize << ',' << nz << ',' << int(to_underlying(anchor.bdpcm()))
        << ',' << (1 << tu.cs->sps->m_log2MaxTransformSkipBlockSize) << ',' << rice << ',' << entryBudget
        << ',' << int(tu.cu->qp) << ',' << g << ',' << historyNonzero << ',' << margin << ',' << oracle << ',' << ties
        << ',' << rates[oracle] << ',' << rates[1];
    for (int s : chosen) row << ',' << s;
    for (int s = 0; s < selectors; ++s) row << ',' << rates[chosen[s]] << ',' << selectorPath[s];
    const bool debug = sink.debug && sink.debugCount < uint64_t(sink.debugLimit);
    for (int m = 0; m < modes; ++m)
    {
      int hit = 0, under = 0, over = 0, enabled = 0;
      std::array<int, 3> nzClasses{};
      std::array<int, 6> hist{};
      std::array<int64_t, 3> classGain{};
      int64_t error = 0, simpleGain = 0;
      for (int i = g * cgSize; i < (g + 1) * cgSize; ++i)
      {
        int l, u; anchor.neighTS(l, u, i, coeff);
        const int a = std::abs(coeff[anchor.blockPos(i)]), p = predict(m, std::abs(l), std::abs(u));
        int cls = p == a ? 0 : p < a ? 1 : 2;
        hit += cls == 0; under += cls == 1; over += cls == 2;
        error += std::abs(p - a); enabled += active[m][i];
        if (a) nzClasses[cls]++;
        const int v = levels[m][i];
        hist[v < 3 ? v : v < 5 ? 3 : v < 10 ? 4 : 5]++;
        classGain[cls] += int64_t(costs[1][i]) - int64_t(costs[m][i]);
        // Gain in mapped magnitude: exact hit earns a-1, over-prediction loses 1.
        // Anchor eligibility uses only the already decoded history and shadow state.
        if (active[1][i]) simpleGain += remap(a, predict(1, std::abs(l), std::abs(u)), false) - remap(a, p, false);
        if (debug) sink.debug << tuId << ',' << tu.cu->slice->m_poc << ',' << g << ',' << i << ','
          << anchor.blockPos(i) << ',' << coeff[anchor.blockPos(i)] << ',' << l << ',' << u << ',' << m
          << ',' << p << ',' << v << ',' << active[m][i] << ',' << costs[m][i] << '\n';
      }
      row << ',' << rates[m] << ',' << pathRates[m] << ',' << hit << ',' << under << ',' << over << ',' << error
          << ',' << enabled;
      for (int v : nzClasses) row << ',' << v;
      for (int v : hist) row << ',' << v;
      for (int64_t v : classGain) row << ',' << v;
      row << ',' << simpleGain;
      const int64_t gain = int64_t(rates[1]) - int64_t(rates[m]);
      cumulative[m] += gain;
      recency[m] = recency[m] - decay(recency[m]) + gain;
      simple[m] = simple[m] - decay(simple[m]) + simpleGain;
    }
    sink.csv << row.str() << '\n';
    CHECK(!sink.csv, "TS statistics write failed");
    if (debug) ++sink.debugCount;
    previous = rates; historyNonzero += nz;
    anchor.remRegBins = nextBudget; anchorCtx = nextCtx;
  }
  shadow.getCtx() = getCtx(); shadow.resetBits(); writer.m_tsAnalysisMode = 1;
  writer.residual_codingTS(tu, compID);
  CHECK(shadow.getEstFracBits() != anchorTotal, "CG counterfactual sum differs from native full TU TS estimator");
}
