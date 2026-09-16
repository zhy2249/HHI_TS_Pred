# TS Adaptive Predictor Experiment Design

版本：2026-09-10。Anchor commit：`16f32500956d74e122e03355e3fc239f974d87cf`，NextSoftware2 1.0。

本阶段目标是证伪或支持“局部 CG 的最佳 magnitude predictor 可以被过去最终量化 CG 预测”。只观察 anchor 最终 q；不修改 RDOQ、正式 writer/reader 的 predictor 或码流。合成 smoke 只证明实现能运行，不能回答有效性问题。正式长时统计由用户本地执行。

## 1. 源码路径与真实数学表达式

下列路径相对工程根目录，函数名是本工程实际名称，可用 `rg -n` 重新定位。

| 流程 | 源码与函数 | 确认事项 |
|---|---|---|
| 变换和量化 | `source/Lib/CommonLib/TrQuant.cpp`: `preCalcTrans → xTransformSkip`、`quantNxN → xQuant → m_quant->quant` | SKIP 不进行普通变换；候选系数进入 quantNxN |
| TS 量化选择 | `source/Lib/CommonLib/QuantRDOQ.cpp`: `QuantRDOQ::quant` | `useTransformSkip ? m_useRDOQTS : m_useRDOQ`；宽/高必须都 >2 才启用 RDOQ；lossless 禁用 RDOQ |
| DQ 分派 | `source/Lib/CommonLib/DepQuant.cpp`: `DepQuant::quant` | TSRC 启用的 SKIP 使 `useRegularResidualCoding=false`，转 `QuantRDOQ::quant`；TSRC-disabled 可能走 DQ，不能混作TSRC样本 |
| TS-RDOQ | 同文件 `xRateDistOptQuantTS`, `xGetCodedLevelTSPred`, `xGetICRateTS` | BDPCM 走 `forwardBDPCM`；其他 TS 走普通 TS-RDOQ；否则可走 `Quant::quant` |
| 邻居与映射 | `source/Lib/CommonLib/ContextModelling.h`: `neighTS`, `deriveModCoeff`, `decDeriveModCoeff` | 名叫 rightPixel/belowPixel 的数据实际上是左和上 |
| CG / scan | `ContextModelling.cpp`: `CoeffCodingContext` 构造函数；`Rom.cpp`: `g_log2TxSubblockSize`, `ScanGenerator`, grouped scan 初始化 | CG 尺寸按宽高的 log2 查表；CG 和 CG 内均正向 diagonal scan |
| 写 TSRC | `source/Lib/EncoderLib/CABACWriter.cpp`: `residual_coding_coef → residual_codingTS → residual_coding_subblockTS` | `mtsIdx==SKIP && !m_tsResidualCodingDisabledFlag` 才走 TSRC |
| 读 TSRC | `source/Lib/DecoderLib/CABACReader.cpp`: 同名函数 | 第三 pass 完成 remainder 后正向逐 coefficient 逆映射，最后恢复符号 |
| CABAC 估计 | `source/Lib/EncoderLib/BinEncoder.h/.cpp`: `BitEstimator_Std`, `encodeBin`, `encodeRemAbsEP` | context bins 用真实概率表并更新，EP 为整数 bit；精度 `SCALE_BITS=15` |

令 `a=|q(x,y)|`，`L=|q(x-1,y)|`，`U=|q(x,y-1)|`，TU 边界外为 0。当前 predictor 精确为：

\[
\boxed{p_{Current}=\max(L,U)}.
\]

非 BDPCM 且允许 remapping 时：

\[
\boxed{f(a,p)=\begin{cases}
0&a=0,\\
1&a>0\land a=p,\\
a+1&0<a<p,\\
a&a>p.
\end{cases}}
\]

BDPCM 或第三 pass 的 `cutoffVal==0` 时为恒等映射 `f(a)=a`。这意味着 under-prediction（p<a）不改变幅值，over-prediction（p>a，a>0）使幅值增加 1，准确命中使 a 映射为 1；三者明显不对称。

