# R7：TS predictor rate estimator 源码、实现与分阶段实验

版本：RATE-20260924-v1。Current为唯一正式anchor；R3-1是主要增量对照。
本轮正式命名为 **R7**，算法版本不变。主宏为`JVET_BJUT_TS_R7_MODE/R7_SHADOW`；
旧`RATE_MODE/RATE_SHADOW`保留兼容别名，runtime名称及统计schema保持兼容。
简明入口见 [R7实验说明](TS_Predictor_R7_Experiment_Design.md)。
本轮取代“马上继续稀疏规则”的执行优先级，不同时修改predictor集合、空间规则、guard或阈值。
已有R2/R3/R6闭环表格仍然有效，研究的是其机制解释，不宣布旧结果失效。

已完成源码实现、原生/闭环正确性测试和六项自然序列shadow。
实测结果及后续收敛计划见 [2026-09-24报告](TS_Predictor_Rate_Shadow_Results_20260924.md)：
新模型局部代价误差降低，但完整CG fixed-q率尚无净改善，暂不直接铺开完整CTC。

## 1. 三个不同的目标

\[
C_{proxy}\ne R_{CABAC-est}\ne J=D+\lambda R.
\]

`syntaxCost`是历史幅值样本的整数语法代理；CABAC fractional bits是指定概率状态和语法路径下的估计率；
RDOQ还比较量化失真、零level、CG清零和最终工具选择。即使cost完全准确，也不保证历史邻域适合预测当前幅值，更不保证最终BD改善。

已有LB CE：R2-risk −0.033694%、R3-1 −0.093288%；R6七组都未超过R3。
不能据此判定R2的全部损失来自代理，也不能据guard有效就判定整数代价足够。

## 2. 还原当前R2/R3评分

源码：`CommonLib/TsFixedPrediction.h::{localPredict,guardedLocalPredict,syntaxCost,riceLength}`，
`CommonLib/ContextModelling.h::{magnitudePredictorModeTS,deriveModCoeff,decDeriveModCoeff}`。

邻域为L/U/D/LL/UU五个因果位置的绝对量化幅值，去掉零，重复值保留。n是非零位置数。
Current是max(L,U)；n<3直接Current。候选为Current、identity及历史样本幅值；p=0/1映射等价。
原raw selector最小化样本cost之和，严格小于才替换；平局先Current，再identity，再较小幅值。

\[
f(a,p)=\begin{cases}0&a=0\\1&a=p>0\\a+1&0<a<p\\a&a>p.\end{cases}
\]

NoPred只表示identity remapping，不取消significance/sign/greater-than/parity/remainder语法。

\[
C(0)=0,\quad C(1)=1,
\]
\[
C(a\ge2)=2+[a\ge2]+[a\ge4]+[a\ge6]+[a\ge8]
 +[a\ge10]L_{Rice}((a-10)\!\gg\!1).
\]

Rice长度复用当前有限escape规则，不是log2近似。令T=COEF_REMAIN_BIN_REDUCTION，r为Rice参数，d为动态范围：
value<T·2^r时长度为 `(value>>r)+1+r`；否则 `code=(value>>r)-T`、`maxPrefix=32-T-d`。
code≥2^maxPrefix−1时为T+maxPrefix+d；否则取最小k满足code≤2^(k+1)−2，长度T+2k+r+1。

这恰好是**完整regular幅值路径中，每个context bin都算1 bit**的成本，不含固定q下可抵消的significance和sign。
R3固定raw winner p*后计算：

\[
d_i=C(f(a_i,p_C))-C(f(a_i,p_*)),\quad G=\sum_i d_i,\quad
H=G-\max(0,\max_i d_i).
\]

仅H>0接受非Current候选。不是重新拟合的leave-one-out，更不是独立样本置信区间。

## 3. 真实TSRC路径及差异

源码：Writer/Reader `residual_codingTS`、`residual_coding_subblockTS`。
TU预算初始化为 `(W*H*7)>>2`；CG按实际grouped diagonal scan正向处理，不写死TU/CG尺寸。

