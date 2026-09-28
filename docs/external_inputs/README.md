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