逆映射：0→0；若 `v==1 && p>0` 则 a=p；否则 `a=v-[v<=p]`。p=0 也是合法恒等映射。`p=a=0` 可记预测命中，但不能记为 magnitude coding 收益；CSV 同时输出 nonzero 条件计数。

邻居因果性不是根据变量名推断：`neighTS` 在 `posX>0` 时访问 `data[-1]`，`posY>0` 时访问 `data[-width]`。observer 对每种实际 W×H 的 inverse scan 验证这两个位置严格早于当前 scanPos。当前 CG 的 mode 在 CG 开始前固定；CG 内使用已经可恢复的左/上幅值不会造成 mode-selection 泄漏。

## 2. TSRC 语法与 rate

TU 初始常规 context-bin 预算 `remRegBins=(W*H*7)>>2`，跨 CG 传递。

1. CG significance flag：最后 CG 在满足推断条件时省略；全零 CG 可只写该 flag 后返回。
2. 第一 pass（剩余 bins≥4）：sig、nonzero 的 sign、mapped-level greater-than-1、必要时 parity。sign/sig/gt1 context 从已知邻居的符号/非零性质选择。
3. 第二 pass（剩余 bins≥4）：阈值 2、4、6、8 的 greater-than flags。
4. 第三 pass：cutoff 分别为 10、2、0（取决于前两 pass 覆盖范围），按原生 `encodeRemAbsEP` 编码 remainder；cutoff=0 时编码未映射幅值及必要的 bypass sign。不是所有 coefficient 都使用 predictor。

Rice 参数是 `1`，若 SPS 的 `m_tsrcRicePresentFlag` 开启则为 `1+slice.m_tsrcIndex`。本版本 `templateAbsSumTS` 返回 1，不能擅自换成其他 VVC 版本的邻域 Rice 估计。模拟固定 decoder 已知的 slice index，绝不更新真实 `slice.m_riceBit`。未来改变整片 predictor 后 Rice index 的选择反馈不在本轮范围。

`xGetICRateTS` 是 RDOQ 中局部候选 rate model，并非逐 coefficient 调用实际三 pass writer 的完整等价物。本实现直接复用 writer 的三 pass 和 `BitEstimator_Std`；因此不会把 RDOQ 的近似误差引入主要 Oracle。

## 3. 尺寸：理论、配置、观察必须区分

`UnitTools.cpp::TU::isTSAllowed` 的准确判定为：SPS TS enabled；component 宽、高分别不大于 `1<<m_log2MaxTransformSkipBlockSize`；`!cu.sbtInfo`。没有 square 条件，也没有单独的 intra-only 条件或 8×8 上限。

| 范围 | 约束 |
|---|---|
| 正常 profile 的 TS 最大宽/高 | EncAppCfg 校验 log2Max≤5，故各≤32；最小允许的 **max-size 参数** 为2，不等于每个 chroma TU 的最小边长 |
| 通用分块下限 | `CommonDef.h`: `MIN_TB_LOG2_SIZEY=2`，luma 最小边为4；`UnitPartitioner.cpp` 对产生的 luma 宽/高检查≥4 |
| Chroma | 从 luma 按 subsampling 缩放：420 可有边长2，422 水平可为2，444 与 luma 同尺度；不能将 luma 的4样本下限套到所有 chroma 上 |
| Dual tree chroma | `MIN_DUALTREE_CHROMA_WIDTH=4`, `MIN_DUALTREE_CHROMA_SIZE=16`；`canSplit` 对 QT/BT/TT 再限制。面积限制与方向不同，不能简单视为所有 chroma 都≥4×4 |
| TS-RDOQ 下限 | `QuantRDOQ::quant` 宽/高都>2；小 chroma TS 仍可走非 RDOQ 量化并使用 TSRC，必须统计 |
| Intra/inter | `TU::getTransCandIntra/Inter` 均可加入 SKIP；chroma 还受 `ChromaTS` 搜索开关限制，inter `noResidual`、SBT 等限制候选 |
| BDPCM | `CU::bdpcmAllowed` 要求 SPS enabled、intra，按对应分量的 CU 宽高检查 TS 上限；BDPCM 强制 SKIP，且 magnitude remapping 关闭 |
| 配置可达性 | 还受 minQT/minBT/minTT、MTT depth、tree type、chroma format、picture boundary、fast transform search、CU tools、CBF、实际 RDO 决策影响 |