| 路径 | 真实syntax | remapping作用 |
|---|---|---|
| CG flag | context-coded | 固定q下显著性不变 |
| 第一遍，进入位置时预算≥4 | significance（可能推断）、sign、gt1、可选parity均context-coded | 改gt1/parity的bin及parity是否存在；sign/sig直接不变 |
| 第二遍，进入位置时剩余预算≥4 | 2/4/6/8门槛的gtX，context-coded | 改bin、存在数量与后续预算 |
| 第三遍，完成第二遍的位置 | cutoff=10，Rice bypass remainder | 使用remapped magnitude |
| 第三遍，只完成第一遍的位置 | cutoff=2，Rice bypass remainder | 使用remapped magnitude |
| 第三遍，没进入第一遍的位置 | cutoff=0，原始abs level的Rice及非零sign bypass | **不remap** |

修改p不改变固定q的零/符号，但预算耗尽位置可变，间接改变后续sign/sig进入regular还是bypass。
Remainder的实际Rice为1，加上启用TSRC Rice信令时的slice tsrcIndex；不是由本地幅值任意重估。
SPS/slice参数、context set switch和动态范围沿用当前工程。

### 确认的误差来源

1. C(2)=C(3)=3，但真实成本相差parity bin的fractional bits；其它相邻偶/奇幅值也如此。
2. gt1=0/1、各gtX=0/1的概率不同；精确命中得到level1不等于所有状态下都固定节省整数bits。
3. bypass每bin确实1 bit，regular bin不一定；把两者全按1计改变了其相对权重。
4. 原C总是假设完整第二遍。cutoff=2路径应直接接Rice，可能与完整路径排序不同；cutoff=0根本不应比较remapped magnitude。
5. context随已编码bins更新，单个level的改变还能影响CG后续状态、bin预算及路径。
6. 整数平局、整数G/H与细粒度fractional差异可能改变Current优先和平局边界；但需统计实际影响，不假定所有Current选择都来自tie。

本轮没有发现 `riceLength` 与 native `encodeRemAbsEP` 长度不一致的证据。
问题主要不是Rice公式写错，而是概率和多遍路径被简化。

## 4. 为什么不能直接用“此刻的getCtx”

Writer在第一遍得到gt1/parity前已需要p，并在后两遍再次调用。
Reader在第三遍逐位置还原最终幅值时才调用p，此时第一、二遍的CABAC状态已更新。
直接读取各自调用时刻的context会使编解码器不一致；Reader的部分状态还包含当前/后续位置bins。

采用**CG开始、编码/解码CG flag之前的共同snapshot**：

- Writer和Reader都在同一CG入口复制必要的fractional-bit表。
- 表在整个CG内只读；不同pass与不同candidate看同一表。
- 使用gt1的三个直接非零邻居context、parity、四个gtX。上下文类型由原cctx确定。
- 样本cost都视作“当前位置的可能幅值”，使用当前位置的gt1 context类别，**不是**给历史样本重新按其原位置编码。
- 不读取当前目标幅值来选候选，不用后续CG/TU/frame，无新syntax。

RDOQ只有传入的估计context。新模式从它深复制私有状态，每个已最终确定的CG用真实三遍规则回放到下一CG：
清零CG决策完成后才回放，使用独立预算，不复用RDOQ近似的逐系数预算。
这个snapshot可能与最终Writer不同，报告中始终称 **RDOQ estimator snapshot**，不称真实Writer状态。
RDOQ的预测不必与最终Writer每次搜索试探都一致；正式Writer/Reader必须一致，已由实际CABAC验证。

## 5. 实现的新代价

源码 `CommonLib/TsRateCost.h::RateTable`：

\[
C_F(a\mid S_g)=r_{gt1}([a>1])+
[a>1]\left(r_{par}((a-2)\&1)+\sum_{c\in\{2,4,6,8\}}[a\ge c]r_{gtX,c}([a\ge c+2])
+[a\ge10]L_{Rice}((a-10)\gg1)\right).
\]

