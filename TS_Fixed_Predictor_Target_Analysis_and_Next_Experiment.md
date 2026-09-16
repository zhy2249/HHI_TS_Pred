# 面向 LB BCE −0.05% / −0.08% / −0.10% 目标的分析与后续实验

## 1. 评价目标和总体口径

用户给出的工程门槛：BCE 平均 ≤−0.05% 达到目标，≤−0.08% 为不错，≤−0.10% 为可观。
不能因为收益不足 1% 就认定无工程意义；也不能把达到门槛与已证明普适性混为一谈。

所有 BD-rate 先分别对分量计算，再 `(6 BD_Y + BD_U + BD_V)/8`。
使用已与工作簿 VBA 核对的 PCHIP。负数为收益。

当前 HHI LB B 类为 MarketPlace、RitualDance、Cactus、BasketballDrive、BQTerrace，
**不是**先前短帧方案中的 ParkScene。B 有 5 条，C 有 4 条，E 有 3 条。
按十二序列等权：

`BD_BCE = (5 BD_B + 4 BD_C + 3 BD_E)/12 = (5 BD_B + 7 BD_CE)/12`。

已核查模板 LB-10 的 Overall 为对序列单元格求平均；当前仅 BCE 有效时采用上述口径，
不是三个类别各占 1/3。后续若填入 A 类数据，不能直接把该工作簿的全类别 Overall 当 BCE。
本轮还没有 B 类真实固定 predictor 结果，不能宣称已达到 BCE 目标。

## 2. 三个固定工具需要什么 B 类结果才能达标？

| 固定工具 | 现有 CE | BCE 达到 −0.05% 所需 B | 达到 −0.08% 所需 B | 达到 −0.10% 所需 B |
| --- | ---: | ---: | ---: | ---: |
| NoPred | −0.0567% | ≤−0.0406% | ≤−0.1126% | ≤−0.1606% |
| gradient | +0.0846% | ≤−0.2385% | ≤−0.3105% | ≤−0.3585% |
| directional | −0.0366% | ≤−0.0687% | ≤−0.1407% | ≤−0.1887% |

计算式为 `(12*目标 − 7*现有CE)/5`，不是对 B 的预测。
若 B 完全无收益，NoPred BCE 只剩 −0.0331%，directional 只剩 −0.0214%，均未达目标。
因此现在最直接的问题是补 B，而不是再增加大量 predictor。

## 3. NoPred：值得继续确认，但不能只看 CE 总均值

- CE −0.0567%，按新的工程门槛值得保留；5/7 序列改善。
- C −0.1202%，E +0.0280%，类别差异明显。
- 主要收益：PartyScene −0.3598%、BasketballDrill −0.1665%。
- 主要退化：FourPeople +0.1189%、BQMall +0.0744%。
- 移除任一序列的均值范围为 [−0.0860%, −0.0062%]，仍为负但幅度不稳。
  其中排除 PartyScene 只剩 −0.0062%。这是敏感性诊断，正式集合不删该序列。
- 分量均值 Y/U/V 分别 −0.0502%/−0.0518%/−0.1005%，不是仅凭 V 拉出负均值。
- 按序列重采样的 CI 跨零意味着泛化证据不足，不等于其 −0.0567% 在本集合中没有工程意义。

优先级：**最值得补 B 的固定替换候选**。如果 B ≤−0.0406%，即达到本次十二序列目标；
再另报最差序列与稳定性，不把“达到均值门槛”和“所有内容稳定受益”混为一谈。

## 4. gradient：不是被某一条坏序列单独拖累

- CE +0.0846%；Y/U/V 三个分量平均均退化。
- Johnny +0.5407%、BQMall +0.3016%、FourPeople +0.1676%。
- 只有 PartyScene、RaceHorsesC、KristenAndSara 改善。
- 移除任一序列后均值仍为正：[+0.0086%, +0.1501%]。
- 相对于 NoPred，七序列均值差 +0.1413 个百分点，仅 2/7 序列更好。
- B 必须达到 −0.2385% 才能将 BCE 拉到 −0.05%，当前没有这样的证据。