注意：`Profile::NONE` 会绕开 EncAppCfg 的 profile 上限检查；不能据此宣称任意大 TS TU 都符合 codec profile。通用变换表本版扩展到256，TS predicate 本身只有 SPS 上限；非常规无 profile 组合还需满足 scan/group 表与其它工具限制。本轮不通过放宽 profile 来扩大实验收益。统计代码自身没有32、8或固定尺寸集合过滤，会按实际 `CoeffCodingContext` 处理所有到达的合法 TSRC TU。

当前四个 `cfg/encoder_*_nx2.cfg` 都设置 TS=1、最大 log2=5、ChromaTS=1、TransformSkipFast=1。理论候选集合用源码规则定义：生成合法分块/component area，再通过上述 TS gate；不是把所有 `{4,8,16,32}²` 当作配置下保证出现的集合。

`ts_pred_size_census.csv` 给出最终实际启用 TS 且编码 residual 的 TU，包括 TSRC-disabled TU；`ts_pred_summary.csv` 的 rate 分析只包括启用 TSRC 的 TU。CBF=0 时没有 TS residual/predictor 语法，不能把 encoder 搜索时的 SKIP 标签当作 decoder 已知 TS TU。被整体清零但所属 TU 仍有残差的 CG 则全部保留。

## 4. 候选集合：实验前固定

| Mode | p | 意义 |
|---|---|---|
| M0 NoPred | 0 | f(a,0)=a；保留 sig、sign、greater-than、parity、remainder、CG flag、预算等全部原生语法，绝不是把全部绝对幅值直接交给 Rice |
| M1 Current | max(L,U) | anchor；调用未改变的 `deriveModCoeff` |
| M2 Left | L | 水平方向相关性 |
| M3 Above | U | 垂直方向相关性 |
| M4 Min | min(L,U) | 避免较大邻居的 over-prediction |
| M5 Mean | floor((L+U)/2) | 降低单侧异常值影响；实现使用 min+abs-difference/2 避免求和溢出 |

所有 mode 在 BDPCM 和 bypass-only 位置仍遵循原有禁用条件。NoPred 的 p=0 命中指标仅为统一表示；重点解释 coding-rate，不把其低命中率直接判为差。

## 5. Counterfactual 定义及范围

选择 Experiment B（完整 CG），没有把 simple bin count 作为主要 rate。

每个已最终写出的 TSRC TU，复制真实 CABAC TU-entry context，建立 shadow anchor。对每个 g，把 anchor 到该 CG 入口的所有 context 与 `remRegBins` 复制给每个 mode，调用同一个 `residual_coding_subblockTS`，候选内部更新自己的概率状态和预算。

\[
R_g^{(m)}=R(CG_g,q;C_g^{anchor},B_g^{anchor},m).
\]

包括 CG flag、sig、sign、gt、parity、Rice remainder 的 fractional-bit cost。单位为1/32768 bit。输出整数避免浮点选择差异。无真实 arithmetic coder byte flush/termination 开销、CBF/TS flag/CU header；该值是 TS residual syntax fractional bits，不是整个码流 bits。

**额外的 TU-continuous simulation**：六个 fixed 和五个 adaptive 分支各保留自己的 CABAC context 与 bin budget，整个 TU 内持续传播，输出 `*_path_rate`。每个新 TU 从相同真实 anchor TU-entry state 开始；没有跨 TU 的反事实 context 传播。Oracle 与 selector 的主要 `rate` 都使用相同的条件 CG 定义，保证比较口径一致；path 用作传播敏感性检查。

这比仅固定 coefficient context 的 Experiment A 更完整，但条件 CG Oracle 的和仍不是全 TU 所有 mode 序列的全局最优。不能声称它严格上界所有连续编码路径的收益；不将 path gain 除以 conditional Oracle 后称为[0,1]内捕获率。