C_F(0)=0。公式中remainder以bit表示，实现统一使用codec的Q15整数（1bit=32768），累计及G/H为int64。
这是**CG-entry frozen full-regular model**，比原C增加真实概率信息，仍不是逐位置完整真实率。
没有拟合平均权重、额外阈值、概率截断、epsilon或新guard。

- 静态fractional表A：暂不实现。把整数乘比例不增加信息；随意平均权重缺少独立校准集。
- 本次选择B的可同步CG-snapshot版本：实际概率、固定候选间共同条件、低存储开销。
- 完整回放C：用于shadow真值参照，深复制完整CABAC状态、真实预算、真实pass和Rice，分支各自更新；
  因为需要当前CG完整q，只作encoder观察，**不将它直接当作decoder selector**。

候选评分独立、只读，既不按候选顺序更新context，也不把5个邻域样本虚构成一个依次编码的流。
将所有fractional bins设为1 bit时，新函数精确退化为原syntaxCost；262,144个level/Rice组合验证了这一点。

## 6. shadow：分清模型误差与统计预测误差

`EncoderLib/TsRateShadow.h`只挂在最终Writer，不挂在搜索CABAC estimator。
实际仍使用原R3-1。所有CG包括零CG进入census，BDPCM跳过；主分歧分母为非零、真实regular-remapped、n≥3位置。

### 6.1 历史评分变化

记录old/new raw winner、guard后predictor、真实目标remapping差异、旧Current tie、新score打破tie、G/H及margin变化。
按component、CU-QP、真实W/H、n、实际cutoff、old/new predictor类别聚合。序列及输入QP由batch任务元数据关联。
R6-2区域 `old G>0,H<=0` 分开old raw identity/nonzero，并记录新raw和guard选择Current/identity/原winner/其它winner。
同时观察new raw identity被guard拒绝时，绕过guard在固定q下是否真的减少率。

### 6.2 模型本身是否更准

只在评价时读取真实目标a。每个p从同一真实CG-entry状态出发，**仅替换这个位置的p**，其它位置保持原R3，
完整回放CG，得到该干预对CG总fractional bits的影响（包括后续context与预算传播）。
比较相对Current的代价差：旧整数proxy、新fractional proxy、真实CG干预差。
报告绝对误差、严格排序反转、proxy平局但真实率不同的次数。
这与“用历史样本选出的winner能不能预测当前a”是不同指标。

另加**事后已知anchor cutoff**的path-aware诊断：同一fractional表使用真实cutoff2/10。
它利用了selector决策时不可完全获得的当前CG路径信息，**不部署、不参与candidate选择**，仅定位路径误差。
候选可能改变真实路径，因此即便此诊断也不是零误差Oracle。

### 6.3 完整CG的fixed-q比较

同一snapshot下回放old R3、old raw、new raw、new guard，各自更新context/预算。
这些是条件CG率：下一CG重新使用anchor真实入口，不串联虚拟分支跨CG传播，更不是闭环BD-rate。
逐位置干预差互相重叠，不能相加冒充完整CG节省；另行完整CG回放才用于总率比较。

每个实测CG的原R3回放还与native `CABACWriter + BitEstimator`比对，率不一致立即终止。
单元测试另外比对最终probability内部状态、窗口/适配参数、预算；模拟绝不写回真实q、Ctx、Rice统计或slice。

## 7. RDOQ关系及可选搜索探针

`QuantRDOQ::quant`进入`xRateDistOptQuantTS`。原实现对round/min level采样，
若upAbsLevel独立且remap到1，会额外加入上取整level；predictor确实影响**candidate set**，不只影响Writer率。
随后`xGetCodedLevelTSPred`比较失真和`xGetICRateTS`，再做CG全零RD决策。
`xGetICRateTS`读取传入Ctx的fractional bits，但用remRegBins<4、4..7、≥8近似全bypass/第一遍/完整路径，
不同于Writer按CG分三遍遍历的真实预算。新predictor评分不修改这个原RDOQ率函数。

