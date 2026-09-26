# TS predictor 实验记录

最后更新：2026-09-26。这是本项目 TS predictor 研究的统一实验台账；
后续实验在本文件追加和更新，不另建互相冲突的总记录。

## 1. 已确定的目标与评价口径

- 工程目标：**LB、BCE 平均 BD-rate ≤−0.05% 为达标，≤−0.08% 为不错，≤−0.10% 为可观**。
- 每条序列先分别计算 Y/U/V BD-rate，再计算 `(6 BD_Y + BD_U + BD_V)/8`。
- 使用工作簿 `bdrate` 对应的 PCHIP，公共质量区间积分，不外推；负数为改善。
- BCE 按十二序列等权：`(5*BD_B + 4*BD_C + 3*BD_E)/12`，不是类别等权。
- LB CTC **采用 HHI INI 半帧**，用户已确认；正式命令不使用 `--full-sequence`。
- 唯一正式anchor为Current，使用 `scripts/JVET-hhi.xlsm` 的Reference，不安排完整anchor重跑。
- NoPred仅为候选/辅助对照；所有正式BD-rate、用户收益门槛与主结论均相对Current。
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
| TS-005 | 补 B：固定 NoPred 和 directional | 已接收外部结果、完成表格审计 | BCE分别−0.041705%/−0.035706%，外部来源仍待日志核实 |
| TS-006 | 条件/历史自适应revision1五组 | 已实现验证、CE初步130/140点 | N1/N2完整CE退化，A1/A2/A3仍有缺失点，见2026-09-18报告 |
| TS-007 | 三固定predictor RA CD | 已接收外部结果、完成表格审计 | NoPred−0.008314%、gradient+0.040742%、directional+0.003174% |
| TS-008 | R2局部幅值预测及Current/NoPred自适应 | 已接收服务器LB CE111/112点并分析 | CE：1 +0.068593%、2 −0.033694%、3 −0.011639%、4 −0.004392%（补1点）；整体Weak，未有本轮B/RA |
| TS-009 | 固定/条件/R2跨轮多维复核 | 已完成分析，非新编码 | 质量区间、分量、序列及配置差异明显；R2-N高质量区间7/7改善，但低质量损失抵消，尚无整体Promising方案 |
| TS-010 | R3证据保护与分量消融 | 四组CE完整；2026-09-24核对R3-1 B已20/20实测，R3-2旧部分结果未更新；远端身份待核验 | R3-1完整BCE−0.075521%，不再补点，暂定Promising；R3-2旧BCE暂估−0.063619%仍有缺点；本次未分析非LB点 |
| TS-011 | R4分支消融、回退补查及非消融扩展 | 六组服务器CE168/168点完整并已分析 | CE依次−0.039815/−0.016843/−0.093288/−0.025079/−0.065248/−0.021221%；3全RD点同R3-1，其他五组均值更差；无组通过冻结扩展门槛，5保留为Weak诊断分支 |
| TS-012 | R5：稳健幅值排序 / Current-only因果否决 | 两组服务器LB CE各28/28点，已核对；远端身份部分验证 | 两组CE均−0.093288%，所有RD点同R3-1/R4-3，增量0；一份R5-1日志确认模式但无活动统计，不能称远端bit-exact；新增RD价值Negative，不扩展B/RA |
| TS-013 | R6：Current偏好 / n<3稀疏区域 | 七组服务器LB CE各28/28点已分析，无补点；远端身份/活动日志缺失 | CE依次−0.012585/−0.092172/−0.026110/−0.007096/−0.048541/−0.029310/−0.016507%；均未超过R3、未通过B扩展门槛；2为Weak诊断，其余本轮增量Negative；仅提出Y稀疏覆盖的后续草案，未实现 |
| TS-014 | **R7**：CG-entry CABAC fractional评分、old-R3 shadow、R2/R3评分替换 | 已实现验证；2026-09-25核验外部两组完整LB CE各28点，无补点；远端身份仍待核验 | R7-1/2 CE对Current −0.070549%/−0.017510%，对R3 +0.023403%/+0.076633%；评分×guard有交互线索，增量Weak；此前shadow条件率不是BD-rate |
| TS-015 | **R8**：评分规则交叉、完整候选、小样本分布、路径和量化搜索 | MODE 1/4/8/13/15/16/17已收到完整LB CE各28点，共196点；19待完成；服务器身份/活动未核验 | 七组均未超R3-1；本轮最佳15为−0.053966%，直接对R7-1仍+0.016585%；4的Y更好但UV抵消；13/17降优先级；Current唯一anchor |

注意：B与RA新增实验来自外部工作簿，没有本地成功marker，不能把“本地marker为0”解释为未编码。
表格完整性和实际编解码身份/hash验证是不同层级；各轮细节与限制见更新历史。

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
| Excel 写入时机 | 当前 batch 每组任务全部返回后立即写该组；共享任务池不停，重试后刷新，未变化组不重复写；早期“全部结束写表”记录仅对应旧版本 |

每轮更新本文件时应追加实验 ID 或状态变更，保存原结论适用范围，不把假设改写成实测。
记录配置、候选版本、样本集合、主指标、完整性证据、结果路径和下一步。
长跑开始不能标为完成；缺 B 数据不能给 BCE 实测结论；多次续跑应核对各模式 marker，
不能仅凭最新一次根目录 summary 判断整个实验完成。

### 更新历史

