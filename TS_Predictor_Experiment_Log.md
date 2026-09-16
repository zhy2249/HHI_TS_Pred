# TS predictor 实验记录

最后更新：2026-09-13（本次会话核验）。这是本项目 TS predictor 研究的统一实验台账；
后续实验在本文件追加和更新，不另建互相冲突的总记录。

## 1. 已确定的目标与评价口径

- 工程目标：**LB、BCE 平均 BD-rate ≤−0.05% 为达标，≤−0.08% 为不错，≤−0.10% 为可观**。
- 每条序列先分别计算 Y/U/V BD-rate，再计算 `(6 BD_Y + BD_U + BD_V)/8`。
- 使用工作簿 `bdrate` 对应的 PCHIP，公共质量区间积分，不外推；负数为改善。
- BCE 按十二序列等权：`(5*BD_B + 4*BD_C + 3*BD_E)/12`，不是类别等权。
- LB CTC **采用 HHI INI 半帧**，用户已确认；正式命令不使用 `--full-sequence`。
- 当前固定工具的 anchor 使用 `scripts/JVET-hhi.xlsm` 的 Reference，不安排完整 anchor 重跑。
- 长时间正式编码由用户执行；分析、验证、计划和结果必须明确区分。
- 不预设正结果；不删除退化序列，不根据验证集结果反复调整公式或阈值。

当前分析使用的 anchor 工作簿 SHA-256：
`3e5dda606666fe38dd37b5597e6ec9cf69a25d5d91e4ec11488fec786d1423f1`。
历史 anchor 完整软件/构建/配置来源未独立复核；半帧已确认不代表全部 provenance 已确认。

## 2. 实验总览

| ID | 实验 | 状态 | 主要结果 / 下一步 |
| --- | --- | --- | --- |
| TS-001 | 固定 anchor 系数的 CE 短帧 counterfactual | 已完成、已分析 | Oracle 有条件潜力，所测 TU-local causal selector 未捕获稳定收益 |
| TS-002 | 新固定 predictor 闭环编解码验证 | 已完成 | 42 个 smoke 任务通过，Current/OFF 与原版 bit-exact |
| TS-003 | LB C/E 半帧，三固定 predictor | 已完成、已分析 | NoPred −0.0567%；gradient +0.0846%；directional −0.0366% |
| TS-004 | 面向 BCE 目标的深入分析 / QP 组合诊断 | 已完成分析，非新编码 | directional 低两档 + Current 高两档的 CE RD 点组合 −0.0993% |
| TS-005 | 补 B：固定 NoPred 和 directional | 已设计、已 dry-run，尚无完成结果 | 计划新增 40 个编码任务，补齐两个模式 BCE |
| TS-006 | decoder 可同步的质量条件启用工具 | 条件性设想，未实现、未启动 | 仅在 B 支持 QP 现象后决定 |

最新只读检查：nopred/gradient/directional 各有 28 个成功 marker，B 类成功 marker 均为 0。
没有以此推断用户机器上一定没有正在运行的任务；这里只记录当前已落盘的完成证据。

## 3. TS-001：固定系数的反事实统计

### 配置和方法

- CE 七序列，普通 `--local-preset AI/LB`，QP22/27/32/37，每任务 16 连续帧，共 56 任务。
- 宏 `JVET_BJUT_TS_PRED_ANALYSIS`，在真实 Writer 记录最终选择 TSRC 的非零 TU component。
- 不记录临时搜索候选；整 TU CBF=0 不进入该统计，非零 TU 内的全零 CG 进入。
- 固定最终 anchor q，CG 条件 CABAC 仿真及 TU 连续路径仿真；不改变实际决策或码流。
- 旧候选：M0 NoPred、M1 Current=max、M2 Left、M3 Above、M4 Min、M5 Mean。
- selector：Previous Winner、Cumulative、Recency、Confidence、Simple；历史仅 TU 内保持。

### 结果与限定

