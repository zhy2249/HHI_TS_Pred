# R8-10 / A10：r8_10_trim_saving

状态：2026-09-26 已实现并接入宏/运行时选择；尚无本组正式 CTC 结果。见 [全量实现与验证](../../../TS_Predictor_R8_All24_Implementation.md)。

- 启用宏：`JVET_BJUT_TS_R8_MODE=10`；须重新编译 Encoder/Decoder。
- 运行时覆盖：`r8_trim_saving`；现有 batch 已注册，使用同一共享任务池。
- cost / samples：`fractional10` / `empirical`。
- candidates / decision / sparse：`P0` / `trim_saving` / `S0`。
- quantization search：`native`；实施批次：2。
- 直接机制对照：R7-1、R6-4；正式 anchor 始终为 Current。
- 结果按 `LB_CE/`、`LB_B/`、`RA_CD/` 分开存放；短测另放 `smoke/`。
- 实际运行后接收工作簿、CSV、真实 run_metadata 和必要日志；不创建空白结果工作簿冒充结果。

完整公式、可用性与实施验收见 [R8 实验设计](../../../TS_Predictor_R8_Experiment_Design.md)。
