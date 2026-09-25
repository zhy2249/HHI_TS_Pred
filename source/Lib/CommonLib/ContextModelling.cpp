/* The copyright in this software is being made available under the BSD
 * License, included below. This software may be subject to other third party
 * and contributor rights, including patent rights, and no such rights are
 * granted under this license.
 *
 * Copyright (c) 2010-2023, ITU/ISO/IEC
 * All rights reserved.
 *
 * Redistribution and use in source and binary forms, with or without
 * modification, are permitted provided that the following conditions are met:
 *
 *  * Redistributions of source code must retain the above copyright notice,
 *    this list of conditions and the following disclaimer.
 *  * Redistributions in binary form must reproduce the above copyright notice,
 *    this list of conditions and the following disclaimer in the documentation
 *    and/or other materials provided with the distribution.
 *  * Neither the name of the ITU/ISO/IEC nor the names of its contributors may
 *    be used to endorse or promote products derived from this software without
 *    specific prior written permission.
 *
 * THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
 * AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
 * IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
 * ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS
 * BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
 * CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
 * SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
 * INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
 * CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
 * ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF
 * THE POSSIBILITY OF SUCH DAMAGE.
 */

/** \file     ContextModelling.cpp
    \brief    Classes providing probability descriptions and contexts
*/

#include <algorithm>

#include "ContextModelling.h"
#include "UnitTools.h"
#include "CodingStructure.h"
#include "Picture.h"
#if JVET_BJUT_TS_FIXED_PREDICTOR
#include "TsVirtualCoding.h"
#include "TsR2Stats.h"
#include "TsR3Stats.h"
#include "TsR4Stats.h"
#include "TsR5Stats.h"
#include "TsR6Stats.h"
#endif

const int CoeffCodingContext::prefixCtx[] = { 0, 0, 0, 3, 6, 10, 15, 21, 28 };

CoeffCodingContext::CoeffCodingContext(const TransformUnit &tu, CompID component, bool signHide, const BdpcmMode bdpcm)
  : m_compID(component)
  , m_chType(toChannelType(m_compID))
  , m_nstIdx(TU::getNstIdx(tu, m_compID))
  , m_width(tu.block(m_compID).width)
  , m_height(tu.block(m_compID).height)
  , m_log2CGWidth(g_log2TxSubblockSize[floorLog2(m_width)][floorLog2(m_height)].width)
  , m_log2CGHeight(g_log2TxSubblockSize[floorLog2(m_width)][floorLog2(m_height)].height)
  , m_log2CGSize(m_log2CGWidth + m_log2CGHeight)
  , m_widthInGroups(getNonzeroTuSize(m_width) >> m_log2CGWidth)
  , m_heightInGroups(getNonzeroTuSize(m_height) >> m_log2CGHeight)
  , m_log2BlockWidth((unsigned)floorLog2(m_width))
  , m_log2BlockHeight((unsigned)floorLog2(m_height))
  , m_maxNumCoeff(m_width * m_height)
  , m_signHiding(signHide)
  , m_extendedPrecision(tu.cs->sps->m_spsRangeExtension.m_extendedPrecisionProcessingFlag)
  , m_maxLog2TrDynamicRange(tu.cs->sps->getMaxLog2TrDynamicRange(m_chType))
  , m_scan(g_scanOrder[SCAN_GROUPED_4x4][CoeffScanType::DIAG][gp_sizeIdxInfo->idxFrom(m_width)]
                      [gp_sizeIdxInfo->idxFrom(m_height)])
  , m_scanCG(g_scanOrder[SCAN_UNGROUPED][CoeffScanType::DIAG][gp_sizeIdxInfo->idxFrom(m_widthInGroups)]
                        [gp_sizeIdxInfo->idxFrom(m_heightInGroups)])
  , m_switchCondition(getSwitchCondition(*tu.cu, m_chType))
  , m_CtxSetLastX((m_switchCondition ? Ctx::LastXCtxSetSwitch : Ctx::LastX)[to_underlying(m_chType)])
  , m_CtxSetLastY((m_switchCondition ? Ctx::LastYCtxSetSwitch : Ctx::LastY)[to_underlying(m_chType)])
  , m_maxLastPosX(g_groupIdx[getNonzeroTuSize(m_width) - 1])
  , m_maxLastPosY(g_groupIdx[getNonzeroTuSize(m_height) - 1])
  , m_lastOffsetX(0)
  , m_lastOffsetY(0)
  , m_lastShiftX(0)
  , m_lastShiftY(0)
  , m_minCoeff(-(1 << tu.cs->sps->getMaxLog2TrDynamicRange(m_chType)))
  , m_maxCoeff((1 << tu.cs->sps->getMaxLog2TrDynamicRange(m_chType)) - 1)
  , m_scanPosLast(-1)
  , m_subSetId(-1)
  , m_subSetPos(-1)
  , m_subSetPosX(-1)
  , m_subSetPosY(-1)
  , m_minSubPos(-1)
  , m_maxSubPos(-1)
  , m_sigGroupCtxId(-1)
  , m_tmplCpSum1(-1)
  , m_tmplCpDiag(-1)
  , m_sigGroupCtxIdSwitch(-1)
  , m_sigGroupCtxIdTSSwitch(-1)
  , m_sigFlagCtxSet { (m_nstIdx              ? Ctx::SigFlagNST
                         : m_switchCondition ? Ctx::SigFlagCtxSetSwitch
                                             : Ctx::SigFlag)[to_underlying(m_chType)],
                      (m_nstIdx              ? Ctx::SigFlagNST
                         : m_switchCondition ? Ctx::SigFlagCtxSetSwitch
                                             : Ctx::SigFlag)[to_underlying(m_chType) + 2],
                      (m_nstIdx              ? Ctx::SigFlagNST
                         : m_switchCondition ? Ctx::SigFlagCtxSetSwitch
                                             : Ctx::SigFlag)[to_underlying(m_chType)],
                      (m_nstIdx              ? Ctx::SigFlagNST
                         : m_switchCondition ? Ctx::SigFlagCtxSetSwitch
                                             : Ctx::SigFlag)[to_underlying(m_chType) + 4] }
  , m_gtxFlagCtxSet { (m_nstIdx              ? Ctx::GtxFlagNST
                         : m_switchCondition ? Ctx::GtxFlagCtxSetSwitch
                                             : Ctx::GtxFlag)[to_underlying(m_chType)],
                      (m_nstIdx              ? Ctx::GtxFlagNST
                         : m_switchCondition ? Ctx::GtxFlagCtxSetSwitch
                                             : Ctx::GtxFlag)[to_underlying(m_chType) + 2],
                      (m_nstIdx              ? Ctx::GtxFlagNST
                         : m_switchCondition ? Ctx::GtxFlagCtxSetSwitch
                                             : Ctx::GtxFlag)[to_underlying(m_chType) + 4],
                      (m_nstIdx              ? Ctx::GtxFlagNST
                         : m_switchCondition ? Ctx::GtxFlagCtxSetSwitch
                                             : Ctx::GtxFlag)[to_underlying(m_chType) + 6] }
  , m_sigGroupCtxIdTS(-1)
  , m_tsSigFlagCtxSet(m_switchCondition ? Ctx::TsSigFlagCtxSetSwitch : Ctx::TsSigFlag)
  , m_tsParFlagCtxSet(m_switchCondition ? Ctx::TsParFlagCtxSetSwitch : Ctx::TsParFlag)
  , m_tsGtxFlagCtxSet(m_switchCondition ? Ctx::TsGtxFlagCtxSetSwitch : Ctx::TsGtxFlag)
  , m_tsLrg1FlagCtxSet(m_switchCondition ? Ctx::TsLrg1FlagCtxSetSwitch : Ctx::TsLrg1Flag)
  , m_tsSignFlagCtxSet(m_switchCondition ? Ctx::TsResidualSignCtxSetSwitch : Ctx::TsResidualSign)
  , m_sigCoeffGroupFlag()
  , m_bdpcm(bdpcm)
  , m_signPredArea()
  , m_numSignsPredArea(0)
{
#if JVET_BJUT_TS_FIXED_PREDICTOR
  m_tsQp = tu.cu->qp;
  m_tsHistoryBins = (m_maxNumCoeff * 7) >> 2;
  m_tsRice = 1 + (tu.cu->slice->m_sps->m_spsRangeExtension.m_tsrcRicePresentFlag &&
                 tu.mtsIdx[component] == MtsType::SKIP ? tu.cu->slice->m_tsrcIndex : 0);
  m_tsPoc = tu.cu->slice->m_poc;
  m_tsIntra = tu.cu->predMode == MODE_INTRA;
#endif
  if (TU::getDelayedSignCoding(tu, component))
  {
    m_signPredArea = TU::getSignPredArea(tu, component);
  }

  // LOGTODO
  unsigned log2sizeX = m_log2BlockWidth;
  unsigned log2sizeY = m_log2BlockHeight;
  if (m_chType == ChannelType::CHROMA)
  {
    const_cast<int &>(m_lastShiftX) = Clip3(0, 2, int(m_width >> 3));
    const_cast<int &>(m_lastShiftY) = Clip3(0, 2, int(m_height >> 3));
  }
  else
  {
    const_cast<int &>(m_lastOffsetX) = prefixCtx[log2sizeX];
    const_cast<int &>(m_lastOffsetY) = prefixCtx[log2sizeY];

    const_cast<int &>(m_lastShiftX) = (log2sizeX + 1) >> 2;
    const_cast<int &>(m_lastShiftY) = (log2sizeY + 1) >> 2;
  }

  m_cctxBaseLevel = 4;   // default value for RRC rice derivation in VVCv1, is updated for extended RRC rice derivation
  m_histValue  = 0;   // default value for RRC rice derivation in VVCv1, is updated for history-based extention of RRC
                     // rice derivation
  m_updateHist = 0;   // default value for RRC rice derivation (history update is disabled), is updated for
                      // history-based extention of RRC rice derivation

  if (tu.cs->sps->m_spsRangeExtension.m_rrcRiceExtensionEnableFlag)
  {
    deriveRiceRRC = &CoeffCodingContext::deriveRiceExt;
  }
  else
  {
    deriveRiceRRC = &CoeffCodingContext::deriveRice;
  }
}

