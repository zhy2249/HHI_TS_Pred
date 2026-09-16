# TS Adaptive Predictor：C/E 主实验结果

分析日期：2026-09-11。数据：`runs/ts_CE`。本报告采用用户在编码前确定的 **C/E 为主、B 为辅** 范围；C/E 是7条序列，而非最初设计文档中的5条示例序列。候选、selector、K、confidence阈值、判定门槛均未根据结果调整。

**综合结论：Negative——当前 TU-local、基于过去 CG 候选 rate 的 adaptive selection 不值得进入 TS-RDOQ / CABACWriter / CABACReader 联合修改。**

不同CG确实有不同的反事实最优候选，但这不等于可利用的统计非平稳性已经被证明。Oracle有一定TSRC内部空间；现有历史selector不能有效捕获，而且折算到整体码流后的工程规模很小。不是某个新fixed predictor已胜出：六个候选中，Current仍是这批数据的最佳全局fixed predictor。

本结论限定于固定anchor q、六候选、TU-local历史和本轮短帧C/E数据。它不是所有可能causal算法都无效的数学证明，也不是BD-rate结论。

## 1. 数据完整性与计算口径

| 项目 | 结果 |
|---|---:|
| 序列 | C：BasketballDrill、BQMall、PartyScene、RaceHorsesC；E：FourPeople、Johnny、KristenAndSara |
| 配置 / nominal QP | AI、LB；22、27、32、37 |
| 成功任务 | 56/56；各16帧，TemporalSubsampleRatio=1 |
| 帧编码次数 | 896（含相同内容在不同QP/配置下的重复编码，不是896个独立样本） |
| 解码校验 | 全部任务16个POC hash通过 |
| coded TSRC TU | 60,568 |
| CG | 257,123 |
| coefficient / nonzero coefficient | 4,112,636 / 324,164 |
| 全零CG | 169,744，66.0167% |
| 实际尺寸 | 23种，最小2×2，最大32×32，包含长方形和2样本边长chroma |
| 实际BDPCM CG | 0；本轮不提供BDPCM内容层面的新证据 |

重新运行原分析器到 `runs/ts_CE/review_verified`，不覆盖用户已有的 `analysis`。56个完成marker全部接受；文件大小、TU/CG顺序、Oracle最小值、histogram守恒、五个selector的历史重放均通过。Current CG counterfactual与Current continuous path逐行一致；编码observer中原生完整TU estimator的整数一致性检查亦未触发。重新计算的核心总rate与用户已有分析完全一致。

额外使用 `scripts/ts_pred_ce_audit.py` 核对预期56项组合、实际码流大小、命令、全部解码日志、TU census与CG记录数量，并补充分解和整序列bootstrap。分析阶段没有重新编码，没有改predictor、量化决策或confidence阈值。

**rate口径**：表中的主rate为原生CABAC fractional-bit estimator的完整CG条件成本，每个候选从该CG的anchor context和bin预算出发；`path`让候选的context及预算在TU内持续传播。新TU仍从相同anchor TU-entry state开始。Oracle是条件CG Oracle之和，不是所有连续模式路径的全局最优。所有百分比gain均定义为 `(Current−Method)/Current`，正值节省，负值增加。

## 2. Oracle有空间，但整体工程规模很小

| 指标 | 数值 |
|---|---:|
| Current TSRC估计rate | 1,739,613.459 bit |
| CG Oracle估计rate | 1,711,359.510 bit |
| Oracle节省 | 28,253.950 bit |
| Oracle gain（TSRC分母） | **1.624151%** |
| 56个实际码流总量 | 120,039,648 bit |
| Current TSRC估计rate / 总码流 | **1.449199%** |
| Oracle节省 / 总码流 | **0.023537%** |

最后一项只是固定q的fractional-bit节省量相对实际码流大小的规模参考，不能写成“BD-rate −0.023537%”。但它表明：即使完美选择每个CG的候选，这批数据的整体潜力也很有限。

