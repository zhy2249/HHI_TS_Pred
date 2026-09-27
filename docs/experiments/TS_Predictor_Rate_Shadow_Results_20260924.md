# R7（原 TS rate estimator）：shadow 短测结果与下一步

日期：2026-09-24；实现 RATE-20260924-v1。正式 anchor 仍为 Current，R3-1 仅作增量对照。
本轮后续统一命名R7：R7-1=原R2-2新评分，R7-2=原R3-1新评分；本报告数据/旧日志路径不改。
源码推导、同步设计、公式、宏和完整命令见 [研究与实现说明](TS_Predictor_Rate_Estimator_Study.md)。

## 1. 结论先行

**整数 syntaxCost 确实丢失了有用的概率信息，不能认为其排序已经足够准确；但本次更精细评分尚未显示 predictor 的净编码收益。**

- 历史样本 raw winner 分歧 **29.32%**，guard 后实际目标 remapping 分歧 **6.93%**，不是无活动实验。
- 对真实目标的 candidate–Current 代价差，平均绝对误差从 **0.8734 降到 0.5225 bit**，减少 **40.18%**；严格反向排序从 **14.69% 降到 11.13%**。
- 固定旧 R3 最终 q、完整 CG 条件回放：new raw 对 old R3 **增加 0.298707%** TSRC fractional rate；new guard **增加 0.033802%**。
- 单独隔离评分变化，new raw 对 old raw 仍 **增加 0.009067%**，没有证据支持“换精确评分就能救回 R2”。
- 更细概率仍配合错误语法路径时会失效；只完成第一遍 regular 的区域是本轮主要警示。

评级：**代价估计精度有改进证据；算法增量暂为 Weak，BD-rate 未验证**。不增加新 predictor、阈值或分量 guard，不全量重跑历史实验。
这些都是短测/固定 q 结果，不能把其中任何百分数当成用户的 BCE −0.05%/−0.08%/−0.10% BD-rate 指标。

## 2. 样本和复现

预先选定 PartyScene（历史 R3 强收益）、BQMall（近零）、KristenAndSara（明显退化），LB QP22/37，各 3 帧，共 6 项；未按新收益换序列。
它们历史 R3-1 对 Current 的完整 CE 序列 BD 分别为 −0.468990%、+0.018316%、+0.139408%。

此次数据位于：

- `runs/ts_rate_shadow_audit/summary.csv` 及对应 encode/decode 日志：扩展诊断版，6/6 成功。
- `runs/ts_rate_shadow_audit/analysis/`：原聚合计数、分维度统计、完整 CG 条件率、独立 RDOQ 搜索表、SHA256 审计。
- `runs/ts_rate_shadow_parent/summary.csv`：保留的旧 `build/ts-r6` 编码器，同 6 项 R3 对照。
- `runs/ts_rate_build_manifest.json`：观察版构建时源码/二进制哈希及宏；观察版 master=1、SHADOW=1，实际 old R3。
- `runs/ts_rate_shadow_pilot/`：首轮日志保留；扩展版只增加路径/NoPred 拒绝/old raw 诊断字段，不改变模型或实际编码。

```bash
python3 scripts/ts_rate_shadow_analyze.py runs/ts_rate_shadow_audit/summary.csv \
  --reference-summary runs/ts_rate_shadow_parent/summary.csv \
  --out runs/ts_rate_shadow_audit/analysis
```

六个 shadow 码流逐项 SHA256 等于旧 R3；全部解码 MD5 通过。统计不改变编码决策。
六份 encode 日志合计约 **0.649 MiB**，含可选搜索计数，没有逐系数文本或重建视频。

最终 Writer census：**5,614 CG、89,824 位置、8,260 非零系数、20 种实际 W×H**。
主要分歧率分母为 **1,644 个 eligible 位置**：最终非零、真实走 remapping regular 路径、n≥3、非 BDPCM。
未把零系数、纯 bypass、n<3 的无变化样本混入分母；它们仍保留在 census。
统计来自最终已选择 TSRC 的 TU component，不是全部 RDO 搜索，也不包含最终未选择 TS 的反事实区域。

