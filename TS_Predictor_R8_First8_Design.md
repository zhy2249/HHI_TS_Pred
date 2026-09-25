# R8 首轮八组：冻结规格与实现设计

版本：`R8-DESIGN-20260925-v2`。按用户“选择8组合适的实验先开始设计”的要求，**替代先前首批10组安排**。
本轮选择 **A01、A04、A08、B01、B03、B04、B05、B07**，公开 MODE 为 **1、4、8、13、15、16、17、19**。
不重新编号为1..8，避免与原24组和收件目录混淆；其它16组保留后续设计，不默认安排运行。

**状态：八组详细设计和可执行 Python 数学参考完成，尚未接入 C++ 编解码器、宏或 batch，也未运行新编码。**
正式 anchor 仍为 Current；R3-1 为增量对照。源数据依据见 [R7 核验](TS_Predictor_R7_Evidence_for_R8.md)，共同工程要求见 [R8 总设计](TS_Predictor_R8_Experiment_Design.md)。

## 1. 为什么选这八组

选择依据是覆盖不同失效机制、保留直接对照并控制实现风险，不是预测哪八组一定获胜。

| MODE / ID | 方法 | 首要直接对照 | 唯一研究变化 / 目的 |
| --- | --- | --- | --- |
| 1 / A01 | fractional Raw＋Smax | R7-1 | 仅改变 n<3 的规则，判断稀疏处理是否依赖评分体系 |
| 4 / A04 | fractional Guard＋Smax | A01；另对R7-2 | 在相同稀疏规则下检验 guard；与R7-2比较则仅改稀疏规则 |
| 8 / A08 | fractional Guard-reject→NoPred | R7-2 | 仅替换 dense 区真正拒绝候选后的 fallback |
| 13 / B01 | 整数与 fractional 1:1 混合 Raw＋Smax | A01 | 仅改变 cost，检验纯 fractional 对有限样本是否过度敏感 |
| 15 / B03 | 完整候选 P1＋Raw＋S0 | R7-1 | 仅补候选，保持原稀疏规则 |
| 16 / B04 | 完整候选 P1＋Raw＋Smax | A01；另对B03 | 对A01只补候选，对B03只改稀疏规则；同时是B07的父对照 |
| 17 / B05 | 对称删一样本 minimax regret＋Smax | A01；另对A04 | 只改 dense 决策目标，不再给Current单独的接受保护 |
| 19 / B07 | 三点平滑幅值分布＋完整候选＋Raw＋Smax | B04 | 对比各自完整候选下的经验分布与平滑分布 |

B04 是本次选择的关键补充：没有它，B07 只对 A01 时同时改变候选覆盖与目标分布，难以解释收益来源。它与 R7-1/A01/B03 构成完整的“候选覆盖×稀疏规则”四角，不是无目的增加一个组合组。

暂缓理由：

- A09/A10 的 trim 与 B05 都处理样本稳健性；八组预算内先保留一个明确不同的对称决策机制。不是按旧负结果永久排除 trim。
- A11/A12 是进一步组合；先分别观察稀疏、fallback、评分机制，再判断组合必要性。
- mean/min、mixed Guard、完整候选 minimax、n>=1 平滑仍保留原编号，暂不扩展笛卡尔积。
- C01/C02 会引入路径模型/历史状态，C03/C04 会改量化搜索；首轮先保持 R7 的概率冻结和原量化搜索，降低归因与同步风险。

八组均为全YUV、全部原生TS尺寸，不新增序列/QP/尺寸特判，也不先限定Y-only。它们都可能通过既有 RDOQ 耦合改变最终 q；“保持原量化搜索”指不主动扩候选搜索规则，不是强制固定旧 q。

## 2. 共同计算约定

五个因果位置为 L/U/D/LL/UU，非零幅值保留重复形成 `a[0..n-1]`，n=0..5。Current `pC=max(abs(L),abs(U))`；p=0/1 在 remapping 上等价并规范化为0。

```text
M(a,p) = 0     (a=0)
         1     (a=p>0)
         a+1   (0<a<p)
         a     (a>p)
```

所有 CF 使用当前 CG 在 group flag 之前的同一冻结 CABAC snapshot、当前目标的 L/U 非零类别、原 Rice 和动态范围，评分路径统一 cutoff=10。不能以当前目标真实 magnitude 或最终 cutoff 构造评分。

`CIq=syntaxCost<<SCALE_BITS`；CF为原Q15 fractional值；不混合整数bin与Q15数而忘记缩放。全部累计/差值使用64位整数，不用浮点阈值。

排序平局统一 Current-equivalent、identity、较小 p。对称只涉及 B05 的主评分，不暗改 tie。全部预测器均只读取因果 q 和同步快照；最终编码该目标时才会读取目标 level 作 remap，不把它反用于选择预测器。

### 稀疏分支先行

仅当 n<3：

- S0：返回Current。用于A08、B03。
- Smax：若 n=2且直接L/U均非零，返回Current；其它情况返回identity。用于其余六组。

n>=3才进入下面的评分。n=0、Current<=1或已经identity等价的情况不计为有效映射改变。B07的平滑支持不改变n，不能将一个观测拆成三个样本后通过n>=3门槛。