`TS_RATE_RDOQ_SHADOW=1`可选探针：保持同一anchor搜索状态，记录old/new额外up candidate、集合变化；
用原xGetCodedLevelTSPred另算一次new guard的one-step最佳level，所有cost输出使用临时变量、cctx复制，
恢复m_testedLevels，不提交level或预算。记录的是**临时搜索level**，不是最终选择TS或CG清零后的系数。
不会用源残差/失真参与公共predictor选择；它们仅存在于encoder诊断。
未实现整条分叉RD search或逐TU最终q的跨模式因果归因，不能把探针计数当作最终改变系数数。

## 8. 两个闭环测试模式

| TypeDef.h R7_MODE | runtime名称（保留兼容） | 新目录 | 唯一算法变化 |
|---|---|---|---|
| 1 | rate_raw | r7_1_raw | 原R2-2/r2_risk的syntaxCost替换为CG冻结fractional模型 |
| 2 | rate_guard | r7_2_guard | 原R3-1（YUV）的评分及G/H替换为同一模型；不是原R3-2 |

内部policy32/33不是宏编号。n<3、候选、tie顺序、fallback和strict H>0保持原样。
两组公用相同estimator，不另加保护、拓扑或跨TU状态。
这些是研究模式，必须配套相同编解码器，不能用原版decoder解码实验码流。
没有实现R6-2-derived bypass-guard模式；先看该区域shadow证据，不能只因raw选NoPred就宣布跳过guard安全。

## 9. 哪些旧实验重测/不重测

- 首选代表是R2-risk与R3-1，两者直接依赖score，足以比较estimator与guard是否各有价值。
- R4补查/R5 margin排序仅当这两组先有闭环价值、且专属shadow显示新增有效映射后再选一个，不全量重跑。
- fixed NoPred、gradient、directional不依赖syntaxCost，已有负/正结果无需因本次代理问题重跑。
- R6-5/6/7的新增n<3规则不依赖score；其n≥3继承R3确实依赖score。
  原消融结论仍成立于原R3基底，换基底是新交互实验，不是宣布旧数据无效或自动重测。
- R6-3字面sum-mincost有结构问题，R6-4换了比较参考；换fractional数值不能自动证明这两种结构合理。
- 原R2的退化可能部分与率排序有关，但shadow来自R3最终q，不可能精确分解历史R2 BD损失中多少由proxy导致。

## 10. 预定规模及停止条件

先固定PartyScene（R3强收益）、BQMall（近零）、KristenAndSara（退化）；LB，QP22/37，每项3帧。
不按新收益换序列。覆盖不足才沿同集合延长16帧；不在短测计算/筛选BD-rate赢家。
shadow与保留原R3程序逐任务SHA256对照，验证bit-exact；记录解码hash、编译宏/二进制/源码来源。

若新旧几乎无分歧或真实remapping不变，停止，不跑CE。
若分歧明显但完整CG固定q率不改善，不说“proxy已足够”，也不宣布新算法Promising；优先检查路径误差与统计预测误差。
有真实活动且正确性通过后，最多两组进入用户本地完整CE，仍可根据本轮阴性fixed-q证据降低优先级。
第三个guard-reject版本需要独立正证据；目前不默认安排。

完整CE为7序列×4QP×2模式=56项，LB半帧。Current/R3/旧R2已有结果仅来源一致时复用，不重跑完整anchor。
各分量先BD后6:1:1，CE七序列等权；直接对R3重新积分。没有完整四QP不作正式准入结论、不补anchor点。
最多一组进入B，再以十二序列等权BCE评价−0.05/−0.08/−0.10%目标。
报均值/中位数/逐序列/分量/质量区间/序列级bootstrap，不用数百万相关搜索试探宣称统计显著。

解释框架（“优于”指真实闭环RD，不是shadow率）：

- new raw≈new guard且优于old R3：支持guard过去部分用于抑制粗评分；仍不是唯一因果解释。
- new guard优于new raw、二者优于old R3：支持两种机制都有价值。
- new guard≈old R3而new raw更差：支持guard仍必要；不否认已经观察到的局部率误差。
- new guard更差：区分已验证的实现正确性、概率/路径近似、邻域代表性及RDOQ反馈，不自动归因bug。

