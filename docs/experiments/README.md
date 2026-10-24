# 实验文档索引

这里存放项目维护的 TS predictor 实验文档。文件名和实验编号保持不变，便于沿用历史引用。
文档有各自的日期与状态；历史报告不因移动目录变成当前结论。

## 常用入口

- [实验结果台账（仅数据与 BD-rate）](TS_Predictor_Results_Ledger.md)
- [逐序列 / 逐 QP 明细与可筛选 CSV](results/README.md)
- [R13 / R14 / R3 / R6 QP 分析汇总（2026-10-24）](TS_Predictor_Results_Ledger.md#qp-analysis) · [分量与逐序列 CSV](results/qp_bdrate.csv) · [类别汇总 CSV](results/qp_group_summary.csv)
- [R9 逐序列 / 逐 QP 结果（仅汇总）](results/r9.md)
- [R10-1～6 CE 及 R10-3 完整 B 明细（仅记录）](results/r10.md)
- [R11 八组 CE 及 R11-2 部分 B 明细（仅汇总）](results/r11.md)
- [R12 十二组 CE 与七组部分 B 明细（仅汇总）](results/r12.md)
- [R13 两组 CE 结果分析（2026-10-23）](TS_Predictor_R13_LB_CE_Results_20261023.md)
- [R13-2 异常点诊断：Johnny 27/32/37、KristenAndSara 32](TS_Predictor_R13_Anomaly_Diagnosis_20261024.md) · [日志审计与本地短测派生数据](results/r13_diagnosis_20261024/README.md)
- [R13 异常后续分析指导：首次搜索分叉、Y→UV与滤波分离](TS_Predictor_R13_Anomaly_Followup_Guide_20261024.md)（基于6784c2b；仅指导，未追加运行）
- [R13 码流解码续查：首个保留划分、CCCM传播与滤波拆分](TS_Predictor_R13_Decoder_Followup_20261024.md) · [只读诊断派生数据](results/r13_followup_20261024/README.md)
- [R13 逐序列 / 逐 QP 数据（仅结果）](results/r13.md)
- [R14 早期部分结果与状态机制分析（历史快照）](TS_Predictor_R14_Partial_Analysis_20261024.md)
- [R14 更新结果：14组完整CE、2的正确部分结果及QP分析](results/r14.md)
- [R14 当前CE多维分析：动态增量、初态、QP、分量与稳定性](TS_Predictor_R14_LB_CE_Analysis_20261024.md) · [配对与分布派生表](results/r14_analysis_20261024/README.md)
- [统一实验记录（过程、分析与决策）](TS_Predictor_Experiment_Log.md)
- [R9 实现、宏与运行命令](TS_Predictor_R9_Implementation.md)
- [R9 验收记录](TS_Predictor_R9_Validation.md)
- [R11 八组实现、宏与分阶段运行](TS_Predictor_R11_Implementation.md)
- [R12 十二组实现与首批六组运行](TS_Predictor_R12_Implementation.md)
- [R12 局部语法与量化验收记录](TS_Predictor_R12_Validation.md)
- [R12 等价复杂度优化与回归验证](TS_Predictor_R12_Exact_Optimization.md)
- [R3 / R6 等价复杂度优化、统计开关与局部计时](TS_Predictor_R3_R6_Exact_Optimization.md)
- [当前所有实验统计默认关闭：开关、脚本与续跑](TS_Predictor_Statistics_Defaults.md)
- [R13 KeepHit：统一 / 空间加权两组冻结设计](TS_Predictor_R13_Experiment_Design.md)
- [R13 实现、宏、默认关闭的观察与运行命令](TS_Predictor_R13_Implementation.md)
- [R14 v3：方向驱动的单／双状态，12组动态＋3组固定对照](TS_Predictor_R14_Experiment_Design.md)
- [R14 本地源码接入设计、同步/回滚和阶段A/B条件](TS_Predictor_R14_Engineering_Plan.md)
- [R14 实现、连续1～15编号与旧号对照、默认关闭观察及非视频验收](TS_Predictor_R14_Implementation.md)
- [R14 独立设计参考](reference/ts_r14_design_reference.py) · [纯函数检查记录，非编解码验收](reference/TS_R14_Design_Validation_20261023.md)
- [KeepHit 评分原始推导与工程指导](TS_Predictor_KeepHit_Score_Experiment_Guide.md)
- [R3 / R6 后续等价复杂度建议（与 R13 分开）](../external_inputs/R3_R6_Remaining_Complexity_Review.md)
- [脚本使用说明](../../scripts/README_TS_PRED.md)
- [外部分析和实验要求收件目录](../external_inputs/README.md)

## 按实验轮次查找

| 阶段 | 设计 / 实现 | 验证 / 结果 |
|---|---|---|
| 初始统计 | [实验设计](TS_Adaptive_Predictor_Experiment_Design.md) | [CE 结果](TS_Adaptive_Predictor_CE_Results.md) |
| 固定 predictor | [编码实验](TS_Fixed_Predictor_Coding_Experiment.md)、[目标与后续设计](TS_Fixed_Predictor_Target_Analysis_and_Next_Experiment.md) | [LB CE](TS_Fixed_Predictor_LB_CE_Results.md)、[LB BCE / RA CD](TS_Fixed_Predictor_LB_BCE_RA_CD_Results.md) |
| 条件 / 历史选择 | [设计](TS_Conditional_Predictor_Experiment_Design.md)、[实现](TS_Conditional_Predictor_Implementation.md) | [验证](TS_Conditional_Predictor_Validation.md)、[初步结果](TS_Conditional_Predictor_Preliminary_Results_20260918.md) |
| R2 | [前期方案](TS_Predictor_Revision2_Design.md)、[协议](TS_Predictor_R2_Experiment_Protocol.md)、[实现](TS_Predictor_R2_Implementation.md) | [验证](TS_Predictor_R2_Validation.md)、[CE 结果](TS_Predictor_R2_LB_CE_Results_20260919.md) |
| R3 | [设计](TS_Predictor_R3_Experiment_Design.md)、[实现](TS_Predictor_R3_Implementation.md) | [验证](TS_Predictor_R3_Validation.md)、[CE 结果](TS_Predictor_R3_LB_CE_Results_20260920.md)、[R3 B / R4 结果](TS_Predictor_R3B_R4_Results_20260921.md)、[已有 LB/AI/RA 的 QP 分析](results/r3.md) |
| R4 | [设计](TS_Predictor_R4_Experiment_Design.md)、[非消融扩展](TS_Predictor_R4_NonAblation_Extension.md)、[实现](TS_Predictor_R4_Implementation.md) | [验证](TS_Predictor_R4_Validation.md)、[结果](TS_Predictor_R3B_R4_Results_20260921.md) |
| R5 | [设计](TS_Predictor_R5_Experiment_Design.md)、[实现](TS_Predictor_R5_Implementation.md) | [验证](TS_Predictor_R5_Validation.md)、[CE 结果](TS_Predictor_R5_LB_CE_Results_20260923.md) |
| R6 | [设计](TS_Predictor_R6_Experiment_Design.md)、[实现](TS_Predictor_R6_Implementation.md)、[后续计划](TS_Predictor_Post_R6_Plan_20260924.md) | [验证](TS_Predictor_R6_Validation.md)、[CE 结果](TS_Predictor_R6_LB_CE_Results_20260924.md)、[逐点与 QP 分析](results/r6.md) |
| R7 / rate estimator | [实验编号](TS_Predictor_R7_Experiment_Design.md)、[评分研究与实现](TS_Predictor_Rate_Estimator_Study.md) | [shadow 结果](TS_Predictor_Rate_Shadow_Results_20260924.md)、[R7→R8 依据](TS_Predictor_R7_Evidence_for_R8.md) |
| R8 | [总设计](TS_Predictor_R8_Experiment_Design.md)、[首八组](TS_Predictor_R8_First8_Design.md)、[初版实现](TS_Predictor_R8_Implementation.md)、[全部24组实现](TS_Predictor_R8_All24_Implementation.md) | [初版验证](TS_Predictor_R8_Validation.md)、[首七组结果](TS_Predictor_R8_First7_Results_20260926.md) |
| R9 | [用户原始计划](../external_inputs/R9_Experiment_Plan.md)、[实施说明](TS_Predictor_R9_Implementation.md) | [验收记录](TS_Predictor_R9_Validation.md)、[结果台账](TS_Predictor_Results_Ledger.md)、[逐序列/逐QP明细（仅汇总）](results/r9.md) |
| R10 | [用户原始计划](../external_inputs/R10_Experiment_Plan.md)、[实现与运行](TS_Predictor_R10_Implementation.md) | [验收记录](TS_Predictor_R10_Validation.md)、[1～6 CE及3的完整B明细](results/r10.md)；7未登记 |
| R11 | [用户原始计划](../external_inputs/R11_Experiment_Plan.md)、[八组实现与运行](TS_Predictor_R11_Implementation.md) | [验收记录](TS_Predictor_R11_Validation.md)、[八组LB CE及2的部分B明细](results/r11.md)、[结果台账](TS_Predictor_Results_Ledger.md)；RA/AI未登记 |
| R12 | [最新原始计划](../external_inputs/R12_Experiment_Plan.md)、[十二组实现与运行](TS_Predictor_R12_Implementation.md) | [局部验收](TS_Predictor_R12_Validation.md)、[十二组CE/七组部分B明细](results/r12.md)、[结果台账](TS_Predictor_Results_Ledger.md)；无完整B/BCE，RA/AI未登记 |
| R13 | [KeepHit评分指导](TS_Predictor_KeepHit_Score_Experiment_Guide.md)、[两组冻结设计](TS_Predictor_R13_Experiment_Design.md)、[实现与验证](TS_Predictor_R13_Implementation.md) | [两组完整CE分析](TS_Predictor_R13_LB_CE_Results_20261023.md)、[CE及1的部分B明细](results/r13.md)；B仅RitualDance完整，无完整B/BCE或可靠计时结论 |
| R14 | [v3：12组动态＋3组固定对照，NONE／PAIR2](TS_Predictor_R14_Experiment_Design.md)、[本地源码接入与分阶段计划](TS_Predictor_R14_Engineering_Plan.md)、[连续1～15及旧号对照](TS_Predictor_R14_Implementation.md) | [当前CE多维分析](TS_Predictor_R14_LB_CE_Analysis_20261024.md)、[整体及QP明细](results/r14.md)、[早期部分结果分析（历史）](TS_Predictor_R14_Partial_Analysis_20261024.md)；412实测/8缺失，除2外14组完整；2正确部分结果纳入；10最佳但未稳定优于R3/R6，无服务器状态计数 |

跨轮分析：[固定/条件/R2 多维复核](TS_Predictor_Cross_Round_Analysis_20260919.md)。

## 放置约定

- 新的项目设计、实施记录、验收和分析继续放本目录；维护实验记录及上方索引。收到新结果时同步更新独立结果台账，不在结果台账中加入分析。
- 外部原稿放旁边的 `external_inputs/`，本地核验或实施说明另写，不修改外部原稿的结论。
- 结果工作簿和日志继续放 `experiments/` / `runs/`，不放进文档目录。
- 所有运行命令默认从仓库根目录执行，不能在本目录直接照抄相对路径命令。