## 6. Oracle、fixed、ties

`oracle=argmin_m R_g^(m)`；全局固定候选为所有 CG 同一 mode 的 rate 之和；Oracle 为每 CG min 的和。严格相等时优先 Current，若 Current 不在并列集合则取最小 index，输出 `oracle_tie_mask` 全集合。

\[
\Delta R_o=R_o-R_1,\quad Gain_o=(R_1-R_o)/R_1.
\]

同时输出六个 fixed 的 conditional/path rate。若最好的 fixed 已接近 Oracle，转向 fixed predictor 研究；不能把 fixed 改善包装成 adaptive 必要性。

## 7. 严格 TU-local causal selectors

CG0 全部使用 Current，所有状态在 TU 内初始化为0。选择动作在当前 CG 任何 rate/metrics 计算前执行，之后才用已完整 CG 更新历史。统计代码不访问 pixel、residual、未量化 coefficient、distortion、motion 或搜索过程。

| Selector | 选择与更新 |
|---|---|
| previous_winner | 上一个 CG 的最小 R；CG0 fallback |
| cumulative | 最大历史 `Σ(R_current-R_m)` |
| recency | 最大 S；`S←S-floor(S/8)+G`，K=3，显式定义负值右移语义 |
| confidence | recency 的保守预注册探针：历史 CG≥2、历史 nonzero≥8、最大/次大 score 差≥1 bit，否则 Current |
| simple | 与 recency 同形式，但 G 使用映射幅值的减少量而非 CABAC bits |

Confidence 阈值不是已验证最优值。CSV 输出历史样本、非零数量、score margin；Python 输出固定小网格的 sequence/QP 分布，不自动挑最好值。若后续要校准，必须以 sequence 为单位划分训练/验证，冻结阈值后在没见过的序列上验证，不能随机切 coefficient。

simple 的 coefficient score 来自映射非对称性：

\[
h_m=\begin{cases}a-1&a=p_m>0,\\-1&0<a<p_m,\\0&\text{otherwise}.\end{cases}
\]

历史增益 `G_simple=Σ(h_m-h_current)=Σ(f(a,p_current)-f(a,p_m))`，仅 anchor 允许映射的位置计入。它是整数幅值成本近似，会错误估计某些 parity/Rice 阈值跨越，因此必须报告与 recency CABAC selector 的 agreement、rate gap 和捕获率。

CABAC score 需要额外 shadow context 计算，虽可由 decoder 已知状态和历史 q 复现，复杂度不等于廉价。正式无 mode-signaling 算法需规定 TU-entry seed、整数算术、ties、预算/score shadow 更新；本轮并未实现 decoder 新 selector。

## 8. Persistence 与可预测性

仅 TU 内，报告 lag=1,2,3,4 的 `P(M_g=M_(g-k))` 和完整6×6转移矩阵；不连接 TU 边界。分别给所有确定 tie-break 后模式、前后均为唯一最优的子集。

随机独立 baseline 按实际 lag pair 的左右边缘频率 `Σ P_prev(m)P_curr(m)` 计算，不默认1/6。大量平局时 persistence 高并不证明可预测；同时看 tie fraction、unique persistence、选择的真实 rate。序列/尺寸分组用于控制 mode 频率混合。bootstrap 不把 coefficient 当作独立样本。

## 9. RDOQ feedback 与全零 CG

`xRateDistOptQuantTS` 在 coefficient RDO 后构造 `costZeroSB`；当 `costZeroSB<baseCost` 时 `resetSigGroup()`，恢复预算，将整个 CG 的 `dstCoeff` 清零。不能在 `xGetCodedLevelTSPred` 产生暂时 level 时更新历史。

observer 在 `CABACWriter::residual_codingTS` 的真实写码调用（`isEncoding()==true`）入口运行。这已晚于 coefficient RDO、CG 清零、TU/CU mode selection；所有历史都是最终写入 bitstream 的 q。RDO estimator 的候选搜索调用不会输出统计。

