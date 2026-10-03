# R12 近似平局与空间加权实验实现

2026-10-03补充：[等价复杂度优化](TS_Predictor_R12_Exact_Optimization.md)已实现并通过局部字节回归，
R12-POS-01算法定义及模式编号不变。默认工程宏 `JVET_BJUT_TS_R12_EXACT_OPT=1`，0保留原计算路径。

日期：2026-10-01；规格 `R12-POS-01`。从当前实验分支快进同步到 `94a3540` 后，依据
[同步的 R12 方案](../external_inputs/R12_Experiment_Plan.md)实现全部 12 组。
正式 BD-rate anchor 仍为 **Current**，机制对照为 **R10-3**。这不是新收益报告。
外部方案保留原文，其“未实现”是原稿状态；本地实施与验证以本文件和[验收记录](TS_Predictor_R12_Validation.md)为准。

## 研究依据与边界

已登记 R10-3 CE 为 −0.156054%，R11 八组 CE 均未超过它；R11-2 为 −0.154095%。
R10-3 B 仍只有 18/20 点，不能把阶段估计当完整 BCE，也不能据 B 的平均改善证明每个 CF 平局决策安全。
数据来源：[结果台账](TS_Predictor_Results_Ledger.md)、[R10 明细](results/r10.md)、[R11 明细](results/r11.md)。

本轮分别测试：整数小差距是否值得再看 CF；删一证据是否揭示不稳定选择；近邻是否应在
专家内部或外层验证中拥有较高权重。固定 2:1 是待证伪的空间相关性假设，不是拟合出的最优值。
不增加候选幅值、QP 门槛、分量或序列特定开关，不把 R4 方向加权的负面结果隐去，也不将它
外推成所有位置加权都无效。

## 十二组定义

表中运行名均加 `r12_` 前缀，结果目录再加公开数字，例如 `r12_7_c_distance_raw`。

| R12_MODE | 运行名后缀 | 唯一主要变化 |
|---|---|---|
| 1 | ci_near1 | 原 CI 唯一赢家；允许其它旧专家在 CI 差距 `(0,Q]` 时挑战 |
| 2 | r3_near1 | 同 1，但只允许原 R3 专家 C 挑战 |
| 3 | current_near1 | 仅 native Current 专家 D 挑战，CI 差距必须 `[0,Q]` |
| 4 | loo_unstable_cf | 至少两个有效证据；合法删一情景的 CI 最优专家并集参加完整 V0 的 CF 比较 |
| 5 | direct_first | V0 的 L/U 子集有唯一 CI 赢家则采用，否则完整 R10-3 |
| 6 | r3_near1_loo | 2 与 4 的挑战集合取并集，不是同时满足才开放 |
| 7 | c_distance_raw | 仅 C 改为位置加权 raw；`Gw>0` 才接受，无删一 guard |
| 8 | c_distance_fulltrim | 同一加权 raw 候选；`Gw−max(0,max wj*dj)>0` 才接受 |
| 9 | validation_distance | 原 ABC 不变；外层 CI 和 CF 同时按验证位置加权 |
| 10 | validation_distance_tie | 原 CI 不变；只对精确 CI 平局内的 CF 加权 |
| 11 | c_distance_softtrim | 同一加权 raw 候选；`Gw−max(0,max dj)>0` 才接受 |
| 12 | c_and_validation_distance | 7 的新 C＋9 的外层加权，构成预设四角，不叠加 near1 |

1/2/3/4/6 完整保留原精确 CI 平局；新增挑战者必须严格改善 CF，等 CF 保留原赢家。
10 保留原唯一 CI 赢家。5/7/8/9/11/12 不具有该保证。保证只适用于同一输入状态，
不能理解为后续量化轨迹相同。模式 0 仅用于诊断 R10-3 等价动作，不注册新 BD-rate 组。

## 公共数学与因果定义

`h=(L,U,D,LL,UU)`；n 是非零位置数，不是权重和。p=0/1 都规范化为 identity。
映射不变：a=0 映射 0；p>1 时，a=p 映射 1，0<a<p 映射 a+1，a>p 映射 a。
所有新动作仍使用原 k=0 remapping，不改语法。

专家 A=R8-12（冻结 CF、identity-trim、稀疏 Smax），B=整数 raw R2-2，C=整数 R3-1。
内层候选仍为 Current、identity、已有非零邻居幅值；Current-first，其后 identity、升序幅值。
7/8/11/12 只替换 C，当前位置和每个历史目标的 C 同时替换。n<3 仍 Current。
`W=(2,2,1,1,1)` 固定对应物理槽位，不先压缩 nz 后对前两项加权。
相同输入下完整删除接受集合⊆部分删除⊆raw；闭环收益不保证单调。