#if JVET_BJUT_TS_FIXED_PREDICTOR
void CoeffCodingContext::finishTsPredictorCG(const TCoeff *coeff, bool trace, bool verifyBudget, bool report)
{
  using namespace TsFixedPrediction;
  const int policy = mode();
  if (r6(policy)) { finishTsR6CG(coeff, trace, verifyBudget, report); return; }
  if (r5(policy)) { finishTsR5CG(coeff, trace, verifyBudget, report); return; }
  if (r4(policy)) { finishTsR4CG(coeff, trace, verifyBudget, report); return; }
  static const bool statsEnabled = !std::getenv("TS_R2_STATS") || std::strcmp(std::getenv("TS_R2_STATS"), "0");
  static const bool r3StatsEnabled = !std::getenv("TS_R3_STATS") || std::strcmp(std::getenv("TS_R3_STATS"), "0");
  const bool collectR2 = report && statsEnabled && policy >= 9 && policy <= 12;
  const bool collectR3 = report && r3StatsEnabled && r3(policy);
  const bool collect = collectR2 || collectR3;
  const bool scopeOn = componentEnabled(policy, m_compID == COMP_Y);
  if (policy < 4) { return; }
  std::array<uint64_t, R2Stats::COUNT> counts{};
  std::array<uint64_t, R3Stats::COUNT> counts3{};
  counts[R2Stats::TU] = m_subSetId == 0;
  counts[R2Stats::CG] = 1;
  counts[R2Stats::COEFF] = m_maxSubPos - m_minSubPos + 1;
  const auto reportR3 = [&]() {
    counts3[R3Stats::TU] = counts[R2Stats::TU];
    counts3[R3Stats::CG] = counts[R2Stats::CG];
    counts3[R3Stats::COEFF] = counts[R2Stats::COEFF];
    counts3[R3Stats::NZ] = counts[R2Stats::NZ];
    counts3[R3Stats::ACTIVE] = counts[R2Stats::ACTIVE];
    counts3[R3Stats::BYPASS] = counts[R2Stats::BYPASS];
    counts3[R3Stats::DIFFERENT] = counts[R2Stats::DIFFERENT];
    counts3[R3Stats::MAPPED] = counts[R2Stats::MAPPED];
    counts3[R3Stats::SCOPE_ON] = scopeOn && m_bdpcm == BdpcmMode::NONE;
    r3Stats().add({policy, int(m_compID), m_width, m_height, m_tsQp, m_tsIntra,
                   int(m_bdpcm), lastSubSet() + 1, m_subSetId}, counts3);
  };
  if (m_bdpcm != BdpcmMode::NONE)
  {
    if (collect)
    {
      for (int s = m_minSubPos; s <= m_maxSubPos; ++s) { counts[R2Stats::NZ] += coeff[blockPos(s)] != 0; }
      if (collectR2) { r2Stats().add({policy, m_tsPoc, int(m_compID), m_width, m_height, m_tsQp, m_tsIntra, int(m_bdpcm)}, counts); }
      if (collectR3) { reportR3(); }
    }
    return;
  }
  static const bool traceEnabled = std::getenv("TS_COND_TRACE") != nullptr;
  const bool debug = trace && traceEnabled;
  if (!adaptive(policy) && !debug && !collect) { return; }
  const int64_t oldState = m_tsState;
  const int64_t oldMargin = m_tsRecentMargin;
  const int selected = selectedMode(policy, m_tsQp, oldState, oldMargin, m_compID == COMP_Y);
  int64_t gain = 0, bestPositive = 0;
  int nonzero = 0, changes = 0, mappedChanges = 0;
  int lastPass1 = m_minSubPos - 1;
  bool significant = false;
  uint64_t hash = 1469598103934665603ULL;
  for (int s = m_minSubPos; s <= m_maxSubPos; ++s)
  {
    significant |= coeff[blockPos(s)] != 0;
    counts[R2Stats::NZ] += coeff[blockPos(s)] != 0;
    if (debug) { hash = (hash ^ uint64_t(int64_t(coeff[blockPos(s)]))) * 1099511628211ULL; }
  }
  const auto modified = [&](int s, int predictorMode) {
    int left, above;
    neighTS(left, above, s, coeff);
    int pred = magnitudePredictorModeTS(predictorMode, s, coeff);
    if (pred < 0) { pred = std::max(std::abs(left), std::abs(above)); }
    return remap(std::abs(int(coeff[blockPos(s)])), pred);
  };
  if (significant)
  {
    for (int s = m_minSubPos; s <= m_maxSubPos && m_tsHistoryBins >= 4; ++s)
    {
      const int a = std::abs(int(coeff[blockPos(s)]));
      if (nonzero || s != m_maxSubPos) { --m_tsHistoryBins; }
      if (a)
      {
        ++nonzero;
        const int mod = modified(s, selected);
        m_tsHistoryBins -= 2 + (mod > 1); // sign, gt1, optional parity
      }
      if (scopeOn && !r3Local(policy))
      {
        const bool noPred = policy == 11 || policy == 12 || r3Adaptive(policy);
        const int contribution = proxyCost(modified(s, 1)) - proxyCost(modified(s, noPred ? 0 : 3));
        gain += contribution;
        bestPositive = std::max(bestPositive, int64_t(contribution));
      }
      if (debug || collect)
      {
        int l, u;
        neighTS(l, u, s, coeff);
        changes += selected != 1 && magnitudePredictorModeTS(selected, s, coeff) != std::max(std::abs(l), std::abs(u));
        mappedChanges += modified(s, selected) != modified(s, 1);
        ++counts[R2Stats::ACTIVE];
        if (collect)
        {
          const int pos = blockPos(s), x = pos % m_width, y = pos / m_width;
          const int offsets[] = {-1, -int(m_width), -int(m_width)-1, -2, -2*int(m_width)};
          const bool valid[] = {x > 0, y > 0, x > 0 && y > 0, x >= 2, y >= 2};
          int values[5], n = 0;
          for (int i = 0; i < 5; ++i)
            if (valid[i])
            {
              ++counts[R2Stats::AVAILABLE];
              const int value = std::abs(int(coeff[pos + offsets[i]]));
              if (value) { values[n++] = value; }
            }
          counts[R2Stats::SUPPORT] += n;
          if (collectR3 && scopeOn && r3Local(policy))
          {
            ++counts3[R3Stats::SUPPORT0 + n];
            const int current = std::max(std::abs(l), std::abs(u));
            const auto local = guardedLocalPredict(current, values, n, m_tsRice, m_maxLog2TrDynamicRange);
            const bool proposed = !equivalentPredictors(current, local.winner);
            counts3[R3Stats::LOCAL_PROPOSED] += proposed;
            counts3[R3Stats::LOCAL_ACCEPT] += proposed && local.margin() > 0;
            counts3[R3Stats::LOCAL_REJECT] += proposed && local.margin() <= 0;
            ++counts3[local.gain > 0 ? R3Stats::LOCAL_GPOS : local.gain < 0 ? R3Stats::LOCAL_GNEG : R3Stats::LOCAL_GZERO];
            ++counts3[R3Stats::LOCAL_B0 + std::min(3, local.bestPositive)];
            ++counts3[local.margin() > 0 ? R3Stats::LOCAL_HPOS : local.margin() < 0 ? R3Stats::LOCAL_HNEG : R3Stats::LOCAL_HZERO];
          }
          bool majority = false;
          for (int i = 0; n >= 3 && i < n; ++i)
          {
            int count = 0;
            for (int j = 0; j < n; ++j) { count += values[i] == values[j]; }
            majority |= 2 * count > n;
          }
          counts[R2Stats::MAJORITY] += majority;
          int p = magnitudePredictorModeTS(selected, s, coeff);
          const int current = std::max(std::abs(l), std::abs(u));
          if (p < 0) { p = current; }
          ++counts[p == current || (p <= 1 && current <= 1) ? R2Stats::PCURRENT : p <= 1 ? R2Stats::PIDENTITY : R2Stats::POTHER];
        }
      }
      lastPass1 = s;
    }
    for (int s = m_minSubPos; s <= m_maxSubPos && m_tsHistoryBins >= 4; ++s)
    {
      const int a = modified(s, selected);
      for (int cutoff = 2; cutoff <= 8; cutoff += 2)
        if (a >= cutoff) { --m_tsHistoryBins; }
    }
  }
  if (verifyBudget)
    CHECK(m_tsHistoryBins != remRegBins, "TS predictor history replay differs from actual syntax budget");
  uint64_t currentRate = 0, nopredRate = 0;
  if (policy == 12)
  {
    if (!m_tsVirtualReady)
    {
      m_tsVirtualCtx = Ctx(static_cast<const BinProbModel_Std *>(nullptr));
      m_tsVirtualCtx.init(Clip3(0, MAX_QP, m_tsQp), I_SLICE);
      m_tsVirtualBins = (m_maxNumCoeff * 7) >> 2;
      m_tsVirtualReady = true;
    }
    Ctx alternative(m_tsVirtualCtx); // Deep copy; never aliases the canonical store.
    int alternativeBins = m_tsVirtualBins;
    FractionalSink current{static_cast<CtxStore<BinProbModel_Std> &>(m_tsVirtualCtx)};
    FractionalSink nopred{static_cast<CtxStore<BinProbModel_Std> &>(alternative)};
    replayCG(*this, coeff, 1, m_tsVirtualBins, m_tsRice, current);
    replayCG(*this, coeff, 0, alternativeBins, m_tsRice, nopred);
    currentRate = current.bits;
    nopredRate = nopred.bits;
    gain = int64_t(currentRate) - int64_t(nopredRate);
    // Keep only the Current branch as next CG's common starting state.
  }
  if (adaptive(policy) && scopeOn) { m_tsState = updateState(policy, oldState, gain); }
  if (r3Adaptive(policy) && scopeOn)
  {
    // A zero/empty CG MUST overwrite the certificate, even when small EWMA
    // values do not decay. Never retain a more distant favorable CG instead.
    m_tsRecentMargin = gain - bestPositive;
  }
  if (collect)
  {
    counts[R2Stats::BYPASS] = significant ? m_maxSubPos - lastPass1 : 0;
    counts[R2Stats::DIFFERENT] = changes;
    counts[R2Stats::MAPPED] = mappedChanges;
    counts[R2Stats::NCG] = selected == 0;
    if (adaptive(policy)) { ++counts[gain > 0 ? R2Stats::GP : gain < 0 ? R2Stats::GN : R2Stats::GZ]; }
    counts[R2Stats::VIRTUAL_C] = currentRate;
    counts[R2Stats::VIRTUAL_N] = nopredRate;
    if (collectR2) { r2Stats().add({policy, m_tsPoc, int(m_compID), m_width, m_height, m_tsQp, m_tsIntra, 0}, counts); }
    if (collectR3)
    {
      counts3[R3Stats::EMPTY_CG] = !significant;
      counts3[R3Stats::NO_ACTIVE_CG] = counts[R2Stats::ACTIVE] == 0;
      if (r3Adaptive(policy) && scopeOn)
      {
        counts3[R3Stats::STATE_POS] = oldState > 0;
        counts3[R3Stats::NOPRED_CG] = selected == 0;
        counts3[R3Stats::CERT_BLOCK] = oldState > 0 && oldMargin <= 0;
        ++counts3[gain > 0 ? R3Stats::GAIN_POS : gain < 0 ? R3Stats::GAIN_NEG : R3Stats::GAIN_ZERO];
        ++counts3[m_tsRecentMargin > 0 ? R3Stats::CERT_POS : m_tsRecentMargin < 0 ? R3Stats::CERT_NEG : R3Stats::CERT_ZERO];
        counts3[R3Stats::GAIN_POS_SUM] = std::max<int64_t>(gain, 0);
        counts3[R3Stats::GAIN_NEG_SUM] = std::max<int64_t>(-gain, 0);
        counts3[R3Stats::BEST_POS_SUM] = bestPositive;
      }
      reportR3();
    }
  }
  // Opt-in small-input debugging only: identical encoder/decoder lines are a state audit.
  if (debug)
    std::fprintf(stderr, "TS_COND c=%d w=%u h=%u q=%d cg=%d policy=%d state=%lld selected=%d gain=%lld next=%lld bins=%d last=%d changes=%d mapped=%d hash=%llu virtual_c=%llu virtual_n=%llu\n",
                 int(m_compID), m_width, m_height, m_tsQp, m_subSetId, policy, (long long)oldState, selected, (long long)gain,
                 (long long)m_tsState, m_tsHistoryBins, lastPass1, changes, mappedChanges, (unsigned long long)hash,
                 (unsigned long long)currentRate, (unsigned long long)nopredRate);
  if (debug && r3(policy))
    std::fprintf(stderr, "TS_R3_CERT c=%d w=%u h=%u cg=%d policy=%d scope=%d prev=%lld best=%lld next=%lld\n",
                 int(m_compID), m_width, m_height, m_subSetId, policy, scopeOn,
                 (long long)oldMargin, (long long)bestPositive, (long long)m_tsRecentMargin);
}
// R4 is stateless. Only final-writer observation / opt-in debug uses this replay.
// RDOQ calls return immediately, including discarded and all-zero CG trials.
void CoeffCodingContext::finishTsR4CG(const TCoeff *coeff, bool trace, bool verifyBudget, bool report)
{
  using namespace TsFixedPrediction;
  static const bool statsEnabled = !std::getenv("TS_R4_STATS") || std::strcmp(std::getenv("TS_R4_STATS"), "0");
  static const bool traceEnabled = std::getenv("TS_COND_TRACE") != nullptr;
  const bool collect = report && statsEnabled, debug = trace && traceEnabled;
  if (!collect && !debug) { return; }
  const int policy = mode();
  std::array<uint64_t, R4Stats::COUNT> counts{};
  counts[R4Stats::TU] = m_subSetId == 0;
  counts[R4Stats::CG] = 1;
  counts[R4Stats::COEFF] = m_maxSubPos - m_minSubPos + 1;
  counts[R4Stats::SCOPE] = m_bdpcm == BdpcmMode::NONE;
  uint64_t hash = 1469598103934665603ULL;
  for (int s = m_minSubPos; s <= m_maxSubPos; ++s)
  {
    const int q = coeff[blockPos(s)];
    counts[R4Stats::NZ] += q != 0;
    if (debug) { hash = (hash ^ uint64_t(int64_t(q))) * 1099511628211ULL; }
  }
  const bool significant = counts[R4Stats::NZ] != 0;
  counts[R4Stats::EMPTY] = !significant;
  int last = m_minSubPos - 1, seen = 0;
  int levels[1 << MLS_CG_SIZE] = {};
  if (significant && m_bdpcm == BdpcmMode::NONE)
  {
    for (int s = m_minSubPos; s <= m_maxSubPos && m_tsHistoryBins >= 4; ++s)
    {
      const auto r = r4PredictionTS(policy, s, coeff);
      const int a = std::abs(int(coeff[blockPos(s)]));
      const int mod = levels[s - m_minSubPos] = remap(a, r.predictor);
      if (seen || s != m_maxSubPos) { --m_tsHistoryBins; }
      if (a) { ++seen; m_tsHistoryBins -= 2 + (mod > 1); }
      ++counts[R4Stats::ACTIVE];
      counts[R4Stats::DIFFERENT] += !equivalentPredictors(r.predictor, r.current);
      counts[R4Stats::MAPPED] += mod != remap(a, r.current);
      counts[R4Stats::PARENT_DIFFERENT] += !equivalentPredictors(r.predictor, r.parent);
      counts[R4Stats::PARENT_MAPPED] += mod != remap(a, r.parent);
      if (collect)
      {
        ++counts[equivalentPredictors(r.predictor, r.current) ? R4Stats::PCURRENT : r.predictor <= 1 ? R4Stats::PIDENTITY : R4Stats::POTHER];
        ++counts[equivalentPredictors(r.parent, r.current) ? R4Stats::R3_CURRENT : r.parent <= 1 ? R4Stats::R3_IDENTITY : R4Stats::R3_OTHER];
        const bool proposed = !equivalentPredictors(r.original.winner, r.current);
        counts[R4Stats::R3_PROPOSED] += proposed;
        counts[R4Stats::R3_ACCEPTED] += proposed && r.original.margin() > 0;
        counts[R4Stats::R3_REJECTED] += proposed && r.original.margin() <= 0;
        counts[R4Stats::SUPPRESSED] += r.suppressed;
        counts[R4Stats::ATTEMPTED] += r.attempted;
        counts[R4Stats::ACCEPTED] += r.accepted;
        counts[R4Stats::RESCUE] += r.rescue;
        ++counts[R4Stats::SUPPORT0 + r.support];
        if (r.attempted)
        {
          ++counts[r.gain > 0 ? R4Stats::GPOS : r.gain < 0 ? R4Stats::GNEG : R4Stats::GZERO];
          ++counts[r.margin() > 0 ? R4Stats::HPOS : r.margin() < 0 ? R4Stats::HNEG : R4Stats::HZERO];
          ++counts[R4Stats::B0 + std::min(3, r.bestPositive)];
        }
        if (policy == 20) { ++counts[r.direction < 0 ? R4Stats::DIR_BOUNDARY : R4Stats::DIR_TIE + r.direction]; }
        if (policy >= 21) { ++counts[R4Stats::MODEL_R3 + r.model]; }
        if (policy == 22)
        {
          const int pos = blockPos(s), x = pos % m_width, y = pos / m_width;
          if (x && y)
          {
            const auto read = [&](int xx, int yy) { return xx < 0 || yy < 0 ? 0 : int(coeff[xx + yy * m_width]); };
            const int l = read(x - 1, y), u = read(x, y - 1), d = read(x - 1, y - 1);
            ++counts[!l || !u || !d ? R4Stats::SIGN_ZERO : ((l < 0) == (u < 0) && (l < 0) == (d < 0)) ? R4Stats::SIGN_SAME : R4Stats::SIGN_OPPOSITE];
            const int plane = r4Expert(read, x, y, m_tsRice, m_maxLog2TrDynamicRange, 4);
            const int gradient = predict(2, x, y, std::abs(l), std::abs(u), std::abs(d), 0, 0);
            counts[R4Stats::PLANE_VS_GRADIENT] += !equivalentPredictors(plane, gradient);
            bool novel = plane > 1;
            for (int k = 0; k < 5; ++k) { novel &= plane != std::abs(read(x + r4Dx[k], y + r4Dy[k])); }
            counts[R4Stats::PLANE_NEW_NONIDENTITY] += novel;
          }
        }
        ++counts[r.predictor == a ? R4Stats::HIT : r.predictor < a ? R4Stats::UNDER : R4Stats::OVER];
        counts[R4Stats::ABS_ERROR] += std::abs(r.predictor - a);
        ++counts[mod <= 2 ? R4Stats::MOD0 + mod : R4Stats::MOD_HIGH];
        const int gain = syntaxCost(remap(a, r.current), m_tsRice, m_maxLog2TrDynamicRange) - syntaxCost(mod, m_tsRice, m_maxLog2TrDynamicRange);
        counts[gain >= 0 ? R4Stats::COST_POS : R4Stats::COST_NEG] += std::abs(gain);
      }
      last = s;
    }
    // Pass 2 cannot extend beyond pass 1: only the remaining regular budget decreases.
    for (int s = m_minSubPos; s <= m_maxSubPos && m_tsHistoryBins >= 4; ++s)
    {
      CHECK(s > last, "R4 replay accessed level outside pass 1");
      for (int cutoff = 2; cutoff <= 8; cutoff += 2)
        if (levels[s - m_minSubPos] >= cutoff) { --m_tsHistoryBins; }
    }
    counts[R4Stats::BYPASS] = m_maxSubPos - last;
  }
  if (verifyBudget && m_bdpcm == BdpcmMode::NONE)
    CHECK(m_tsHistoryBins != remRegBins, "R4 diagnostic replay differs from native syntax budget");
  if (collect)
    r4Stats().add({policy, int(m_compID), m_width, m_height, m_tsQp, m_tsIntra,
                  int(m_bdpcm), lastSubSet() + 1, m_subSetId}, counts);
  if (debug && m_bdpcm == BdpcmMode::NONE)
    std::fprintf(stderr, "TS_COND c=%d w=%u h=%u q=%d cg=%d policy=%d state=0 selected=%d gain=0 next=0 bins=%d last=%d changes=%llu mapped=%llu hash=%llu virtual_c=0 virtual_n=0\n",
                 int(m_compID), m_width, m_height, m_tsQp, m_subSetId, policy, policy, m_tsHistoryBins, last,
                 (unsigned long long)counts[R4Stats::DIFFERENT], (unsigned long long)counts[R4Stats::MAPPED], (unsigned long long)hash);
}
// R6 replay observes final coefficients only; none of these counters affect RDOQ.
void CoeffCodingContext::finishTsR6CG(const TCoeff *coeff, bool trace, bool verifyBudget, bool report)
{
  using namespace TsFixedPrediction;
  static const bool statsEnabled = !std::getenv("TS_R6_STATS") || std::strcmp(std::getenv("TS_R6_STATS"), "0");
  static const bool traceEnabled = std::getenv("TS_COND_TRACE") != nullptr;
  const bool collect = report && statsEnabled, debug = trace && traceEnabled;
  if (!collect && !debug) { return; }
  const int policy = mode();
  std::array<uint64_t, R6Stats::COUNT> counts{};
  counts[R6Stats::TU] = m_subSetId == 0;
  counts[R6Stats::CG] = 1;
  counts[R6Stats::COEFF] = m_maxSubPos - m_minSubPos + 1;
  counts[R6Stats::SCOPE] = m_bdpcm == BdpcmMode::NONE;
  uint64_t hash = 1469598103934665603ULL;
  for (int s = m_minSubPos; s <= m_maxSubPos; ++s)
  {
    const int q = coeff[blockPos(s)];
    counts[R6Stats::NZ] += q != 0;
    if (debug) { hash = (hash ^ uint64_t(int64_t(q))) * 1099511628211ULL; }
  }
  const bool significant = counts[R6Stats::NZ] != 0;
  counts[R6Stats::EMPTY] = !significant;
  int last = m_minSubPos - 1, seen = 0;
  int levels[1 << MLS_CG_SIZE] = {};
  if (significant && m_bdpcm == BdpcmMode::NONE)
  {
    for (int s = m_minSubPos; s <= m_maxSubPos && m_tsHistoryBins >= 4; ++s)
    {
      const auto r = r6PredictionTS(policy, s, coeff);
      const int a = std::abs(int(coeff[blockPos(s)]));
      const int mod = levels[s - m_minSubPos] = remap(a, r.predictor);
      if (seen || s != m_maxSubPos) { --m_tsHistoryBins; }
      if (a) { ++seen; m_tsHistoryBins -= 2 + (mod > 1); }
      ++counts[R6Stats::ACTIVE];
      counts[R6Stats::ACTIVE_NZ] += a != 0;
      counts[R6Stats::DIFFERENT] += !equivalentPredictors(r.predictor, r.current);
      counts[R6Stats::MAPPED] += mod != remap(a, r.current);
      const bool changed = !equivalentPredictors(r.predictor, r.parent);
      const bool mapped = mod != remap(a, r.parent);
      counts[R6Stats::PARENT_DIFFERENT] += changed;
      counts[R6Stats::PARENT_MAPPED] += mapped;
      if (collect)
      {
        ++counts[equivalentPredictors(r.predictor, r.current) ? R6Stats::PCURRENT : r.predictor <= 1 ? R6Stats::PIDENTITY : R6Stats::POTHER];
        counts[R6Stats::R3_PROPOSED] += r.proposed;
        counts[R6Stats::R3_ACCEPTED] += r.parentAccepted;
        counts[R6Stats::R3_REJECTED] += r.proposed && !r.parentAccepted;
        counts[R6Stats::ATTEMPTED] += r.attempted;
        if (r.support >= 3)
        {
          ++counts[r.parentAccepted ? R6Stats::DENSE_ACCEPTED : r.proposed ? R6Stats::DENSE_REJECTED : R6Stats::DENSE_CURRENT];
          if (policy <= 26 && !r.parentAccepted && (policy == 25 || r.proposed))
            ++counts[r.proposed ? R6Stats::FALLBACK_REJECTED : R6Stats::FALLBACK_CURRENT];
        }
        ++counts[r.currentHits == 0 ? R6Stats::CURRENT_HITS0 : r.currentHits == 1 ? R6Stats::CURRENT_HITS1 : R6Stats::CURRENT_HITS_MULTI];
        counts[R6Stats::SCORE_TIE] += r.scoreTieCurrent;
        ++counts[R6Stats::SUPPORT0 + r.support];
        counts[R6Stats::MAPPED_N0 + r.support] += mapped;
        if (r.luOnly)
        {
          ++counts[R6Stats::LU_ONLY];
          const int pos = blockPos(s);
          const bool equal = std::abs(int(coeff[pos-1])) == std::abs(int(coeff[pos-m_width]));
          ++counts[equal ? R6Stats::LU_EQUAL : R6Stats::LU_UNEQUAL];
          counts[R6Stats::LU_DIFFERENT] += changed;
          counts[R6Stats::LU_MAPPED] += mapped;
        }
        ++counts[r.predictor == a ? R6Stats::HIT : r.predictor < a ? R6Stats::UNDER : R6Stats::OVER];
        counts[R6Stats::ABS_ERROR] += std::abs(r.predictor - a);
        ++counts[mod == 0 ? R6Stats::MOD0 : mod == 1 ? R6Stats::MOD1 : mod == 2 ? R6Stats::MOD2 : R6Stats::MOD_HIGH];
        const int cost = syntaxCost(mod, m_tsRice, m_maxLog2TrDynamicRange);
        const int gain = syntaxCost(remap(a, r.current), m_tsRice, m_maxLog2TrDynamicRange) - cost;
        const int parentGain = syntaxCost(remap(a, r.parent), m_tsRice, m_maxLog2TrDynamicRange) - cost;
        counts[gain >= 0 ? R6Stats::COST_POS : R6Stats::COST_NEG] += std::abs(gain);
        counts[parentGain >= 0 ? R6Stats::PARENT_COST_POS : R6Stats::PARENT_COST_NEG] += std::abs(parentGain);
      }
      last = s;
    }
    for (int s = m_minSubPos; s <= m_maxSubPos && m_tsHistoryBins >= 4; ++s)
    {
      CHECK(s > last, "R6 replay accessed level outside pass 1");
      for (int cutoff = 2; cutoff <= 8; cutoff += 2)
        if (levels[s - m_minSubPos] >= cutoff) { --m_tsHistoryBins; }
    }
    counts[R6Stats::BYPASS] = m_maxSubPos - last;
  }
  if (verifyBudget && m_bdpcm == BdpcmMode::NONE)
    CHECK(m_tsHistoryBins != remRegBins, "R6 diagnostic replay differs from native syntax budget");
  if (collect)
    r6Stats().add({policy, int(m_compID), m_width, m_height, m_tsQp, m_tsIntra,
                  int(m_bdpcm), lastSubSet() + 1, m_subSetId}, counts);
  if (debug && m_bdpcm == BdpcmMode::NONE)
    std::fprintf(stderr, "TS_COND c=%d w=%u h=%u q=%d cg=%d policy=%d state=0 selected=%d gain=0 next=0 bins=%d last=%d changes=%llu mapped=%llu hash=%llu virtual_c=0 virtual_n=0\n",
                 int(m_compID), m_width, m_height, m_tsQp, m_subSetId, policy, policy, m_tsHistoryBins, last,
                 (unsigned long long)counts[R6Stats::DIFFERENT], (unsigned long long)counts[R6Stats::MAPPED], (unsigned long long)hash);
}

