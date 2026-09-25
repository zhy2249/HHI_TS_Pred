# R8：机制交叉、完整候选与评分分布实验

设计版本：`R8-DESIGN-20260925-v2`。依据用户提供的 [探索计划](TS_Predictor_R8_Exploration_Plan.md)，结合本地源码与重新审计的 R7 表格。
按用户后续要求，首轮收敛为八组；详见 [首轮八组规格](TS_Predictor_R8_First8_Design.md)。24组原公式和公开MODE数字不变。

**状态：完成实验规格、数学参考验证和收件目录；尚未修改编码算法、TypeDef.h 或批量运行器，没有 R8 编码结果。本文中的 R8_MODE 和 runtime 均为预留名称，不是目前可运行的选项。**

## 1. 本轮决定

保留探索计划的全部 **24 组**，不新增经验阈值、不扫描更多预测公式；分批实施，不一次启动 672 个正式 CE 编码点。

- 第一批八组：A01、A04、A08、B01、B03、B04、B05、B07；先验证接口、实际活动和编解码同步，再运行完整 CE。替代原首批10组安排，不叠加执行。
- 第 2 批12组保留其余 A/B 方向，包括 mean/min、trim 和其它机制配对。暂缓不等于否定，不以第一批必须超过 R3 作为实施前提。
- 第 3 批 C01/C02 检验语法路径模型；第 4 批 C03/C04 检验量化搜索交互。后者需要独立的 encoder 搜索接口，不混入公共 predictor 的第一版改造。
- 正式 anchor 始终 Current；R3-1 是强增量对照，不是必须保留其已接受分支的规则。
- 新方法都允许影响 TS-RDOQ、工具竞争与最终 q，正式性能用闭环编码判断；固定旧 q 的 shadow 只解释机制。

## 2. 已有数据支持什么

本次只核验 LB CE：R7 两组各 28/28 个实测点，CSV B–J 与各自工作簿一致；相关 CE Reference 与 Current 一致，无补点。远端源码、模式、实际帧数和解码 hash 尚不能由表格独立认证。

| 方法 | CE 对 Current | 中位数 | 对 Current 改善序列数 | 关键直接比较 |
| --- | ---: | ---: | ---: | --- |
| R2-2 / 整数 Raw | −0.033694% | +0.053939% | 3/7 | R7-1 对它 −0.036119% |
| R3-1 / 整数 Guard | −0.093288% | −0.082512% | 4/7 | 仍为当前较强对照 |
| R7-1 / fractional Raw | −0.070549% | −0.123637% | 5/7 | 对 R3 +0.023403% |
| R7-2 / fractional Guard | −0.017510% | −0.017239% | 4/7 | 对 R3 +0.076633%；对 R7-1 +0.054503% |

“直接比较”是重新积分对应两条曲线，不是相减上表对 Current 的百分数。R7-1 的中位数与改善序列数比 R3 好、均值却更差，说明不能只按一次均值封死研究路线；也不能据此宣称它更稳健。

R7-1 在 BasketballDrill、FourPeople、KristenAndSara 的对 Current 值分别为 −0.260644%、−0.258613%、−0.167831%；BQMall、Johnny 分别 +0.173686%、+0.235246%。R7-2 保留较多 PartyScene 收益（−0.334925%），但 BasketballDrill 变为 +0.114677%。这是闭环结果分布，不证明能从局部邻居识别赢家。

据此优先研究：评分×guard 的交互、小样本幅值分布、非单调 cost 下候选缺失；不新增“某个序列/分辨率/QP 就切换”的规则。R6 的旧负结果限定于旧评分及其原搜索，不能直接排除 fractional 交叉组。R5 的无增量现象要求严格区分“执行了分支”和“改变了最终映射”。

完整数据范围、来源 SHA、限制和复算入口见 [R7→R8 依据核验](TS_Predictor_R7_Evidence_for_R8.md)。本次不声称重新完成了 R3 BCE 或任何 RA 的分析。

## 3. 对原探索计划的校正

