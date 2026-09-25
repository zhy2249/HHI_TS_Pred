// Final-writer-only aggregates. No coefficient text and no RDO search samples.
#pragma once
#include <array>
#include <cstdint>
#include <cstdio>
#include <map>
#include <mutex>
#include <tuple>

namespace TsFixedPrediction
{
struct R3Stats
{
  // No POC key: aggregate a whole run rather than emit one record per TU/CG.
  using Key = std::tuple<int, int, unsigned, unsigned, int, int, int, int, int>;
  enum Field { TU, CG, COEFF, NZ, ACTIVE, BYPASS, DIFFERENT, MAPPED, SCOPE_ON,
               LOCAL_PROPOSED, LOCAL_ACCEPT, LOCAL_REJECT,
               SUPPORT0, SUPPORT1, SUPPORT2, SUPPORT3, SUPPORT4, SUPPORT5,
               LOCAL_GPOS, LOCAL_GZERO, LOCAL_GNEG, LOCAL_B0, LOCAL_B1, LOCAL_B2, LOCAL_B3PLUS,
               LOCAL_HPOS, LOCAL_HZERO, LOCAL_HNEG,
               STATE_POS, NOPRED_CG, CERT_BLOCK, GAIN_POS, GAIN_ZERO, GAIN_NEG,
               CERT_POS, CERT_ZERO, CERT_NEG, EMPTY_CG, NO_ACTIVE_CG,
               GAIN_POS_SUM, GAIN_NEG_SUM, BEST_POS_SUM, COUNT };
  std::map<Key, std::array<uint64_t, COUNT>> rows;
  std::mutex mutex;
  void add(const Key &key, const std::array<uint64_t, COUNT> &values)
  {
    std::lock_guard<std::mutex> lock(mutex);
    auto &row = rows[key];
    for (int i = 0; i < COUNT; ++i) { row[i] += values[i]; }
  }
  ~R3Stats()
  {
    if (rows.empty()) { return; }
    const char *const fields[] = {
      "tu_count", "cg_count", "coeff_count", "nonzero_count", "active_count", "bypass_count",
      "p_different", "remap_different", "scope_enabled_cg", "local_proposed", "local_accept", "local_reject",
      "support0", "support1", "support2", "support3", "support4", "support5",
      "local_g_positive", "local_g_zero", "local_g_negative", "local_b0", "local_b1", "local_b2", "local_b3plus",
      "local_h_positive", "local_h_zero", "local_h_negative", "state_positive_cg", "nopred_cg", "certificate_block_cg",
      "gain_positive_cg", "gain_zero_cg", "gain_negative_cg", "next_certificate_positive_cg", "next_certificate_zero_cg",
      "next_certificate_negative_cg", "empty_cg", "no_active_cg", "gain_positive_sum", "gain_negative_abs_sum", "best_positive_sum"
    };
    static_assert(sizeof(fields) / sizeof(fields[0]) == COUNT, "R3 statistics columns mismatch");
    std::fprintf(stderr, "TS_R3_STATS_HEADER policy,component,width,height,cu_qp,intra,bdpcm,cg_count_in_tu,cg_index");
    for (const char *field : fields) { std::fprintf(stderr, ",%s", field); }
    std::fprintf(stderr, "\n");
    for (const auto &entry : rows)
    {
      const auto &k = entry.first;
      std::fprintf(stderr, "TS_R3_STATS %d,%d,%u,%u,%d,%d,%d,%d,%d", std::get<0>(k), std::get<1>(k),
                   std::get<2>(k), std::get<3>(k), std::get<4>(k), std::get<5>(k), std::get<6>(k),
                   std::get<7>(k), std::get<8>(k));
      for (uint64_t value : entry.second) { std::fprintf(stderr, ",%llu", (unsigned long long)value); }
      std::fprintf(stderr, "\n");
    }
  }
};
inline R3Stats &r3Stats() { static R3Stats stats; return stats; }
}