// R5 pure predictions never consume this diagnostic budget. No RDOQ history writes.
void CoeffCodingContext::finishTsR5CG(const TCoeff *coeff, bool trace, bool verifyBudget, bool report)
{
  using namespace TsFixedPrediction;
  static const bool statsEnabled = !std::getenv("TS_R5_STATS") || std::strcmp(std::getenv("TS_R5_STATS"), "0");
  static const bool traceEnabled = std::getenv("TS_COND_TRACE") != nullptr;
  const bool collect = report && statsEnabled, debug = trace && traceEnabled;
  if (!collect && !debug) { return; }
  const int policy = mode();
  std::array<uint64_t, R5Stats::COUNT> counts{};
  counts[R5Stats::TU] = m_subSetId == 0;
  counts[R5Stats::CG] = 1;
  counts[R5Stats::COEFF] = m_maxSubPos - m_minSubPos + 1;
  counts[R5Stats::SCOPE] = m_bdpcm == BdpcmMode::NONE;
  uint64_t hash = 1469598103934665603ULL;
  for (int s = m_minSubPos; s <= m_maxSubPos; ++s)
  {
    const int q = coeff[blockPos(s)];
    counts[R5Stats::NZ] += q != 0;
    if (debug) { hash = (hash ^ uint64_t(int64_t(q))) * 1099511628211ULL; }
  }
  const bool significant = counts[R5Stats::NZ] != 0;
  counts[R5Stats::EMPTY] = !significant;
  int last = m_minSubPos - 1, seen = 0;
  int levels[1 << MLS_CG_SIZE] = {};
  if (significant && m_bdpcm == BdpcmMode::NONE)
  {
    for (int s = m_minSubPos; s <= m_maxSubPos && m_tsHistoryBins >= 4; ++s)
    {
      const auto r = r5PredictionTS(policy, s, coeff);
      const int a = std::abs(int(coeff[blockPos(s)]));
      const int mod = levels[s - m_minSubPos] = remap(a, r.predictor);
      if (seen || s != m_maxSubPos) { --m_tsHistoryBins; }
      if (a) { ++seen; m_tsHistoryBins -= 2 + (mod > 1); }
      ++counts[R5Stats::ACTIVE];
      counts[R5Stats::DIFFERENT] += !equivalentPredictors(r.predictor, r.current);
      counts[R5Stats::MAPPED] += mod != remap(a, r.current);
      const bool changed = !equivalentPredictors(r.predictor, r.parent);
      const bool parentActive = !equivalentPredictors(r.parent, r.current);
      counts[R5Stats::PARENT_DIFFERENT] += changed;
      counts[R5Stats::PARENT_MAPPED] += mod != remap(a, r.parent);
      if (collect)
      {
        ++counts[equivalentPredictors(r.predictor, r.current) ? R5Stats::PCURRENT : r.predictor <= 1 ? R5Stats::PIDENTITY : R5Stats::POTHER];
        ++counts[parentActive ? (r.parent <= 1 ? R5Stats::R3_IDENTITY : R5Stats::R3_OTHER) : R5Stats::R3_CURRENT];
        const bool proposed = !equivalentPredictors(r.original.winner, r.current);
        counts[R5Stats::R3_PROPOSED] += proposed;
        counts[R5Stats::R3_ACCEPTED] += proposed && r.original.margin() > 0;
        counts[R5Stats::R3_REJECTED] += proposed && r.original.margin() <= 0;
        counts[R5Stats::ATTEMPTED] += r.attempted;
        counts[R5Stats::ACCEPTED] += r.accepted;
        counts[R5Stats::REORDER] += policy == 23 && parentActive && changed;
        counts[R5Stats::RESCUE] += policy == 23 && !parentActive && changed;
        counts[R5Stats::VETO] += policy == 24 && r.accepted;
        counts[R5Stats::VETO_IDENTITY] += policy == 24 && r.accepted && r.parent <= 1;
        counts[R5Stats::VETO_OTHER] += policy == 24 && r.accepted && r.parent > 1;
        ++counts[R5Stats::SUPPORT0 + r.support];
        if (r.attempted)
        {
          ++counts[r.gain > 0 ? R5Stats::GPOS : r.gain < 0 ? R5Stats::GNEG : R5Stats::GZERO];
          ++counts[r.margin() > 0 ? R5Stats::HPOS : r.margin() < 0 ? R5Stats::HNEG : R5Stats::HZERO];
          ++counts[R5Stats::B0 + std::min(3, r.bestPositive)];
        }
        ++counts[r.predictor == a ? R5Stats::HIT : r.predictor < a ? R5Stats::UNDER : R5Stats::OVER];
        counts[R5Stats::ABS_ERROR] += std::abs(r.predictor - a);
        ++counts[mod == 0 ? R5Stats::MOD0 : mod == 1 ? R5Stats::MOD1 : mod == 2 ? R5Stats::MOD2 : R5Stats::MOD_HIGH];
        const int cost = syntaxCost(mod, m_tsRice, m_maxLog2TrDynamicRange);
        const int gain = syntaxCost(remap(a, r.current), m_tsRice, m_maxLog2TrDynamicRange) - cost;
        const int parentGain = syntaxCost(remap(a, r.parent), m_tsRice, m_maxLog2TrDynamicRange) - cost;
        counts[gain >= 0 ? R5Stats::COST_POS : R5Stats::COST_NEG] += std::abs(gain);
        counts[parentGain >= 0 ? R5Stats::PARENT_COST_POS : R5Stats::PARENT_COST_NEG] += std::abs(parentGain);
      }
      last = s;
    }
    for (int s = m_minSubPos; s <= m_maxSubPos && m_tsHistoryBins >= 4; ++s)
    {
      CHECK(s > last, "R5 replay accessed level outside pass 1");
      for (int cutoff = 2; cutoff <= 8; cutoff += 2)
        if (levels[s - m_minSubPos] >= cutoff) { --m_tsHistoryBins; }
    }
    counts[R5Stats::BYPASS] = m_maxSubPos - last;
  }
  if (verifyBudget && m_bdpcm == BdpcmMode::NONE)
    CHECK(m_tsHistoryBins != remRegBins, "R5 diagnostic replay differs from native syntax budget");
  if (collect)
    r5Stats().add({policy, int(m_compID), m_width, m_height, m_tsQp, m_tsIntra,
                  int(m_bdpcm), lastSubSet() + 1, m_subSetId}, counts);
  if (debug && m_bdpcm == BdpcmMode::NONE)
    std::fprintf(stderr, "TS_COND c=%d w=%u h=%u q=%d cg=%d policy=%d state=0 selected=%d gain=0 next=0 bins=%d last=%d changes=%llu mapped=%llu hash=%llu virtual_c=0 virtual_n=0\n",
                 int(m_compID), m_width, m_height, m_tsQp, m_subSetId, policy, policy, m_tsHistoryBins, last,
                 (unsigned long long)counts[R5Stats::DIFFERENT], (unsigned long long)counts[R5Stats::MAPPED], (unsigned long long)hash);
}
#endif