1. 本地没有计划引用的 `TS_Predictor_Current_Analysis.md`、`experiment_manifest.json`、`verify_candidate_coverage.py` 或其结果附件；也没有核验所称 ZIP 内代码与工作区完全一致。以本次工作区及源表为实际依据，新生成的 manifest 和数学检查明确另起文件名。
2. `C_F` 是 **CG 入口冻结概率 + 假设 regular 路径**的幅值评分，不是当前目标系数的完整实时 CABAC rate，更不是最终 RD。后文不称其“精确真实码率”。
3. 放宽 `upAbsLevel` 的 remap==1 限制之后，候选仍至多是 round、min、up 三个不同值。现有 `coeffLevels[3]` / `coeffLevelError[4]` 容量足够；需要修正插入条件、去重和索引检查，不应无理由增加第四个量化值。仅当后续另加候选才重做容量设计。
4. C03/C04 的比较目标应记为 `J_owner=D_owner+lambda*R_owner`：复用所属 IntraSearch/InterSearch 分支实际的重建/残差失真、滤波、色度处理与 RD 权重。当前 InterSearch 中多处是 residual SSE，不能一概改称像素重建 SSE，更不能另造一个 `D_recon` 替换它。
5. B05/B06 的每个删一情景都保留**同一个完整候选集合**。若删除样本时同步删除由该位置产生的候选，已是另一种算法，本轮不做。
6. C03/C04 的成对局部 RD 统计和最终 Writer 统计不能混为一张“q 改变”计数表；最终 Writer 本身无法知道另一次未选择搜索的 q。

原探索文件保留原文作为来源；当前实施规格以本文和 `scripts/ts_r8_experiment_manifest.json` 为准。

本次源码核对基点为 `7a34fa8` 工作树：`TsFixedPrediction.h:236/249/278`（整数cost/Raw/Guard）、
`TsRateCost.h:8/40`（冻结cost/候选决策）、`ContextModelling.h:583/600/680/708`（freeze/调用/remap/逆映射）、
`QuantRDOQ.cpp:1254/1334/1482/1775`（候选容量/up门控/最终CG回放/零提前返回）、
`CABACWriter.cpp:4091` 和 `CABACReader.cpp:4487`（共同冻结点）、`InterSearch.cpp:7739`（所属搜索层rate/重建/失真）。
行号仅用于当前版本定位，不替代函数语义；本轮没有改这些源码。

## 4. 固定的公共定义

`a[]` 为 L、U、D、LL、UU 五个因果位置的非零最终/当前搜索已确定幅值，重复位置值保留。`n` 是非零位置数，范围 0..5，不是不同幅值数、CG 数或独立样本数。正式 Writer/Reader 使用可解码的前序 q；RDOQ 使用本次私有量化路径的前序 q。

`pC=max(abs(L),abs(U))`。remapping：

```text
M(0,p) = 0
M(a,p) = 1       if a=p>0
         a+1     if 0<a<p
         a       if a>p
```

identity 为 p=0；p=1 与它全域映射等价，候选去重规范化为 0。保持 Current-equivalent 优先，然后 identity，然后较小 p 的平局顺序；所谓对称评分不顺便改变平局规则。合法上限读取实际动态范围，所有新增 p 先裁剪，禁止用图像位深硬编码上限。

所有主组为 YUV、全部原生 TS 尺寸、原生 scan；BDPCM 保持原有排除方式。普通 transform、语法、lambda、QP、原有 TU 搜索工具参数不变。R8 的选择粒度仍为因果邻域的逐系数预测，不冒充原始“整 CG 专家选择”问题已经解决；只有 C02 的路径权重保持 TU-local 跨 CG 状态。

### 4.1 三种评分信息

`CI`：`TsFixedPrediction.h::syntaxCost`，等概率 bin 的整数长度代理。

`CF10/CF2`：`TsRateCost.h::RateTable::cost`，CG 开始、group flag 之前冻结 CABAC fractional bits；gt1 分类使用目标位置直接 L/U 非零个数（0/1/2），不是被评估历史位置的旧概率。significance/sign 在固定非零目标与固定路径下与 p 无关，因此局部评分不计；完整 replay 仍计入。

完整闭环 `J`：实际量化候选、后继邻域、CABAC、失真和工具竞争共同决定。不能把 `sum CF(M(ai,p))` 的下降当作 `J` 的下降。

混合使用 `(int64_t(CI)<<SCALE_BITS)+CF10`，路径混合使用 `CF10+CF2`；不除以 2，不引入舍入改变平局。整个 loss/score/G/H/regret 用 int64_t。所有候选共享同一快照，评分无真实 CABAC 写入。

### 4.2 sparse 与 dense