外层 V0 仅包括 query 五邻居中真实可得、同 CG、非零且 native scan 更早的位置，最多 5 个。
每个历史目标 j 用自己的 h_j 产生专家，再评分已知 a_j，绝不使用 query 的实际 a_i。
CI=`int64_t(syntaxCost)<<SCALE_BITS`，CF 使用**当前 CG 入口**冻结概率和历史 h_j 的 L/U 非零分类，
cutoff=10。Q=`int64_t(1)<<SCALE_BITS`，本工程为 32768，不是 QP，也不保证等于真实 CABAC 一比特。
`n_eff` 按 ABC 对历史目标的映射幅值差异计数，不按 CI 差异或第四专家 D 计数。

内层权重相对历史目标 j；外层权重相对当前 query i。两者位置含义不同。
先检查边界、inverse scan 可得性再读系数；支持来自当前 trial 的已知 prefix，可包含先前 CG，
但外层验证目标仍只在当前 CG。无跨 TU 学习、递归专家、全 CG 前缀扫描或持久缓存。
不因 ABC 当前动作相同合并专家历史；特别是模式 3 的 D 必须有机会参与。

## 代码位置与闭环接入

- `TypeDef.h`：R12_MODE、0～12 范围、master 与所有旧实验及 R10_CACHE 互斥。
- `TsFixedPrediction.h`：运行名、默认模式、覆盖选择、内部 ID 86～97、启动身份和统计选项校验。
- `TsR12Prediction.h`：独立加权 C、共享映射 cost 小缓存、64 位 CI/CF、near/LOO/空间选择。
- `ContextModelling.cpp` 的 `r12PredictionTS`：因果几何、历史专家、冻结表和公共动作。
- `ContextModelling.h` 的 `magnitudeActionTS` / `magnitudePredictorModeTS`：公共 dispatch。

既有 QuantRDOQ、CABACWriter、CABACReader 和最终 q replay 都通过这条公共动作路径。
`needsTsRateContext` 纳入 R12，自动复用已有 CG 快照与 RDOQ finalized-CG replay，
不另写一套近似 Writer/Reader。RDOQ 可改变 coefficient、CG 清零及 TS 获选；本轮不声称仅改变最终 Writer。
真实 Encoder trial 与最终 Writer 的概率快照不必一致，Writer/Reader 同入口快照和动作必须一致。
BDPCM 与纯 bypass 沿用原不映射路径；普通 transform、允许尺寸、扫描、lambda 和量化搜索规则不改。
不增加 predictor mode syntax，故两端必须使用相同实验；新模式与旧 decoder 不兼容。

## 宏及模式选择

直接在 `source/Lib/CommonLib/TypeDef.h` 修改，不用 CMake 选择算法：

```cpp
#define JVET_BJUT_TS_FIXED_PREDICTOR 1
#define JVET_BJUT_TS_R12_MODE        7  // 1..12；例如 R12-7
#define JVET_BJUT_TS_R10_CACHE       0
// fixed、conditional、R2..R11 默认模式必须全部为0。
```

编解码器均重编。无显式参数时运行宏选中的模式；`TS_FIXED_PREDICTOR` 或 batch 的
`--fixed-predictors` 可覆盖。仓库默认 R12_MODE=0，旧宏也为0，因此默认仍 Current。
R12=0 不代表 R10-3；机制对照显式使用 `r10_integer_then_fractional`。
检查日志 `TS R12 revision=R12-POS-01; mode=...; runtime=...`，不能仅凭源码宏判断实际任务身份。

## 统计与日志

默认关闭；`TS_R12_STATS=1` 只在最终 Writer 提交处聚合，不统计 RDO 搜索试探人口。
支持 R12 或 R10-3 实际轨迹。默认只统计当前模式；R10-3 默认观察诊断模式 0。
`TS_R12_SHADOW_MODES=1,7,9` 可指定最多三个互不重复的模式，仅 stats=1 时合法。
非法编号、重复、多于三个、不支持的实际轨迹、错误布尔值均报错，不静默降级。

`TS_R12_STATS_HEADER` / `TS_R12_STATS` 为 CSV。在线按实际轨迹、观察模式、YUV、W/H、
CU-QP、intra/inter、BDPCM、真实 cutoff 和 n 聚合；包含 TU/CG/系数/非零人口、专家选择、
CI tie/gap、V0 槽位、有效证据、near/LOO/direct 活动、原始 R10-3 动作及 remap 差异，
各专家最终目标 CI/CF10/实际 cutoff CF、选择 loss/regret，以及新 C 的 G/Gw、full/soft penalty、逐槽位贡献等。
旧 B/raw 与新加权 raw 分开记录；在替换 C 的模式中，**原始 R10-3 必须另算**，不能拿修改后的专家池冒充它。