优先级：**暂停固定 gradient 的完整 B 测试**。不是宣称 B 不可能改善，而是预算优先用于
更接近目标的候选。不要根据这七条序列继续修改梯度公式直到均值转负。

## 5. directional：总体不突出，但 QP 区间的反转值得研究

- 固定工具 CE −0.0366%，4/7 序列改善；比 NoPred 差 0.0201 个百分点。
- Y/U/V 平均 −0.0157%/+0.0498%/−0.2488%，V 对净收益贡献较大。
- 如 KristenAndSara：U +1.8904%、V −0.9183%、Y 约 +0.0019%，最终仍退化 +0.1230%。
- 移除任一序列后均值范围 [−0.0771%, +0.0066%]，可改变符号。

### 5.1 区间积分，而不是同 QP 的裸码率比较

对每个分量保留原四点 PCHIP，用 anchor QP27/32 的质量值将公共积分区间划成三段。
每段分别计算分量 BD-rate，再 6:1:1 加权，最后对七序列平均。
没有用两个点重拟合，也没有将单 QP 码率变化叫作 BD-rate。
端点裁剪在双方公共区间内，各分量区间不同，因此下表三列不能直接等权相加得到总 BD-rate。

| 工具 | QP22–27 对应高质量区间 | QP27–32 区间 | QP32–37 对应低质量区间 |
| --- | ---: | ---: | ---: |
| NoPred | −0.0988%（5/7 改善） | −0.0455%（3/7） | −0.0158%（3/7） |
| gradient | +0.0242%（4/7） | +0.0371%（3/7） | +0.1910%（3/7） |
| directional | **−0.1963%（7/7）** | −0.0439%（4/7） | **+0.1508%（2/7）** |

directional 不是在所有质量区间都接近零，而是明显存在正负抵消。
这比继续增加一个 predictor 公式更值得验证。但区间曲线本身仍由四个点共同决定，
不能据此证明实际局部 QP 小时任意 CG 都应使用 directional。

### 5.2 冻结一个探索性运行级 QP 策略

在观察到区间反转后，只定义一个待验证假设：

`名义编码 QP 为 22/27 时整条运行用 directional；QP 为 32/37 时整条运行用 Current`。

用现有完整编码的 RD 点重新组成四点曲线：低两个 QP 取 directional，
高两个 QP 取 Reference，再分别计算 Y/U/V BD-rate 并加权。
不是把两个区间的 BD-rate 直接相加，也没有混合某个序列内部的帧或系数。

| 序列 | directional 低两档、Current 高两档：探索性 RD 点组合 |
| --- | ---: |
| BasketballDrill | −0.1155% |
| BQMall | −0.0312% |
| PartyScene | −0.2620% |
| RaceHorsesC | −0.0648% |
| FourPeople | −0.1067% |
| Johnny | −0.0759% |
| KristenAndSara | −0.0392% |
| **七序列平均** | **−0.0993%** |

七条均为负，排除 PartyScene 的六条均值仍为 −0.0722%。
旧 cubic 对照为 −0.1081%，PCHIP 仍是主口径，不能改用更好看的 cubic 宣称达到 −0.10%。

同样的 QP 组合用于 NoPred，CE 为 −0.0525%，不优于一直 NoPred 的 −0.0567%，
且 Johnny 退化 +0.2308%。所以没有证据需要给 NoPred 增加这项限制。

**性质必须明确：** −0.0993% 是已编码 RD 点的探索性组合，精确对应“外部配置根据名义 QP
选择整条编码的工具”的离散测试点；不是已经实现并重编码的 decoder-synchronous QP 自适应工具。
该规则是看过 CE 后提出，CE 属于发现集，不是独立确认集。不能调多个切换点后只报告最优值。
阈值解释先固定为低两档/高两档，不对未测 QP 28–31 的表现作插值之外的工具承诺。

其所需 B 类组合结果为：

