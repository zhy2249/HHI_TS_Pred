# R8-13 / B01：r8_13_mixed_raw

状态：C++、宏及batch已实现；人工smoke通过，正式CTC尚未运行。本目录不是已完成正式实验的证据。

- 宏：`JVET_BJUT_TS_R8_MODE=13`；总开关需为1，其它轮MODE为0，重新编译两端。
- runtime：`r8_mixed_raw`；batch显式覆盖宏，省略覆盖参数使用编译默认。
- cost / samples：`integer_fractional_1_1` / `empirical`。
- candidates / decision / sparse：`P0` / `raw` / `Smax`。
- quantization search：`native`；实施批次：1。
- 直接机制对照：A01；正式 anchor 始终为 Current。
- 结果按 `LB_CE/`、`LB_B/`、`RA_CD/` 分开存放；短测另放 `smoke/`。
- 实际运行后接收工作簿、CSV、真实 run_metadata 和必要日志；不创建空白结果工作簿冒充结果。

公式见 [R8 实验设计](../../../TS_Predictor_R8_Experiment_Design.md)；运行见 [实现说明](../../../TS_Predictor_R8_Implementation.md)，证据见 [验收记录](../../../TS_Predictor_R8_Validation.md)。
