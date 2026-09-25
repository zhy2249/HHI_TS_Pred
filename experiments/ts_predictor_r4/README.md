# R4 experiments — LB CE complete, analysed 2026-09-21

版本R4-20260920-v2。核心设计见根目录 `TS_Predictor_R4_Experiment_Design.md`，
新增非消融方法见 `TS_Predictor_R4_NonAblation_Extension.md`。原三组公式不变。
六组已接入codec/宏，启用见根目录 `TS_Predictor_R4_Implementation.md`，验证见 `TS_Predictor_R4_Validation.md`。
R3长跑及结果保持不变，Current是唯一正式anchor。

已收到六组服务器CE各28/28点，共168点，无填补。源文件在每个编号文件夹根目录：
`R4_n_JVET-hhi.xlsm` 与 `R4_n.csv`，本次不搬移或改写。
报告见根目录 `TS_Predictor_R3B_R4_Results_20260921.md`；CE加权BD依次为
−0.039815/−0.016843/−0.093288/−0.025079/−0.065248/−0.021221%。
R4-3全部RD点同R3-1，其余五组均值更差；没有候选通过冻结的扩展门槛，B/RA不自动追加。
尚缺远端模式/版本/帧数/hash与活动核验；不能仅凭表格相同断言bit-exact或宏未开启。

| R4_MODE | 文件夹 | 运行mode（不变） | 说明 |
|---|---|---|---|
| 1 | r4_1_identity_only | r4_identity_only | 仅保留R3-1已接受的identity分支 |
| 2 | r4_2_magnitude_only | r4_magnitude_only | 仅保留R3-1已接受的非identity幅值分支 |
| 3 | r4_3_guard_rescue | r4_guard_rescue | 保持R3接受分支，仅在回退时补查其他H>0候选 |
| 4 | r4_4_directional_risk | r4_directional_risk | 方向一致性加权局部风险，首批新增组 |
| 5 | r4_5_causal_models | r4_causal_models | 以邻近历史目标的因果回看选择预测规则，首批新增组 |
| 6 | r4_6_signed_plane | r4_signed_plane | 带符号平面幅值加因果回看保护，次优先探索组 |

命名约定：本轮及后续新轮次统一使用 `r<轮次>_<对应MODE宏值>_<方法名>`，不使用内部policy ID。
例如R4-4是 `r4_4_directional_risk`，不是 `r4_20_directional_risk`。
目录名称不作为运行参数；宏值和原 `--fixed-predictors` 模式字符串保持不变。
新batch任务、summary和XLSM使用编号目录；已有无编号运行目录仍可续跑/读取，不自动搬移旧结果。
同一根目录同时存在新旧两种目录时会报错，要求先核对归并，防止静默选错或重复编码。
映射统一在 `scripts/ts_predictor_naming.py`；后续新增轮次同时登记其公开宏值。

原计划每组LB CE四QP半帧28项，六组168项现已收到完整结果。
预设合计最多一个候选按冻结门槛进入RA/B，本次无组通过，不为扩展而放宽规则。
本地未重跑服务器CTC；模式可通过TypeDef.h或显式batch参数选择。
后续每个编号文件夹/LB_CE接收 `JVET-hhi.xlsm`、配套CSV、有效模式/版本/帧数/hash元数据及聚合stats。
按分量BD后6:1:1、序列等权统计；不替换Reference、不默认补点、不创建空白结果表。