- S0：n<3 时 Current。
- Smax/Smean/Smin：n<3 时先取 identity；仅 n=2 且直接 L/U 都非零，分别取 max、`(L+U+1)/2` 整数下取整、min。
- n=0 或 pC<=1 时注意 identity 等价，不将模式编号差异误计为有效预测变化。
- B08 特例：n>=1 都进入平滑 Raw；n=0 取 identity。它不继承 Smax 的双直接邻居分支。

P0=`{0,ai}`，最多 6 个；P1=`{0,ai,clip(ai+1)}`，最多 11 个；两者均包含 Current 的等价代表。

对 loss `li(p)=C(M(ai,p))`：

```text
S(p) = sum_i li(p)
p*   = argmin S(p)
G    = S(pC)-S(p*)
H    = G-max(0,max_i(li(pC)-li(p*)))
```

Raw 取 p*；Guard 只在非 Current-equivalent winner 且 H>0 时接受，否则 Current。

## 5. 实验编号与直接对照

宏预留 `JVET_BJUT_TS_R8_MODE=0..24`，0 不选 R8；总开关仍为 `JVET_BJUT_TS_FIXED_PREDICTOR`。与所有旧固定/条件/R2–R7 默认模式互斥。以下 MODE 值为公开编号，不是内部 policy 数值。
首轮未来只实现1/4/8/13/15/16/17/19，其余非零值仍为预留，误请求必须报错而不是静默使用Current；当前所有R8值均尚未接入编码器。

### 5.1 A 组：同一 CF10 下改变稀疏或接受规则

| MODE / ID | dense / sparse | 直接对照 | 首次批次 |
| --- | --- | --- | --- |
| 1 / A01 | Raw / Smax | R7-1 | 1 |
| 2 / A02 | Raw / Smean | R7-1、A01 | 2 |
| 3 / A03 | Raw / Smin | R7-1、A01 | 2 |
| 4 / A04 | Guard / Smax | R7-2、A01、R6-5 | 1 |
| 5 / A05 | Guard / Smean | R7-2、A02、A04、R6-6 | 2 |
| 6 / A06 | Guard / Smin | R7-2、A03、A04、R6-7 | 2 |
| 7 / A07 | All-unaccepted-to-0 / S0 | R7-2、R6-1 | 2 |
| 8 / A08 | Rejected-to-0 / S0 | R7-2、R6-2 | 1 |
| 9 / A09 | Trim-cost / S0 | R7-1、R6-3 | 2 |
| 10 / A10 | Trim-saving / S0 | R7-1、R6-4 | 2 |
| 11 / A11 | Rejected-to-0 / Smax | A08、A04 | 2 |
| 12 / A12 | Trim-saving / Smax | A10、A01 | 2 |

全部 P0。A07 在 dense 区只有 Guard 接受非 Current 候选才保留它，其余全部 identity。A08 原始 winner 为 Current 时保留 Current，非 Current winner 被 guard 拒绝时才 identity。

`Trim-cost(p)=S(p)-min_i li(p)`；`Trim-saving(p)=S(p)+max(0,max_i(C(ai)-li(p)))`，各自最小化，不再叠加 G/H。

风险预注册：Trim-cost 不一定真正消除“自带命中”的优势；Trim-saving 的 identity 参考也不是无偏的真实分布。保留 A09/A10 是检验评分交互，不预设对称形式更好。

R7-1/2 加 A01–A06 构成 fractional 下的 Raw/Guard × S0/max/mean/min 2×4 矩阵。A11 不能只对 R7-2 解释为单因素，需要同时看 A08 和 A04。

### 5.2 B 组：候选覆盖与小样本分布

| MODE / ID | 改动 | 直接对照 | 首次批次 |
| --- | --- | --- | --- |
| 13 / B01 | CI+CF10，Raw，P0，Smax | A01 | 1 |
| 14 / B02 | 同混合 cost，Guard，P0，Smax | B01、A04 | 2 |
| 15 / B03 | CF10，Raw，P1，S0 | R7-1 | 1 |
| 16 / B04 | CF10，Raw，P1，Smax | B03、A01 | 1 |
| 17 / B05 | CF10，对称 minimax regret，P0，Smax | A01、A04 | 1 |
| 18 / B06 | 同 B05，P1 | B05、B04 | 2 |
| 19 / B07 | 三点平滑 CF10，完整平滑候选，Raw，Smax | B04、A01 | 1 |
| 20 / B08 | 同 B07，n>=1 都评分 | B07 | 2 |

