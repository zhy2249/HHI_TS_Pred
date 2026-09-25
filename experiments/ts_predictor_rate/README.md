# Rate estimator 研究收件

本轮已正式命名 **R7**。新结果请放`experiments/ts_predictor_r7/`；本旧目录保留兼容，不移动已有数据。
旧RATE_MODE/RATE_SHADOW对应R7_MODE/R7_SHADOW；旧rate_1_raw/rate_2_guard对应R7-1/R7-2。

RATE-20260924-v1；Current唯一正式anchor，R3-1增量对照。
设计/实现见根目录 `TS_Predictor_Rate_Estimator_Study.md`。
本地短测报告 `TS_Predictor_Rate_Shadow_Results_20260924.md`：评分更准，但fixed-q净率未改善；新模式完整CTC尚未运行。

- `shadow_r3`：原R3实际编码的shadow日志、summary、manifest及分析；不是新的编码算法结果。
- `rate_1_raw`：公开RATE_MODE=1，runtime rate_raw（内部policy32）。
- `rate_2_guard`：公开RATE_MODE=2，runtime rate_guard（内部policy33）。

每组接收独立XLSM/CSV、完整stdout+stderr、实际帧数、source/binary hash及解码记录，不放重建YUV。
目录存在不表示已完成CTC，不创建空白结果工作簿。既有R2/R3/R6原文件不移动。