| BCE 门槛 | B 类探索性组合必须达到 |
| --- | ---: |
| −0.05% | ≤+0.0191% |
| −0.08% | ≤−0.0529% |
| −0.10% | ≤−0.1009% |

若该运行级组合在 B 为 0，BCE 为 −0.0579%。这是一项有吸引力的**条件计算**，
不是对 B 的实际预测，更不是已实现工具的 BD-rate。

### 5.3 名义 QP 不等于 decoder 当前使用的 QP

实际 FourPeople 日志显示：

- 名义 QP22：首帧 slice QP21，后续部分帧 QP28/26。
- 名义 QP27：首帧 slice QP26，后续部分帧 QP35/33。

因此不能直接实现 `sliceQP <= 27`，然后声称复现上述 −0.0993%。
那会改变一条运行内部的启用模式、RDOQ 和参考传播，必须重新编码验证。

若 B 确认此现象，可进入新一阶段的工具启用机制设计：
先明确使用何种 decoder 可知的 QP/序列初始化信息，以及随机访问和 reset 行为，
再为一条明确规则做完整编解码实验。不要在统计脚本中将外部命令行 QP 冒充 decoder 信息。
这属于质量条件下启用工具的研究，不是原来的 CG history selector；不维护 CG 评分历史。

## 6. 暂不从数据中拼接更多“好看”的工具

按每条序列事后选择 Current/三个候选中的最优值，可得到 CE −0.1335%。
但这是使用序列完整结果的后见选择，**不是 CG Oracle，不是 codec 上限，也不是可部署 selector**。
该数值只说明内容差异，不能把序列名称硬编码进模式选择。

类似地，把 NoPred 的 Y 分量 BD-rate 与 directional 的 V 分量 BD-rate 拼接，
不能预测混合工具收益：每个分量 BD-rate 的横轴都使用该次完整编码的总 bitrate，
还包含模式决策和参考重建反馈。若未来测试分量分工，必须作为新工具重新编码，
本轮不据这种代数拼接新增候选。

## 7. 推荐的下一轮实际编码：补 B，两个模式，共 40 个新增任务

候选冻结为 **NoPred、directional**，先不测 gradient，不改 predictor 公式。
B 的五条序列全部纳入；半帧、QP22/27/32/37，额外 2×5×4=40 任务。

同一批数据可回答三件事：

1. 固定 NoPred 能否达到 BCE −0.05% / −0.08% / −0.10%。
2. 固定 directional 的 BCE 表现和 B 类 QP 区间是否也有反转。
3. 已冻结的“低两档 directional、高两档 Current”组合在未用来设计规则的 B 类上是否成立。

为保证完整证伪，不只跑 B 的低两档。高两档数据用于检验反转假设及固定 directional，
不是因为预期退化就不测。B 作为未看结果的内容扩展，仍不是大量随机序列总体。

### 推荐命令：沿用现有目录，自动续跑并生成完整 BCE 表格

```bash
python3 -u scripts/batch_test.py \
  --preset LBeu --class B,C,E \
  --qps 22,27,32,37 \
  --fixed-predictors nopred,directional \
  --encoder build/ts-fixed/bin/EncoderApp \
  --decoder build/ts-fixed/bin/DecoderApp \
  --decode-md5 --no-recon --jobs 10 \
  --input-dir /home/zhy/videos \
  --xlsm-template scripts/JVET-hhi.xlsm \
  --out-dir runs/ts_fixed_LB_CE_half
```

已 dry-run 核对配置及输入路径，计划 96 个任务。保持原二进制/配置/参数不变时，
其中 NoPred 与 directional 已完成的 CE 共 56 个任务会跳过，只新增 B 的 40 个。
**不要加 --overwrite，不加 --full-sequence，不改成新的输出目录。**
虽然目录名称保留 CE，它会扩展为包含 BCE；这避免搬动码流路径导致 fingerprint/续跑失配。
gradient 的既有目录不动，也不新增 gradient 的 B 任务。

