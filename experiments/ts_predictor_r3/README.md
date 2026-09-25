# R3 experiments — CE complete, B partial results received 2026-09-21

设计：`../../TS_Predictor_R3_Experiment_Design.md`，版本R3-20260919-v1。
状态：四个模式及R3宏已实现；已收到服务器四组LB CE结果，各28/28点，共112点，无填补。
CE报告：根目录 `TS_Predictor_R3_LB_CE_Results_20260920.md`。
2026-09-21新增R3-1/2 B为16/20、17/20点；更新工作簿分别44/45点，与CE+B CSV并集一致。
按用户授权仅以Current暂代缺失B QP22四点/三点，BCE暂估−0.075273%/−0.063619%，不是完整实测。
最新报告：`TS_Predictor_R3B_R4_Results_20260921.md`；尚无R3 RA结果，远端配置/帧数/有效模式待日志核验。
使用与验证见根目录 `TS_Predictor_R3_Implementation.md`、`TS_Predictor_R3_Validation.md`。
唯一正式anchor为Current；先分量BD-rate后6:1:1，LB半帧。

| ID | mode | mechanism | components |
|---|---|---|---|
| R3-1 | r3_risk_guard | R2-R winner + remove-one-contribution check | Y/U/V |
| R3-2 | r3_risk_guard_y | same as R3-1 | Y only, U/V Current |
| R3-3 | r3_cn_guard | R2-N + robust immediately preceding CG evidence | Y/U/V |
| R3-4 | r3_cn_guard_y | same as R3-3 | Y only, U/V Current |

当前结果放在每个mode根目录的 `JVET-hhi.xlsm` 与 `R3_1..4.csv`，不是LB_CE子目录；Reference保持Current。
R3-1/2新增B源CSV为 `R3_1_B.csv` / `R3_2_B.csv`，缺点只在派生分析中暂代，源文件保持原样。
R3-1的 `E_.xlsm` 为辅助表，不混用其Reference。R3既定后续测试保持原版本，不据部分数据调公式。
未来可在每组LB_CE接收独立工作簿和metadata；本次不移动或改写用户结果文件。
建议一起提供有效模式banner、宏/源码版本、编解码器SHA、配置、帧数与hash通过信息及聚合stats。
当前CE统计RG/RGY/NG/NGY：−0.093288/−0.078682/−0.011663/−0.014754%；BCE是否正式达标仍须补齐B。
本地未重跑服务器正式编码，不生成空白XLSM占位。