- 2026-09-26：按“先将剩余的几个实验代码都设计完成”，补齐R8剩余16组，MODE 1..24全部可运行。
  原八组冻结公式不变，旧policy编号不重排；TypeDef直接选MODE，默认0=Current，旧轮互斥/参数覆盖保留。
  22使用TU-local最终CG路径权重，私有原生预算回放；23/24在Intra/Inter owner层成对完整局部RD比较，非仅扩大RDOQ搜索。
  新增独立search聚合及解析，区分试编码q变化与最终Writer；各组数字目录、manifest、说明同步。
  95项Python测试通过；全部24组native CABAC/因果测试通过；新增6888公式对照，旧24672对照仍通过。
  288项人工闭环hash通过，旧34模式bit-exact，24组关统计/禁TS同流，六case新旧master-OFF同流；历史168份共享码流未变。
  15874个两端CG trace和619个C02权重记录相同；原生量化压力测试23/24各512次、各300次q改变。
  人工编码23/24分别391/2185次试编码q改变、217/1423次q1局部获胜，但六case最终码流均与父法相同；先真实活动短测，不据此宣称BD收益。
  剩余16组LB CE dry-run448点；23/24配对预检dry-run32点。未启动正式CTC、未改源表；原首八组批量默认清单不变。
  详见TS_Predictor_R8_All24_Implementation.md，证据runs/ts_r8_all_smoke_final/；正式baseline仍Current。

- 2026-09-26：只读核验R8七组LB CE（1/4/8/13/15/16/17），各28/28点、无QP22补点；
  CSV与工作簿B–J一致，完整Reference与Current一致，公式交叉验证差<4.24e−13个百分点，源表SHA不变。
  Y/U/V各自BD后6:1:1、七序列等权；CE依次−0.004577/−0.043397/−0.029361/+0.050328/
  −0.053966/−0.027349/+0.056429%。均未超过R3-1的−0.093288%；R8-19未纳入。
  直接父法重积分及四曲线共同质量区间证实稀疏×guard、稀疏×候选补全的闭环交互，不做BD百分比直接相减。
  4/15的Y优于R3但UV抵消，去掉PartyScene后对R3约持平；此诊断不改变正式七序列平均。
  七组低质量段均退化；13固定混合与17当前minimax降优先级，其余Weak，暂不七组全扩B。
  没有服务器宏/配置/帧数/解码hash/活动日志，不能由表格推断TU尺寸、n或复杂度；未改算法、未启动编码。
  报告TS_Predictor_R8_First7_Results_20260926.md；复算scripts/ts_r8_results_analysis.py，派生runs/ts_r8_results_20260926/。

- 2026-09-25：按“开始实现”接入R8首批八组，沿用R8-DESIGN-20260925-v2公式与公开编号。
  TsR8Prediction使用int64固定数组、有限幅值成本预计算；RDOQ/Writer/Reader统一CG入口冻结评分；
  原RDOQ搜索、CG全零判断、正式syntax及BDPCM路径不变。新增最终Writer聚合与可选CG trace。
  TypeDef.h直接选模式，默认0=Current，旧轮互斥，未实现编号报错；batch支持显式覆盖。
  新增LB CE/真实短测包装脚本，dry-run分别224/96项；跨组共享池、逐组写表、半帧、无重建、resume保留。
  人工验证与精确数量见TS_Predictor_R8_Validation.md；尚无正式CTC或R8 BD-rate，不据活动宣称收益。

- 2026-09-25：按“选择8组合适的实验先开始设计”将R8首轮固定为A01/A04/A08/B01/B03/B04/B05/B07，
  公开MODE 1/4/8/13/15/16/17/19不重新编号。版本R8-DESIGN-20260925-v2替代旧首批10组安排，不叠加运行。
  B04提前使候选覆盖×稀疏的四角闭合，并为B07提供同样完整候选的未平滑父法；A09/A10/A11暂缓。
  首轮全YUV、原生TS尺寸、旧量化搜索规则；固定CF10与1:1混合/1:2:1平滑，无新增阈值扫描。
  新增TS_Predictor_R8_First8_Design.md，manifest/收件README/空白元数据版本同步，24组原公式与目录数字不变。
  新数学参考脚本30720次合成决策检查通过，八组均有相对主父法的映射差异反例；不是CTC可达性或收益证据。
  全部84项TS Python测试通过，其中10项R8设计检查，含主父对照/manifest一致性与拒绝分支边界。
  计划短测含四对照96点、完整LB CE新增224点；未修改TypeDef/codec/batch、未编译或编码，不提供伪R8运行命令。

- 2026-09-25：依据用户提供的R8探索计划完成TS-015实施规格，保留A12+B8+C4共24组，
  公开R8_MODE预留1..24，目录统一带对应数字；所有状态明确为not_implemented，未修改TypeDef/codec/batch。
  首批10组分1a六组与1b四组；17帧四序列QP22/37作工程预检，正式CE半帧28点/组，全部上限672点。
  明确P1/Psmooth覆盖、minimax固定候选集、C02最终CG路径更新和C03/4所属搜索层成对RD的同步/回滚要求。
  根据现有代码明确放宽up条件仍最多3候选，无需新增槽位；不把Inter residual SSE一概称像素重建SSE。
  新增数学参考脚本，1287原/1287平滑多重集合覆盖及1287个minimax检查通过，另验证边界、逆映射、候选上界；
  这些不是C++/CABAC/BD验证。探索文档引用的分析/测试附件本地未找到，本次独立核验而非引用其完成声明。
  设计见TS_Predictor_R8_Experiment_Design.md，规格scripts/ts_r8_experiment_manifest.json，目录experiments/ts_predictor_r8/。
  全部79项TS Python测试通过（新增5项设计检查）；未启动R8 smoke/CTC或声称获得新BD收益。