- 56/56 完成；60,568 个 TSRC component TU，257,123 个 CG，23 种观察到的 TU 尺寸。
- 条件 CG Oracle 节省约 **1.6242% TSRC rate**，不是整码流 BD-rate。
- Recency 条件 gain 约 **−0.03834% TSRC rate**，capture ratio 约 **−2.36%**。
- 各种 alternative fixed 在该固定-q 条件样本上总体不优于 Current。
- 85.60% CG 的六候选 rate 全部相同，非平凡历史信息稀少。

结论：**该条件样本上的所测 causal selector 为 Negative**，不能据此否定所有真实 predictor 工具。
重要限制有两层：q 已经由 Current rate model 优化；最终 TS 入选本身也受 Current RD cost 影响。
该选择偏差不能仅靠 bootstrap 消除。由此进入真实闭环实验 TS-003。

资料：[原始设计](TS_Adaptive_Predictor_Experiment_Design.md)、
[CE 统计报告](TS_Adaptive_Predictor_CE_Results.md)。
数据：`runs/ts_CE/stats/`、`review_verified/`、`ce_audit/`。

## 4. TS-002：新工具的正确性验证

真实实验宏 `JVET_BJUT_TS_FIXED_PREDICTOR` 与旧分析宏互斥。
统一实验 Encoder/Decoder，通过每进程 `TS_FIXED_PREDICTOR` 选择工具，匹配解码器必需。

| 参数名 | 定义 | 边界 |
| --- | --- | --- |
| current | `max(L,U)` | 缺失邻居为 0 |
| nopred | `p=0`，identity remapping，其他 TSRC 语法不变 | 无额外边界 |
| gradient | `clip(L+U-D,min(L,U),max(L,U))` | 第一行/列用 Current |
| directional | `EH=abs(L-LL)+abs(U-D)`；`EV=abs(U-UU)+abs(L-D)`；EH<EV 取 L，反之取 U，相等取 Current | x<2 或 y<2 用 Current |

L/U/D/LL/UU 分别为左、上、左上、左二、上二的量化系数幅值。
**新 gradient/directional 与旧 M2/M3 不是同一候选，禁止按数字编号混合结果。**

验证：

- TS-RDOQ 候选、CABAC estimator/Writer、Reader 反映射使用一致 predictor。
- AI、LB、LB-High、BDPCM、lossless、TSRC-off、TS-off 七种 case；六个版本/模式共 42 任务。
- 全部 hash 解码通过；Current、宏 OFF 在各 case 与 untouched 原版 bit-exact。
- TSRC-off/TS-off 时三 alternative 与 Current bit-exact；活动 TS case 验证 alternative 确实生效。
- 原生 scan 的 64 个完整形状、1,267,924 个邻居先后检查通过；该形状集包含 TS 尺寸但不全是合法 TS 尺寸。
- 无重建视频输出；synthetic_input.yuv 仅为 smoke 输入。

资料：[真实编码设计](TS_Fixed_Predictor_Coding_Experiment.md)。
证据：`runs/ts_fixed_smoke/validation.json`、`runs/ts_fixed_batch_smoke/`。

## 5. TS-003：LB C/E 半帧真实固定工具实验

### 配置

- HHI `--preset LBeu`，实际为 `encoder_lowdelay_nx2High.cfg`，不同于 TS-001 普通 LB。
- QP22/27/32/37，nopred/gradient/directional 三模式，共 84 任务。
- BasketballDrill、PartyScene 250 帧；RaceHorsesC 150 帧；
  BQMall、FourPeople、Johnny、KristenAndSara 各 300 帧。
- 完整重编码，允许量化、TS 选择、预测/划分、参考重建自然变化。
- 不输出重建视频；保存码流并逐帧核对 hash；原脚本统一任务池、不同组无 barrier。

### 完整性和中断恢复