当前 q 受 anchor predictor 影响。本轮比较的是同 q 下 predictor-side coding potential；真正集成后 q→q'、TU/CG selection、Rice index、其它 TU context 都可能变化。任何 BD-rate 判断必须下一阶段联合改 TS-RDOQ/writer/reader，并重新跑多 QP。固定 q 的 Oracle 小不能严格证明重优化后的 predictor 永无价值；但足以降低本问题的研究优先级。

## 10. TU-size 与捕获率

CG 大小从 `g_log2TxSubblockSize[log2 W][log2 H]` 取得：例如≥4×4的常规形状 CG 是4×4；小 chroma 形状可为2×2或2×8，不能统一用 WH/16。

`N_CG=WH/(1<<log2CGSize)`，observer 使用同一源码计算值。

* N=1：没有历史，所有 adaptive=Current；fixed 和 Oracle 仍可能有收益。
* N=2：仅 CG1 能用历史；confidence 探针因最少历史数2将始终 fallback，应与 previous/cumulative 分开解释。
* N>2：历史更多，但不预设 gain 更高。

输出 W、H、W×H、CG/TU、component、intra/inter/other（IBC 不伪装成 inter）、BDPCM、sequence、nominal QP、configuration 与交叉分组。单独报告每组 TS TU count、CG count、coefficient/nonzero count、average CG/TU、Oracle/adaptive gain、persistence。

\[
\eta=\frac{R_1-R_{adaptive}}{R_1-R_o}\quad (R_1>R_o).
\]

分母0输出空值；负η保留，代表适应选择使 rate 更差，不能裁剪到0。比值使用总rate之比而不是逐CG η的平均。

## 11. 输出与数据量

编译宏 `JVET_BJUT_TS_PRED_ANALYSIS` 默认 OFF。ON 后仅设置环境变量 `TS_PRED_STATS=/absolute/path.csv` 才观察。`TS_PRED_SEQUENCE/CONFIGURATION/QP` 由 batch 自动设置。`QP` 是实验 nominal QP，`cu_qp` 是实际 CU QP（避免 LB/RA 层级 QP 混淆）。

每 CG 一行，包含坐标、真实宽高、CG index/count、系数数/非零数、mode、conditional/path rates、history/confidence、各 predictor hit/under/over/MAE、nonzero 条件计数、active count、实际 mapped level 的0/1/2/3–4/5–9/≥10分桶，以及按 hit/under/over 归属的 coefficient-rate gain。

`modified_level_*` 是实际三 pass 后采用的值，已考虑各分支不同的预算耗尽位置；不是无条件套公式的假想分布。`*_gain` 按该候选的预测误差类别汇总各 coefficient 在三 pass 的 fractional costs；context 传播收益可归属到后面的 coefficient，不能解释为单 coefficient 的因果独立贡献。CG flag 未分摊到 coefficient，但进入 CG rate。

默认无 coefficient 文本；debug 需 `TS_PRED_DEBUG=...`，最多 `TS_PRED_DEBUG_CGS`（默认2）个CG，列出 signed q、L/U、p、mapped、active 和 fractional cost。

CG 行约0.5–1.5KB，百万CG约0.5–1.5GB；没有宣称 CG 日志绝不大。一个最坏4K 420全TS帧、CG=16时约78万CG，几十帧仍可能很大。正式先8–16采样帧，按实际 CSV bytes/CG 和 TS count 外推磁盘；处理后可 gzip 原始 CSV（分析前解压）。TU census 额外每个 coded TS TU一行。编码端只缓存当前 TU 的候选数据并在线生成 CG 聚合，不保存每 coefficient 全序列文本。Python 流式读取，统计 moments 在线累计，分位数采用每组2048个 reservoir sample，CI保留每帧 cluster sums。

分析输出：`ts_pred_summary.csv`、`ts_pred_transitions.csv`、`ts_pred_size_census.csv`、`ts_pred_confidence_exploratory.csv`、`ts_pred_sequence_stability.csv`、`ts_pred_jobs.csv`、`analysis.json`、`TS_Adaptive_Predictor_Results.md`。jobs表保留零TSRC任务，并用任务实际码流大小提供Oracle绝对节省量相对总码流的规模参考（仍非BD-rate）；没有TSRC的任务不能计算TSRC条件gain，不应从覆盖清单中消失。未带 batch 成功标记的输入默认拒收；smoke 显式 `--allow-unmarked`。