- 2026-09-25：为R8设计复算TS-014已收到的两组R7 LB CE表，各28/28实测、无补点，CSV B–J一致，
  相关CE Reference同Current，所有输入SHA读前读后不变；不核验或使用其它配置结果。
  分量BD后6:1:1、七序列等权：R7-1 −0.070549%，R7-2 −0.017510%；直接对R3分别+0.023403%/+0.076633%。
  R7-1直接对R2-2 −0.036119%，R7-2直接对R7-1 +0.054503%，支持继续研究评分×接受规则，而非宣称guard普遍有害。
  R7-1的5/7改善和更低中位数未转化为超越R3的CE均值；保持Weak增量判断，旧“CTC未收到”状态更新。
  复算scripts/ts_r7_results_for_r8.py，报告TS_Predictor_R7_Evidence_for_R8.md；远端模式/帧数/hash仍不能由表格确认。

- 2026-09-24：按用户要求将TS-014正式命名R7。TypeDef.h新增R7_MODE/R7_SHADOW主名称，
  原RATE宏保留兼容别名、冲突时报错；所有TS实验宏/取值已标明对应历史轮次及具体规则。
  R7-1明确对应原R2-2，R7-2明确对应原R3-1(YUV)，不是原R3-2；runtime名称和统计schema不变。
  新收件目录`experiments/ts_predictor_r7/{r7_1_raw,r7_2_guard,shadow_r3}`；batch新目录带R7公开编号，
  旧rate目录原地resume，多路径歧义报错，不移动结果、不改变算法/已有数值。新增R7说明入口。
  `build/ts-r7`编译通过；宏10项、batch20项、shadow解析4项及三模式native测试通过；
  36项smoke全部解码hash通过，码流与重命名前逐项SHA256一致，记录`runs/ts_r7_naming_smoke/`；未跑正式CTC。

- 2026-09-24：TS-014按用户新请求先研究syntaxCost，暂停原Y稀疏覆盖草案的实现优先级。
  确认旧代理等价完整regular幅值路径的等概率bin数，Rice长度本身没有发现公式错误；
  新CG-entry冻结真实CABAC表避免Writer第一遍/Reader第三遍即时context不一致，Q15评分，候选/guard不变。
  RDOQ私有context仅在CG清零RD完成后回放更新，原xGetICRateTS不改；新增rate_raw/rate_guard，RATE_MODE=1/2。
  三条预定序列LB22/37各3帧，6/6解码通过，全部shadow码流与旧R3 SHA256一致。
  最终Writer 5,614 CG、1,644 eligible位置；raw winner分歧29.32%、guard实际映射分歧6.93%；
  成本差MAE 0.8734→0.5225 bit，排序反转14.69%→11.13%，但new raw对old raw条件率仍+0.009067%。
  cutoff2区域指出路径误差，事后path诊断仅用于定位、未部署；new NoPred winner绕过guard的诊断未支持扩组。
  42项短测全部hash通过，Current/R3/OFF对保留程序bit-exact；3模式各160 native TU同步/上下文/因果测试通过。
  新旧宏默认/覆盖/互斥9项、batch18项、shadow解析4项通过；默认仍Current，不改既有实验数据或anchor。
  报告`TS_Predictor_Rate_Shadow_Results_20260924.md`，源码说明`TS_Predictor_Rate_Estimator_Study.md`；
  数据`runs/ts_rate_shadow_audit/analysis/`。算法增量暂Weak，先同内容自然短测，最多两组完整CE；不声称BD收益。

- 2026-09-24：TS-013收到R6七组完整LB CE共196个实测点；根目录R6_1..7 CSV的B–J列均与对应XLSM一致，
  Reference全同Current。未补点、未移动源文件，排除Excel临时锁文件；没有远端模式/帧数/hash/TS_R6_STATS，不能认证运行身份或TU-size机制。
  按分量先BD后6:1:1、七序列等权，七组直接对R3增量依次为
  +0.080790/+0.001946/+0.067784/+0.086792/+0.045027/+0.064466/+0.076878%，均值/中位数均正，序列bootstrap CI均跨0。
  R6-2去KristenAndSara后+0.086339%，近零均值依赖强收益单序列；Current不对称存在但未证实是应去除的RD缺陷。
  R6-6/7直接对5为+0.019546/+0.032148%，保留max；R6-5 Y为−0.010822%、5/7好，但UV退化使总增量+0.045027%，
  Y高质量区间仍+0.014915%，因此只提出Weak的“仅Y新增稀疏覆盖、UV和稠密继续原R3”验证，不拼接分量曲线预测组合收益。
  七组未通过原冻结B门槛，停止扩大本轮B/RA；2保留Weak诊断，其余本轮新增RD价值Negative，不宣称统计证明全域有害。
  同时复核TS-010：R3-1 B现已20/20实测，B−0.050647%、完整BCE−0.075521%，替代旧补点暂估−0.075273%，
  达到−0.05%目标，距−0.08%差0.004479个百分点；去Party为−0.039751%，来源核验仍待完成。
  R3-1工作簿另有83个非LB点，本轮未分析；R3-2旧缺点结论未更新。
  报告TS_Predictor_R6_LB_CE_Results_20260924.md；下一步设计TS_Predictor_Post_R6_Plan_20260924.md；
  复算scripts/ts_r6_results_analysis.py，输出runs/ts_r6_results_20260924，输入SHA前后不变，工作簿公式差≤3.41e-13个百分点。
  本次只新增分析脚本/测试、报告和计划，未改codec/宏/批量编码脚本，未执行编码。

