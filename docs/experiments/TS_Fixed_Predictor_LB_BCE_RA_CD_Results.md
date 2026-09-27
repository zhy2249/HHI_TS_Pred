# TS fixed predictor：LB BCE / RA CD 外部编码结果

日期：2026-09-16。负值为收益。主指标为各分量独立 PCHIP BD-rate 后
`(6*BD_Y + BD_U + BD_V)/8`，序列等权；BCE 为 12 序列、CD 为 8 序列，不能先对 class 等权。

## 1. 数据与审计范围

读取 `runs/ts_fixed_LB_CE_half/{nopred,gradient,directional}/JVET-hhi.xlsm`，
不是未更新的 `scripts/JVET-hhi.xlsm` 的 Test，也不是旁边的 `E.xlsm`。
NoPred/directional 各有 LB BCE 48 点及 RA CD 32 点；gradient 有 LB CE 28 点及 RA CD 32 点。
总共 220 点，新增 LB B 40 点和 RA CD 96 点。QP 均为 22/27/32/37。

已验证三个工作簿的 Reference 数值及状态与原 anchor 一致；目标序列无缺点、无重复、
四点码率和各分量质量严格单调、有共同积分区间，状态均为 pass。
独立 VBA 算法数值复核最大差为 3.21e-13 个百分点；没有运行 Excel 宏。
SHA256 及完整数据来源保存在 `external_analysis_611/audit.json`。

**外部编码限制**：无法凭表格 pass 验证实际源码版本、模式环境变量、二进制、输入、
配置、帧数或解码 hash。LB 半帧是既定要求，但本轮没有外部日志独立确认；RA 实际帧数也尚未确认。
以下是表格数值层面的结果，不能声称完成本地编码级审计。
没有利用外部运行时间推断编码复杂度，因为机器条件未核实。

## 2. 固定 predictor 主结果

| 模式 | LB B | LB C | LB E | LB BCE | RA C | RA D | RA CD |
|---|---:|---:|---:|---:|---:|---:|---:|
| NoPred | −0.020685% | −0.120237% | +0.027972% | **−0.041705%** | +0.009698% | −0.026326% | **−0.008314%** |
| gradient | 未测试 | +0.009162% | +0.185242% | 不可计算 | +0.035531% | +0.045953% | **+0.040742%** |
| directional | −0.034429% | −0.118621% | +0.072720% | **−0.035706%** | +0.010504% | −0.004156% | **+0.003174%** |

固定 NoPred 距 −0.05% 目标仍差 0.008295 个百分点；directional 差 0.014294 个百分点。
不能把 CE 的 −0.056719% 当作 NoPred 的 BCE 结果。gradient 不值得补 B 来凑完整表格。

| LB B 序列 | NoPred | directional | 预先提出的低 QP 组合 |
|---|---:|---:|---:|
| MarketPlace | +0.084365% | +0.012615% | −0.004862% |
| RitualDance | −0.021184% | +0.051803% | −0.017082% |
| Cactus | −0.228968% | −0.306319% | −0.178582% |
| BasketballDrive | +0.096056% | −0.023430% | +0.044212% |
| BQTerrace | −0.033692% | +0.093184% | +0.008477% |

B 收益集中在 Cactus。去除它后，B 平均 NoPred 约 +0.0314%，directional 约 +0.0335%；
不能据 B 平均略负推断多数 1080p 内容受益。

| RA 序列 | NoPred | gradient | directional |
|---|---:|---:|---:|
| BasketballDrill | +0.010682% | −0.014504% | +0.036367% |
| BQMall | +0.006732% | −0.012558% | −0.016839% |
| PartyScene | −0.014173% | +0.092007% | +0.020346% |
| RaceHorsesC | +0.035552% | +0.077180% | +0.002141% |
| BasketballPass | +0.120201% | +0.129099% | +0.186497% |
| BQSquare | −0.215850% | −0.119552% | −0.251193% |
| BlowingBubbles | −0.013002% | +0.108599% | +0.001475% |
| RaceHorses | +0.003349% | +0.065665% | +0.046596% |

RA NoPred 去除 BQSquare 后 CD 平均变为 +0.021334%；directional 为 +0.039512%。
PartyScene 的 LB 收益没有在 RA 复现，说明不能仅靠序列内容标签推广固定模式。
这不直接证明 CG 历史是否可预测，当前数据没有 CG 状态。

## 3. 不确定性、分量与工程效果

