# R6：R3 Current 偏好与稀疏邻域的独立实验

冻结版本：R6-20260923-v1。Current 是唯一正式 anchor，R3-1 是增量对照。
本轮只研究两个问题，不组合最佳规则，不按 QP、序列、分量设特例，不扫描阈值。
七组包括五个直接实验和两个必要诊断对照，不表示应立即运行七组完整 CTC。

## 1. 真实 R3 实现

`ContextModelling.h::magnitudePredictorModeTS` 在 mode=13 时调用
`TsFixedPrediction.h::guardedLocalPredict`。邻域为五个因果位置：

\[
T=(L,U,D,LL,UU)=(|q_{x-1,y}|,|q_{x,y-1}|,|q_{x-1,y-1}|,|q_{x-2,y}|,|q_{x,y-2}|).
\]

TU 外上/左位置为0；去掉零幅值，得到多重集 \(T^+\)。
**n 是非零位置数量，不是非零幅值种类、CG 数或独立统计样本数。**重复幅值保留，0≤n≤5。
这些位置在当前 grouped scan 中均已可用；可以位于当前 CG 内，并非纯前 CG 选择器。

Current 为 \(p_C=\max(L,U)\)。幅值 a 的映射经真实 `deriveModCoeff/decDeriveModCoeff` 确认：

\[
f(a,p)=\begin{cases}0&a=0\\1&a=p>0\\a+1&0<a<p\\a&a>p.\end{cases}
\]

p=0 与 p=1 都是 identity remapping。NoPred 在本轮仅表示 p=0；significance、sign、greater-than、parity、Rice 和 bypass 等 TSRC 语法都保留，不是整个系数改为裸 absolute-level 编码。

R3 的整数代理 C 为源码 `syntaxCost`：C(0)=0、C(1)=1；a≥2 时

\[
C(a)=2+[a\ge2]+[a\ge4]+[a\ge6]+[a\ge8]
       +[a\ge10]L_{Rice}(\lfloor(a-10)/2\rfloor).
\]

Rice remainder 长度复用真实长度规则，但整个 C **不是 CABAC fractional bits**，也不适用于所有实际 pass/budget 状态。
本轮保持同一不可变 TU Rice/range 参数，避免多遍 Writer/Reader 状态不一致；最终主评价必须是真实闭环 BD-rate。

R3 在 n<3 时 Current；否则候选为 Current、identity、T+ 内幅值（p≤1归一为identity）：

\[
p_* = \arg\min_p\sum_i C(f(a_i,p)),\quad
d_i=C(f(a_i,p_C))-C(f(a_i,p_*)),\quad
G=\sum_i d_i,\quad H=G-\max(0,\max_i d_i).
\]

候选成本打平先保留 Current，再 identity，再小幅值。仅 H>0 接受非Current候选，否则 Current。
这是固定候选的删一贡献敏感性检查，不是重新拟合的 leave-one-out，也不是置信区间。

## 2. 问题是否成立

### Current 偏好：结构成立，性能问题待验证

- pC>0 时，L 或 U 必有一个样本等于 pC，Current 至少一个 perfect match；这是精确结论。
- 但其它从 T+ 取值的非零候选也至少有一个 perfect match，不能把全部样本内选优偏差只归因于 Current。
- 不对称性确实存在：Current 无须通过 H>0；它也是不足支持、无优胜者、guard拒绝与平局的默认值。
- “有偏好”不等于“应去除”：Current 是 codec 原基线，保守策略可能正是 R3 优于无guard R2 的原因。
- R4-1/2 分别删掉两类候选后均退化，故本轮保留 identity 与幅值候选。R4-3/R5 全CE同R3，说明仅微调排序容易没有增量，须先检查实际 remapping。
- 已有 CE：R3-1 −0.093288%、R2-risk −0.033694%；它们不是只凭这一对平均就证明 guard 因果有效，但足以警惕无保护替换。

### 稀疏门槛：是可检验假设，不是已证实不足

- n=0：L=U=0，Current=NoPred，任何模式应无新增映射。
- n=1：若非零位于 D/LL/UU，Current已经0；只有直接 L 或 U 非零才可能不同，幅值1仍等价。
- n=2 且 L/U 均非零：D/LL/UU 必全零；只说明空间位置支持，**不说明 L/U 幅值接近**。
- n=2 但不是上述布局：改NoPred可能抑制孤立大的Current，也可能损失真实的单方向连续性。因此单独测试，不预设正收益。

因此稀疏max真正可能改变映射的范围更窄：n<3、恰有一个直接L/U非零且其幅值>1。
没有直接非零邻居或其幅值仅为1时，本来就与identity等价；不能把全部n<3位置都算成有效新增活动。

## 3. 实验定义与编号

新宏 `JVET_BJUT_TS_R6_MODE=0..7`，内部 policy=25..31；目录采用公开宏编号。
全部 YUV，与 R3-1 一致；不改 BDPCM / TSRC-off / non-TS 原路径。