### 候选与 loss

- P0=`{0,ai}`，去重且规范化，至多6个。
- P1=`{0,ai,clip(ai+1)}`，至多11个；包含不命中任何历史幅值、但可能由于CF非单调而有利的候选。
- Psmooth：B07的三点平滑正支持V，使用`{0,v,clip(v+1):v in V}`，至多21个。

所有clip采用源码合法系数幅值上限，不用固定8bit/10bit像素上限。`li(p)=C(M(ai,p))`，`S(p)=sum li(p)`。先求总成本 raw winner p*，再计算：

```text
G_raw = S(pC)-S(p*)
H_raw = G_raw-max(0,max_i(li(pC)-li(p*)))
```

## 3. 八组 dense 规则

### A01、A04、A08：拆分稀疏、guard、fallback

A01直接取CF/P0的p*。

A04在p*不同于Current且H_raw>0时取p*，否则Current。

A08：

```text
if p* 等价 Current:          Current
else if H_raw > 0:          p*
else:                       identity
```

这里p*是严格更低cost的非Current候选才会进入最后分支；winner本来Current时不强制NoPred。原始winner就是NoPred和非零winner被拒绝，日志分别统计，不把两者混为“更合理fallback”。

首轮可回答：稀疏覆盖与guard是否交互，及fractional评分下guard拒绝是否仍适合回Current。若A08改进仅来自少数内容或只是继承R7原收益，需要明确报告，而不是扩大无条件NoPred。

### B01：同单位评分收缩

`Cmix=CIq+CF`，在P0上Raw选择；共同除以2不影响排序，因此不做整数除法。其余完全同A01。

这不是“更精确CABAC码率”的声明，而是评分敏感性的固定正则化假设。首轮不增加0.25/0.75权重或按QP改变比例。若CF=CIq，各候选成本整体乘2，winner必须与A01相同；作为必测性质。

### B03、B04：补全 remapping 状态

只将P0换为P1，不加guard、不修改CF。B03对R7-1保留S0，B04对A01保留Smax。

固定历史向量和同一CF下，P1的最小历史总cost必不大于P0，因为P0是其子集；这不是目标系数码率或闭环RD保证。必须记录新增`ai+1`候选获胜、真实target remap改变及最终TS活动，而不只记录候选列表变长。

### B05：对称最坏后悔值

保留P0。在完整样本以及每个删除一个位置的情景j中：

```text
S_p^0 = sum_i li(p)
S_p^j = S_p^0-lj(p)
r(p)  = max_j [S_p^j-min_q S_q^j]
chosen = argmin (r(p), S_p^0, tie_order(p))
```

所有情景保持相同P0、CF、context类别；不删除由被删样本生成的候选。没有另叠原H>0 guard。相同幅值出现在不同位置时，删除一个位置只删除它的一份贡献。

这是有限情景稳健优化，不是独立留一验证或置信概率；它仍保留Current优先平局。测试它能否减少原guard的偏向，同时不把噪声winner全放进来。

### B07：平滑分布，而不是平滑 predictor 值

每个原样本ai贡献`clip(ai-1),ai,clip(ai+1)`，权重1:2:1；同幅值权重合并，裁剪后的总权重仍为4n。以Psmooth作Raw选择，n<3严格走Smax。

这并非选择mean predictor。它降低经验分布只在精确观察值上集中的程度，但也可能损坏真正重复幅值的强证据。B07对B04比较“各自具有完整候选的平滑/未平滑模型”，不是候选数单因素消融。

零支持项的significance等公共代价在局部排序可抵消，不能据`cost(0)=0`宣称实际零系数免费。首轮固定±1和1:2:1，不增加带宽扫描。

## 4. 对照闭合与可回答的问题

八组内的首要父对照都存在；外部只有已实现的R7-1/2，不依赖某个延期的R8组：

- guard×sparse：R7-1、R7-2、A01、A04。
- candidates×sparse：R7-1、A01、B03、B04。
- 评分收缩：A01→B01。
- 接受风险规则：A01→A04或B05，不混合二者。
- guard拒绝出口：R7-2→A08。
- 幅值分布平滑：B04→B07。

Current与R3-1始终同时报告；机制父对照只是解释增量，不替换正式anchor。R6-2/5可在确认配置身份后作评分跨轮辅助，不增加首轮新方法数量。

交互必须在四条曲线共同质量区间的log-rate积分上计算；不相减不同区间的两个BD百分比。某组超过Current但未超过父法，不能把继承收益算为本次改动贡献。

## 5. 首轮工程实现边界

拟新增`TsR8Prediction.h`承载只读局部模板、候选生成、loss和选择；公共配置字段为cost/sample/candidates/decision/sparse。八组均不新增跨CG学习权重；沿用R7的CG snapshot和私有RDOQ回放。

生产代码按需要缓存有限幅值cost，不照搬Python参考程序的整幅值表分配。最多21候选×5原样本的64位loss矩阵是840字节，另有候选/score/缓存空间；实际栈与运行开销须实测。平滑每位置至多三项，不引入动态分配。

