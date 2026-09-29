# R11：因果证据、验证上下文与专家池实验

日期：2026-09-29；版本 `R11-20260929-v1`。
开始前从 GitHub 快进至 `c9994d1`，采用[最新版 R11 计划](../external_inputs/R11_Experiment_Plan.md)
及其 catalog；外部原稿不修改。较早 R10/R9-B 分析中的“首轮同时测试 B”与后续计划冲突，
本实现采用更新后的 **先完整 CE、再分级 B** 策略。

本文件描述代码，不是新 BD-rate 结果。Current 仍是正式 BD-rate anchor，**R10-3 是机制对照**；
不重新定义 R9/R10，不把 R10-3 的 CE 与 R9-9 的 B 拼成新 BCE。

## 1. 八个独立模式

| R11_MODE | 运行名 | 相对 R10-3 的改动 |
|---|---|---|
| 1 | `r11_no_evidence_r3` | 仅结构性无证据时回专家 C＝R3，不是原生 Current |
| 2 | `r11_query_context_tie` | CI 最小集合内，CF 验证使用当前目标的 L/U 非零分类 |
| 3 | `r11_same_cg_local8` | V0 前缀后，同 CG、曼哈顿半径 3，补至最多 8 个历史目标 |
| 4 | `r11_same_tu_local8` | 完整保留模式 3 集合，再用同 TU 更早 CG 补至 8 个 |
| 5 | `r11_add_native_current` | 独立加入 D＝canonical(max(L,U),0) |
| 6 | `r11_add_identity` | 独立加入 D＝identity；不与模式 5 同时扩池 |
| 7 | `r11_no_evidence_query` | 预设组合 1＋2 |
| 8 | `r11_no_evidence_tu8` | 预设组合 1＋4；在扩展集合上计算有效证据 |

所有模式统一 Y/U/V；不按 sequence、class、分辨率或 QP 门控。
R11=0 表示不选择 R11，**不会自动选择 R10-3**；要运行机制对照须设置 R10_MODE=3 或对应运行名。

## 2. 共同数学定义

保留 `h_i=(L,U,D,LL,UU)`，只读同 TU 原生 scan 更早的量化幅值。
专家 A＝完整 R8-12（冻结 fractional、P0、identity-trim、Smax），B＝整数 raw R2-2，C＝整数 R3-1。
复用 `r10Experts(3,...)`，B/C 共享整数候选评分。各专家均为不递归的纯函数。
所有动作 k=0；p=0/1 规范化成 `(0,0)`。

映射保持 `a=0 → 0`；非零时，`a=p → 1`，`a<p → a+1`，`a>p → a`。
因此无证据按各专家对历史目标的**映射幅值是否相同**判断，不按 p 的数量或整数代价平局判断：

`n_eff = count_j(any_e M(a_j,p_e(h_j)) != M(a_j,p_A(h_j)))`。

每个历史 j 先从自己的 h_j 产生专家动作，之后才评分已知 a_j。
CI=`syntaxCost << SCALE_BITS`；CF=`RateTable.cost(...,cutoff=10)`；合计为 64 位。
先最小化 CI，仅在最小集合内比较 CF，最终按 A→B→C→D。
当前所有活动专家动作相同则返回公共动作；模式 5/6 必须包括第四个专家。
除模式 1/7/8 的无证据回退外，空集仍 A。不按当前动作相同合并历史不同的策略。

模式 2/7 **只换历史验证 loss 的分类**，仍在当前 CG 的同一入口概率快照上评分。
历史专家 A 自身的生成始终使用 h_j 的分类，不替换成 h_i。
唯一 CI 赢家不得被 CF 改变；所有历史分类等于 query 时，模式 2 与基础规则一致。
CF 不是完整 CABAC 反事实，也不是 `D+lambda*R`。

## 3. 有界几何集合与历史可得性

V0 原样保留 L/U/D/LL/UU 顺序中真实存在、同 CG、非零、scan 更早的位置。
V3 再枚举半径 3 的 24 个偏移，先检查 TU 边界、scan 顺序和 CG，再读取幅值。
排除重复及零值，按 `(距离升序, scan降序, y升序, x升序)` 补至 8 个。
V4 在完整 V3 后仅补更早 CG；V0 是 V3 前缀，V3 是 V4 前缀，不挤掉既有样本。
使用原生 inverse scan 和实际 `log2CGSize`，不硬编码 CG=16；不累计全 TU/CG 前缀。

所有历史专家在当前 CG 快照上重算，不保存旧 CG 概率，不跨 TU 保存学习状态。
第一版 **不使用缓存**；R10_CACHE 与 R11 宏互斥，运行时不兼容组合也报错。
这避免沿用只能索引当前 CG 的缓存访问历史 CG；不声称无缓存版本已具备生产速度。

代码路径核对：