- 2026-09-23：TS-013实现R6-20260923-v1，针对用户提出的两个问题拆成七组，原R3/R4/R5保持不变。
  确认n是五个因果位置的非零数量，重复幅值计数；Current非零必有匹配，但其它样本幅值候选也有。
  指出sum(cost)-min(cost)对匹配候选都只减1，不能消除样本内优势；保留模式3诊断，模式4统一以identity成本归一、删最大正节省贡献。
  模式1/2只改n≥3的fallback，模式5/6/7只改n<3；无组合、无QP/分量特例、无阈值扫描。
  新TypeDef.h R6_MODE=0..7及新旧互斥；共享公共预测入口、无持久状态；stderr最终Writer活动按n/LU/拒绝原因分解。
  模板458752项、宽幅值因果/符号89600项、原生CABAC每组240TU通过；166项合成短测hash/trace通过，
  Current/OFF各13例对anchor bit-exact，25旧模式QP0回归、7组关闭统计一致；七组均有相对R3实际映射变化。
  7宏/18调度/19基础BD测试通过；84项首批LB CE半帧仅dry-run。共享池/逐组XLSM和6:1:1分析复用原脚本。
  BasketballDrill LB QP22三帧9项通过hash，七组相对R3映射改变171/81/45/138/312/312/317次，七组码流均与R3不同；
  mean/min的LU分支分别2/6次实际映射变化。具体覆盖见TS_Predictor_R6_Validation.md，不用单QP短帧计算BD-rate。
  未启动完整CTC，未修改服务器结果或Current Reference；交付master=1、所有模式0，默认Current。

- 2026-09-23：收到R5-1/2完整LB CE结果，各28点，无补点；各CSV的B–J列与对应工作簿一致，Reference均为Current。
  两组各112个RD标量全同R3-1/R4-3，CE分量BD后6:1:1、七序列等权均−0.093288%，直接对R3增量0。
  R5-2工作簿目前位于ts_predictor_r5根目录，按配套R5_2.csv归属，未移动文件。
  唯一BasketballDrill QP22日志确认R5-1宏默认、版本、250帧和解码hash；没有TS_R5_STATS、R5-2日志或配对码流SHA，
  不能把表格一致称为远端bit-exact，也不能断言新增分支触发为0。日志计时与CSV不同，不作为完整任务manifest。
  本轮新增RD价值Negative，停止扩大两组B/RA长跑；保留原R3-1，不调阈值追求差异。
  见TS_Predictor_R5_LB_CE_Results_20260923.md。本次未修改算法、结果源表或启动编码。

- 2026-09-21：按“继续优化R3_1”实现TS-012两个独立变体，R5-20260921-v1：
  R5-1按H优先/G次优排序原候选；R5-2仅在因果回看证明Current有稳健优势时否决原R3。
  原R3/R4公式、旧二进制及结果不变；TypeDef.h新增R5_MODE=0/1/2，新旧宏互斥；交付master=1、所有模式0。
  共享RDOQ/Writer/Reader纯预测入口，无符号依赖、无持久q或CG状态；最终Writer独立聚合增量活动。
  复用原batch共享池/分组即时XLSM，无重建；编号目录和revision=r5基础分析/活动提取完成。
  3,145,728个小幅值模板与384000个网格目标/模式检查通过，但R5-1重排原R3已接受winner计数0，
  上述测试与R4-3逐项比较也无预测差异（不是全域等价证明），不能把潜在代码路径当有效机制；R5-2人工网格仅否决3次。
  两组各240个人工TU原生CABAC往返与因果检查通过，专门加入regular路径的rescue/veto样例；未改公式追求活动。
  351项合成短帧hash/trace通过，Current/OFF各13例对anchor bit-exact；2项stats-off及23项旧模式回归通过。
  两组13个case全同R3-1、相对R3实际映射0；真实BasketballDrill LB QP22三帧4组hash通过，也全同R3-1。
  **当前不建议两组完整CTC**：R5-1增量依据弱，R5-2真实活动不足；只有正确性结论，没有BD收益结论。
  设计/使用/验证见 `TS_Predictor_R5_*.md`，输出 `runs/ts_r5_smoke/`、`runs/ts_r5_real_preflight/`；
  收件骨架 `experiments/ts_predictor_r5/r5_<MODE>_<name>/{LB_CE,LB_B,RA_CD}`。
  6项宏、16项batch、15项基础分析通过；56项半帧CE计划仅dry-run，不启动正式编码、不生成空白结果表。

- 2026-09-21：收到R3-1/2 B CSV及更新工作簿，分别16/20、17/20点；CE仍完整。
  仅按本次授权用对应Current完整RD点暂代七个缺失B QP22，不改源文件。R3-1/2 B暂估
  −0.050053%/−0.042531%，BCE十二序列等权−0.075273%/−0.063619%，暂过−0.05%目标。
  R3-1距−0.08%还差0.004727个百分点；评级Promising（暂定），优先补点与来源核验，不认证正式达标。
  无QP22的实测三点B诊断仍−0.045677%/−0.044127%，两组B的Y均值为正、色度贡献较大。
  R3-1去Party的BCE十一序列−0.039481%*，收益并非只来自Party，但达标幅度仍受它影响。
  R3-2为Weak分量对照；关闭色度predictor不保证色度BD不变，不据分量表推断直接因果。
  R4六组CE168/168点完整、CSV与表格匹配、Reference同Current。R4-3的28个RD点全同R3-1，
  不冒充码流bit-exact/活动已验证；其他五组均值均不如R3-1。R4-5改善RaceHorsesC/Kristen，
  但削弱Party、恶化BQMall，共同低质量区间退步；六组无一通过事先冻结门槛，不建议全铺B/RA。
  报告 `TS_Predictor_R3B_R4_Results_20260921.md`；复算脚本 `scripts/ts_r34_results_analysis.py`，
  数据 `runs/ts_r34_results_20260921/`；默认严格，显式 `--impute-r3-b-qp22` 才允许本次补点。
  新增9项、连同既有分析23项测试通过；独立VBA最大差2.97e-13个百分点，所有源SHA未变。
  只有结果表，远端模式/半帧/配置/hash/活动与复杂度仍不可独立验证；未修改算法或运行编码。