void CoeffCodingContext::initSubblock(int SubsetId, bool sigGroupFlag)
{
  m_subSetId   = SubsetId;
  m_subSetPos  = m_scanCG[m_subSetId].idx;
  m_subSetPosY = m_subSetPos / m_widthInGroups;
  m_subSetPosX = m_subSetPos - (m_subSetPosY * m_widthInGroups);
  m_minSubPos  = m_subSetId << m_log2CGSize;
  m_maxSubPos  = m_minSubPos + (1 << m_log2CGSize) - 1;
  if (sigGroupFlag)
  {
    m_sigCoeffGroupFlag.set(m_subSetPos);
  }
  unsigned CGPosY   = m_subSetPosY;
  unsigned CGPosX   = m_subSetPosX;
  unsigned sigRight = unsigned((CGPosX + 1) < m_widthInGroups ? m_sigCoeffGroupFlag[m_subSetPos + 1] : false);
  unsigned sigLower =
    unsigned((CGPosY + 1) < m_heightInGroups ? m_sigCoeffGroupFlag[m_subSetPos + m_widthInGroups] : false);
  m_sigGroupCtxId         = Ctx::SigCoeffGroup[to_underlying(m_chType)](sigRight | sigLower);
  unsigned sigLeft        = unsigned(CGPosX > 0 ? m_sigCoeffGroupFlag[m_subSetPos - 1] : false);
  unsigned sigAbove       = unsigned(CGPosY > 0 ? m_sigCoeffGroupFlag[m_subSetPos - m_widthInGroups] : false);
  m_sigGroupCtxIdTS       = Ctx::TsSigCoeffGroup(sigLeft + sigAbove);
  m_sigGroupCtxIdSwitch   = Ctx::SigCoeffGroupCtxSetSwitch[to_underlying(m_chType)](sigRight | sigLower);
  m_sigGroupCtxIdTSSwitch = Ctx::TsSigCoeffGroupCtxSetSwitch(sigLeft + sigAbove);
}