Oracle不是仅在一条序列上出现：7条序列聚合gain均在1.1858%至1.8845%。7序列等权平均为1.5467%，中位数1.6036%，标准差0.2555个百分点。以整条序列重采样、保留其全部QP/配置/帧依赖的2000次bootstrap，码量加权Oracle gain的95%区间为 **[1.3830%, 1.7693%]**。局部空间确实存在，但不能由此直接推出adaptive可行。

## 3. 所有fixed候选：Current仍是整体最优

| Fixed候选 | 条件CG rate（bit） | 条件gain | TU连续path gain |
|---|---:|---:|---:|
| NoPred | 1,756,343.220 | −0.9617% | −0.9479% |
| Current=max(L,U) | 1,739,613.459 | 0 | 0 |
| Left | 1,748,998.540 | −0.5395% | −0.5683% |
| Above | 1,745,876.812 | −0.3600% | −0.3797% |
| Min | 1,754,314.830 | −0.8451% | −0.8540% |
| Mean | 1,756,085.007 | −0.9469% | −0.9711% |

因此不属于“一个新fixed几乎等于Oracle，可直接替换”的情况。Above是alternative中整体损失最小的一个，仍明显差于Current。Johnny等个别序列上某些fixed有小幅正收益，不能推广为全局替代。

## 4. Causal selectors：没有捕获正的实用收益

| Selector | 条件gain | 捕获率η | TU连续path gain | 条件节省bit |
|---|---:|---:|---:|---:|
| Previous winner | −0.029912% | −1.8417% | −0.037445% | −520.347 |
| Cumulative | −0.038714% | −2.3836% | −0.045858% | −673.473 |
| **Recency，预设主selector** | **−0.038339%** | **−2.3605%** | **−0.045815%** | **−666.945** |
| Confidence | +0.00001194% | +0.0007349% | −0.000631% | +0.208 |
| Simple integer | −0.026086% | −1.6062% | −0.033138% | −453.803 |

Confidence的总条件收益只有约0.21 bit，连续path反而增加约10.97 bit，工程上相当于没有收益。不能把它的正号当作成功，也不能在看到结果后用它替换预设主selector。

Recency在1,856个CG上节省合计2,250.391 bit，在1,605个CG上损失合计2,917.336 bit。虽然有利CG数量更多，但每个有利CG平均节省1.2125 bit，每个不利CG平均损失1.8177 bit，最终净损失666.945 bit。这说明mode命中或胜负次数不能替代rate评价。

### 4.1 分布与显著性

令 `Δ=R_adaptive−R_current`，正值为损失。Recency的CG均值为 **+0.00259388 bit**，标准差0.265883 bit；中位数、p05、p95、p99均为0（分位数使用原分析器的2048样本reservoir）。只有3,461/257,123个CG的条件rate实际变化，整体分布高度集中于0；每TU平均损失0.0110115 bit。

原分析器按`sequence/config/QP/POC`分cluster所得95%区间，对相对Δ为 **[+0.022743%, +0.053587%]**。这种分组仍可能低估相同内容跨QP、配置以及相邻帧的依赖，因此补充整序列bootstrap：

* Recency码量加权gain：95%区间 **[−0.054187%, −0.000316%]**；η区间 **[−3.1482%, −0.0204%]**。
* Recency连续path gain：95%区间 **[−0.065192%, +0.001824%]**，跨0。
* 7序列等权recency mean为 **−0.021984%**，中位数−0.033108%，标准差0.044687个百分点；原分析器的等权序列CI跨0。

不同权重/重采样口径的符号显著性并不完全相同，不据此声称普遍且精确确定的编码损失。共同结论是：**没有接近预设0.5% TSRC gain、η≥50%的实用改善证据**。这里只有7个独立内容，不能用数百万系数夸大泛化置信度。

## 5. 失败机制：不是简单因为只有一个CG

### 5.1 排除首CG不可适应后的结果

| CG范围 | CG数 | Oracle节省bit | 占全部Oracle空间 | Recency η |
|---|---:|---:|---:|---:|
| 每TU的CG0 | 60,568 | 8,532.934 | 30.2009% | 0，预设fallback |
| g≥1，有过去CG的位置 | 196,555 | 19,721.015 | **69.7991%** | **−3.3819%** |

