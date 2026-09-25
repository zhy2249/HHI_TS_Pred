# R8-9 / A09：r8_9_trim_cost

状态：仅设计，尚未实现或编码；本目录不是已完成实验的证据。

- 预留宏：`JVET_BJUT_TS_R8_MODE=9`；当前编码器尚不支持。
- 预留 runtime：`r8_trim_cost`；当前 batch 尚不接受此名称。
- cost / samples：`fractional10` / `empirical`。
- candidates / decision / sparse：`P0` / `trim_cost` / `S0`。
- quantization search：`native`；实施批次：1b。
- 直接机制对照：R7-1、R6-3；正式 anchor 始终为 Current。
- 结果按 `LB_CE/`、`LB_B/`、`RA_CD/` 分开存放；短测另放 `smoke/`。
- 实际运行后接收工作簿、CSV、真实 run_metadata 和必要日志；不创建空白结果工作簿冒充结果。

完整公式、可用性与实施验收见 [R8 实验设计](../../../TS_Predictor_R8_Experiment_Design.md)。