- 2026-09-20：按用户要求将R4六个收件文件夹改为 `r4_1_identity_only`、`r4_2_magnitude_only`、
  `r4_3_guard_rescue`、`r4_4_directional_risk`、`r4_5_causal_models`、`r4_6_signed_plane`。
  后续新轮次统一“轮次＋对应MODE宏值＋方法名”，数字使用公开宏1..6，不使用内部policy17..22。
  `ts_predictor_naming.py`统一映射，batch新任务/summary/XLSM与分析器同步；运行mode字符串和算法均不变。
  已有无编号运行目录保持续跑兼容，新旧目录并存则报错，避免静默选错数据；未搬移旧短测结果、未重编码。
  调度/编号/表格测试14项、分析新旧/flat目录测试11项通过。

- 2026-09-20：按“开始设计代码”实施TS-011全部六组，冻结R4-20260920-v2公式不变。
  TypeDef.h新增R4_MODE=0..6，与所有旧模式互斥、macro-OFF误配置报错；交付master=1、全部模式=0，即Current。
  TsR4Prediction.h实现六个无状态局部规则；复用RDOQ/Writer公共入口；Reader SP使用已解码sign的只读视图，
  不改语法、不提前改写coeff、不使用encoder-only信息、不维护跨TU历史或依赖q的持久缓存。
  TsR4Stats.h只在最终Writer聚合；新增相对Current/R3的实际映射差异、分支类别、方向/专家/符号等机制计数。
  batch只增加六个mode，复用共享池/逐组写表/无重建；activity及基础BD分析加revision=r4，分量BD后6:1:1不变。
  独立ON/OFF构建成功；325项2帧合成回归hash/trace通过，Current/OFF各13项对旧anchor bit-exact，
  另6项统计OFF bit-exact，17项旧模式对保留R3程序bit-exact。旧R3/anchor SHA未变，头文件master已恢复1。
  每组240个人工TU原生CABAC往返、2254CG、35476次扫描因果/符号视图检查通过，包括C的有效rescue手工反例。
  3145728核心原型组合、32000扩展原型目标与生产公式一致；宏6项、调度11项、BD分析9项测试通过。
  合成最终Writer中R4-3补查1398次、接受1次却相对R3映射改变0，不能把继承R3的77次作用冒充新增覆盖。
  本地另作BasketballDrill/LBeu/QP22/2帧的8组限量预检，8/8成功且hash通过，335行聚合数据，
  不写XLSM、不输出重建、不作RD结论。R4-4/5/6相对R3映射改变5/6/1，码流均不同；
  R4-2与Current同流且对Current映射改变0，R4-3与R3同流且补查159/接受0，仍需更广真实覆盖。
  核对本地输入前两帧数据相同、第三帧不同，不能把此两帧预检当作充分运动验证；未据此改冻结公式。
  实现与验证文档 `TS_Predictor_R4_Implementation.md`、`TS_Predictor_R4_Validation.md`；结果在 `runs/ts_r4_smoke/`。
  正式CTC、BCE收益、复杂度和四序列四QP预检尚未完成，未替换任何服务器R3数据或正式anchor。

- 2026-09-20：按用户要求在原三组外增加非消融方法，冻结R4-20260920-v2，R4-1/2/3公式不变。
  数据显示固定directional与R3在不同内容上互补，但不能据序列级表格声称局部赢家可识别；
  BQMall/Kristen的中低质量退化支持检验更好的局部评分，而不是增加序列/QP特例。
  R4-4 DR以1/2方向权重重算风险、删除整个加权位置贡献；R4-5 CB回看历史位置自身的因果预测，
  在R3/Current/NoPred/directional间选择；R4-6 SP引入带符号clipped plane，并由相同因果回看保护，低优先级。
  三组独立，不叠加R4-3补查；只作逐系数局部自适应，不冒充原始整CG历史选择问题已解决。
  Reader的sign要到第三遍结束才写回coeff，SP未来实现需只读sign视图，不能直接读取尚未恢复的数组符号。
  新设计 `TS_Predictor_R4_NonAblation_Extension.md`；原型 `scripts/ts_r4_extension_design_check.cpp`
  复用真实R3/remapping/cost，在32000个人工目标上通过保护、边界、当前/未来及自身目标污染、signed范围检查。
  三组映射差异184/6569/7342只是非等价人工例子，不是CTC活动率/收益；尚未验证真实Reader多遍或闭环RD。
  新收件目录已建立；原84项CE外，优先4/5共56项、6另28项；全六组168项，合计最多一组扩展52项，上限220。
  Current唯一正式anchor、R3-1增量对照、LB半帧、分量BD后6:1:1；CE开发集，不冒称独立验证。
  本次未改codec/TypeDef.h/CMake/batch、未覆盖编解码程序或原结果、未启动编码，R3后续测试保持原样。

- 2026-09-20：用户说明R3后续数据仍需等待，要求先基于现有结果设计新实验。
  冻结R4-20260920-v1三组：I/M分别保留R3-1已接受的identity/非identity分支，不重新搜索删减后的候选；
  C保持R3已接受预测，仅在R3拒绝原winner后补查原集合内其他H>0候选，按H/G/identity/较小幅值定序。
  沿用n>=3、G−最大正贡献>0、语法代理cost和YUV范围，不新增QP门槛、不继续扩CG历史/跨TU状态。
  原代码成本例子[L,U,D,LL,UU]=[2,1,10,1,1]、Rice=1：原winner10的G=5/H=−2被拒绝，
  但NoPred有G=4/H=2，构成补查与R3非等价的结构性反例，不是实际收益证据。
  独立代数程序复用真实函数，3,145,728人工模板/Rice组合通过分支分解/接受保持/保护条件检查，2520组合出现rescue。
  文档 `TS_Predictor_R4_Experiment_Design.md`，程序 `scripts/ts_r4_design_check.cpp`，收件目录 `experiments/ts_predictor_r4/`。
  计划LB CE三组84项，最多一个候选经门槛进入RA/B；只是设计，未改codec、宏、CMake、batch或已运行二进制，未启动编码。
  R3继续按原版本测试，后续结果不据此追溯改写；新组只用Current作正式anchor，R3-1/NoPred作为增量/辅助比较。

