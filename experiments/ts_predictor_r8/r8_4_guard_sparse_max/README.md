# R8-4 / A04：r8_4_guard_sparse_max

状态（2026-09-26）：服务器LB CE已收到28/28点，无补点，CSV/工作簿与Current Reference审计通过。
结果当前在父目录 `r8_4_JVET-hhi.xlsm` / `4.csv`，未移动源文件；CE加权BD=-0.043397%。
服务器宏/配置/帧数/解码hash与活动仍缺日志证据。详见 [七组结果分析](../../../TS_Predictor_R8_First7_Results_20260926.md)。

- 宏：`JVET_BJUT_TS_R8_MODE=4`；总开关需为1，其它轮MODE为0，重新编译两端。
- runtime：`r8_guard_sparse_max`；batch显式覆盖宏，省略覆盖参数使用编译默认。
- cost / samples：`fractional10` / `empirical`。
- candidates / decision / sparse：`P0` / `guard` / `Smax`。
- quantization search：`native`；实施批次：1。
- 直接机制对照：R7-2、A01、R6-5；正式 anchor 始终为 Current。
- 结果按 `LB_CE/`、`LB_B/`、`RA_CD/` 分开存放；短测另放 `smoke/`。
- 实际运行后接收工作簿、CSV、真实 run_metadata 和必要日志；不创建空白结果工作簿冒充结果。

公式见 [R8 实验设计](../../../TS_Predictor_R8_Experiment_Design.md)；运行见 [实现说明](../../../TS_Predictor_R8_Implementation.md)，证据见 [验收记录](../../../TS_Predictor_R8_Validation.md)。