因此不能把η为负仅解释成首CG占用Oracle分母。即使只评价后续CG，选择仍然有害。

### 5.2 “有过去CG”不等于“有可区分候选的历史”

本节为结果后的机制诊断，没有产生新selector或调整阈值。

* 85.6018%的CG六候选成本完全相同；只有37,021个CG（14.3982%）具有候选成本差异。
* 历史非零数的中位数为0，平均约1.963；confidence score margin中位数同样为0。
* 77.7695%的全部Oracle节省出现在“此前还没有任何CG出现候选成本差异”的位置。
* 更直接地，**85.7513%的Oracle节省出现在“此前没有任何alternative严格胜过Current”的位置**；满足这个历史事件的位置只承载14.2487%的Oracle空间，即4,025.823 bit。

对本轮previous/cumulative/recency/confidence的零初始score和Current优先tie-break，如果历史上没有alternative正增益，selector不会离开Current。于是，在这份固定q、条件CG rate数据上，即使在第一次历史正增益之后每次都选到Oracle，这类选择规则也只能捕获约 **14.25%** 的总Oracle空间，对应 **0.23142% TSRC gain**，已经低于预设η≥50%、gain≥0.5%的目标。

这只是针对上述“历史rate尚无正证据便保持Current”的规则族的样本内条件Oracle诊断，**不是所有TU-local causal方法的上限，也不是连续path的全局上限**。在已经有历史正增益的26,629个CG中，recency的η仍为 **−16.57%**；所以既有历史启动太晚的问题，也有启动后选择不可靠的问题。

## 6. Oracle模式连续性：有弱迹象，不能把平局当预测能力

Current属于Oracle并列最优集合的CG占91.8195%；在8.1805%的CG上被严格超过。只有10,327个CG具有唯一Oracle，即4.0164%。不同mode确实各有唯一胜出区域，说明观测到的CG最优并不统一。

| lag | 所有tie-break模式的persistence | 对应独立边缘baseline | 前后均唯一最优的pair数 | 唯一子集persistence | 唯一子集baseline |
|---:|---:|---:|---:|---:|---:|
| 1 | 87.9097% | 87.3972% | 437 | 24.2563% | 19.0387% |
| 2 | 91.3746% | 90.8590% | 308 | 27.5974% | 19.1031% |
| 3 | 92.1861% | 91.9810% | 126 | 17.4603% | 19.2555% |
| 4 | 94.7448% | 94.4874% | 83 | 30.1205% | 18.7545% |

lag1的88%左右表面连续性主要有很高的Current频率/平局背景，不能拿1/6当baseline。唯一子集lag1、lag2存在高于经验baseline的迹象，但pair少、lag3不支持同样方向，并且这些pair本身不是独立样本。

不能宣称“模式完全随机”或“绝对没有连续性”。更准确的判断是：**局部相关迹象没有转化成现有causal selector的正rate收益**。Oracle局部变化也可能部分来自有限CG样本噪声，单靠变化频率不足以证明底层分布随区域变化的统计非平稳性。

完整6×6 transition矩阵（各lag、各分组、all/unique）保存在 `review_verified/ts_pred_transitions.csv`。

## 7. C/E、AI/LB、序列与QP稳定性

### 7.1 主类与配置

| 分组 | Oracle gain | Recency gain | η |
|---|---:|---:|---:|
| C | 1.6528% | −0.0402% | −2.43% |
| E | 1.3409% | −0.0197% | −1.47% |
| C-AI | 1.7570% | −0.0457% | −2.60% |
| C-LB | 1.2404% | −0.0186% | −1.50% |
| E-AI | 1.3685% | −0.0163% | −1.19% |
| E-LB | 1.1398% | −0.0450% | −3.95% |

AI整体Oracle为1.7181%、recency为−0.0427%；LB为1.2347%、−0.0201%。负结论并非仅由C类码量主导掩盖了E类的稳定正收益：两个类及四个class/config组合均无正的recency整体收益。