void DeriveCtx::CtxSplit(const CodingStructure &cs, Partitioner &partitioner, unsigned &ctxSpl, unsigned &ctxQt,
                         unsigned &ctxHv, unsigned &ctxHorBt, unsigned &ctxVerBt, bool *_canSplit /*= nullptr */) const
{
  const CodingUnit *cuLeft  = cuRestrictedLeft[to_underlying(partitioner.chType)];
  const CodingUnit *cuAbove = cuRestrictedAbove[to_underlying(partitioner.chType)];

  bool canSplit[6];

  if (_canSplit == nullptr)
  {
    partitioner.canSplit(cs, canSplit[0], canSplit[1], canSplit[2], canSplit[3], canSplit[4], canSplit[5]);
  }
  else
  {
    memcpy(canSplit, _canSplit, 6 * sizeof(bool));
  }

  ///////////////////////
  // CTX do split (0-8)
  ///////////////////////
  const unsigned widthCurr  = partitioner.currArea().block(partitioner.chType).width;
  const unsigned heightCurr = partitioner.currArea().block(partitioner.chType).height;

  ctxSpl = 0;

  if (cuLeft)
  {
    const unsigned heightLeft = cuLeft->block(partitioner.chType).height;
    ctxSpl += (heightLeft < heightCurr ? 1 : 0);
  }
  if (cuAbove)
  {
    const unsigned widthAbove = cuAbove->block(partitioner.chType).width;
    ctxSpl += (widthAbove < widthCurr ? 1 : 0);
  }

  unsigned numSplit = 0;
  if (canSplit[1])
  {
    numSplit += 2;
  }
  if (canSplit[2])
  {
    numSplit += 1;
  }
  if (canSplit[3])
  {
    numSplit += 1;
  }
  if (canSplit[4])
  {
    numSplit += 1;
  }
  if (canSplit[5])
  {
    numSplit += 1;
  }

  if (numSplit > 0)
  {
    numSplit--;
  }

  ctxSpl += 3 * (numSplit >> 1);

  int maxWidthHeight = std::max(partitioner.currArea().lwidth(), partitioner.currArea().lheight());
  if (partitioner.chType == ChannelType::LUMA && partitioner.currPartIdx() == 1 && partitioner.currBtDepth == 1 &&
      partitioner.currArea().lx() + maxWidthHeight <= cs.picture->lwidth() &&
      partitioner.currArea().ly() + maxWidthHeight <= cs.picture->lheight())
  {
    const PartLevel &partLevel = partitioner.currPartLevel();
    if ((partLevel.split == CU_HORZ_SPLIT && partLevel.firstSubPartSplit == CU_VERT_SPLIT) ||
        (partLevel.split == CU_VERT_SPLIT && partLevel.firstSubPartSplit == CU_HORZ_SPLIT))
    {
      ctxSpl = 9;
    }
  }

  //////////////////////////
  // CTX is qt split (0-5)
  //////////////////////////
  ctxQt = (cuLeft && cuLeft->qtDepth > partitioner.currQtDepth) ? 1 : 0;
  ctxQt += (cuAbove && cuAbove->qtDepth > partitioner.currQtDepth) ? 1 : 0;
  ctxQt += partitioner.currQtDepth < 2 ? 0 : 3;

  ////////////////////////////
  // CTX is ver split (0-4)
  ////////////////////////////
  ctxHv = 0;

  const unsigned numHor = (canSplit[2] ? 1 : 0) + (canSplit[4] ? 1 : 0);
  const unsigned numVer = (canSplit[3] ? 1 : 0) + (canSplit[5] ? 1 : 0);

  if (numVer == numHor)
  {
    const Area &area = partitioner.currArea().block(partitioner.chType);

    const unsigned wAbove = cuAbove ? cuAbove->block(partitioner.chType).width : 1;
    const unsigned hLeft  = cuLeft ? cuLeft->block(partitioner.chType).height : 1;

    const unsigned depAbove = area.width / wAbove;
    const unsigned depLeft  = area.height / hLeft;

    if (depAbove == depLeft || !cuLeft || !cuAbove)
    {
      ctxHv = 0;
    }
    else if (depAbove < depLeft)
    {
      ctxHv = 1;
    }
    else
    {
      ctxHv = 2;
    }
  }
  else if (numVer < numHor)
  {
    ctxHv = 3;
  }
  else
  {
    ctxHv = 4;
  }

  //////////////////////////
  // CTX is h/v bt (0-3)
  //////////////////////////
  ctxHorBt = (partitioner.currMtDepth <= 1 ? 1 : 0);
  ctxVerBt = (partitioner.currMtDepth <= 1 ? 3 : 2);
}

