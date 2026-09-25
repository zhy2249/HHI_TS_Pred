# TS predictor revision 2：从空间方向转向离散幅值与 remapping 成本

日期：2026-09-18。**本文保留早期方案，不是当前实现规范，不替换revision1结果。**
R2最终四组实现见 `TS_Predictor_R2_Implementation.md`；不要按本文已被替代的初版公式编码。
更新：加入NoPred和严格消融后的完整规范见 `TS_Predictor_R2_Experiment_Protocol.md`，以该文件为准。
本文保留初版构想；特别是原Current/directional评分主线已调整为Current/NoPred两组评分对照，
modal已改为严格多数，并按可用邻居处理边界，不再要求五邻居全部存在。
正式anchor始终为Current；NoPred仅为候选和辅助对照，所有正式BD-rate与用户目标均相对Current。

## 1. 证据与研究边界

已完整的N1/N2在LB CE分别+0.030428%/+0.043798%；A1/A2补QP22后的微小收益仍依赖PartyScene。
这些结果足以说明现有候选尚未达到工程目标，不能证明anchor必然有很大剩余空间，
也不能在缺少CG trace时认定失败全部来自某个机制。
本轮设计区分三个问题：预测幅值本身、历史成本模型、历史选择器。
不把更复杂当作必然更准确，不新增大量QP阈值或按现有结果屏蔽U分量。

## 2. 从真实 remapping 推导目标

`ContextModelling.h::deriveModCoeff` 对非BDPCM、有效remapping位置定义：

\[
f(a,p)=\begin{cases}0&a=0\\1&a=p>0\\a+1&0<a<p\\a&a>p\end{cases}
\]

p=0与p=1都是identity，编码意义相同。p>=2才可能改变幅值符号。
这不是常规预测残差 a−p；方向平滑或绝对误差小，不保证省码率。
在同一固定成本函数C下，以identity映射（NoPred）作数学参照的局部期望收益为
（此处不是实验anchor或BD-rate基准）：

\[
B(p)=P(a=p)[C(p)-C(1)]-\sum_{1\le a<p}P(a)[C(a+1)-C(a)].
\]

因此应重视“某个离散量化幅值重复出现的证据”和它在remapping后的成本，而不是只选择平滑方向。
此式只对固定C的局部比较成立；真实CABAC概率、bin预算和后续context传播会使完整CG成本更复杂。
特别是实际fractional cost不必随level严格单调，预测过大的成本不能一概称为固定正惩罚。

## 3. R2-1：离散幅值共识 predictor（modal）

因果样本集 T={L,U,D,LL,UU}，全部是已恢复的量化幅值。
仅在五个邻居全部可用（x>=2,y>=2）时使用；否则保持Current。
排除零值后得到T+，它是对“当前非零幅值”分布的简陋局部估计，不用它更改significance语法。

固定规则：

1. T+少于3个样本：Current。
2. 找出现次数最多的幅值v；如果存在唯一众数且次数>=2，取p=v。
3. 众数并列或所有样本不同：Current。
4. v=1可规范化为p=0，两者remapping相同。

不使用QP gate，不引入TU历史。该规则在首个CG也能发挥作用，不受历史冷启动约束。
3个有效样本/至少2次重复是预先固定的最小支持条件，不声称从现有数据估计得出最优值。
主要风险：只有5个空间样本，众数未必代表当前系数；零被排除后的分布也可能有空间偏差。

例：L=8,U=2,D=2,LL=2,UU=3。
Current预测8；原directional的EH=6、EV=7，也预测8；conf2则回退Current=8。
modal看到幅值2重复三次，预测2。它提出了现有方向机制无法表达的新判断，
但这个构造例子不是实际序列收益证据。

## 4. R2-2：局部 remapping 风险最小 predictor（local-risk，主候选）

使用相同的T+、边界及至少3个非零样本限制，使与modal的比较尽量只改变决策准则。
候选幅值为去重后的 `{0, p_Current} ∪ {v in T+: v>=2}`，最多7个。
对每个候选直接计算：