- 初次检查：nopred 28/28、gradient 28/28、directional 22/28。
- 已恢复前两组 Excel/CSV，Reference 不变。
- directional 剩余 PartyScene/FourPeople/Johnny QP22，KristenAndSara QP22/27/32，后续均完成。
- 最终 **84/84 成功、22,200 个编码帧 hash 核验通过**。
- 根目录 summary/plan 曾因只续跑 directional 而只包含该组；完整分析使用所有模式成功 marker，
  不依赖根目录汇总代表全部任务。

### 主结果（各分量 BD-rate 后 6:1:1 加权）

| 模式 | C | E | CE 七序列均值 | 改善数 | 七序列均值 bootstrap 95% 区间 |
| --- | ---: | ---: | ---: | ---: | ---: |
| nopred | −0.1202% | +0.0280% | **−0.0567%** | 5/7 | [−0.1810%, +0.0412%] |
| gradient | +0.0092% | +0.1852% | **+0.0846%** | 3/7 | [−0.1154%, +0.2795%] |
| directional | −0.1186% | +0.0727% | **−0.0366%** | 4/7 | [−0.1719%, +0.0925%] |

NoPred 固定替换优先补 B；gradient 暂停；directional 总体较弱但保留 QP 结构线索。
CI 跨零代表泛化不确定，不等于低于 0.1% 的收益自动没有工程意义。
没有新模式最终 TS census，不能报告 TS 使用率/CG 数变化，也没有新的 CG capture ratio。

数据：`runs/ts_fixed_LB_CE_half/{nopred,gradient,directional}/`。
报告：[LB CE 结果](TS_Fixed_Predictor_LB_CE_Results.md)。
复现：`python3 scripts/ts_fixed_analyze.py`。
主结果 CSV：`runs/ts_fixed_LB_CE_half/analysis_611/bd_rate_summary.csv`。

## 6. TS-004：目标与 QP 结构分析（非新编码）

### 固定候选达到 BCE 门槛所需的 B 类均值

| 模式 | BCE ≤−0.05% | BCE ≤−0.08% | BCE ≤−0.10% |
| --- | ---: | ---: | ---: |
| nopred | B ≤−0.0406% | B ≤−0.1126% | B ≤−0.1606% |
| gradient | B ≤−0.2385% | B ≤−0.3105% | B ≤−0.3585% |
| directional | B ≤−0.0687% | B ≤−0.1407% | B ≤−0.1887% |

这是条件计算，不是 B 类实测或预测。

### directional 的主要线索

原四点 PCHIP 曲线分段积分后，directional 在 QP22–27 对应区间平均 −0.1963%，
QP27–32 区间 −0.0439%，QP32–37 区间 +0.1508%，存在正负抵消。

冻结的探索性组合：名义 QP22/27 取整次 directional 编码点，QP32/37 取 Current anchor 点，
重新计算四点 BD-rate。CE **−0.0993%**，7/7 序列为负；排除 PartyScene 后仍为 −0.0722%。
同样的 NoPred 组合仅 −0.0525%，不优于全 QP NoPred，不继续增加这条规则。

**−0.0993% 是运行级 RD 点组合，不是已实现的 decoder-synchronous QP 自适应工具结果。**
规则看过 CE 后提出，CE 是发现集；不能据此宣称独立验证成功。
名义 QP 与实际 slice/TU QP 不同，不能直接实现 `sliceQP<=27` 并声称等价。

资料：[目标分析与下一轮设计](TS_Fixed_Predictor_Target_Analysis_and_Next_Experiment.md)。
复现：`python3 scripts/ts_fixed_deep_analysis.py`。
数据：`runs/ts_fixed_LB_CE_half/target_analysis/`。

## 7. TS-005：下一轮执行计划（待用户运行/回传）

### 冻结条件

- B：MarketPlace、RitualDance、Cactus、BasketballDrive、BQTerrace。
- HHI LBeu 半帧；分别 300、300、250、250、300 帧，脚本读取实际 INI。
- QP22/27/32/37，固定 nopred、directional，**新增 40 任务**。
- 不新增 gradient，不修改公式，不重跑完整 anchor，不只挑低 QP 或有利序列。
- 用同一 B 数据验证固定工具，以及已冻结的低两档 directional 组合；不在看到 B 后调切换点。