unsigned DeriveCtx::CtxQtCbf(const CompID compID, const bool prevCbf)
{
  if (compID == COMP_Cr)
  {
    return (prevCbf ? 1 : 0);
  }
  return 0;
}

unsigned DeriveCtx::CtxInterDir(const CodingUnit &cu) const
{
  return (MAX_CU_DEPTH - ((floorLog2(cu.lumaSize().width) + floorLog2(cu.lumaSize().height) + 1) >> 1));
}

unsigned DeriveCtx::CtxAffineFlag(const CodingUnit &cu) const
{
  unsigned ctxId = 0;

  const CodingUnit *cuLeft  = cuRestrictedLeft[to_underlying(ChannelType::LUMA)];
  const CodingUnit *cuAbove = cuRestrictedAbove[to_underlying(ChannelType::LUMA)];

  ctxId = (cuLeft && cuLeft->affine) ? 1 : 0;
  ctxId += (cuAbove && cuAbove->affine) ? 1 : 0;

  if (CU::affineCtxInc(cu))
  {
    ctxId += 3;
  }

  return ctxId;
}

unsigned DeriveCtx::CtxBMMrgFlag(const CodingUnit &cu) const
{
  unsigned ctxId = 0;

  const CodingUnit *cuLeft  = cuRestrictedLeft[to_underlying(ChannelType::LUMA)];
  const CodingUnit *cuAbove = cuRestrictedAbove[to_underlying(ChannelType::LUMA)];

  ctxId = (cuLeft && (cuLeft->bmMergeFlag || (!cuLeft->mergeFlag && cuLeft->interDir == 3))) ? 1 : 0;
  ctxId += (cuAbove && (cuAbove->bmMergeFlag || (!cuAbove->mergeFlag && cuAbove->interDir == 3))) ? 1 : 0;

  return ctxId;
}