| MODE | 名称/目录 | 唯一改动 | 保持不变 |
|---|---|---|---|
| 1 | r6_1_dense_nopred | n≥3、R3没有接受非Current候选时用NoPred | n<3、已接受候选、原候选搜索/G/H |
| 2 | r6_2_reject_nopred | 仅“原始cost严格更优，但H≤0”的候选被拒绝时用NoPred | n<3、无优胜者、已接受候选 |
| 3 | r6_3_trim_cost | n≥3，所有候选最小化 sum(cost)−min(cost) | n<3、候选集、平局规则 |
| 4 | r6_4_trim_saving | n≥3，所有候选扣除最大正节省贡献后比较 | n<3、候选集、平局规则 |
| 5 | r6_5_sparse_max | n<3：仅两个非零恰为L/U时max，否则NoPred | n≥3完整R3 |
| 6 | r6_6_sparse_mean | 与5相同，仅L/U分支换成 (L+U+1)/2 | 其它区域与5相同 |
| 7 | r6_7_sparse_min | 与5相同，仅L/U分支换成min | 其它区域与5相同 |

运行名称为去掉目录数字的字符串，如 `r6_trim_saving`；宏0不选择R6。不实现组合模式。

### A：为何把 fallback 拆成1/2

“没有接受候选”包含两种不同原因：原始成本没有更优候选，以及选出了更优候选但 guard 拒绝。
MODE1覆盖两者，是较强的fallback诊断；MODE2仅改变第二种，是更干净的guard拒绝出口对照。
若把 n<3 也统一改NoPred，就同时修改问题2，故本轮明确排除它。
直接回退NoPred不要求NoPred自己具有证据，它可能比Current甚至被拒绝者更差；这不是“公平性修复”的预设答案。
1对2的直接差异主要诊断“无优胜者改NoPred”，2对R3诊断“guard拒绝出口”；真实闭环q不同，不能据此做逐系数静态因果分解。

### B：原公式的逻辑漏洞与修正版

MODE3忠实实现：
\[
S_C(p)=\sum_i C(f(a_i,p))-\min_i C(f(a_i,p)).
\]

每个 p>1 且来自样本的候选都命中某样本，因此最小cost均为1；它们之间只统一减1，排序根本不变。
若样本含1，identity的最小cost也为1，整个排序退化为无guard的原总cost排序（R2-risk）。
若样本不含1，identity删去的cost更大，可能只是引入对identity的偏好。
而且各候选删的是不同样本，余下样本难度不相同。它不等于对同一个配对数据集消除一次过拟合。
因此仅作为低优先级诊断，不称作已经消除Current偏置的robust算法。

MODE4使用统一 identity 编码成本作为每个位置的参考，**包括Current在内**全部同样评价：
\[
g_i(p)=C(a_i)-C(f(a_i,p)),\quad
H_N(p)=\sum_i g_i(p)-\max(0,\max_i g_i(p)),\quad
p=\arg\max H_N(p).
\]

等价实现为最小化 \(\sum_i C(f(a_i,p))+\max(0,\max_i g_i(p))\)，避免不必要的常数项。
删除的是预测器相对统一参考的**最大有利贡献**，而不是由目标幅值难度决定的最小cost。
Current 的单次大命中也受同样处罚；重复匹配只删最大的一次，余下支持保留。
identity 的所有 g=0，因此候选最大值至少0；若全为0仍沿用Current平局优先，若Current<0则不能享受免检保护。
这里identity只是局部损失的共同参考，**正式anchor仍是Current**。它与原R3的Current相对配对损失不同，不能宣称绝对无偏。
不在对称评分后再叠加原 R3 H>0，否则又引入被研究的不对称。
各候选仍来自同一小样本，邻居相关且候选选择有多重比较；这不是独立验证集，也不保证真实CABAC/RD改善。

一个能看清差别的固定模板：L=3、U=2、D=2、LL=UU=0，n=3，Current=3。
原始总cost：Current为1+3+3=7，候选2为3+1+1=5，identity为3+3+3=9。
R3候选2的配对贡献为(−2,+2,+2)，G=2、H=0，因此拒绝并回Current。
修正版对Current的identity相对贡献为(+2,0,0)，删最大后0；对候选2为(0,+2,+2)，删最大后2，因此选2。
它直接检验“一个Current自带命中是否挡住两个重复幅值支持”；但下一系数实际更像3、2还是别的值，仍须闭环实验回答。
同一模板中MODE2会回退identity，其历史总cost甚至高于Current，因此不能将fallback-NoPred实验说成风险必然更小。

## 4. 稀疏 max / mean / min 的 remapping 含义

mean 用正整数四舍五入（半数向上），int64加法避免溢出；不额外截断或加门控。
若 L=U，三者完全一致。若只差1，mean=max，故须检查 L/U 不等且三者真正分离的样本。

例如 L=2、U=6：