## 12. 预注册实验配置

QP 22,27,32,37。初轮 AI、LB，补 RA 验证是否可推广。不要根据初步正收益删序列或配置。

| 序列 | 用途 |
|---|---|
| BasketballPass（416×240） | 低分辨率、运动 |
| BQMall（832×480） | 中分辨率、运动和结构 |
| BasketballDrillText（832×480） | 文字/图像混合，可能较多 TS |
| FourPeople（1280×720） | 低运动会议场景 |
| BasketballDrive（1920×1080） | 高分辨率运动 |

这是根据内容类别提前选的集合，不是基于收益挑选；路径用现有 batch 的 per-sequence cfg 和 input discovery。更高分辨率/原生 screen-content 在输入可用后预注册补充，不把下载未完成文件作为数据。

重要：本项目 AI cfg 有 `TemporalSubsampleRatio=8`，`--frames` 是输入范围，并不保证实际编码相同数量的 POC。主统计命令显式设 `TemporalSubsampleRatio=1`，采连续短帧，记录所有附加参数；未来也可保留CTC采样，但须写清实际 encoded POC 数。RA短帧有启动偏差，不能把仅首个I帧当作RA结果；建议先32输入帧检查出现 inter/TId。

小于4的 chroma、罕见长方形、BDPCM 必须由观察表证明覆盖。未出现是未观察，不是软件不支持。lossless/BDPCM/444 smoke 是代码路径验证，不能混入主要 lossy QP study。

## 13. 批量执行与复现

复用 `scripts/batch_test.py` 原有序列、manifest、配置、QP、jobs、failure log、decode hash 和输出规范。新参数 `--ts-pred-stats-dir` 为每任务独立统计文件；子进程环境独立，不跨任务共用 CSV。统计任务 resume 必须有成功 marker、统计文件及与 encoder/input/cfg/args 相同的 fingerprint，不因一个残留 bitstream 就判成功。修改配置会重新执行该任务。

构建和可复制命令见 `scripts/README_TS_PRED.md`。`NX2_TOPLEVEL_OUTPUT_DIRS=OFF` 用于隔离二进制；修复了原项目 Linux post-build copy 在这种模式仍尝试 `/EncoderApp` 的问题，不改变编码逻辑。

## 14. 正确性与验证边界

`scripts/ts_pred_smoke.py` 从固定随机种子的64×64两帧合成序列运行三个版本：git snapshot 原版、宏OFF、宏ON统计。SHA256 必须完全相同；用正常 DecoderApp 检查 decoded-picture hash。

1. Test1：原版 vs OFF bit-exact。
2. Test2：原版 vs ON bit-exact。
3. Test3：每个 TU 的 conditional Current CG sum、连续 Current path、直接原生完整 `writer.residual_codingTS` 的 `BitEstimator_Std` cost 要整数完全相同；不是仅高相关。检查在每个观察TU内强制执行。
4. Test4：限制2个CG debug，逐项核对 q/neighbours/p/f(a,p)/eligibility/cost；Python 检查 mode、count 和实际 histogram 守恒。

扩展用例包含 AI/LB、420/444、BDPCM、lossless、TSRC-disabled、TS disabled。444 原版 CCSAO SIMD 不支持该采样格式，smoke 三种版本统一关闭 CCSAO；不修复其它编码工具。已运行结果另存 `runs/ts_smoke/validation.json`，最终验证摘要另见 `scripts/TS_PRED_VALIDATION.md`。通过小样本 bit-exact 不是所有合法输入的形式化证明；隔离状态、保持原生M1路径是结构保证。

## 15. 显著性、effect size 与泛化

对各 selector 的 `R_adaptive-R_current` 输出CG mean/median/std/p05/p95/p99、每TU绝对bits、相对gain与η。按序列/QP/宽高输出变化，不单看overall。