- 2026-09-20：TS-010收到四组服务器LB CE完整结果，共112个实测点，无填补。
  四份主表Reference与Current一致，配套CSV全部RD点一致；R3-1另有E_.xlsm，规范化标签后Test与主表相同，
  但其他RA/LP Reference有差异，只审计不纳入主计算、不替换anchor。源文件SHA前后不变。
  主口径分量PCHIP后6:1:1、CE七序列等权：RG/RGY/NG/NGY为−0.093288/−0.078682/−0.011663/−0.014754%。
  前两组中位数均−0.082512%，去PartyScene仍−0.030671/−0.032475%；后两组中位数+0.010799%，
  去PartyScene为+0.044599/+0.043040%，未通过冻结的扩展数值门槛。
  R3-1在三方共同质量范围对R2-R低质量改善−0.095395个百分点、高质量收益保留183.8%；
  NG/NGY高质量只保留42.0%/45.9%，低质量减损未转化为稳定净增量。R3-1/2的E全部12点相同，
  因此色度回退本身未消除KristenAndSara退化；不据表格声称bit-exact、CG覆盖或因果机制已经确认。
  R3-1对R2-R、NoPred、directional直接配对BD分别−0.058082/−0.035511/−0.055210%，配对CI仍跨0。
  总体正式评级仍Weak；局部保护优先保留R3-1，历史保护本规则的扩展证据Negative。按协议先核验日志再RA CD，
  RA通过后LB B；不同时扩大同族两组、不调整公式/阈值。R3-1达到BCE−0.05%所需B均值≤+0.01060%，仅为条件计算。
  报告 `TS_Predictor_R3_LB_CE_Results_20260920.md`，复算 `scripts/ts_r3_results_analysis.py`，
  输出 `runs/ts_r3_results_20260920/{base,detail}/`；新增共同区间3测试、旧跨轮3测试、分析6测试通过。
  本次只分析，未启动任何编码、未改codec/宏/源表；没有B/RA、复杂度、Oracle/η、TU尺寸/CG活动实测结论。

- 2026-09-19：按“开始修改算法/继续”实施TS-010四组R3，保持R3-20260919-v1公式不变。
  TypeDef.h新增R3_MODE=0..4，与旧实验默认模式互斥；master=1、所有模式=0交付，默认Current。
  统一预测和最终CG更新路径同时服务TS-RDOQ/Writer/Reader；Y-only不学习色度历史，全零CG清除近期证据。
  247项两帧smoke全部解码hash通过，Current/master-OFF对保留anchor bit-exact；4项统计关闭、13项旧模式回归通过。
  四模式各6587个CG/104192次因果预测检查通过，覆盖CG1启用、空CG后禁用和未来系数污染；
  64种原生scan形状1267924项邻居检查通过；原Current/NoPred fractional回放及R2-N/F状态测试保持通过。
  Python宏/调度/分析分别6/10/6项通过。batch仅扩展四个名字，共享池/逐组写表保持；112项LB CE半帧dry-run通过。
  新构建使用 `build/ts-r3/`、`build/ts-r3-off/`；保留的旧build目录二进制未变。
  初次构建曾更新顶层bin/lib构建产物，随后改为隔离目录；请勿将顶层默认程序当作已记录旧实验程序续跑。
  验证 `runs/ts_r3_smoke/validation.json`，文档 `TS_Predictor_R3_Implementation.md`、`TS_Predictor_R3_Validation.md`。
  真实序列短帧预检尚未做（默认输入路径缺文件）；未运行正式CTC、未写新结果XLSM或改Current Reference。
  1790行聚合仅是合成输入最终TS条件活动统计；不能解释为BD-rate或对选择偏差的消除证明。

- 2026-09-19：TS-010按跨轮分析设计四组R3，文档 `TS_Predictor_R3_Experiment_Design.md`。
  RG沿用R2-R的模板/cost/winner，仅在固定候选优势G减去最大正贡献B仍>0时离开Current；RGY仅Y启用。
  NG保留R2-N的log代理与EWMA，仅S>0且紧邻上一最终CG的G−B>0时选NoPred；NGY仅Y启用。
  CG0 Current，全零/无有效历史CG清除近期通过证据，不等待两个历史CG，不跨TU；不新增QP阈值。
  四组用来检验小样本/旧证据保护与色度介入范围，不将“删一贡献”称为置信界或交叉验证。
  首轮LB CE半帧四QP112项；最多两组按预设完整CE/质量区间/活动条件进入RA CD，再判断LB B；
  Current是唯一正式anchor，不全套重跑，未生成结果。收件目录 `experiments/ts_predictor_r3/` 已建，仅README占位。
  少量代数例子检查通过，不是codec验证；未添加R3宏/模式，未修改算法、批量脚本或二进制。