### 命令

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

总计划 96，已有两模式 CE 56 个成功任务在 fingerprint 不变时跳过，新增 B 40 个。
保留原目录名称以复用 marker；不加 `--overwrite`、不加 `--full-sequence`。
结束后这两个模式的 Excel 汇总完整 BCE，各有 48 个 RD 点。

```bash
python3 scripts/ts_fixed_analyze.py \
  --run runs/ts_fixed_LB_CE_half \
  --classes B,C,E --modes nopred,directional \
  --anchor scripts/JVET-hhi.xlsm \
  --out runs/ts_fixed_LB_CE_half/analysis_BCE_611
```

### 完成后必须回填

- [ ] 各模式 B 20/20 完成，帧数、hash、marker 和 Excel 点值一致。
- [ ] 实际使用的二进制/配置/输入/anchor 身份与实验计划一致。
- [ ] B、C、E、BCE 的分量与 6:1:1 BD-rate，是否达到三个门槛。
- [ ] 低/高 QP 结构是否在 B 上复现；组合结果明确标记其性质。
- [ ] 最差序列、内容稳定性、是否出现实现或 anchor 对齐疑点。
- [ ] 决策：固定 NoPred、固定 directional、质量条件启用工具，或停止。

## 8. 关键更正与维护规则

| 事项 | 当前有效决定 |
| --- | --- |
| LB 完整帧还是半帧 | 用户确认本项目 CTC LB 为半帧，以 HHI INI 为准 |
| YUV 6:1:1 | 先分量 BD-rate 后加权；先加权 PSNR 的临时结果仅为 diagnostic，不用于主结论 |
| 条件 Oracle 的解释 | TSRC 固定-q 潜力，不能称为真实 BD-rate 或新编码器收益上限 |
| TS 选择偏差 | 最终 TS 样本有条件性；已以真实闭环固定工具实验补充，未量化分离偏差来源 |
| 小收益的工程意义 | 采用用户 −0.05/−0.08/−0.10% 门槛；同时独立报告稳定性与不确定性 |
| QP 组合 | 探索性复用已编码点，不是已实现的 slice/TU QP 启用工具 |
| Excel 写入时机 | 当前 batch 全部计划任务结束后写表；中途可用恢复脚本生成已完成组，不声称已有提前写表功能 |

每轮更新本文件时应追加实验 ID 或状态变更，保存原结论适用范围，不把假设改写成实测。
记录配置、候选版本、样本集合、主指标、完整性证据、结果路径和下一步。
长跑开始不能标为完成；缺 B 数据不能给 BCE 实测结论；多次续跑应核对各模式 marker，
不能仅凭最新一次根目录 summary 判断整个实验完成。

### 更新历史

- 2026-09-13：增加 `JVET_BJUT_TS_FIXED_NOPRED/GRADIENT/DIRECTIONAL` 三个 0/1 默认模式宏，
  最多开启一个，全关闭为 Current；总开关仍独立控制实验能力。
  `--fixed-predictors` 优先覆盖，省略时 batch 从实际二进制探测默认并同步 Encoder/Decoder。
  已通过 6 项独立编译/模式覆盖测试和 4 项批量测试；未重编既有实验二进制。
- 2026-09-13：固定 predictor 宏的默认值移入 `CommonLib/TypeDef.h`（0）；
  CMake 新构建默认 AUTO，ON/OFF 可显式覆盖。运行时 predictor 仍由环境变量/批量参数选择。
  本次未重编既有实验二进制，不改变已记录编码结果或其续跑指纹。
- 2026-09-13：建立统一记录，补录 TS-001 至 TS-004；冻结 TS-005 计划，B 完成证据为 0；
  纳入用户确认的半帧、分量 BD-rate 后加权及三个工程门槛。