因此存在与前期研究相同的选择限制：q 及 TS 入选均经过旧 R3 的 RD 优化；本次主要识别模型误差，不能替代闭环效果评价。
三序列、每项三帧不足以估计普适 BD 效果；不利用大量相关系数或搜索试探给出虚假的高显著性。

## 3. 排序、平局与 guard

| 指标 | 计数 / 比例 |
|---|---:|
| old/new raw winner 不同 | 482 / 1,644 = 29.3187% |
| guard 后 predictor 不同 | 165 / 1,644 = 10.0365% |
| raw 对真实当前幅值产生不同 remapping | 308 / 1,644 = 18.7348% |
| guard 对真实当前幅值产生不同 remapping | 114 / 1,644 = 6.9343% |
| old/new 接受数 | 90 / 131 |
| old accept → new reject | 59 |
| old reject → new accept | 100 |
| raw winner 相同，但 H 改变 | 147 / 1,162 |
| 上项中 H 改变量 <1 bit / ≥1 bit | 59 / 88 |

**平局不能只报一个大数字**：406 个位置有某个非 Current 候选与 Current 旧分数相等；
38 个位置该类平局被新分数打破并偏向候选（38/406=9.36%）。
但其中有些位置旧 raw 本就选了第三个更好候选；真正“旧 winner 是 Current，新 winner 来自旧 Current 平局”的只有 **18 个**：
占 eligible 的 **1.09%**，占旧 raw Current 1,121 个的 **1.61%**。
故概率平局确实有影响，但**不支持“大量 Current 选择主要是平局偏置”**。

## 4. 模型误差：与完整 CG 干预回放比较

只在评价阶段使用实际当前幅值。对每个 candidate，固定其它位置 predictor 为 old R3，
从同一真实 CG-entry context 回放完整 CG；比较相对 Current 的 CG 率变化。
这包括后续 context、预算和 pass 传播。每个候选独立复制状态，不串联候选状态。

共 **2,560 个 candidate–Current 对**；不是全部 candidate 两两比较，也不是最终量化搜索 winner。

| 评分 | 代价差 MAE（bit） | 严格符号反转 | 代理平局但实际率不同 |
|---|---:|---:|---:|
| 旧整数 syntaxCost | 0.873392 | 376/2,560 = 14.6875% | 320 |
| CG-entry frozen fractional，完整 regular 假设 | 0.522458 | 285/2,560 = 11.1328% | 0 |
| 事后代入实际 anchor cutoff 的诊断 | 0.425652 | 213/2,560 = 8.3203% | 未作为选择器评价 |

严格符号反转不包含代理平局；因此与平局计数一起看。新模型不是每个 pair 都更准，也不是每条序列排序都改善。
对真实当前幅值评估 cost 更准确，**不等于用历史邻域选中的 predictor 更适合当前幅值**。

### 路径分解

| 实际路径 | eligible | 旧 / 新 MAE（bit） | 旧 / 新反向排序 | 事后路径诊断 MAE / 反向排序 |
|---|---:|---:|---:|---:|
| cutoff=10，第二遍完成 | 1,236 | 0.969873 / 0.460391 | 16.3615% / 9.8051% | 0.460391 / 9.8051% |
| cutoff=2，仅第一遍完成 | 408 | 0.684993 / 0.643658 | 11.4187% / **13.7255%** | **0.357818 / 5.4210%** |

后一类占 eligible **24.82%**。新 guard 相对旧 guard 的逐位置完整 CG 干预差累计 +14.436676 bit，
其中 cutoff=2 为 +13.781189 bit，占约 **95.46%**。
这些逐位置干预有重叠，**不能相加当作整码流节省/损失**；只作误差定位，整组收益用下一节独立完整 CG 回放。