- 2026-09-19：TS-009完成固定三组、revision1五组、R2四组跨轮多维分析，未启动编码或修改codec。
  重新读取12份工作簿、461个实测点；沿用既有授权填补缺失QP22，117条可计算曲线复现既有结果，最大差0。
  新增原四点PCHIP的三质量区间分解：R2-N高质量QP22–27对应区间−0.162250%、7/7改善，
  低质量QP32–37对应区间+0.152004%；R2-R对应−0.100019%/+0.051711%。这些不是实际QP门控工具结果。
  BQMall在12种方案整曲线上均退化，但多个方法在高质量区间改善；
  R2-N/F的U均值损失高度集中在KristenAndSara，不能泛称U在多数序列失败。
  R2-N直接相对固定NoPred为+0.044680%（完整CE），证明当前历史选择尚无稳定增量；NoPred仍仅辅助对照。
  B收益集中于Cactus且该序列主要是色度收益；RA的改善也集中，不能从class均值推断分辨率或TU尺寸因果效应。
  报告 `TS_Predictor_Cross_Round_Analysis_20260919.md`，脚本 `scripts/ts_predictor_cross_round_analysis.py`，
  输出 `runs/ts_cross_round_20260919/`。三个新增数值测试及全部分段积分重建检查通过，源表SHA不变。
  结论仍Weak；优先补点和定位中低质量失效机制，不依据本次探索性分解反复调阈值。

- 2026-09-19：TS-008接收四组服务器LB CE结果（只分析结果文件，不检查本地编码程序、不重新编码）。
  四份Reference与Current一致，111个实测RD点与配套CSV一致；按用户要求仅把实验4 PartyScene QP22
  的完整RD点用Current暂代，不修改源表。实验1/2/3/4 CE分别为+0.068593%/−0.033694%/−0.011639%/−0.004392%*。
  去掉PartyScene共同六序列分别+0.114901%/+0.007916%/+0.045488%/+0.019731%，均为正；CE bootstrap CI均跨0。
  评级：1 Negative（本CE）、2 Weak且本轮优先、3 Weak、4 Weak/接近零且补点敏感。没有本轮BCE/RA结论。
  实验4完整六序列直接相对实验3改善约−0.024784%，但不稳定，不能据暂估七序列断言复杂评分必然更差。
  先补唯一缺点，不建议四组直接铺开B；不修改公式/阈值。报告 `TS_Predictor_R2_LB_CE_Results_20260919.md`，
  可复算输出 `runs/ts_r2_partial_20260919/`。远端编译宏、实际帧数、hash及内部切换不由表格独立认证。

- 2026-09-18：TS-008四组R2实现完成：r2_modal/r2_risk/r2_cn_log/r2_cn_frac，
  共用RDOQ/Writer/Reader入口，TU-local最终CG更新；F使用独立虚拟CABAC，真实上下文只做最终Writer观察。
  TypeDef.h新增R2模式0..4，新旧宏互斥；取消CMake对master的覆盖，误请求实验不再静默Current。
  交付默认master=1、所有模式宏=0，仍为Current。原batch支持四模式，保留共享池/无重建/分组即时写表。
  原生评分对照Current/NoPred各6014个CG零fractional差异，N/F各5718个未来污染/状态检查；
  110项两帧smoke全部hash通过，Current/OFF对旧anchor bit-exact，4项关闭统计及3项旧固定回归通过。
  6宏+9调度+3分析测试通过；645行在线活动汇总不是RD结论。
  新说明 `TS_Predictor_R2_Implementation.md`、`TS_Predictor_R2_Validation.md`，结果目录状态已同步。
  LB CE dry-run112项半帧确认；RAeu默认64/32帧单段，外部RA anchor帧数/分段未确认前不能正式比较。
  未运行正式CTC、未生成新正式结果工作簿、未改anchor Reference、未覆盖旧实验二进制。

- 2026-09-18：按用户要求明确R2唯一正式anchor仍为Current，保留原Reference。
  更正此前将NoPred列为“必需基线”的措辞；NoPred保留候选/辅助对照身份。
  取消“不差于NoPred”的B准入硬门槛，正式收益与推广门槛均对Current；
  方法间配对分析仅作复杂度/增量诊断。已同步协议、初版设计、目录说明与元数据模板，未改codec或结果表。

- 2026-09-18：TS-008形成完整R2协议 `TS_Predictor_R2_Experiment_Protocol.md`：
  M严格多数幅值、R含NoPred的局部成本最小、N原A2评分的Current/NoPred、F同候选虚拟CABAC评分。
  候选替换与评分升级分开对照；共同使用可用因果邻居，避免旧设计对窄矩形的整窗口限制。
  计划CE28+RA CD32项/组、四组共240项，B仅按预设条件最多两组追加40项。
  宏优先、误配置不得静默Current、完整数据判定、直接相对NoPred BD-rate、作用覆盖与decoder开销纳入规范。
  结果目录骨架 `experiments/ts_predictor_r2/` 已建立；**仍仅设计，未修改codec、未新增可运行模式或启动编码**。

- 2026-09-18：新增revision2设计 `TS_Predictor_Revision2_Design.md`（仅设计、未实现）：
  R2-1因果邻域离散众数；R2-2以TSRC语法成本近似最小化局部remapping风险；
  R2-3保持Current/directional与原A2更新规则，仅将历史评价换成TU-local确定性虚拟CABAC双分支评分。
  不修改正在收集结果的revision1，不预设正收益，不增加QP/分量专用阈值；
  三候选历史组合仅在前置证据成立后考虑。未来宏优先源码控制的用户偏好已纳入设计。

- 2026-09-18：接收TS-006五组LB CE初步表格，实际130/140点；缺9个QP22、A3 PartyScene QP27。
  按用户要求仅用对应anchor替代缺失QP22；不补QP27，A3排除PartyScene。
  N1/N2完整CE为+0.030428%/+0.043798%；A1/A2补点暂估−0.017523%/−0.005227%；
  A3为6序列子集+0.022220%，不可当完整CE比较。去除PartyScene的共同6序列五组均退化。
  源表/CSV数值一致、Reference与原anchor一致，但没有远端模式/配置/hash日志核实；RD点相同不等于码流bit-exact。
  报告 `TS_Conditional_Predictor_Preliminary_Results_20260918.md`，复现脚本
  `scripts/ts_conditional_partial_analysis.py`，数据输出 `runs/ts_conditional_partial_20260918/`。
  当前N1/N2在CE证据为Negative，A1/A2为Weak，A3证据不足；先补齐，不根据补点结果调参或扩大B长跑。