### 7.2 各序列

| 序列 | Oracle gain | Recency gain | η | Recency path gain |
|---|---:|---:|---:|---:|
| BQMall | 1.8845% | −0.0650% | −3.45% | −0.0784% |
| BasketballDrill | 1.6036% | +0.0096% | +0.60% | +0.0137% |
| FourPeople | 1.5941% | −0.0562% | −3.52% | −0.0638% |
| Johnny | 1.7087% | +0.0625% | +3.66% | +0.0867% |
| KristenAndSara | 1.1858% | −0.0235% | −1.98% | −0.0191% |
| PartyScene | 1.6324% | −0.0483% | −2.96% | −0.0588% |
| RaceHorsesC | 1.2179% | −0.0331% | −2.72% | −0.0477% |

只有2/7条序列聚合recency为正；即便最好的Johnny，η也只有3.66%。56个sequence/config/QP任务中19个recency为正，不能以这些任务替换原实验集合。

### 7.3 各QP

| nominal QP | Oracle gain | Recency gain | η |
|---:|---:|---:|---:|
| 22 | 1.4935% | −0.0159% | −1.07% |
| 27 | 1.6954% | −0.0409% | −2.41% |
| 32 | 1.7131% | −0.0384% | −2.24% |
| 37 | 1.8347% | −0.1222% | −6.66% |

不是简单的高低QP正负反转：四个QP整体都无收益，高QP反而更差。没有依据增加事后QP-specific阈值。

分量方面，Y/Cb/Cr的recency gain分别约−0.0391%、−0.0084%、−0.0287%；intra/inter分别约−0.0466%、−0.0137%。原统计中`other`分组有微小正收益，保留原标签，不将其混入inter。各维度及交叉统计见完整summary。

## 8. 所有实际TU尺寸与CG数

下表不删除零收益或罕见尺寸。小chroma的CG尺寸由codec表决定，因此2×4和4×2在本版各有2个CG，不可统一以WH/16计算。

| W×H | TSRC TU数 | CG/TU | Oracle gain | Recency gain | η |
|---|---:|---:|---:|---:|---:|
| 2×2 | 5 | 1 | 0% | 0% | N/A |
| 2×4 | 28 | 2 | 0% | 0% | N/A |
| 2×8 | 204 | 1 | 1.8396% | 0% | 0% |
| 2×16 | 159 | 2 | 1.2804% | +0.0048% | +0.37% |
| 4×2 | 25 | 2 | 1.3838% | 0% | 0% |
| 4×4 | 9,230 | 1 | 1.2448% | 0% | 0% |
| 4×8 | 12,844 | 2 | 1.6335% | −0.0318% | −1.94% |
| 4×16 | 3,695 | 4 | 1.8751% | −0.1079% | −5.75% |
| 4×32 | 494 | 8 | 1.9890% | −0.0132% | −0.66% |
| 8×2 | 202 | 1 | 1.4500% | 0% | 0% |
| 8×4 | 11,893 | 2 | 1.6144% | −0.0304% | −1.89% |
| 8×8 | 9,379 | 4 | 1.6921% | −0.0492% | −2.91% |
| 8×16 | 3,132 | 8 | 1.7548% | −0.0624% | −3.56% |
| 8×32 | 419 | 16 | 1.3425% | −0.3118% | −23.22% |
| 16×2 | 60 | 2 | 0.8902% | 0% | 0% |
| 16×4 | 2,810 | 4 | 1.8736% | −0.0283% | −1.51% |
| 16×8 | 2,867 | 8 | 1.8369% | +0.0296% | +1.61% |
| 16×16 | 1,646 | 16 | 1.5426% | −0.0741% | −4.80% |
| 16×32 | 326 | 32 | 1.1679% | −0.0691% | −5.92% |
| 32×4 | 276 | 8 | 1.1752% | −0.0870% | −7.40% |
| 32×8 | 263 | 16 | 1.0512% | −0.0889% | −8.46% |
| 32×16 | 219 | 32 | 0.9383% | −0.0252% | −2.68% |
| 32×32 | 392 | 64 | 1.0989% | +0.0149% | +1.36% |