所有任务使用现有统一池，无组间等待，不输出重建文件。结束后 nopred/directional 各自
XLSM 会包含 B+C+E 共 48 条 RD 点，Reference 仍来自原模板。
只指定 `--class B` 也能编码，但最后生成的模式表格会只填入 B；上述命令同时汇总旧 CE，
避免把只含 B 的 Test 表格误读成完整 BCE。
根目录总 summary/experiment_plan 会更新为本次两模式 BCE 计划；旧三模式 CE 数值
仍保存在各模式目录及 `analysis_611/` 中。

完成后主固定工具分析命令：

```bash
python3 scripts/ts_fixed_analyze.py \
  --run runs/ts_fixed_LB_CE_half \
  --classes B,C,E --modes nopred,directional \
  --anchor scripts/JVET-hhi.xlsm \
  --out runs/ts_fixed_LB_CE_half/analysis_BCE_611
```

脚本已扩展支持选择类别/候选，缺任意要求的成功任务就停止，不静默给缺样本的 BCE 均值。
低/高 QP 组合另外标记为探索性策略，不覆盖正式 fixed 结果。

## 8. 第二阶段的决定条件

- **NoPred 实测 BCE ≤−0.05%**：按用户门槛达到目标，列为 Promising 候选；同步列出
  最差序列、分量、稳定性，而不是因为 bootstrap 跨零就一票否定工程效果。
- **≤−0.08% / ≤−0.10%**：分别按“不错/可观”报告，仍注明验证集合及历史 anchor 限制。
- **两固定模式均未达标，但 QP 组合在 B 仍成立**：优先设计一个 decoder 可同步的质量条件启用工具，
  重新编码 CE/BCE 验证，不扩大 predictor 公式搜索。
- **QP 组合只在 CE 有效、在 B 失败**：降低该假设优先级，不调切换点来挽救同一批 B 数据。
- **全部未达目标且没有稳定结构性信号**：停止这一轮方向；CG adaptive 也不能靠序列后见最优来背书。

不安排完整 anchor 重跑。由于目标只有 0.05 个百分点，历史 anchor 版本/配置来源应优先核查；
若不能核实，是否增加小规模锚点对齐测试需另行决定，不能把环境差异当 predictor 收益。

## 9. 后续机制统计（仅在需要解释/设计启用规则时）

当前没有新模式的最终 TS coefficient census，以下只是待检验机制，不能当成已有观察。
对当前 remapping，p=0 或 p=1 时均为恒等映射；工具差异主要发生在某分支预测值 ≥2 的场合。
因此平均绝对误差未必对应真实收益。

若 B 结果支持进一步研究，增加不改变决策的在线聚合：
按实际 slice/TU QP、component、W×H、CG 数统计最终 TS 使用量，p=0/1/2/3+ 分布，
Current 与 directional 预测不同/映射不同的次数、最终非零系数和幅值 ≥2 的数量。
只在最终 Writer 记录，不记录临时搜索块，不输出海量系数文本。
需要重新证明开启统计 bit-exact，不把原 legacy observer 的模式编号套到新模式。

这种统计可以检验“高量化下邻域方向证据稀疏/不稳定”等机制；目前的 QP 区间结果
不能独自证明是哪一种机制导致退化。

## 10. 数据文件

新分析脚本：`scripts/ts_fixed_deep_analysis.py`。
结果目录：`runs/ts_fixed_LB_CE_half/target_analysis/`。

- `B_required_targets.csv`：达标所需 B 均值；区分固定模式和诊断组合。
- `quality_bands.csv` / `quality_band_summary.csv`：按原四点曲线分段积分。
- `leave_one_sequence_out.csv`：序列影响诊断。
- `paired_mode_contrasts.csv`：与 NoPred 的相对表现差（不是两模式直接 BD-rate）。
- `qp_policy_diagnostic.csv`：完整 RD 点组合的探索性结果。
- `hindsight_sequence_selection.csv`：明确不可部署的后见选择诊断。
- `target_analysis.json`：定义与结果汇总。

本轮只完成分析、脚本及 dry-run，没有启动任何长时间编码。