\[
J(p)=\sum_{a\in T^+} C_{TS}(f(a,p)),\quad p^*=\arg\min_p J(p).
\]

平局优先Current，其次NoPred（p=0），再按较小p确定。所有判断使用整数。
该方法不是再增加一个left/min/average公式，而是根据当前局部离散样本，
在保持原remapping的前提下直接选择低成本符号分布。

### 首版 C_TS 的精确定义

复用TSRC level语法结构，假设完整regular三遍路径；每个context bin暂按1单位，
Golomb-Rice/escape bypass长度复用实际 `BitEstimatorBase::encodeRemAbsEP` 的整数长度规则。
不计significance/sign：对于同一个非零样本、同一位置的p比较，它们不直接由p改变。
令r为本TU实际TSRC Rice参数，d为实际dynamic range：

\[
C_{TS}(0)=0,\quad C_{TS}(1)=1,
\]
\[
C_{TS}(t\ge2)=2+\sum_{k=1}^{4}[t\ge2k]
 +[t\ge10]\,L_{Rice}((t-10)>>1,r,d).
\]

两个基础单位为gt1和parity；四个阈值为2/4/6/8。源码cutoff为10、COEF_REMAIN_BIN_REDUCTION为5。
r=1、低幅值下，t=1..11的成本为1,3,3,4,4,5,5,6,6,8,8。
相比旧log2代理，它能区分4/5与6/7，也保留2/3等由同样bin数导致的平局，不人为强行拆分。
**这仍不是实际CABAC fractional rate**：parity的0/1可能不同价，context概率非均匀，
CG预算可能提前耗尽。使用完整路径模型是刻意的固定近似，不能拿其预测收益当结论。
不读取“当前CG最终pass2截止位置”选择当前predictor，那是当前解码时尚不知道的未来信息。

上面的构造样本在r=1时：J(Current=8)=14，J(p=2)=12，J(NoPred)=18，因而选择2。
这只说明准则可解释，真实优劣仍需闭环编码。

R2-2保留NoPred的局部可能性：若命中不足以抵消其它样本被上移的成本，可以选择identity。
它不按原始残差或当前待编码系数作判断，Decoder能在inverse remapping前复现。

## 5. R2-3：只升级历史成本模型（shadow-rate，机制诊断对照）

保持revision1 A2的候选 **Current / 原directional**、CG0 Current、TU-local、K=2和相同符号选择规则。
不同时换成modal或local-risk，以便判断“旧评分太粗”究竟是不是重要限制。
把log2评分替换为两个完整CG的独立TSRC fractional-rate模拟。

### 为什么不能直接声称复用真实 CABAC context 就够了

Writer/Reader在CG开始的真实context虽可获得，但RDOQ传入的估算context/时序未必与最终路径一致；
若用它驱动选择，可能使RDOQ采用的模式与最终语法模式不同。
因此此组明确使用**额外的、TU内重置的虚拟CABAC模型**，不依赖编码搜索context或跨TU状态。

### 确定性虚拟模型

- 初始化：每个component TU，使用codec现有CABAC初始化函数，以clip到合法CABAC范围的CU QP和固定I表
  初始化独立模型。固定I表是实验定义，不跟随encoder-only CABAC table search、temp CABAC cache等状态。
- 虚拟significance历史、TSRC预算在TU内从零/初值开始，邻域与context索引由最终q及decoder-known TU信息推导。
- CG g 完成后，复制同一虚拟起点，两分支分别以Current/directional编码完整CG；
  各自更新概率、regular预算和remainder，得到R_C、R_D，G=R_C−R_D。
- 仅保留Current分支结束后的虚拟状态，作为下一CG共同起点。保留哪条分支固定，不依赖获胜者。
- 用codec原生fractional-bit精度累积历史分数（64-bit整数），K=2；原饱和范围按bit单位等比例换算。
  不提前舍入为整bit；平局、零CG的衰减处理沿用A2，不在此组额外修改。