接口设计：

```text
readCausalMagnitudes(cctx, scanPos, q) -> L/U/D/LL/UU
selectR8(config, magnitudes, frozenCostView, legalRange) -> decision
decision: predictor, support, candidateCount, rawWinner,
          rawGain/rawMargin, selectedObjective, branch
```

`rawGain/rawMargin`在B05仍是Raw赢家的诊断值，不能误称为minimax选中者的接受条件；稀疏未评分时输出not_evaluated而不是伪造0成本。

必须同时接入公共RDOQ/Writer/Reader入口，统一`needsTsRateContext`，不能仍只识别旧policy32/33。统计比较父法时显式传其配置，不临时改全局环境/模式污染真实编码。

未来`TypeDef.h`仅放一个R8_MODE总选择，0不启用；首轮合法非零值为1/4/8/13/15/16/17/19，其余预留值请求时明确报“尚未实现”，禁止静默Current。旧固定/条件/R2–R7互斥；总开关关闭却请求R8时报错。省略batch覆盖参数使用宏默认，显式`--fixed-predictors`覆盖并在Encoder/Decoder记录相同有效模式。

八组不改`xGetICRateTS`、round/min/up插入规则、lambda、CG全零RD判断，也不改变正式bitstream语法。实际实验码流仍要求用相同预测策略的实验Decoder解码，不能冒称与未修改的Current解码器兼容。

## 6. 日志与验收

先复用最终Writer聚合层，仅统计最终选中TS的系数，按分量/n/尺寸/CG位置/实际cutoff分桶。至少记录：相对主父法的predictor-equivalent与真实remap差异、raw winner/最终winner类别、guard迁移、新增候选获胜、B05相对Raw改判、B07相对B04改判。

Current p<=1等价、pure bypass不应用remap和BDPCM排除必须单列。TU/CG用独立census去重，不跨系数分桶重复累加。`q_changed`若没有同入口成对搜索探针就明确not_measured；不同闭环同坐标不一定同输入，不据此虚构量化变化率。

最终Writer观察仍有工具选择偏差，只解释活动。正式优劣取闭环RD；冻结旧q无收益不能自动排除本组。不产生逐系数GB日志。

正确性先于性能：

1. 参考公式与C++逐项对照，覆盖n=0..5、重复值、边界/矩形、最大幅值、0/1等价与全部平局；不只比较平均分数。
2. 原生TU/CABAC往返、Writer/Reader同快照trace，cutoff10/2/bypass，CG清零/reset、BDPCM、YUV及未来系数污染检查。
3. Current/macro-OFF对anchor、旧R3/R7对保留二进制、统计开关前后bit-exact回归。
4. 新八组逐一有有效模式banner、解码hash与实际映射活动证据；无活动先解释，不调参数制造差异。

本次已经运行Python参考：1024个五邻域模板×3个合成cost表×10个公式（八组加R7两个对照），共30720次决策；八组都找到相对主父法的映射差异反例。另验证混合cost缩放、dense父法保持、P1全域小范围最优与fallback边界。
这只证明公式在人工域不等价，不证明对应CABAC状态可达、CTC有活动或BD收益；尚无任何新R8编解码验证。

本轮全部84项TS Python测试通过，其中10项R8设计测试；不能据脚本测试通过声称新编码算法已经实现或验证。

## 7. 运行规模与后续选择

短测仍为PartyScene/BQMall/KristenAndSara/Johnny，QP22/37、17帧，八组64任务；Current/R3/R7-1/R7-2四对照32任务，共96。只验活动/正确性，不用其BD给八组排序。

短测通过后，八组LB CE半帧、QP22/27/32/37，共 **8×7×4=224个新增正式编码点**。已有合法对照复用，不重跑完整Current。帧数由现有LBeu INI读取，已经半帧、不再除2；无重建；跨组共享任务池；每组完成立即写自身XLSM并保持resume。

建议实现次序：先A01/A04/A08/B01复用P0验证公共路径，再B03/B04扩候选，最后B05/B07引入新目标。这是代码依赖次序，**不是要求编码调度逐组等待结束**。

结果先按各分量BD后6:1:1、七序列等权比较Current与主父法，再看序列/分量/质量区间/尺寸活动和复杂度。BCE −0.05/−0.08/−0.10%目标仍是对Current；八组CE本身不能宣称已达到BCE。

若完整候选只降低历史S而真实rate/RD持续变差，降低覆盖扩展优先级；若B05在更细cost下仍不优于Raw，不继续叠guard阈值；若平滑有清晰活动但持续破坏重复幅值区域，否定该固定平滑假设。短测或一次均值不是永久删组标准，但也不把负结果一律归于路径噪声。

## 8. 文件与可运行检查

```bash
python3 scripts/ts_r8_design_check.py
python3 scripts/ts_r8_first8_reference.py
python3 -m unittest discover -s scripts -p 'test_ts_r8_design.py'
```

`scripts/ts_r8_experiment_manifest.json`保存首轮八组、主/辅助父对照与224/96任务计数；各结果目录数字不变。以上是设计检查命令，不是编码命令；此时设置R8宏不能启动实验。