**B03/B04 的完整性**：排序不同幅值 v1<...<vm；命中点 p=vj、每个非空开区间的代表 vj+1、最小值以下的 identity 覆盖所有合法 p 的历史 remapping 向量。CF 可非单调，所以“没有历史 hit 的 p”不能预先删除。固定历史目标更优不保证下一个系数或闭环更优。

**B05/B06**：对原样本和每个删除一个位置的情景 j，计算该情景所有候选的最小总 cost；每个 p 的 regret 是其各情景相对最优的最大差。按 `(max_regret, full_S, common_tie_order)` 排序。所有情景固定 P、概率、context 分类与路径；不把 n 个相关邻居称为独立交叉验证。预生成 loss 矩阵，用 O(n|P|) 求解，不做候选两两编码，不额外叠加 H>0。

**B07/B08**：每个原样本 ai 生成 `clip(ai-1),ai,clip(ai+1)`，权重 1:2:1，裁剪后合并；所有位置总权重为 4n。以正支持 V 构造 `Psmooth={0,v,clip(v+1)}`，最多 21 候选。零项的 predictor 无关部分可抵消，不能称真实零系数无编码成本。

平滑 loss 的分布与完整候选必须一起更改，这是一个明确的模型变化，不声称 B07 对 A01 只改了候选数。B07 对 B04 才是较合适的“原经验分布 vs 平滑分布（各自完整候选）”对照。

B01/B02 的 1:1 是固定试点，不宣称更准确物理码率；B07/B08 的 ±1/1:2:1 也是待证伪假设，本轮不再调权重或带宽。

### 5.3 C 组：路径与量化搜索

| MODE / ID | 改动 | 直接对照 | 首次批次 |
| --- | --- | --- | --- |
| 21 / C01 | CF10+CF2，Raw/P1/Smax | B04 | 3 |
| 22 / C02 | 因果历史 CG 的 w10*CF10+w2*CF2 | C01 | 3 |
| 23 / C03 | 原 R3-1 predictor＋成对 TU 量化搜索 | R3-1 | 4 |
| 24 / C04 | A01 predictor＋同成对 TU 量化搜索 | A01、C03 | 4 |

C01 固定 1:1，只验证路径敏感性；pure bypass 编码未 remap 的 a，与 p 无关，不将 `C0(M(a,p))` 混进去。

C02：TU 开始 w10=w2=1；CG 开始冻结权重。仅在一个 CG 最终完成后统计实际非零 regular 位置 N10/N2；两者都为 0 时不更新，否则各自 `w=max(1,w/2+N)`（非负整数除法）。未通过最终 CG 清零决策的临时 q 不更新；不读取当前 CG 最终 cutoff 决定该 CG predictor。CG0 与 C01 相同，单 CG TU 不可能取得历史权重的增量。

Writer 的 estimator 调用也必须使用 TU 分支私有状态，不能把多次试编码当多次历史；Reader 只在最终反映射完成后更新一次。RDOQ 的 N10/N2 来自最终 q 的私有原生 replay，不能来自其逐点近似 `remRegBins`。失败/未选择 TU 不向别的 TU 泄漏状态。有限计数上界由实际最大 CG coefficient 数推导并检查，不另加可调截断参数。

C03/C04：从同一 TU/component 搜索入口生成 q0（旧候选搜索）和 q1（round>0 时无条件加入合法、非重复 up）。两条分支重新量化整个目标区域、重建其后继 predictor 和 CABAC；保留 round==0 原提前返回和原全零分支。通过所属搜索层的完整相关语法和同一 RD 口径比较，平局选 q0。

不在 `QuantRDOQ` 内仅比其内部逐点 proxy 后称为“最终 TU RD 非劣”。需要由 IntraSearch/InterSearch 或共用的上层 TU evaluator 保存/恢复系数、CBF、absSum、重建/残差缓存、CABAC、滤波临时状态及与该分量相关的联合色度信息。若某耦合工具分支无法安全复评，必须先实现同范围回放，或另行记录范围修订；不能静默只在容易路径启用仍声称全覆盖。