9,641个TU只有1个CG，占TU的15.92%，它们的adaptive必定为Current。按CG/TU=2、4、8、16、32、64分组，recency gain依次约为−0.0309%、−0.0588%、−0.0199%、−0.1145%、−0.0508%、+0.0149%。**增大TU或历史CG数量没有带来稳定提升。**

16×8、32×32有小幅正值，但η仅约1%–2%；这两种尺寸并非按coefficient占比都可以忽略，所以不把负结论简单归因于“所有正收益只在极罕见尺寸”。真正的问题是正收益本身很弱，且最常见的4×8、8×4、8×8均无收益。不要据此事后定制shape-specific开关。

## 9. 预测误差、remapping与NoPred

下表hit/under/over条件为a>0；MAE和mapped-level-1概率的分母为全部coefficient。边界外邻居为0；BDPCM/bypass-only保持原生禁用逻辑。

| Predictor | nonzero hit | nonzero under | nonzero over | 全系数MAE | P(actual modified=1) | fixed gain |
|---|---:|---:|---:|---:|---:|---:|
| NoPred | 0% | 100% | 0% | 0.15500 | 4.5081% | −0.9617% |
| Current | 30.74% | 52.97% | 16.29% | 0.16997 | 4.5352% | 0 |
| Left | 18.69% | 72.21% | 9.10% | 0.15664 | 4.5355% | −0.5395% |
| Above | 19.21% | 71.88% | 8.90% | 0.15241 | 4.5540% | −0.3600% |
| Min | 7.16% | 91.13% | 1.71% | 0.13908 | 4.5547% | −0.8451% |
| Mean | 12.89% | 81.79% | 5.32% | 0.13818 | 4.4945% | −0.9469% |

Current的MAE反而最高，Mean的MAE明显更低，实际fixed rate却更差。Min/Above的P(modified=1)也略高于Current，但不构成净rate优势。因此本实验直接验证了“不能只看预测误差或mapped-level-1概率”的必要性。

全部候选的P(modified=0)均为92.1179%，由固定q决定。Current的modified分桶0/1/2/3–4/5–9/≥10分别为92.1179%、4.5352%、1.8238%、1.0176%、0.4227%、0.0828%；完整候选分布和hit/under/over归属rate在summary中保留。

NoPred在17,855个CG（6.9441%）上严格优于Current，其中1,382个CG是唯一Oracle；局部优势是真实存在的。其有利CG合计节省20,099.036 bit，不利CG合计增加36,828.797 bit，净增加16,729.761 bit。因此NoPred不能直接固定替换Current。

映射不对称性仍是解释基础：命中可把a映射为1，0<a<p时增1，p<a时幅值保持。rate归属还受三pass预算、context传播和parity/Rice阈值影响，不能把表中按误差类别归属的rate当作独立coefficient的因果贡献。

## 10. 简单整数score与confidence

Simple与recency的mode agreement为94.5929%，看似很高；但当至少一者选择非Current时，agreement降为 **55.4848%**。整体高agreement主要来自共同fallback，不能解释为简单score已经捕获Oracle潜力。

Simple相对recency少损失约213.142 bit，但自身gain仍为−0.026086%、η为−1.6062%。更准确的结论是两者都未成功，而不是复杂CABAC selector成功后被廉价近似保留了收益。

Confidence只在1,494个CG选择alternative，其中270个CG实际改变条件rate。全体score margin中位数0，p95约0.177 bit、p99约1.745 bit（reservoir近似）；历史nonzero中位数0，p95为10。

既有36组confidence探索网格聚合后的gain范围为 **[−0.035156%, +0.000712%]**，中位数约−0.000356%。即便报告网格中最高的样本内值，也仅节省约12.4 bit，远低于预设工程门槛。最高值是多次比较后的描述，**不是独立验证结果，也没有据此选定新阈值**。继续扫更多阈值没有当前数据支持的优先级。

