# TS 固定 predictor：LB、C/E 半帧编码结果

## 结论

按用户指定的 **先分别计算分量 BD-rate，再以 Y:U:V=6:1:1 加权**：

| 方法 | C 类 | E 类 | C/E 七序列等权平均 | 改善序列 |
| --- | ---: | ---: | ---: | ---: |
| NoPred | -0.1202% | +0.0280% | **-0.0567%** | 5/7 |
| 有界梯度 gradient | +0.0092% | +0.1852% | **+0.0846%** | 3/7 |
| 方向一致性 directional | -0.1186% | +0.0727% | **-0.0366%** | 4/7 |

负数表示节省码率，正数表示退化。没有任何候选显示稳定、普遍的优势。
总体评级 **Weak**：NoPred 和 directional 有小幅平均收益，但序列依赖明显；
gradient 在该测试集平均退化，不建议将其作为固定替换继续优先推进。
这不是对所有潜在 predictor 或 CG adaptive 策略的否定。

## 1. 数据完整性

- nopred/gradient/directional 各 28/28，总计 84/84 成功。
- 七序列，QP 22/27/32/37，HHI LBeu / LB-High，按用户确认的 CTC 半帧。
- BasketballDrill/PartyScene 250 帧，RaceHorsesC 150 帧，其余四序列 300 帧。
- 累计核验 22,200 个编码帧的解码 hash；这是三种模式和四个 QP 的重复编码，
  **不是 22,200 个独立内容样本**。
- marker、码流大小、编码日志、解码日志和三组 Excel 的 Test 数值一致；
  三组工作簿 Reference 均与 `scripts/JVET-hhi.xlsm` 一致。
- 从每个任务成功 marker 恢复完整记录，不只读取第三组续跑生成的根目录 summary.csv。
- 不重新编码 anchor，不修改编码器或已有工作簿。

历史 anchor 来自用户提供的 Reference。用户已确认半帧；其完整软件版本、构建和工具配置来源
没有独立运行记录供本次逐项复核。因此下面是相对于该 Reference 的比较，不能声称通过新的
全 CTC Current 重跑排除了所有历史环境差异。此前合成 smoke 的 bit-exact 仅验证实验框架。

## 2. BD-rate 口径与表格公式验证

对每个序列，以同一个总 bitrate 分别构建 Y、U、V 的四点 RD 曲线：

\[
BD_c=100\left(\exp\left[
\frac{\int_{Q_{lo,c}}^{Q_{hi,c}}(\ln R_{test,c}(Q)-\ln R_{anchor,c}(Q))dQ}
{Q_{hi,c}-Q_{lo,c}}
\right]-1\right),\quad c\in\{Y,U,V\}.
\]

每个分量使用其自己的公共 PSNR 区间，不外推，PCHIP 插值。
然后才计算：

\[
\boxed{BD_{YUV}=(6BD_Y+BD_U+BD_V)/8}.
\]

最后对七序列等权平均；C/E 分类也分别按组内序列等权。
**不是**先对 PSNR 进行 6:1:1 加权再计算 BD-rate，也不是对三个分量的 MSE 加权。
先前临时计算的 weighted-PSNR BD-rate 已降为明确命名的 diagnostic，不用于结论。

已只读解压并检查 `xl/vbaProject.bin` 的 Module1：`bdrate` 为 PCHIP，`bdrateOld`
为旧四点三次多项式。表格使用 log10/10^x；Python 主计算使用 ln/exp，数学等价。
另写了表格 VBA 公式的独立 Python 翻译，对本轮曲线交叉验证，最大差异
3.21×10^-13 个百分点。

没有在环境中执行 Excel 宏。工作簿自动公式缓存有 `#VALUE!`，不能直接当作有效结果读取；
本报告根据已核验的原始 RD 点复现表格算法。用户在启用宏的 Excel 中重算应得到相同主结果。

## 3. 序列明细：6:1:1 分量 BD-rate 加权

| 序列 | NoPred | gradient | directional |
| --- | ---: | ---: | ---: |
| BasketballDrill | -0.1665% | +0.0988% | -0.2561% |
| BQMall | +0.0744% | +0.3016% | +0.1212% |
| PartyScene | -0.3598% | -0.3083% | -0.2961% |
| RaceHorsesC | -0.0291% | -0.0554% | -0.0435% |
| FourPeople | +0.1189% | +0.1676% | +0.2060% |
| Johnny | -0.0063% | +0.5407% | -0.1108% |
| KristenAndSara | -0.0287% | -0.1526% | +0.1230% |

PartyScene 三种候选均有收益；BQMall、FourPeople 三种均退化。
这说明内容依赖明显，但不能把序列间不同直接解释为相邻 CG 最优模式可预测。

影响诊断（不从正式集合中删样本）：如果暂时排除 PartyScene，NoPred 的六序列平均只剩
-0.0062%，directional 变为 +0.0066%。因此两者总体小幅正收益对单条序列很敏感。
完整七序列仍是主结果，不用删序列后的结果代替 CTC 平均。

## 4. 分量结果