不要求 decoder 尝试 q0/q1：每个实验只有一个公共 predictor，最终发送的 q 正常解码。`min(J0,J1)<=J0` 只对同输入、同入口状态和本 evaluator 的局部目标成立，不保证同序列实际字节或 BD-rate 非劣。仅扩一次 `up`、不加 beam/额外幅值；两条量化路径的复杂度必须实测。

## 6. 因子比较如何避免混淆

- 评分×guard 四角：R2-2、R3-1、R7-1、R7-2（已有 CE）。
- 评分×稀疏 Smax（固定 Guard）：R3-1、R6-5、R7-2、A04。mean/min 可用 R6-6/7、A05/6 构造对应四角。
- fractional 下 guard×sparse：R7-1、R7-2、A01、A04。
- fractional 下候选覆盖×sparse：R7-1、A01、B03、B04。
- 完整候选×minimax：A01、B04、B05、B06。
- predictor×量化搜索：R3-1、A01、C03、C04。

整数 Raw+Smax 没有现成旧组，不能把 R6-5（其 dense 是 Guard）冒充这个缺失角；本轮不为凑齐所有笛卡尔积增加组数。

需要交互数时，对每序列、每分量的四条曲线共同质量区间积分 log(R)，计算 `(L11-L10)-(L01-L00)`，然后分量 6:1:1、序列等权。该数是 log-rate interaction，不直接标为普通 BD-rate%。不相减各用不同区间的 BD 百分比当作交互估计。

主实验不默认 Y-only。若需要分量归因，另行锁定至多两个机制不同的方法，各做 R3/R3、新/R3、R3/新、新/新四角，明确属于追加设计，不混入这 24 组结果。整码流码率被 Y/U/V 共用，所以不能从 UV BD 退化直接推断 UV predictor 有害。

## 7. 工程接口和必须避免的伪实验

| 位置 | 预定改动 / 不变量 |
| --- | --- |
| `TypeDef.h` / `TsFixedPrediction.h` | R8_MODE、互斥检查、版本/配置日志；默认 0、旧组行为不变；runtime 显式覆盖宏需在日志同时记录 |
| 拟新增 `TsR8Prediction.h` | 常量配置＋统一候选/loss/decision；不在 R6/R7 分支叠嵌 24 套逻辑；最大 21 候选×5 原位置，预分配数组 |
| `TsRateCost.h` | 复用 Q15 概率表与 cutoff=2/10；评分 callback；保持旧 R7 数值与 tie bit-exact |
| `ContextModelling.h` | 因果读取、动态范围、统一模式分派；C02 的 TU-local 状态及 CG freeze/update |
| Writer / Reader | group flag 前同点冻结；统一 `needsTsRateContext(mode)`；实际多遍结束后路径计数；不只判断 policy32/33 |
| `QuantRDOQ.cpp` / `TsRateReplay.h` | 私有概率和预算；全零 CG 决策后 replay；C03/4 的候选上界仍为 3，原零分支不变 |
| IntraSearch / InterSearch | 只为 C03/4 接入成对完整局部 RD；其余 22 组不改此层目标 |
| `batch_test.py` / naming | 实现完成后只扩展模式注册；共用跨组池、resume、无重建、逐组即时 XLSM，不另写串行按组调度 |

缓存键必须包含相关 CG snapshot、直接非零类别、Rice、动态范围和路径，不跨类别复用错误 cost。热路径无动态分配、log 或 pow。C02 权重被冻结到 CG 结束，不能随 hypothetical 候选变化。批量参数未指定时按宏默认，指定时显式覆盖，不静默读入旧环境变量；Encoder/Decoder banner 必须匹配配置指纹。

## 8. 统计：明确三个层级

### 8.1 最终提交 Writer 聚合

仅最终选择 TSRC 的 TU，按 `mode, sequence, QP, component, W,H,n,directNZ,CG_count,CG_index,actual_cutoff` 聚合：TU/CG/coeff/nz 数、新增候选 winner、相对 Current/R3/直接父法的 predictor-equivalence 与实际 remap 差异、winner 类别、tie、G/H/score margin 直方图、实际 cutoff10/2/0。

TU/CG 分母用独立 census 去重；同一 TU/CG 可以含多个 n 或 cutoff，不能跨这些系数分桶累加 TU/CG 数。gain/persistence 若按尺寸报告也必须使用该尺寸的正确分母，不以系数数量冒充 TU 样本量。