## 11. 对证伪条件与Q1–Q10的明确回答

预设失败条件中，最明确触发的是 **Failure4（causal捕获率极低/为负）**；Failure1的“TSRC内部Oracle<1%”分支没有触发，但整体码流规模极小的工程顾虑存在。不能把未触发的条件凑成负结论：Oracle并非仅一个序列有效，某个fixed也没有基本等于Oracle，四个QP并未发生正负反转；连续path对主结论提供了同方向支持，不能把失败随意归因于context模拟偏差。

| 问题 | CE回答 |
|---|---|
| Q1 Current是否明显非最优？ | CG oracle可比它低1.6242%，有局部空间；但它仍是六候选中最佳整体fixed，不能称为已找到明显更好的固定替代。 |
| Q2 有没有新fixed可直接替换？ | 没有。五个alternative整体均增加rate。 |
| Q3 不同CG最佳是否不同？ | 是，存在各候选唯一胜出CG；但95.98%有并列，有限样本变化不等于已证明底层非平稳性。 |
| Q4 是否有历史连续性？ | 有弱迹象；表面高persistence主要有平局/模式频率背景，unique pair少且lag表现不一致。 |
| Q5 历史CG能否预测当前最佳？ | 本轮五selector未给出有实用rate收益的证据；历史正证据常出现太晚，启动后也未可靠选择。不是所有causal方法不可能的证明。 |
| Q6 捕获多少Oracle潜力？ | 主recency η=−2.3605%；排除CG0后仍为−3.3819%。Confidence约0，simple为负。 |
| Q7 尺寸是否一致？ | 多数常见尺寸无收益；少数尺寸小正值不能构成稳定可推广方案。 |
| Q8 小尺寸是否天然不适合？ | 单CG TU结构上没有history；但多CG、大TU也未成功，不能只归因于尺寸小。 |
| Q9 NoPred有无局部优势？ | 有，6.9441%的CG严格优于Current；fixed总体反而损失0.9617%。 |
| Q10 是否进入真实联合修改？ | **Negative：当前证据不支持。** 保留Current，不推进新的TS-RDOQ/writer/reader工具。 |

RDOQ feedback仍未消除：q来自Current的rate model，换predictor后重优化的q'可能改变结果。此限制既不能把本轮Oracle直接转成BD-rate，也不能作为无正证据时继续大规模集成的理由。总体收益太小、捕获失败、跨配置/类均无收益，已经足以降低本方向优先级。

## 12. 下一步与复现文件

本轮不再增加候选、调threshold或改正式codec。B类如果已经产生结果，可作为冻结当前方法的外部补充验证；如果还没运行，不必为了期待正结果扩大编码矩阵。B的局部好结果也不能覆盖C/E主实验的负结果。跨TU history或其它当前decoder已知特征属于新实验假设，需要单独预注册，不在本轮自动实现。

输出：

* 本报告：`TS_Adaptive_Predictor_CE_Results.md`。
* 完整重算：`runs/ts_CE/review_verified/ts_pred_summary.csv`、`ts_pred_transitions.csv`、`ts_pred_sequence_stability.csv`、`ts_pred_confidence_exploratory.csv`等。
* 独立核查/机制分解：`runs/ts_CE/ce_audit/ce_audit.json`、`ce_decomposition.csv`、`ce_jobs.csv`。
* 可复用核查脚本：`scripts/ts_pred_ce_audit.py`。它验证冻结的56项CE任务并计算whole-sequence bootstrap，不拟合selector。

复现（不重新编码）：

```bash
python3 scripts/ts_pred_analyze.py runs/ts_CE/stats \
  --out runs/ts_CE/review_verified --bootstrap 500
python3 scripts/ts_pred_ce_audit.py \
  --run runs/ts_CE --out runs/ts_CE/ce_audit
```

用户原始码流、统计CSV和既有`analysis`保留。本次只有新增核查脚本、结果文件和本报告，没有修改编码器统计实现或正式编码算法。
