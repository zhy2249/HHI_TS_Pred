# 外部分析与实验要求收件目录

你上传的其他来源分析、实验要求、原始方案可以直接放在本目录。
可以沿用原文件名；多版文件建议在名称中加入日期或版本，避免覆盖。

## 已归档资料

- [R8 探索计划](TS_Predictor_R8_Exploration_Plan.md)：已纳入版本库的用户原始方案。
- [R9 实验计划](R9_Experiment_Plan.md)：已纳入版本库的用户原始规格。
- [R10 实验计划](R10_Experiment_Plan.md)：2026-09-28从GitHub同步，原稿保留。
- [R9 最新结果分析](R9_Latest_Results_Analysis.md)、[汇总CSV](R9_Latest_Results_Summary.csv)、
  [匹配比较CSV](R9_Latest_Matched_Comparisons.csv)：同批同步的外部分析资料；实施核验另见项目文档。
- `TS_Predictor_R8_All_Experiments_Analysis.md`：本地上传的外部分析，整理时保持未跟踪状态，未随此次文档提交上传。

上述原稿只移动位置，正文保持原样。随上传文件产生的 `:Zone.Identifier` 元数据也保留在此地，不上传版本库。

## 使用约定

- 外部原稿作为输入，不自动视为本工程已实现、已编码或已核验的证据。
- 阅读后形成的源码核验、实验实施和结果分析写入 [项目实验文档](../experiments/README.md)，并引用原稿。
- 不覆盖原始分析中的数据、假设或结论；存在差异时在项目文档中说明。
- 新收到的未跟踪原稿不会仅因放入本目录就自动上传Git，尤其不自动上传工作簿、大体积数据或压缩包。
- 正式结果文件仍应放 `experiments/` 对应编号目录；本目录主要接收分析和要求文档。

## R10 / R9-B分析与R11设计

按用户本次授权，以下外部分析和小体积派生结果同步至本目录；不覆盖旧原稿或正式台账。固定分析输入为 `e1413fd0bf361cdea7d06fbc1b3a78c7036de5de`。

- [R10-1～6及R9-9 Class B分析](R10_Results_and_R9_B_Analysis.md)
- [R11-1～8实验设计](R11_Experiment_Plan.md)、[配置清单](R11_Experiment_Catalog.csv)
- [R10汇总及对R9-9增量](R10_Results_Summary.csv)
- [B类四点暂估与三点纯实测诊断](R9_B_Interval_Analysis.csv)
- [复算脚本、参考实现和验证边界](r11_analysis/README.md)

R11尚未实施或运行；B三点结果不冒充完整四点CTC，R10-6两处补点保留标记。后续新结果另行登记，不能把本轮设计表当作已完成实验。


## R11结果分析与R12设计

固定分析输入为 `e6ba16bce2d1c1a6eb45a8340b7f27a22ab4b53b`。本批只新增外部分析、派生CSV和下一轮规格，不修改编码器源码或正式结果台账。

- [R11结果与R10-3 Class B阶段性分析](R11_Results_and_R10_3_B_Analysis.md)
- [R12实验设计](R12_Experiment_Plan.md)、[配置清单](R12_Experiment_Catalog.csv)
- [R11相对R10-3直接比较](R11_Direct_Comparisons.csv)
- [R10-3 Class B阶段性曲线](R10_3_B_Partial_Analysis.csv)

R12尚未实现或运行。BQTerrace/BasketballDrive的三点值只用于QP27/32/37公共区间诊断，不冒充四点正式BD-rate。
