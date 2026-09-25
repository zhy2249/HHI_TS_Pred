# R6 结果收件

版本 R6-20260923-v1；Current唯一anchor，R3-1增量对照。模式号见各目录。
根目录设计/使用/验证文档为 `TS_Predictor_R6_Experiment_Design.md`、`TS_Predictor_R6_Implementation.md`、`TS_Predictor_R6_Validation.md`。
每组放工作簿、CSV、运行metadata与完整stdout/stderr，不放重建YUV，不创建空白结果表。
收到文件不等于已验证模式；须检查有效banner、帧数、源码/二进制SHA、解码hash。
日志应有TS_R6_STATS；对6/7还应检查LU分支实际remapping，不只看共用稀疏NoPred分支。
结果目录均按R6_MODE编号，不是内部policy25..31；原batch支持编号目录和flat工作簿。

## 2026-09-24 收件与分析

七组LB CE各28/28实测点已收到：当前保存在本根目录的 `R6_1_JVET-hhi.xlsm` 至
`R6_7_JVET-hhi.xlsm`，以及 `R6_1.csv` 至 `R6_7.csv`；保留原位，不搬入编号子目录。
CSV的B–J与工作簿一致，Reference同Current，无缺点、无补点；Excel锁文件不算结果。
没有远端完整日志或实际metadata，模板不是身份核验证据。

七组直接对R3的CE均值均退化，未通过原冻结B准入，不建议扩大本轮B/RA。
报告见根目录 `TS_Predictor_R6_LB_CE_Results_20260924.md`；后续只读设计见
`TS_Predictor_Post_R6_Plan_20260924.md`，不是已实现/已运行的新模式。

在工程根目录复算：

```bash
python3 scripts/ts_r6_results_analysis.py --out runs/ts_r6_results_20260924
```

脚本不修改工作簿，只输出派生CSV/JSON；缺失点或不一致直接报错，不用anchor替代。