- 当前CG模式仍然在其开始时由过去S决定；完成后的虚拟评分只能影响下一CG。

这用的是真实codec概率模型与语法，但状态是虚拟初始化/规范历史，**不是实际码流bit数，也不是Oracle**。
它仍只评价本轮最终q，不能模拟两个predictor各自重新RDOQ得到的另一组系数。
该组主要用于检验复杂评分是否有增益，不作为低复杂度最终方案；Decoder双分支估算有明显开销。
若它显著有效，再研究小查找表/整数近似捕获其收益；若无效，不继续堆叠评分复杂度。

## 6. R2-4：有条件才做的组合，不列入首轮必跑

只有R2-2或R2-3有稳定正证据后，才考虑Current / NoPred / local-risk三候选CG选择，
采用R2-3虚拟模型。否则把更多候选与更复杂历史同时引入，只会扩大解释困难和过拟合空间。
“无有效信息CG保持历史而不衰减”也留作独立消融，不与R2-3第一版一起改。

## 7. 首轮实验矩阵与顺序

| 实验 | 改变内容 | 无历史/历史 | 主要对照 |
|---|---|---|---|
| R2-1 modal | 新的离散幅值预测 | 无历史，逐系数 | Current、固定directional |
| R2-2 local-risk | 同一局部样本的remapping成本选择 | 无历史，逐系数 | modal、Current、固定NoPred |
| R2-3 shadow-rate | 仅升级A2的评分模型 | TU内历史，逐CG | 原A2 ewma |

优先实现R2-1/R2-2；R2-3成本较高，作为独立机制验证，不必等待它才能测前两组。
闭环接入TS-RDOQ、Writer、Reader，允许TS选择和q重新变化。保留原revision1结果，不覆写模式身份。
不以旧anchor最终TS样本统计作最终淘汰依据，但可以用最终CG trace诊断实现与代理偏差。
不引入cross-TU history，不增加QP32/34/36等阈值集合，不依据现有U退化直接做U-only关闭。

先完成revision1缺失点及身份核实；新组先短帧正确性，再LB CE四QP半帧与RA CD回归。
每组本轮CE为7×4=28点，RA CD为8×4=32点；三组都运行时共180点。
B类仅在CE证据值得继续后追加；最终BCE仍需12序列等权判断−0.05/−0.08/−0.10%。

## 8. 验证、诊断与失败条件

验证：p=0/1 identity，remap逆映射全范围往返；tie与边界；原生scan因果邻居；整数cost对照
实际bin序列；Rice escape及dynamic range；BDPCM/bypass不改；CG最终清零；DQP与多component；
RDOQ/Writer/Reader模式和虚拟状态一致；宏OFF与Current bit-exact、所有实验解码hash通过。
虚拟模型只维护独立状态，禁止将模拟更新写入真实CABAC。未来实现优先由TypeDef.h宏选实验，
保持环境显式覆盖和新旧宏互斥；不依赖CMake覆盖源码宏。

在线聚合必须区分：可用邻域、有效样本数、众数存在率、p不同、remap实际不同、regular/bypass位置，
以及TU CG数、component、W×H、QP。局部计数是作用范围诊断，不是全编码收益的无偏替代。
对R2-3还应报告评分非零率、切换率、首CG不可适应占比、decoder时间/内存开销；
少量CG比较整数评分与独立完整fractional模拟是否同号，但不根据测试结果迭代挑选最有利权重。

失败条件：新幅值预测未超过Current；local-risk未优于简单modal；shadow-rate未优于原A2；
收益仍集中在单个序列/极少尺寸；RA明显回归；Decoder开销与收益不相称。
如果更贴近TSRC的成本也无收益，应降低该方向优先级，而非继续默认存在−0.1%潜力。
新方案目前是可证伪假设，不授予Promising实测结论；所有RD结论待新闭环实验。