- `QuantRDOQ.cpp`：按 CG 顺序完成量化；当前 CG 的后续全零 RD 清除发生在进入下一 CG 前。
  R11 直接读取当前 trial 的已确定 prefix，不引入提前更新的学习状态。
- Writer：最终 q 已确定，多遍调用同一个 `magnitudeActionTS`，不修改 coefficient。
- Reader：第三遍按 scan 顺序补 remainder 并逆映射；j<i 的同 CG 幅值已恢复，
  更早 CG 已完成恢复/符号赋值。策略只用幅值，不依赖当前 CG 尚未赋回的符号。
- RDOQ 概率快照由该 trial 的 finalized-CG replay 得到，未强求与最终 Writer 快照相同。
  Writer/Reader 在各自 CG 入口冻结同一概率状态。

原量化候选生成、lambda、TS 尺寸、scan、语法和 regular/bypass 规则不改。
但 predictor 通过现有 up-level remapping 条件、rate 评估影响 RDOQ 的 q、CG 清零和 TU 模式获选，
因此正式效果必须闭环重编码。BDPCM/pure-bypass 保持不映射路径。

## 4. 宏与启动身份

直接修改 `source/Lib/CommonLib/TypeDef.h`，不增加 CMake 算法选项：

```cpp
#define JVET_BJUT_TS_FIXED_PREDICTOR 1
#define JVET_BJUT_TS_R11_MODE        1 // 1..8 按上表；0关闭本轮
#define JVET_BJUT_TS_R10_MODE        0
#define JVET_BJUT_TS_R10_CACHE       0
// fixed / conditional / R2..R9 默认模式也全部为0。
```

编解码器使用一致设置并重新构建。提交时 R11_MODE=0，所有默认算法关闭，仍为 Current。
无实验参数时使用宏默认；显式 `TS_FIXED_PREDICTOR` 或 batch `--fixed-predictors` 可覆盖宏选择。
master关闭时请求新实验会报错，不能静默运行 anchor。互斥检查包含 R10 及全部旧实验。

启动日志包含 `TS R11 revision=R11-20260929-v1; mode=...; runtime=...; parent=R10-3`。
内部 dispatch ID 78～85 仅用于程序/观察轨迹，不是公开模式号。
与旧 decoder 不兼容：两端必须运行相同新模式，不新增模式语法比特。

## 5. 最终 Writer shadow 统计

`TS_R11_STATS=1` 开启，默认关闭。支持实际轨迹 R3-1、R9-9、R10-3 以及八个 R11。
每个已最终选择的 TS coefficient，在相同历史/q/CG入口快照上观察八个 R11 决策，
不把观察结果写回实际 predictor、q、CABAC 或 RDOQ。R3 的观察只在 Writer/Reader 增加快照，
不改变 R3 的 RDOQ rate model。独立观察预算 `m_tsR11HistoryBins` 不复用旧算法状态。

stderr输出 `TS_R11_STATS_HEADER` 和 `TS_R11_STATS`，在线分层聚合，无默认逐系数文本。
包含实际轨迹、观察模式、分量、W/H、CU-QP、intra/inter、CG数量/位置、n/n1/d、
实际 cutoff、V0/V3/V4/当前集合大小、n_eff、distinct动作、所选与目标最佳专家。
计数区分空集、结构性无证据、CI严格最小/平局、默认A/C、D选择、几何/跨CG增样，
并记录相对同状态 R10-3 的完整动作与实际 remap 差异。

目标已确定后，对每专家输出 CI、CF10、冻结概率下实际 cutoff 的 CF，及对应 target regret；
同时输出所选专家 loss/regret。真实目标与 cutoff 只用于观察，不进入公共选择。
所有 cost 为 Q15 累加。实际路径 CF 不更新假想分支预算/上下文，不能称为完整 CABAC 重编码。
零 CG 与 BDPCM/bypass保留人口计数，不虚构 predictor 收益；D 仅在 5/6 存在。

一个实际人口会有八份模式观察，**不能跨模式加总 TU/CG/系数人口**；也不能把 baseline
轨迹上的 shadow 当成八个新模式的闭环结果。零 TU/未选择TS不在该人口，不能从这些条件统计外推全体块。
当前所有动作一致时仍可统计因果 V；动作仍快捷返回 A 所代表的公共动作。

```bash
python3 scripts/ts_r11_activity.py runs/ts_r11_smoke --out runs/ts_r11_smoke/activity
```

输出 `final_by_stratum.csv`、`final_by_job_mode.csv`、`log_status.csv`、`audit.json`。
统计开销可能明显；正式全 CE 默认关闭，固定短测时开启，计时必须关闭。
本轮合成短测的相关日志已约66 MB（306,167个分层记录），八份shadow和高维分层会放大体积；
不要直接给完整CTC开启此观察。汇总脚本中的合成任务沿用模板sequence标签，不能视为真实序列数据。
`TS_R11_TRACE=1` 为 Writer/Reader 每CG系数、动作、证据集合及预算 hash 核验，正式运行关闭。