重要边界：实际 cutoff 受当前 CG 全部第一遍消耗、候选自身 remapping 和第二遍消耗影响。
Writer 在决定第一遍 predictor 时并不知道所有未来最终 bins；Reader 却在第三遍知道更多。
因此不能把事后 cutoff、剩余预算或即时 getCtx 直接塞入公共 predictor，否则会产生循环依赖或编解码不同步。
这里的 path diagnostic 是首轮后的原因排查，不是新可部署算法，也不是为更好结果调出的新实验组。

## 5. 固定 q 的完整 CG 条件率

下表统一用 `100*(R_new−R_old_R3)/R_old_R3`，**正值为更差**；分析 CSV 的 gain 字段符号相反。
四分支都从相同真实 CG-entry 状态开始，CG 内各自更新 context/预算；下一个 CG 重新从旧 R3 入口开始。
包含所有所观察 CG 的有效语法率，总 old R3 约 44,939.043 fractional bits；不是全码流率。

| 内容 | old raw | new raw | new guard |
|---|---:|---:|---:|
| 全部，按条件率求和 | +0.289614% | +0.298707% | +0.033802% |
| BQMall | — | +0.471679% | +0.032570% |
| PartyScene | — | +0.278969% | +0.044012% |
| KristenAndSara | — | −0.044091% | −0.022280% |

new raw 相对 old raw 为 +0.009067%；new guard 明显比 new raw 接近 old R3。
这更支持“guard 仍可能有独立作用”，不支持现在直接删除 guard；但仍需闭环才能确认。
这些数是条件率总和，不是序列等权 BD 平均，也不使用 6:1:1 对 syntax bits 加权。
绝对 effect size：new raw/new guard 相对 old R3 的完整 CG 累计差约 **+134.236 / +15.190 bit**。
样本短、差值小，不把其符号当作最终方案的确定性否定。

### 其它维度

| 分组 | eligible | raw winner 分歧 | guard 实际 remapping 分歧 | 旧 → 新 MAE（bit） |
|---|---:|---:|---:|---:|
| QP22（输入 QP） | 1,185 | 36.88% | 8.44% | 0.857 → 0.486 |
| QP37（输入 QP） | 459 | 9.80% | 3.05% | 0.945 → 0.681 |
| Y | 1,554 | 27.99% | 6.56% | 0.860 → 0.525 |
| U | 71 | 52.11% | 12.68% | 1.074 → 0.457 |
| V | 19 | 52.63% | 15.79% | 1.437 → 0.541 |
| n=3 | 839 | 25.03% | 3.22% | 0.896 → 0.514 |
| n=4 | 588 | 32.99% | 10.03% | 0.920 → 0.505 |
| n=5 | 217 | 35.94% | 12.90% | 0.747 → 0.569 |

CU QP 单独保存，不能与输入 QP 混淆。Y 的条件率变差，U/V 略好，但色度特别是 V 样本太少，不能据此新增分量开关。
KristenAndSara 的 MAE 降低，但严格排序反转 9.93%→10.64%；n=5 也有类似现象。
实际 W×H 全部保留在 CSV，未只测 8×8；4×4 的新反向排序升高而 8×8 下降，稀有大矩形只有几个 eligible，不能按尺寸挑选“获益规则”。

## 6. R6-2 区域及 NoPred 诊断

old G>0、H≤0 的位置 **433 个**：old raw NoPred 252 个，nonzero predictor 181 个。

| 新选择 | new raw | new guard |
|---|---:|---:|
| Current | 179 | 407 |
| NoPred（非 Current 等价） | 113 | 10 |
| 原 nonzero winner | 127 | 14 |
| 其它 nonzero winner | 14 | 2 |

新 guard 在原 R6-2 区域仍有 **94.00%** 选择 Current；不能认为只要换概率评分就会支持原 R6-2 的 NoPred fallback。