bootstrap以整帧为cluster，同一帧内所有TU/CG共同重采样，500次、固定seed；不到2个cluster不报CI。帧间可能仍相关，短帧CI只是条件稳定性，不等价于跨内容泛化。正式决策优先每序列效应方向及等权序列结果，不能靠数百万coefficient制造微小差异的显著性。若接近决策边界，扩大预注册序列集/帧段，以整序列或连续多帧 block 重采样；不要只增加 bootstrap 次数。

## 16. 预先证伪标准与三级决策

以下是工程筛选门槛，不是宣称标准组织规定。必须与实际 TS 占比和绝对 bits 联合解读。主selector预注册为 recency(K=3)；其它为对照，不能结果出来后挑其中最好的替代主selector。

* Failure1：整体 conditional Oracle gain<1% TS residual bits，或绝对节省折算到总码流极小 → 优先 Negative。
* Failure2：收益集中于一个序列，少于约3/5预注册序列具有同方向、有意义收益 → Weak/Negative。
* Failure3：unique-mode persistence 未明显高于其经验边缘 baseline，且历史selector无收益 → 否定历史预测证据。
* Failure4：recency η≤0.2 或相对gain≤0，尤其跨序列不稳定 → adaptive Weak/Negative，即使 Oracle 强也不能升级。
* Failure5：某个 fixed 捕获≥90% conditional Oracle improvement、同时 path 稳定 → adaptive 没必要，转 fixed 研究。
* Failure6：gain只在占TS coefficient少于5%的极少尺寸出现 → 降级，不隐藏常见尺寸的损失。
* Failure7：高低QP有实质符号翻转 → Weak，需解释并独立验证，不临时增加QP-specific thresholds。
* Failure8：simple捕获率<0.2且与CABAC selector有明显rate gap → 不能声称低复杂度 decoder 同步方案已成立。
* Failure9：conditional与path结果明显冲突、或gain仅在anchor q的特定稀有分布出现 → feedback/context bias风险，暂不升级。

Promising 要求：Oracle≥1%，预注册 recency稳定捕获≥50%潜力，adaptive gain至少0.5% TS residual bits，多数序列与QP方向一致，常见尺寸覆盖，连续path无实质反转，且fixed不能解释大部分Oracle。simple接近CABAC可加强证据，但不能单凭它的一个总均值升级。

Weak：Oracle有空间但causal、低复杂度或泛化证据不足。Negative：Oracle本身小，或causal系统性无效/变差，或fixed已解释几乎所有收益（此时只否定adaptive必要性）。正式结果不存在时不能强行给这三个标签之一：本轮状态为 **待正式数据**。

## 17. 结果阶段的Q1–Q10

| 问题 | 需要的证据 |
|---|---|
| Q1 Current是否明显非最优 | Oracle及fixed的相对/绝对改善、序列CI |
| Q2 是否可直接换fixed | 最佳fixed与Oracle gap、path稳定性 |
| Q3 不同CG最佳是否不同 | unique mode频率、tie比例、局部gain分布 |
| Q4 是否连续 | lag与transition、经验baseline、unique子集 |
| Q5 历史能否预测 | 预注册causal selector，不能用当前CG oracle决定mode |
| Q6 捕获多少 | η和rate gain，分母0及负值如实报告 |
| Q7 尺寸是否一致 | 每个实际W×H、component、CG/TU表 |
| Q8 小尺寸是否不适合 | NCG=1无历史的结构限制；NCG=2与更大实测比较 |
| Q9 NoPred局部优势 | M0 unique/tie胜出比例、rate改善、over-prediction与mapping分布 |
| Q10 是否联合改codec | 依预注册门槛给Promising/Weak/Negative，并强调不是BD-rate |

本阶段仅Q8中“单CG的TU-local history不可用”可以由结构直接回答；其余效能问题等待用户正式运行结果。若Oracle strong但adaptive weak，结论是局部最优变化存在而历史不可预测；若某个fixed≈Oracle，优先fixed；只在两项都稳定时进入TS-RDOQ/CABACWriter/CABACReader联合修改。