这里用同一个最终 q 重新评价父法，属于条件样本，不冒充父法独立编码轨迹。全零 CG、CBF0 与 BDPCM 单列可达/排除计数；不能因为 residual writer 未进入就把未观察到的 TS CBF0 TU 当作已统计。新增候选遍历次数不是有效活动。

### 8.2 同入口成对搜索诊断

在有限、预先锁定的输入位置比较 q0/q1：候选集差异、临时 q 差异、最终 CG 清零后 q 差异、`DeltaRfrac/DeltaD/DeltaJ`、候选搜索胜者、是否最终保留该 TU/工具。仅搜索层可以给出这些值；不具备成对搜索时输出 `not_measured` 而不是 0。

区分 search trials、trial-winning TU、最终码流 TS TU，保留不同分母。不同闭环运行同坐标的 TU 不一定有相同输入/划分，不能直接称它们“同输入 q 改变”。该探针只诊断，不向公共 predictor 提供 source residual/distortion/search 信息。

### 8.3 闭环性能

保存每次完整运行的码率、Y/U/V PSNR、可得的分量 SSE、编码/解码时间、hash 和身份。缺少 SSE 原始日志时不从四舍五入平均 PSNR 反推“精确 SSE”。主结果仍是分量 BD 后 6:1:1、序列等权；分别报告类、序列、质量区间、mean/median/stddev/p10/p90 和配对序列 bootstrap CI。

禁止把相邻 coefficient 当独立统计样本。CE/B 都已用于开发，CI 为描述性；新内容/配对窗口按原序列成簇。重复同一确定性编码用于检查 hash，不增加独立样本数。

不默认输出逐系数文本。预期每模式每短任务数百至数千聚合行，真实数据量在 smoke 后报告；限额 trace 只定位问题。raw log/码流保留本地，不自动入 Git。

## 9. 执行阶段、任务量和停止条件

### 阶段 0：本次已完成与尚未完成

已完成：本地源码核对、R7 CE 数值审计、24 组 manifest 校验；1287 个原样本多重集合与 1287 个平滑支持集合的映射覆盖；1287 个 minimax 快/慢/位置排列/缩放检查；169 个 remap/inverse 小域往返；边界平滑、非单调成本反例、三量化候选上界检查。

这些是独立 Python 数学规格验证，**没有与尚不存在的 C++ R8 实现对照，不是 codec smoke 或实际收益**。

`python3 -m unittest discover -s scripts -p 'test_ts_*.py'`：首轮八组规格更新后84项通过，其中10项R8设计检查；其余为既有脚本回归，不等于本轮重新编码验证。v1时79项通过的记录保留在实验台账历史。

### 阶段 1：实现及短测，禁止据短帧 BD 排名

首轮八组：A01、A04、A08、B01、B03、B04、B05、B07；预留MODE为1、4、8、13、15、16、17、19。以同一框架实现，不实现为按组串行占满任务池。

先人工 TU 单测全 n、重复值、边界/矩形/原生尺寸、cutoff10/2/0、CG清零、reset、BDPCM、分量、符号、上下文复制和未来系数污染；Writer/Reader trace 与 decode hash 对齐。统计开/关同流；Current/macro-OFF 与旧 anchor 回归同流；旧 R3/R7 与保留程序回归同流。

真实短测预注册 **PartyScene、BQMall、KristenAndSara、Johnny，QP22/37，17 帧**：包含原 R3 强项、共同弱项以及 fractional 的改善/退化两面；GOP=8，17 帧可检查两组后续帧，不用只有两个相同起始画面的输入替代运动覆盖。

首批八组64个短任务，四对照 Current/R3/R7-1/R7-2 共32个短任务，共96点；这是必要的同帧工程对照，不是重跑完整 anchor。若输入不足或实际配置不满足该长度，先更新并冻结任务清单，不能悄悄改帧数。

停止/修复：解码失配、身份不符、状态污染必须停止；无新增映射/候选/最终 q 活动的组先给等价说明或定位，不为制造差异调参。固定旧 q shadow 无收益本身不作为淘汰会改变量化搜索的组的依据。

### 阶段 2：完整 CE 开发实验

短测验收后先跑第一批八组 LBeu CE、QP22/27/32/37，其余组按后续阶段评估。配置读取 `scripts/HHI测试cfg/LBeu/ConfigLB.ini`：BasketballDrill=250、BQMall=300、PartyScene=250、RaceHorsesC=150、FourPeople/Johnny/KristenAndSara=300 帧。已经是半帧，**不再除 2**，不传 `--full-sequence`。不限制为 8×8；现有 lowdelay cfg 启用 RDOQTS、TS 最大 log2=5，真实可达/观察尺寸仍由 SPS、工具竞争与日志区分。