unsigned DeriveCtx::CtxSkipFlag(const CodingUnit &cu) const
{
  unsigned ctxId = 0;

  const CodingUnit *cuLeft  = cuRestrictedLeft[to_underlying(ChannelType::LUMA)];
  const CodingUnit *cuAbove = cuRestrictedAbove[to_underlying(ChannelType::LUMA)];

  ctxId = (cuLeft && cuLeft->skip) ? 1 : 0;
  ctxId += (cuAbove && cuAbove->skip) ? 1 : 0;

  return ctxId;
}

unsigned DeriveCtx::CtxSgpmFlag(const CodingUnit &cu) const
{
  unsigned ctxId = 0;

  const CodingUnit *cuLeft  = cuRestrictedLeft[to_underlying(ChannelType::LUMA)];
  const CodingUnit *cuAbove = cuRestrictedAbove[to_underlying(ChannelType::LUMA)];

  ctxId = (cuLeft && cuLeft->sgpm) ? 1 : 0;
  ctxId += (cuAbove && cuAbove->sgpm) ? 1 : 0;
  return ctxId;
}

unsigned DeriveCtx::CtxPredModeFlag(const CodingUnit &cu) const
{
  const CodingUnit *cuLeft  = cuRestrictedLeft[to_underlying(ChannelType::LUMA)];
  const CodingUnit *cuAbove = cuRestrictedAbove[to_underlying(ChannelType::LUMA)];

  unsigned ctxId = ((cuAbove && CU::isIntra(*cuAbove)) || (cuLeft && CU::isIntra(*cuLeft))) ? 1 : 0;

  return ctxId;
}

unsigned DeriveCtx::CtxIBCFlag(const CodingUnit &cu) const
{
  unsigned ctxId = 0;

  const CodingUnit *cuLeft  = cuRestrictedLeft[to_underlying(cu.chType)];
  const CodingUnit *cuAbove = cuRestrictedAbove[to_underlying(cu.chType)];

  ctxId += (cuLeft && CU::isIBC(*cuLeft)) ? 1 : 0;
  ctxId += (cuAbove && CU::isIBC(*cuAbove)) ? 1 : 0;

  return ctxId;
}