另对“**new raw=NoPred，new H≤0**”的 165 个位置做隔离干预：
绕过 guard 相对 Current，48 个减少率、61 个增加率、56 个率不变，累计干预差 **+38.489014 bit**。
它不是完整新方法率，但没有提供值得再增加第三组算法的正证据。
决定：**本轮不实现/不安排新的 guard-reject → NoPred 组**，保留统计供扩展样本验证。

## 7. RDOQ 探针：确有反馈，不能冒充最终 q 变化

可选搜索探针观察 456,731,520 个位置试探，其中 regular 430,564,988 个。
它们包含最终没被选中的 TU/mode/search，不可与最终 Writer 的 1,644 个 eligible 合并。

- old/new predictor 不同：4,386,026（全部试探的 0.9603%）。
- 额外 up-level 候选导致 candidate set 改变：586,048（0.1283%）。
- 在同一旧搜索状态用原 D+λR 重新比较后，临时最佳 level 不同：67,552（0.01479%）。

这确认 predictor 不只影响最终 Writer rate，也会改变 RDOQ 搜索候选和临时 RD 决策。
但分叉没有继续进入完整搜索、CG 清零、TU 工具竞争，不能说最终 67,552 个系数改变，
也没有从此计算“新 predictor 与最终最优 RDOQ predictor 一致率”。日志中 level-map-to-1 计数只是辅助命中，不是 RD 最优证明。
新模型 RDOQ 私有 context 从原 estimator 输入开始，不保证每次等于最终 Writer context；该残余误差已在实现说明中标明。

## 8. 正确性和交付状态

- 原生 C++ 对 old R3 / new raw / new guard 各验证：262,144 组 neutral-probability 长度、40,000 组旧评分退化等价、160 TU、1,491 CG、23,436 次当前/未来系数污染检查。
- 真 CABAC 编解码 roundtrip；覆盖 Y/U/V、矩形、预算耗尽、Rice 1..8、BDPCM。回放对 native BitEstimator 的 fractional bits、预算及概率内部状态一致。
- shadow 中每个实测 CG 还实时核对 old R3 native estimator 率，全部通过。
- 42 项 AI/LB/RA/no-TS/BDPCM-allowed 等短测全部解码 hash 通过；Current/原 R3/宏关闭对保留程序 bit-exact。
- 两个新模式均在闭环合成短测中产生实际码流差异；这不是自然序列 LB 增益证明。BDPCM-allowed case 改变不代表 BDPCM 分支被修改。
- Python 宏默认/覆盖/互斥/误请求检查 9 项、batch 回归 18 项、shadow 分析 4 项通过。
- TypeDef.h 最终交付 master=1、R7_MODE=0、R7_SHADOW=0，其它模式0，即 Current；两个实验通过 R7_MODE=1/2 或 batch 参数启用。原RATE宏为兼容别名。
- 保留观察版 `build/ts-rate`（SHADOW=1）及宏关闭验证版 `build/ts-rate-off`；交付默认配置另构建 `build/ts-rate-final`。不覆盖旧 `build/ts-r6`。

默认交付版已重新完成上述三模式原生测试和42项smoke，记录在`runs/ts_rate_final_smoke/validation.json`；
构建来源为`runs/ts_rate_final_build_manifest.json`。后续18项短测/56项CE只做了dry-run，未启动长编码。

## 9. 回答本轮十二个问题