- 第一批八组：224 正式编码点，不包含已有对照。
- 第 2 批十二组：336 点（未来上限，不是本轮任务）。
- C01/C02：56 点；C03/C04：56 点。
- 全 24 组上限 672 点，不含短测、旧对照缺失点或追加验证，不代表小时估计。

现有完整且身份/帧范围匹配的 Current、R3、R6、R7 可复用；仅同名或 Excel pass 不能确认可复用。任何缺失点都不默认用 anchor 补。复用失败也不自动启动大规模 anchor 重跑，应明确所缺信息/点。

共用现有 batch 共享任务池，某组最后几个任务未完成时下一组仍可占空槽；每组完成立即复制模板、写该组 XLSM，重试后刷新；Reference 不改，无重建输出。当前尚不添加伪运行命令：R8 runtime 注册和模式探测通过后才发布正式命令。

### 阶段 3：B、初始化与内容确认

优先选至多两条机制不同、真实有活动的路线做 B（每组 20 点）。不单凭一个 CE 均值永久否定其它组，也不以“旧赢家分支保持”当正确性条件；若保留均值暂差的路线，必须记录其不同失效分布或已测局部机制依据，不无限追加。

随后锁定合法起始位置/等长窗口及未用于规则设计的新内容，与 Current/R3 配对；清单在查看新结果之前固定。非标准窗口结果单列，不能拼到标准半帧 BCE 表里。新内容须核对素材可用性，本文不虚构已存在的盲测集。

最终相近方法另检查完整相对 RD 曲线，必要时在相同配置增加中间支持 QP 点并单列插值敏感性。不使用文献其他数据集的误差范围给本项目划一条“微小收益必为噪声”的阈值。此处参考 [The Bjøntegaard Bible](https://arxiv.org/abs/2304.12852) 对相对曲线与支持点的建议，未将其数据当本项目证据。

### 阶段 4：判断

- **Promising**：身份/编解码正确，真实闭环收益达到工程量级，在预定内容/初始化检查中有可复核支持，复杂度可接受；进入更完整验证。BCE −0.05%/−0.08%/−0.10% 分别沿用达标/不错/可观；这些是对 Current 的用户目标，不是对 R3 的显著性门槛。
- **Weak**：机制确实改变，但 CE 增量、稳定性或复杂度尚不支持部署；保留有明确问题的有限下一步。
- **Negative**：无真实增量活动，或跨预定内容持续退化且无相应局部机制价值；停止扩大该组。不能将所有负结果归为闭环“随机波动”。

新增候选若仅降低历史 S 而增加同目标真实 rate/最终 J，需要否定其泛化假设；更好 CF 下 guard 仍损失则重新解释风险规则，而非继续提高阈值。C02 若不优于 C01 或单 CG 占比使其覆盖很少，历史校准优先级下降。C03 若额外候选几乎不入选/最终没有 q 差异，则不铺全量双搜索。

## 10. 文件、验证命令与交付边界

- `scripts/ts_r8_experiment_manifest.json`：24 组声明式规格，非 batch 的 CSV manifest。
- `scripts/ts_r8_design_check.py`：纯数学/编号/父对照字段检查。
- `scripts/ts_r7_results_for_r8.py`：只读源表，输出 R8 依据的逐序列/汇总/audit。
- `experiments/ts_predictor_r8/r8_<MODE>_<name>/`：24 个带公开数字的收件目录；分阶段数据放 `smoke`、`LB_CE`、`LB_B`、`RA_CD`，不生成假结果表。
- `run_metadata.template.json`：空白来源字段，不是运行记录。

现在可以直接运行的只是设计验证和已有结果复核：

```bash
python3 scripts/ts_r8_design_check.py
python3 scripts/ts_r7_results_for_r8.py --out runs/ts_r8_design/r7_evidence
```

本次没有改 codec/CMake/宏默认，没有重编旧二进制，没有启动新编码，也没有覆盖旧工作簿。下一工程里程碑是统一 R8 选择框架与第一批模式的 C++ 对照/原生 CABAC 往返，而不是立即开跑 24 组。