| 方法 | Y 平均 BD-rate | U 平均 BD-rate | V 平均 BD-rate | 6:1:1 加权 |
| --- | ---: | ---: | ---: | ---: |
| NoPred | -0.0502% | -0.0518% | -0.1005% | -0.0567% |
| gradient | +0.0913% | +0.0955% | +0.0334% | +0.0846% |
| directional | -0.0157% | +0.0498% | -0.2488% | -0.0366% |

directional 的亮度收益比加权总体更小，V 的改善拉低了总体；不能只报告 V 的明显负值。
例如 directional 在 KristenAndSara 的 U 为 +1.8904%，V 为 -0.9183%，Y 约 +0.0019%，
最终加权仍为 +0.1230%。分量差异不能被单一平均数完全代表。

## 5. 稳定性与插值敏感性

以整条序列为重采样单位，固定随机种子，10,000 次 bootstrap 七序列等权均值。

| 方法 | 中位数 | 序列标准差（百分点） | 均值 bootstrap 95% 区间 |
| --- | ---: | ---: | ---: |
| NoPred | -0.0287% | 0.1613 | [-0.1810%, +0.0412%] |
| gradient | +0.0988% | 0.2865 | [-0.1154%, +0.2795%] |
| directional | -0.0435% | 0.1959 | [-0.1719%, +0.0925%] |

三个区间都跨 0。仅七条、且按类别选定的序列，不足以把 bootstrap 解释为广泛内容总体的严格
保证；它主要说明当前均值对序列构成敏感。不能声称“统计证明新 predictor 普遍更好”，
也不能仅凭 gradient 的正均值声称其在所有内容上必然更差。

用旧四点 cubic 作为敏感性检查，七序列加权均值依次为：
NoPred -0.0463%、gradient +0.1087%、directional -0.0346%。
主结果始终采用表格 `bdrate` 的 PCHIP。两种插值下总体方向及排序一致，
但差异量级提醒我们不应过度解释百分之零点几以下的微小均值。

四个 QP 的同 QP bitrate/PSNR 变化保存在 `rd_points_611.csv`，仅用于 RD 点诊断。
相同 QP 的码率下降若伴随质量下降，不能称为该 QP 的压缩收益。
不将单个 QP 点伪称 BD-rate；每个正式 BD-rate 都使用四点。

## 6. 对此前选择偏差问题的回答

本轮让 predictor 实际影响 RDOQ、TS 选择、划分和参考重建，已经不局限于 anchor 最终选 TS 的
固定系数样本。NoPred 在旧固定-q CE 样本上总体增加 TSRC rate，而本轮相对历史 anchor 的
整码流 BD-rate 均值略有改善，说明不能把旧条件样本的候选排序直接当作闭环最终排序。

但两阶段还有配置、帧数和评价指标差异（旧普通 AI/LB 短帧 vs 本轮 HHI LB-High 半帧），
故不能把数值差异全部定量归因于“选择偏差得到纠正”，也不能由此断言新方法真正强。

本轮没有收集新模式最终 TS census，因此不能报告新旧 TS 使用率、具体进入/退出 TS 的块数、
TU 尺寸或 CG history 的变化。不能使用旧 CE census 代替本轮数据。
同理，本轮没有新的 CG Oracle、persistence 或 adaptive capture ratio，不能据此肯定 adaptive。

## 7. 后续建议

1. **NoPred：Weak，保留为低复杂度确认候选。** 当前均值最优，但收益很小，且 E 类平均退化。
2. **gradient：当前固定替换结果 Negative。** 不建议继续优先投入完整 CTC 或为了结果重新调公式；
   该标签是对本次固定候选测试的工程判断，不是统计证明其必然有害。
3. **directional：Weak，低于 NoPred 的优先级。** 没有显示相对于更简单 NoPred 的稳定总体优势；
   某些序列更优并不意味着 TU 内自适应有用。
4. 若要继续，冻结现有候选，优先用此前预定的 B 类补充内容验证 NoPred/directional，
   或先补查历史 anchor 的版本/配置来源。不要继续依据这七条序列搜索最优公式。
5. 是否推进 CG adaptive 仍应由局部 Oracle 与 causal capture 的新证据决定；本轮结果本身不足。

## 8. 输出与复现

- `runs/ts_fixed_LB_CE_half/analysis_611/bd_rate_summary.csv`：主加权 BD-rate、分类及 CI。
- `bd_rate_by_sequence.csv`：每序列分量与加权 BD-rate、各分量积分区间、cubic 对照。
- `rd_points_611.csv`：同 QP 原始 rate 和质量诊断；不是主 BD-rate 汇总。
- `analysis.json`：审计、定义、anchor SHA-256、公式一致性检查及全部结果。

```bash
python3 scripts/ts_fixed_analyze.py \
  --run runs/ts_fixed_LB_CE_half \
  --anchor scripts/JVET-hhi.xlsm \
  --out runs/ts_fixed_LB_CE_half/analysis_611
```

脚本仅用 Python 标准库，不启动编码、不执行宏、不修改已有 XLSM。