| 集合/模式 | 改善序列 | 序列 bootstrap 95% CI |
|---|---:|---:|
| LB BCE NoPred | 8/12 | [−0.122048%, +0.031354%] |
| LB BCE directional | 6/12 | [−0.131893%, +0.056414%] |
| RA CD NoPred | 3/8 | [−0.077868%, +0.045337%] |
| RA CD gradient | 3/8 | [−0.016641%, +0.089285%] |
| RA CD directional | 2/8 | [−0.083191%, +0.075456%] |

10000 次序列重采样，固定 seed 20260916。CI 只描述该小规模内容集合的不确定性，
不是重复编码噪声；序列集合也不是随机抽样的全部视频总体。均值、中位数、标准差、
P10/P90、最差/最好和 leave-one-out 全部输出在 summary.csv。

LB BCE NoPred 的 Y/U/V 为 −0.038448/−0.011652/−0.091298%；
directional 为 −0.013576/−0.010517/−0.193674%。后者收益较依赖 V 分量。
RA CD NoPred 的 Y 为 +0.009705%，整体微小收益主要来自 U 的 −0.126855%；
不宜宣称亮度编码得到改善。
三次多项式敏感性结果 LB BCE NoPred −0.038134%、directional −0.037107%，仍均未达到目标。

## 4. 冻结的低 QP directional 组合复核

规则早于本次 B 结果提出：每个序列 QP22/27 使用 directional 的完整运行结果，
QP32/37 使用 anchor；重新构造四点曲线后计算分量 BD-rate。
本次没有调整阈值、逐序列挑选或把 NoPred 混入组合。

| 集合 | 加权 BD-rate | 改善数 |
|---|---:|---:|
| B（后续验证集合） | −0.029567% | 3/5 |
| CE（规则发现集合） | −0.099323% | 7/7 |
| BCE | **−0.070258%** | **10/12** |

BCE 达到 −0.05% 目标，未达到 −0.08%“不错”及 −0.10%“可观”门槛。
B 本身 CI [−0.108870%, +0.022139%]，推广证据有限；且组合 B 平均不如固定 directional 的 B 平均。
BCE CI [−0.118761%, −0.026970%]；逐一去除任一序列后均值范围
[−0.080665%, −0.052826%]，比固定模式的集中收益更稳健。
但 BCE 含用于发现规则的 CE，因此不能将其 CI 当作完全独立确认。
三次多项式结果 −0.073834%，结论方向一致。

**这不是已实现的 slice/TU QP 条件工具**。nominal QP 与解码器看到的 slice/TU QP 不同；
直接把规则改成 `sliceQP <= 27` 不会重现此数据。
混合已有四点也不提供 QP 过渡区的新测量，仍有曲线插值依赖。
不把它称为 CG 自适应效果，也不计算 CG Oracle capture ratio。

## 5. 判断与下一步

- 固定 NoPred：**Weak**。LB 接近目标但未达标，RA 近零且依赖少数序列；保留对照，不宜直接全局替换。
- 固定 directional：**Weak**。BCE 不如 NoPred，RA 无平均收益；不建议继续无条件扩跑 RA B。
- 固定 gradient：**Negative**。LB CE 和 RA CD 都退化，降低优先级，不补 LB B。
- 低 QP directional：**Promising（有限、条件性）**。值得一次预注册的真实条件启用实验，尚不是工具成功。

下一阶段先取得外部任务配置、源码 commit/模式和帧数信息，排除 anchor 不一致。
然后仅实现一套 decoder 可复现的条件规则，明确 slice/TU QP 语义、初始化与边界，
在跑编码之前冻结阈值及候选数量；不能用本轮 BCE 反复调阈值追 −0.08%。
先做 Current/OFF 一致性、条件两端和解码 hash smoke，再跑 LB BCE 半帧四 QP，RA CD 用于回归检查。
可额外预留未用于定规则的序列/中间 QP 验证稳定性。此报告没有擅自实现新的编码规则或启动长跑。

当前数据不能回答 CG 历史可预测性、各 TU size 效果或因果 selector 捕获率；
“固定模式有配置/QP差异”不等于“历史 CG 可以选对模式”。

## 6. 复现

```bash
python3 scripts/ts_fixed_workbook_analysis.py \
  --run runs/ts_fixed_LB_CE_half \
  --anchor scripts/JVET-hhi.xlsm \
  --out runs/ts_fixed_LB_CE_half/external_analysis_611
```

输出 `rd_points.csv`、`by_sequence.csv`、`summary.csv`、`audit.json`。
只读输入工作簿，不重新编码，不覆盖历史 analysis_611 或原有工作簿。