`TS_R12_DETAIL_LIMIT=3` 可额外打印前三个 regular 位置的完整诊断，范围0～1024，默认0。
包含 h、w、Current、raw、guard、历史 scan/槽位/CI/CF。`TS_R12_TRACE=1` 提供逐 CG 两端摘要，
只用于局部验证。观察预算独立，不影响概率、q、预测或搜索；所有目标 loss 只在事后读取。
细节中的 `base` 是**该模式专家池内未加权 CI→CF 的索引**，不是替换 C 前的 R10-3；聚合字段
`*_r10_3` 才是原机制对照。

实际路径 CF 仍冻结上下文，仅使用真实 cutoff；它不是重新模拟每个反事实的 budget/概率传播。
target loss 不含固定 q 下不变的 significance/sign，不能直接当全 TSRC 码率。
人口已条件于最终 TS 获选，存在选择偏差；shadow 不替代重新编码。
同一人口观察多个模式时不得跨模式累加；D 只在模式3存在，其它模式的零 D 字段是未测，不是零成本。
全 CTС 默认不启用统计，计时必须关闭统计和 trace。

```bash
python3 scripts/ts_r12_activity.py runs/你的统计目录 --out runs/你的统计目录/activity
```

生成分层与逐任务模式 CSV、日志状态、audit；不计算或伪造新 BD-rate。

## 构建与运行准备

以下构建选项只管理构建目录和优化，不选择实验算法。命令从仓库根目录执行：

```bash
cmake -S . -B build/ts-r12 -DCMAKE_BUILD_TYPE=Release \
  -DNX2_TOPLEVEL_OUTPUT_DIRS=OFF -DNX2_ENABLE_LINK_TIME_OPT=OFF
cmake --build build/ts-r12 --target EncoderApp DecoderApp TsRateCodecTest TsR12QuantTest -j4
python3 -m unittest discover -s scripts -p test_ts_r12_design.py -v
python3 scripts/test_ts_r12_native.py --jobs 2
```

`TsRateCodecTest` 是合成 TU 的原生语法单元测试，`TsR12QuantTest` 是合成残差数组量化单元测试；
不启动视频序列编码/解码。真实内容短测仍待服务器执行，本地遵守不跑完整编解码的约定。

批量复用 `batch_test.py`，默认六个优先模式 **1/2/4/7/8/9**，C/E、QP22/27/32/37、
LBeu INI 规定的半帧，28点/组，共168点。不新增 Current 任务，不输出重建视频；统一线程任务池，
组间无完成屏障，每组结束即复制模板并写本组工作簿。失败日志、retry、逐任务指纹和 resume 沿用原实现，
R12 revision 及统计请求纳入指纹；旧轮未启用新选项时不改变旧指纹。

```bash
# 只规划，不编码。
bash scripts/run_ts_r12_lb_ce.sh --dry-run --allow-missing-input

# 以下是用户后续在服务器运行的正式任务，本次未执行。
bash scripts/run_ts_r12_lb_ce.sh --input-dir /你的序列目录 --jobs 10

# 续跑同一命令；成功且指纹匹配的任务跳过，不加 --overwrite。
# 只测一组，示例 R12-7。
bash scripts/run_ts_r12_lb_ce.sh --input-dir /你的序列目录 --jobs 10 \
  --fixed-predictors r12_c_distance_raw --out-dir runs/ts_r12_7_pos01_LB_CE_half
```

wrapper 的参数可显式覆盖默认模式。核对实际二进制路径，不能覆盖仍在运行的旧轮二进制。
`experiments/ts_predictor_r12/r12_<数字>_<名称>/LB_CE/` 为服务器结果收件目录，
`LB_B_sentinel/` 与 `LB_B/` 分开，避免九点诊断被误认完整 B；目录名不决定实际启动身份。

## 分阶段决策与证伪

先六组 CE，7/8 必须配对。其余3/5/6/10/11/12先规则/活动检查，全部十二组 CE 上限336点，
不是自动扩跑要求。只有 CE≤−0.15%且相对 R10-3 无明显退化的少数候选才人工决定进入 B 哨兵：
MarketPlace、BasketballDrive、Cactus 的 QP27/32/37，共9点；之后再补11点形成完整20点 B。
不自动启动 B、不自动补缺失 QP22，不把预算门槛写入 predictor 算法。

每序列先分别计算 Y/U/V BD-rate，再 `(6Y+U+V)/8`；CE=7条等权，B=5条等权，
BCE=`(7CE+5B)/12`，不是 `(B+C+E)/3`。组合12的收益用四条曲线共同区间验证，不相加7和9的BD-rate。

若统计显示几乎没有实际 remap 活动，先核验身份/范围，不为同码流重复跑全 CTC；
若闭环 CE 不能保留 R10-3 收益，或 B 的改进只来自极少内容，不机械进入更大测试。
若7/8一致则检查 guard 活动，若7/9有效但12退化则保留交互结论，不调权重追逐正值。
只有真实闭环和可比数据能证明收益；当前实施阶段不作 Promising 收益判定，不改结果台账。