void MergeCtx::setGeoMmvdMergeInfo(CodingUnit &cu, int mergeIdx, int mmvdIdx) const
{
  bool extMMVD = cu.cs->picHeader->m_gpmMMVDTableFlag;
  CHECK(mergeIdx >= numValidMergeCand, "Merge candidate does not exist");
  CHECK(mmvdIdx >= (extMMVD ? GPM_EXT_MMVD_MAX_REFINE_NUM : GPM_MMVD_MAX_REFINE_NUM), "GPM MMVD index is invalid");
  CHECK(mmvdIdx < 0, "GPM MMVD index is invalid");
  CHECK(!cu.geoFlag || CU::isIBC(cu), "incorrect GPM setting")

  cu.regularMergeFlag = !(cu.ciipFlag || cu.geoFlag);
  cu.mergeFlag        = true;
  cu.mmvdMergeFlag    = false;
  int desiredDir      = interDirNeighbours[mergeIdx];

  if (interDirNeighbours[mergeIdx] == 3)
  {
    if (!cu.cs->slice->m_checkLdc)
    {
      desiredDir = (mergeIdx % 2) + 1;
    }
  }

  cu.interDir  = desiredDir;
  cu.imv       = 0;
  cu.mergeIdx  = mergeIdx;
  cu.mergeType = MergeType::DEFAULT_N;

  constexpr int mvShift           = MV_FRACTIONAL_BITS_DIFF;
  constexpr int refMvdCands[8]    = { 1 << mvShift,  2 << mvShift,  4 << mvShift,  8 << mvShift,
                                      16 << mvShift, 32 << mvShift, 64 << mvShift, 128 << mvShift };
  constexpr int refExtMvdCands[9] = { 1 << mvShift,  2 << mvShift,  4 << mvShift,  8 << mvShift, 12 << mvShift,
                                      16 << mvShift, 24 << mvShift, 32 << mvShift, 64 << mvShift };
  int           fPosStep          = (extMMVD ? (mmvdIdx >> 3) : (mmvdIdx >> 2));
  int           fPosPosition      = (extMMVD ? (mmvdIdx - (fPosStep << 3)) : (mmvdIdx - (fPosStep << 2)));
  int           offset            = (extMMVD ? refExtMvdCands[fPosStep] : refMvdCands[fPosStep]);
  Mv            mvOffset;

  if (fPosPosition == 0)
  {
    mvOffset = Mv(offset, 0);
  }
  else if (fPosPosition == 1)
  {
    mvOffset = Mv(-offset, 0);
  }
  else if (fPosPosition == 2)
  {
    mvOffset = Mv(0, offset);
  }
  else if (fPosPosition == 3)
  {
    mvOffset = Mv(0, -offset);
  }
  else if (fPosPosition == 4)
  {
    mvOffset = Mv(offset, offset);
  }
  else if (fPosPosition == 5)
  {
    mvOffset = Mv(offset, -offset);
  }
  else if (fPosPosition == 6)
  {
    mvOffset = Mv(-offset, offset);
  }
  else if (fPosPosition == 7)
  {
    mvOffset = Mv(-offset, -offset);
  }
  if (desiredDir == 3)
  {
    cu.refIdx[RPL0] = mvFieldNeighbours[mergeIdx][RPL0].refIdx;
    cu.refIdx[RPL1] = mvFieldNeighbours[mergeIdx][RPL1].refIdx;
  }
  else
  {
    int listTarget = desiredDir - 1;
    int listEmpty  = 1 - listTarget;

    cu.refIdx[RefPicList(listTarget)] = mvFieldNeighbours[mergeIdx][listTarget].refIdx;
    cu.refIdx[RefPicList(listEmpty)]  = -1;
  }

  if (cu.refIdx[RPL0] >= 0 && cu.refIdx[RPL1] >= 0)
  {
    Mv tempMv[2];

    const int refListIdx0 = cu.refIdx[RPL0];
    const int refListIdx1 = cu.refIdx[RPL1];

    const int poc0    = cu.cs->slice->getRefPOC(RPL0, refListIdx0);
    const int poc1    = cu.cs->slice->getRefPOC(RPL1, refListIdx1);
    const int currPoc = cu.cs->slice->m_poc;

    tempMv[0] = mvOffset;

    if ((poc0 - currPoc) == (poc1 - currPoc))
    {
      tempMv[1] = tempMv[0];
    }
    else if (abs(poc1 - currPoc) > abs(poc0 - currPoc))
    {
      const int scale = PU::getDistScaleFactor(currPoc, poc0, currPoc, poc1);
      tempMv[1]       = tempMv[0];

      const bool isL0RefLongTerm = cu.cs->slice->getRefPic(RPL0, refListIdx0)->m_longTerm;
      const bool isL1RefLongTerm = cu.cs->slice->getRefPic(RPL1, refListIdx1)->m_longTerm;

      if (isL0RefLongTerm || isL1RefLongTerm)
      {
        if ((poc1 - currPoc) * (poc0 - currPoc) > 0)
        {
          tempMv[0] = tempMv[1];
        }
        else
        {
          tempMv[0].set(-1 * tempMv[1].getHor(), -1 * tempMv[1].getVer());
        }
      }
      else
      {
        tempMv[0] = tempMv[1].getScaledMv(scale);
      }
    }
    else
    {
      const int  scale           = PU::getDistScaleFactor(currPoc, poc1, currPoc, poc0);
      const bool isL0RefLongTerm = cu.cs->slice->getRefPic(RPL0, refListIdx0)->m_longTerm;
      const bool isL1RefLongTerm = cu.cs->slice->getRefPic(RPL1, refListIdx1)->m_longTerm;
      if (isL0RefLongTerm || isL1RefLongTerm)
      {
        if ((poc1 - currPoc) * (poc0 - currPoc) > 0)
        {
          tempMv[1] = tempMv[0];
        }
        else
        {
          tempMv[1].set(-1 * tempMv[0].getHor(), -1 * tempMv[0].getVer());
        }
      }
      else
      {
        tempMv[1] = tempMv[0].getScaledMv(scale);
      }
    }

    cu.mv[RPL0] = mvFieldNeighbours[mergeIdx][RPL0].mv + tempMv[0];
    cu.mv[RPL1] = mvFieldNeighbours[mergeIdx][RPL1].mv + tempMv[1];
  }
  else
  {
    cu.mv[RPL0] = (cu.refIdx[RPL0] >= 0) ? mvFieldNeighbours[mergeIdx][RPL0].mv + mvOffset : Mv();
    cu.mv[RPL1] = (cu.refIdx[RPL1] >= 0) ? mvFieldNeighbours[mergeIdx][RPL1].mv + mvOffset : Mv();
  }

  cu.bdmvrRefine  = false;
  cu.mvd[RPL0]    = Mv();
  cu.mvd[RPL1]    = Mv();
  cu.mvpIdx[RPL0] = NOT_VALID;
  cu.mvpIdx[RPL1] = NOT_VALID;
  cu.mvpNum[RPL0] = NOT_VALID;
  cu.mvpNum[RPL1] = NOT_VALID;
  cu.bcwIdx       = (interDirNeighbours[mergeIdx] == 3) ? bcwIdx[mergeIdx] : BCW_DEFAULT;

  PU::restrictBiPredMergeCandsOne(cu);
  cu.mmvdEncOptMode = 0;
}

void DeriveCtx::setNeighbourCus(const CodingStructure &cs, const UnitArea &ua, const ChannelType ch)
{
  const Position &posLuma     = ua.lumaPos();
  const Position &pos         = isLuma(ch) ? posLuma : ua.chromaPos();
  const uint32_t  curSliceIdx = cs.slice->m_independentSliceIdx;
  const uint32_t  curTileIdx  = cs.pps->getTileIdx(posLuma);

  cuRestrictedLeft[to_underlying(ch)]  = cs.getCURestricted(pos.offset(-1, 0), pos, curSliceIdx, curTileIdx, ch);
  cuRestrictedAbove[to_underlying(ch)] = cs.getCURestricted(pos.offset(0, -1), pos, curSliceIdx, curTileIdx, ch);
}

unsigned DeriveCtx::CtxMipFlag(const CodingUnit &cu) const
{
  unsigned ctxId = 0;

  const CodingUnit *cuLeft  = cuRestrictedLeft[to_underlying(ChannelType::LUMA)];
  const CodingUnit *cuAbove = cuRestrictedAbove[to_underlying(ChannelType::LUMA)];

  ctxId = (cuLeft && cuLeft->mipFlag) ? 1 : 0;
  ctxId += (cuAbove && cuAbove->mipFlag) ? 1 : 0;

  ctxId = (cu.lwidth() > 2 * cu.lheight() || cu.lheight() > 2 * cu.lwidth()) ? 3 : ctxId;

  return ctxId;
}

unsigned DeriveCtx::CtxDimdFlag(const CodingUnit &cu) const
{
  unsigned ctxId = 0;

  const CodingUnit *cuLeft  = cuRestrictedLeft[to_underlying(ChannelType::LUMA)];
  const CodingUnit *cuAbove = cuRestrictedAbove[to_underlying(ChannelType::LUMA)];

  ctxId = (cuLeft && cuLeft->dimdFlag) ? 1 : 0;
  ctxId += (cuAbove && cuAbove->dimdFlag) ? 1 : 0;

  return ctxId;
}

unsigned DeriveCtx::CtxTimdFlag(const CodingUnit &cu) const
{
  unsigned ctxId = 0;

  const CodingUnit *cuLeft  = cuRestrictedLeft[to_underlying(ChannelType::LUMA)];
  const CodingUnit *cuAbove = cuRestrictedAbove[to_underlying(ChannelType::LUMA)];

  ctxId = (cuLeft && cuLeft->timdFlag) ? 1 : 0;
  ctxId += (cuAbove && cuAbove->timdFlag) ? 1 : 0;

  return ctxId;
}

unsigned DeriveCtx::CtxPltCopyFlag(const unsigned prevRunType, const unsigned dist)
{
  uint8_t *ucCtxLut = (prevRunType == PLT_RUN_INDEX) ? g_paletteRunLeftLut : g_paletteRunTopLut;
  if (dist <= RUN_IDX_THRE)
  {
    return ucCtxLut[dist];
  }
  else
  {
    return ucCtxLut[RUN_IDX_THRE];
  }
}