1. **主要差异？** 旧 cost 是完整 regular 幅值路径的等概率整数 bin 长度，遗漏实际概率、cutoff 路径及状态/预算传播；Rice 长度本身未发现错误。
2. **为何更准确？** 使用真实 CG-entry 概率的 Q15 fractional bits、原 gt1/parity/gtX context 和原 Rice；实测 MAE 降 40.18%，不是仅提高数字精度。
3. **双方是否可获得？** 可部署模式只用同一 CG 入口冻结 CABAC 表、因果量化邻居和公共语法参数；Writer/Reader roundtrip 已验证。事后 cutoff、完整 q 回放仅诊断，不进入 selector。
4. **winner 分歧？** eligible 中 29.32%；guard 后 predictor 10.04%，实际 remapping 6.93%。
5. **Current tie 打破多少？** 38 个有候选 tie 变优；真正 old Current → 该 tie winner 为 18 个，不能夸大为 406 个。
6. **guard 改变多少？** accept→reject 59，reject→accept 100；同 winner 的 margin 改变 147 个。
7. **旧 R2 退化多少来自错误 ranking？** 不能量化其 BD 归因；概率误差存在，但 new raw 在本次固定 q 回放甚至比 old raw 略差，不支持简单归咎粗 proxy。
8. **新模型下 guard 仍必要？** 条件率明显偏向保留 guard；最终必要性要由 R2-new/R3-new 闭环配对确认。
9. **哪些旧负面机制需重新解释？** 依赖 score 的 raw selector、边界 G/H 和 R6-2 不能被解释成“候选思想无效”；但旧实测 BD 仍成立，新的 scoring 是新工具。
10. **哪些无需重跑？** fixed NoPred/gradient/directional；R6-5/6/7 的新增稀疏固定规则不因评分误差失效。R6-3/4 结构问题不靠换小数自动解决；R4/R5 不机械复跑。
11. **转成闭环 BD 收益了吗？** 尚未验证。当前只有正确性闭环短测和 old R3 shadow，没有 new 模式完整四 QP CTC。
12. **无收益更可能意味着什么？** “旧 proxy 已经足够准确”不符合本次误差证据；已明确的概率/路径错配、历史样本代表性、RDOQ 反馈均可能阻止转化。不能仅凭 shadow 判定最后一个因素占主导。

## 10. 后续执行计划：仅保留两个有解释价值的模式

**优先级调整**：先做同三序列、QP22/37、16 帧的自然内容闭环短测（old R3 对照 + 两个新模式），
核对活动、解码与耗时；不根据这一短测调整阈值/挑序列，不据两点算 BD。
旧 R3 的短帧控制需要重跑是因为帧数不同，**不是重跑已有完整 Current anchor**。

```bash
env -u TS_RATE_SHADOW -u TS_RATE_RDOQ_SHADOW python3 scripts/batch_test.py \
  --preset LBeu --sequences PartyScene,BQMall,KristenAndSara --qps 22,37 --frames 16 \
  --fixed-predictors r3_risk_guard,rate_raw,rate_guard \
  --encoder build/ts-rate-final/bin/EncoderApp --decoder build/ts-rate-final/bin/DecoderApp \
  --jobs 6 --decode-md5 --no-recon --no-xlsm-report \
  --out-dir runs/ts_rate_LB_short16 --dry-run
```

删掉 dry-run 才编码，共18项。若真实活动不足、同步失败或开销无法接受，停止进入 CE；
若活动足够且接受本轮 fixed-q 阴性证据所提示的风险，才运行研究说明中的两组完整 LB CE（56项、半帧），
回答 estimator/guard 的机制问题。**不把完整 CE 描述为已经有收益把握的推广。**

分析必须直接相对 Current 和 old R3 分别积分，各分量先 BD 再 6:1:1；CE七序列等权，BCE十二序列等权。
旧 R2 完整结果作为 raw-selector 增量对照，来源/配置匹配才复用。不同帧数短测不能与完整 anchor 表计算 BD。
最多一个稳定优于 old R3 的模式进入 B；否则保留 R3-1，不继续成本表/guard 参数扫描。

路径感知的公共 selector 暂列研究问题，不仓促实现：须先证明不借助当前/未来 bins、无循环依赖、Writer/Reader 同步，
并在独立样本表明路径成本有用；否则止于诊断。本轮不加入 RD-aware 大模型。
