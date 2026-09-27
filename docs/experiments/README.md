# 实验文档索引

这里存放项目维护的 TS predictor 实验文档。文件名和实验编号保持不变，便于沿用历史引用。
文档有各自的日期与状态；历史报告不因移动目录变成当前结论。

## 常用入口

- [实验结果台账（仅数据与 BD-rate）](TS_Predictor_Results_Ledger.md)
- [统一实验记录（过程、分析与决策）](TS_Predictor_Experiment_Log.md)
- [R9 实现、宏与运行命令](TS_Predictor_R9_Implementation.md)
- [R9 验收记录](TS_Predictor_R9_Validation.md)
- [脚本使用说明](../../scripts/README_TS_PRED.md)
- [外部分析和实验要求收件目录](../external_inputs/README.md)

## 按实验轮次查找

| 阶段 | 设计 / 实现 | 验证 / 结果 |
|---|---|---|
| 初始统计 | [实验设计](TS_Adaptive_Predictor_Experiment_Design.md) | [CE 结果](TS_Adaptive_Predictor_CE_Results.md) |
| 固定 predictor | [编码实验](TS_Fixed_Predictor_Coding_Experiment.md)、[目标与后续设计](TS_Fixed_Predictor_Target_Analysis_and_Next_Experiment.md) | [LB CE](TS_Fixed_Predictor_LB_CE_Results.md)、[LB BCE / RA CD](TS_Fixed_Predictor_LB_BCE_RA_CD_Results.md) |
| 条件 / 历史选择 | [设计](TS_Conditional_Predictor_Experiment_Design.md)、[实现](TS_Conditional_Predictor_Implementation.md) | [验证](TS_Conditional_Predictor_Validation.md)、[初步结果](TS_Conditional_Predictor_Preliminary_Results_20260918.md) |
| R2 | [前期方案](TS_Predictor_Revision2_Design.md)、[协议](TS_Predictor_R2_Experiment_Protocol.md)、[实现](TS_Predictor_R2_Implementation.md) | [验证](TS_Predictor_R2_Validation.md)、[CE 结果](TS_Predictor_R2_LB_CE_Results_20260919.md) |
| R3 | [设计](TS_Predictor_R3_Experiment_Design.md)、[实现](TS_Predictor_R3_Implementation.md) | [验证](TS_Predictor_R3_Validation.md)、[CE 结果](TS_Predictor_R3_LB_CE_Results_20260920.md)、[R3 B / R4 结果](TS_Predictor_R3B_R4_Results_20260921.md) |
| R4 | [设计](TS_Predictor_R4_Experiment_Design.md)、[非消融扩展](TS_Predictor_R4_NonAblation_Extension.md)、[实现](TS_Predictor_R4_Implementation.md) | [验证](TS_Predictor_R4_Validation.md)、[结果](TS_Predictor_R3B_R4_Results_20260921.md) |
| R5 | [设计](TS_Predictor_R5_Experiment_Design.md)、[实现](TS_Predictor_R5_Implementation.md) | [验证](TS_Predictor_R5_Validation.md)、[CE 结果](TS_Predictor_R5_LB_CE_Results_20260923.md) |
| R6 | [设计](TS_Predictor_R6_Experiment_Design.md)、[实现](TS_Predictor_R6_Implementation.md)、[后续计划](TS_Predictor_Post_R6_Plan_20260924.md) | [验证](TS_Predictor_R6_Validation.md)、[CE 结果](TS_Predictor_R6_LB_CE_Results_20260924.md) |
| R7 / rate estimator | [实验编号](TS_Predictor_R7_Experiment_Design.md)、[评分研究与实现](TS_Predictor_Rate_Estimator_Study.md) | [shadow 结果](TS_Predictor_Rate_Shadow_Results_20260924.md)、[R7→R8 依据](TS_Predictor_R7_Evidence_for_R8.md) |
| R8 | [总设计](TS_Predictor_R8_Experiment_Design.md)、[首八组](TS_Predictor_R8_First8_Design.md)、[初版实现](TS_Predictor_R8_Implementation.md)、[全部24组实现](TS_Predictor_R8_All24_Implementation.md) | [初版验证](TS_Predictor_R8_Validation.md)、[首七组结果](TS_Predictor_R8_First7_Results_20260926.md) |
| R9 | [用户原始计划](../external_inputs/R9_Experiment_Plan.md)、[实施说明](TS_Predictor_R9_Implementation.md) | [验收记录](TS_Predictor_R9_Validation.md) |

跨轮分析：[固定/条件/R2 多维复核](TS_Predictor_Cross_Round_Analysis_20260919.md)。

## 放置约定

- 新的项目设计、实施记录、验收和分析继续放本目录；维护实验记录及上方索引。收到新结果时同步更新独立结果台账，不在结果台账中加入分析。
- 外部原稿放旁边的 `external_inputs/`，本地核验或实施说明另写，不修改外部原稿的结论。
- 结果工作簿和日志继续放 `experiments/` / `runs/`，不放进文档目录。
- 所有运行命令默认从仓库根目录执行，不能在本目录直接照抄相对路径命令。
