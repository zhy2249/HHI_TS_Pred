# R2 结果收件目录

2026-09-19已收到四组LB CE服务器结果：111/112点，缺实验4 PartyScene QP22。
按用户要求用对应Current点暂估；分析见 [CE结果报告](../../TS_Predictor_R2_LB_CE_Results_20260919.md)。
没有本轮B/RA结果。下面的数量为计划，不代表全部完成。

完整规范：[下一轮实验协议](../../TS_Predictor_R2_Experiment_Protocol.md)。

唯一正式anchor为Current，沿用原工作簿Reference；各实验的BD-rate和收益门槛均相对Current。
NoPred仅为候选/辅助对照，不替换Reference，也不是进入B验证的硬性比较门槛。

| ID | 模式/目录 | 定义 |
|---|---|---|
| R2-M | r2_modal | 因果非零幅值严格多数，否则Current |
| R2-R | r2_risk | 因果样本的remapping语法风险最小，含NoPred |
| R2-N | r2_cn_log | Current/NoPred，原A2整数评分 |
| R2-F | r2_cn_frac | Current/NoPred，独立虚拟CABAC完整CG评分 |

每个模式有 LB_CE、RA_CD、LB_B 三个子目录。前两种分别28/32项，共240项计划任务；
LB_B为条件性后续验证，最多两组共40项。编码由外部服务器运行，本地不启动正式CTC。
未来每目录放 `JVET-hhi.xlsm`、`run_metadata.json`、`logs/`；不要上传重建视频。
四个模式已由R2二进制和现有批量脚本支持；旧revision1二进制不支持。
宏、命令与验证见 [实现说明](../../TS_Predictor_R2_Implementation.md)。