## 6. 构建、短测与正式 CE

仓库根目录：CMake 只配置构建，不选择算法。

```bash
cmake -S . -B build/ts-r11 -DCMAKE_BUILD_TYPE=Release \
  -DNX2_TOPLEVEL_OUTPUT_DIRS=OFF -DNX2_ENABLE_LINK_TIME_OPT=OFF
cmake --build build/ts-r11 -j 8 --target EncoderApp DecoderApp TsRateCodecTest
python3 -m unittest discover -s scripts -p 'test_ts_*.py'
```

本轮按用户要求不再启动编解码流水线，以上仅构建/单元测试。以下为以后需要时的可选合成验收命令，
**会运行两帧合成输入的编码→解码→MD5流程**，不是纯单元测试，也不是完整CTC：

```bash
python3 scripts/ts_r11_smoke.py --jobs 8
```

服务器固定短测内容沿用 BQMall、RaceHorsesC、Johnny、KristenAndSara，QP22/37、8帧，
不得看到新结果后只保留有利序列。先观察三条既有量化轨迹，再检查新组码流活动：

```bash
TS_R11_STATS=1 bash scripts/run_ts_r11_lb_ce.sh \
  --input-dir /path/to/videos --jobs 10 \
  --sequences BQMall,RaceHorsesC,Johnny,KristenAndSara --qps 22,37 --frames 8 \
  --fixed-predictors r3_risk_guard,r9_expert_integer,r10_integer_then_fractional \
  --no-xlsm-report --out-dir runs/ts_r11_frozen_trajectories

TS_R11_STATS=1 bash scripts/run_ts_r11_lb_ce.sh \
  --input-dir /path/to/videos --jobs 10 \
  --sequences BQMall,RaceHorsesC,Johnny,KristenAndSara --qps 22,37 --frames 8 \
  --no-xlsm-report --out-dir runs/ts_r11_precheck
```

完整八组 CE，共224点；不新增Current编码：

```bash
bash scripts/run_ts_r11_lb_ce.sh --input-dir /path/to/videos --jobs 10
```

沿用 `batch_test.py`：LB按HHI INI半帧，共享任务池、组间无屏障、失败重试、resume，
每组独立完成后复制模板并写入该组 `JVET-hhi.xlsm`；编码和解码均不保存重建视频。
`--fixed-predictors` 允许只重跑部分模式；`--out-dir` 可指定服务器结果位置。
观察开关参与任务指纹，避免静默复用缺少观察量的旧任务；旧算法无R11观察时原指纹保持不变。
结果收件目录为 `experiments/ts_predictor_r11/r11_<数字>_<名字>/`。

## 7. 分级 B，不自动启动

八组先完整 CE。只有 CE≤−0.14% 的候选默认进入 B 哨兵；例外必须在启动前说明独立证据。
哨兵为 MarketPlace/BQTerrace/Cactus × QP27/32/37，9点；仅诊断共同质量区间，
不是正式四点 B，也不能直接与 CE 拼成 BCE。

R10-3 已满足 CE 门槛，机制对照也只先跑这9点，不把完整B作为R11启动前置。
以下命令仅供人工决定后运行，不由 CE wrapper 自动触发：

```bash
bash scripts/run_ts_r11_lb_ce.sh --class B \
  --sequences MarketPlace,BQTerrace,Cactus --qps 27,32,37 \
  --fixed-predictors r10_integer_then_fractional \
  --input-dir /path/to/videos --jobs 10 --no-xlsm-report \
  --out-dir runs/ts_r11_B_sentinel
```

候选通过门槛后把运行名换成对应 R11。哨兵明显失效则优先早停；接近零不硬判。
再补前三序列QP22及BasketballDrive/RitualDance四QP，共11点，才形成完整B。
最终 `BCE=(7*CE+5*B)/12`；为达到−0.10%，所需 `B<=(-1.20-7*CE)/5`（单位百分点）。
不以哨兵均值估计B，不自动补QP22，不重新编码已有Current。

## 8. 验证与未完成事项

独立纯选择参考、原生scan/专家参考、future污染、q编辑/CG清零、快照复制恢复、
Writer/replay fractional bits/context比较、Reader反映射、宏互斥、观察开关及旧模式回归，
实际结果见[验收记录](TS_Predictor_R11_Validation.md)。
不得用数学参考或合成短测宣称真实内容速度、RD收益、跨类别稳定性。
尚未进行服务器真实内容短测或完整CTC；不在数值台账中加入虚构R11值。
R11-5在现有合成输入中未出现相对R10-3的码流差异；2/6仅AI0有差异。
三组都应先核验真实内容上的模式身份、动作与remap活动，不据此调参或宣称有效。