| 当前 a | p=max=6 | p=mean=4 | p=min=2 |
|---|---:|---:|---:|
| 2 | 3 | 3 | 1 |
| 4 | 5 | 1 | 4 |
| 6 | 1 | 6 | 6 |
| 7 | 7 | 7 | 7 |

表内是 modified magnitude，不是cost或CABAC bits。max有利于目标延续大幅值；min有利于小幅值且缩小a<p的上移区间；mean只有目标真的靠近并命中中间整数时可能有利。
若两个观测是分离的两峰，中间整数可能从未出现，mean不能凭“平均误差较小”获得编码优势。
a>max时三者映射相同；零也相同。p数值改变不等于实际编码改变。

## 5. 实现范围、同步与反馈

- 原 R3 函数不变，新 `TsR6Prediction.h` 纯函数在公共Context入口分派；QuantRDOQ/Writer/Reader已有入口统一复用。
- 只读上述五个幅值，忽略符号；Reader当前CG的幅值视图即可。无跨TU/CG持久统计状态，无当前/未来目标读入。
- RDOQ使用自身当前因果候选q；真实Writer/Reader使用最终q。预测改动参与RDOQ及TS选择，是闭环编码实验。
- 没有持久的临时搜索q缓存，CG最终清零不会污染后续history；最终活动统计只在真实Writer，不在RDOQ或估算分支写入。
- 非TS、BDPCM以及原语法bypass不新增remapping；不增加码流标志，实验编解码器必须采用相同模式。
- 稀疏模式的空间假设不是新的跨CG adaptive selector，不冒充最初的TU-local历史CG选择器。

## 6. 日志和数据解释

默认 `TS_R6_STATS_HEADER` / `TS_R6_STATS` 写 **stderr**；外部脚本须合并stderr，例如 `> run.log 2>&1`。
`TS_R6_STATS=0`只关闭观察，不能关闭算法。`TS_COND_TRACE`仅用于短测，长跑不设置。
按policy、分量、真实W/H、CU-QP、intra、BDPCM、CG数量/位置在线聚合，无逐系数文本、无POC键。

关键字段：support0..5、current_hits0/1/multi、dense_no_proposal/rejected/accepted、fallback两种来源、
candidate_tie_current、lu_only/equal/unequal、p_vs_r3、remap_vs_r3及按n分解、lu_remap_vs_r3、hit/under/over、modified分布、目标事后代理损益。
`active_count`是最终非零CG中regular第一遍访问的位置，含零目标；不是全部TS系数。
命中类别与支持数在active位置统计；TU/CG计数包含进入TSRC的零CG，但不包含CBF0和TSRC-off TU。
fallback计数是分支被执行次数，不等于p或映射实际改变；candidate_tie_current指存在非等价候选与Current同分，不一定最终平局获胜。
所有活动和代理损益都受最终TS选择条件影响，只诊断机制，不能代替BD-rate或宣称无偏Oracle潜力。

## 7. 推荐运行顺序和证伪门槛

1. 全七组先做独立公式/分支隔离/native CABAC/短帧hash检查；必须检查相对R3的实际映射，不仅对Current。
2. 固定的快速内容集合可用 BasketballDrill、BQMall、KristenAndSara，LB，QP22/37，各3帧，全部模式加Current/R3共54项；它同时含原有正负序列，不按新收益挑选。
   三帧只能验证身份/活动。若无活动，预先约定同集合延长到16帧，不换有利内容、不放宽规则；仍无活动则暂停长跑。
3. 首批完整LB CE半帧推荐 **2、4、5**：分别测试guard拒绝出口、对称最大贡献惩罚、稀疏拓扑。
4. 6/7与5组成LU predictor消融；若快速预检证实lu_remap_vs_r3有覆盖，可与首批同一共享队列跑三者，而不是只测均值最像好的那一组。
5. 1/3是诊断控制，预算允许时补齐；1相比2量化无优胜者回退的影响，3验证字面删最低cost是否只是退回R2/偏向identity。
6. 正式Current anchor不重跑；相对R3的BD必须重新积分，不把两种对Current的BD相减。分量先BD后6:1:1，CE七序列、BCE十二序列等权。
7. 先比较各自对R3的均值/中位数/逐序列/分量/四QP及共同高低质量区间；不能只看是否仍优于Current。
   预设B准入：完整CE对Current均值<0、直接对R3均值<0且中位数≤0、去Party平均不劣于R3、无低质量区间一致性退化、有效活动和编解码身份明确。
8. 若只改变p而不改变映射、完整CE零增量、稳定退化、收益仅孤立序列或明显拖累decoder，则降低优先级/否定，不反复调参。
   CE是已多轮开发集，最佳组也须B外部验证；BCE目标−0.05%、不错−0.08%、可观−0.10%保持不变。
9. 只有独立实验完成后才讨论组合；本版没有组合开关。最多两组扩展B，按直接对R3收益和复杂度排序，不新增参数网格。

已执行检查与实际活动数据另见 `TS_Predictor_R6_Validation.md`；本设计不预写BD结果。