## 11. 宏、命令及数据

算法开关只写`source/Lib/CommonLib/TypeDef.h`，不用CMake选择实验。
默认交付master=1，所有模式0、R7_SHADOW=0，实际Current。

shadow构建：master=1、R7_SHADOW=1、R7_MODE=0；R3_MODE=1可作为默认，或脚本强制r3_risk_guard。
shadow宏编译观察能力，运行脚本设置TS_RATE_SHADOW=1；默认不启用昂贵的RDOQ搜索探针。
正式new模式：master=1、R7_MODE=1或2，其余实验模式全0。新旧宏互斥，环境/`--fixed-predictors`可强制覆盖。
实际启动banner必须核对；shadow只允许old R3，不能混入new模式的正式任务。
未编译观察能力却请求任一shadow环境开关会立即报错，master关闭时也不静默忽略。
本地已保留SHADOW=1的观察版`build/ts-rate`；当前源码默认配置的二进制另在`build/ts-rate-final`，避免覆盖观察版来源。

```bash
# 在TypeDef.h设置所需宏后，普通构建；以下选项仅隔离产物/设置优化，不选择算法。
cmake -S . -B build/ts-rate -DCMAKE_BUILD_TYPE=Release -DNX2_TOPLEVEL_OUTPUT_DIRS=OFF -DNX2_ENABLE_LINK_TIME_OPT=OFF
cmake --build build/ts-rate --target EncoderApp DecoderApp TsRateCodecTest -j 8

bash scripts/run_ts_rate_shadow.sh
# 可选，另开结果目录；统计搜索试探，不改变实际编码
TS_RATE_RDOQ_SHADOW=1 bash scripts/run_ts_rate_shadow.sh --out-dir runs/ts_rate_shadow_with_search
python3 scripts/ts_rate_shadow_analyze.py runs/ts_rate_shadow/summary.csv --out runs/ts_rate_shadow/analysis
# 有同帧数旧R3短测时，加 --reference-summary <old-R3-summary.csv> 自动核对码流SHA256。

# 正确性短测，不是BD-rate
TS_FIXED_PREDICTOR=rate_raw build/ts-rate/bin/TsRateCodecTest
TS_FIXED_PREDICTOR=rate_guard build/ts-rate/bin/TsRateCodecTest
python3 scripts/ts_rate_smoke.py --jobs 3
```

只有决定进入完整CE后才执行：

```bash
env -u TS_RATE_SHADOW -u TS_RATE_RDOQ_SHADOW python3 scripts/batch_test.py \
  --preset LBeu --class C,E --qps 22,27,32,37 --fixed-predictors rate_raw,rate_guard \
  --encoder build/ts-rate-final/bin/EncoderApp --decoder build/ts-rate-final/bin/DecoderApp \
  --jobs 10 --decode-md5 --no-recon --xlsm-report \
  --xlsm-template scripts/JVET-hhi.xlsm --out-dir runs/ts_rate_LB_CE_half --dry-run
```

删去dry-run才编码；不传frames/full-sequence即使用HHI半帧。共享池不等上一组结束，每组完成立即写自身XLSM，resume保留。
统计开关纳入resume指纹，不能把无shadow结果当作已完成shadow；启动能力探测清理统计环境，不影响实际任务开关。

日志只有聚合`TS_RATE_SHADOW`、`TS_RATE_CG`、可选`TS_RATE_RDOQ`，没有默认逐系数文本。
analysis输出原聚合计数、各维度比例、条件CG率和单独的RDOQ搜索表；源日志不改。
新结果收件目录为 `experiments/ts_predictor_r7/{shadow_r3,r7_1_raw,r7_2_guard}`。
旧`experiments/ts_predictor_rate`及既有`runs`不移动；batch识别原`rate_1_raw/rate_2_guard`续跑路径，
新旧目录同时存在则报歧义，不静默合并。不能把内部policy32/33当作目录宏编号。
