# R7实验收件

正式名称R7（原Rate estimator）。Current唯一anchor；各分量先BD再6:1:1，CE/BCE按序列等权。

- `r7_1_raw`：R7_MODE=1，原R2-2/r2_risk仅更换评分；runtime rate_raw。
- `r7_2_guard`：R7_MODE=2，原R3-1(YUV)仅更换评分及G/H；runtime rate_guard。
- `shadow_r3`：原R3-1实际编码的观察日志，不是新算法BD结果。

接收各配置的XLSM/CSV、完整日志、帧数及源码/二进制身份、解码hash；不存重建视频。
目录存在不表示编码已完成，不创建空白结果表。旧`experiments/ts_predictor_rate`、`runs`和旧结果不搬移。
说明见根目录`TS_Predictor_R7_Experiment_Design.md`；本地shadow报告和原始数据位置不变。

2026-09-25：根目录已收到 `R7_1/2_JVET-hhi.xlsm` 及 CSV，各28点完整LB CE；原文件保留原位。
表格复核见 [R7→R8依据](../../TS_Predictor_R7_Evidence_for_R8.md)，不以编号子目录尚空认定未完成。