- 2026-09-16：按用户要求改为按模式组即时写表；组内任务全部返回（含续跑跳过、失败）后，
  立即生成该组 `JVET-hhi.xlsm` 和 summary/failures，其他组继续执行。重试结果变化时刷新，
  终场不重复写未变化的组。Excel采用临时文件完成后替换，失败保留旧表。
  8项batch测试通过，包含跨组写入时机、重试刷新和真实工作簿Reference/失败保护检查；未运行正式编码。

- 2026-09-16：按后续请求扩展 batch CLI 支持五个条件/自适应模式及编译默认值识别，
  增加逐模式编码器/解码器启动探测，新增 `scripts/run_ts_conditional_lb_ce.sh`。
  默认 LBeu C/E 半帧四QP五模式，共140项、10并发、共享队列、无重建、解码hash、保留续跑及分组Excel输出。
  结果目录 `runs/ts_conditional_LB_CE_half/<mode>/`；Excel仍在全部任务结束后生成。
  已通过5项batch测试、宏默认测试及140项dry-run和10次模式支持探测，未启动正式编码。

- 2026-09-16：TS-006 更新为五组闭环规则 N1=q32、N2=conf2、A1=prev、A2=ewma、A3=q32_ewma，
  源码/宏选择已完成，**正式 CTC 尚未编码**。这替代早期 G3=q32_conf2 方案；旧设计保留但注明已被替代。
  历史仅 TU 内保持，在 CG 最终清零决策之后更新；使用最终系数回放 Writer 三遍语法预算，
  不把 RDOQ 的近似预算误作历史评分的有效 remapping 范围。三组历史评分为整数代理，不宣称 CABAC bits。
- 2026-09-16：TS-006 本地验证通过：99项短帧 encode/decode hash、Writer/Reader CG状态一致，
  Current/OFF 对旧anchor bit-exact，五项 trace-off 编码 bit-exact；10项Python测试和C++扫描/状态测试通过。
  详情见 `TS_Conditional_Predictor_Validation.md`。旧实验二进制未覆盖，未修改批量运行脚本。
- 2026-09-16：建立外部结果收件目录 `experiments/ts_conditional_v1/<mode>/{LB_BCE,RA_CD}/`，
  每目录待放 `JVET-hhi.xlsm`、`run_metadata.json` 和可选 logs；源码运行说明见
  `TS_Conditional_Predictor_Implementation.md`。未创建空白结果表，不将计划或 smoke 标成 CTC 结果。

- 2026-09-16：TS-006 条件启用阶段新增首轮设计 `TS_Conditional_Predictor_Experiment_Design.md`：
  G1 实际 CU luma QP<=32，G2 方向分数 2:1 置信门控，G3 二者同时满足；
  均选择既有 directional 或 Current，不加入 NoPred 混合。参数为预先声明的工程假设，不是最优阈值。
  三组未来各 LB BCE 48 + RA CD 32 任务，复用统一池；当前仅设计、未实现、未编码。
  G2/G3 可利用当前 CG 内已经解码的因果邻居，不冒充历史 CG 整组 selector。

- 2026-09-16：TS-005 的 LB B 外部编码结果已从各模式 `JVET-hhi.xlsm` 接收并完成数值审计。
  NoPred/directional 各 B 20 点，合并原 CE 后 BCE 各 48 点；加权 BD-rate 分别
  −0.041705%、−0.035706%，均未达到 −0.05% 目标。历史“尚未测试 B”状态至此失效，
  但上方帧数、hash、二进制身份检查项仍未完成，不能用 Excel pass 代替日志审计。
- 2026-09-16：新增 TS-007（RA CD 外部闭环固定 predictor），三个模式各 32 点。
  NoPred −0.008314%、gradient +0.040742%、directional +0.003174%。Reference 与原 anchor 一致；
  实际 RA 配置/帧数/编码二进制未取得，状态为“表格完整、编码来源待核实”。
- 2026-09-16：冻结的 nominal QP22/27 directional + QP32/37 anchor 组合：
  B −0.029567%、BCE −0.070258%，10/12 序列改善；这是曲线复用诊断，不是 TS-006 工具实现。
  判断：固定 NoPred/directional 为 Weak，gradient 为 Negative，低 QP 条件方向为有限 Promising。
  新增 `scripts/ts_fixed_workbook_analysis.py` 和 `TS_Fixed_Predictor_LB_BCE_RA_CD_Results.md`；
  数据及 SHA256 输出至 `runs/ts_fixed_LB_CE_half/external_analysis_611/`。未启动新编码、未修改 codec。

- 2026-09-13：增加 `JVET_BJUT_TS_FIXED_NOPRED/GRADIENT/DIRECTIONAL` 三个 0/1 默认模式宏，
  最多开启一个，全关闭为 Current；总开关仍独立控制实验能力。
  `--fixed-predictors` 优先覆盖，省略时 batch 从实际二进制探测默认并同步 Encoder/Decoder。
  已通过 6 项独立编译/模式覆盖测试和 4 项批量测试；未重编既有实验二进制。
- 2026-09-13：固定 predictor 宏的默认值移入 `CommonLib/TypeDef.h`（0）；
  CMake 新构建默认 AUTO，ON/OFF 可显式覆盖。运行时 predictor 仍由环境变量/批量参数选择。
  本次未重编既有实验二进制，不改变已记录编码结果或其续跑指纹。
- 2026-09-13：建立统一记录，补录 TS-001 至 TS-004；冻结 TS-005 计划，B 完成证据为 0；
  纳入用户确认的半帧、分量 BD-rate 后加权及三个工程门槛。
