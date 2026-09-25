# R4-3 / guarded fallback completion / LB CE

2026-09-21已收到完整28点，源文件在上级 `R4_3_JVET-hhi.xlsm`、`R4_3.csv`。
CE −0.093288%，全部RD点与R3-1一致（不是bit-exact认证），未显示增量；需核验远端模式/活动。
报告见根目录 `TS_Predictor_R3B_R4_Results_20260921.md`；启用见 `TS_Predictor_R4_Implementation.md`。
保持R3-1已接受预测；只有被保护拒绝时补查其他H>0候选，按H、G、identity/较小幅值确定唯一输出。
不改变n>=3、H>0、cost、候选、Rice或分量范围。
计划C4+E3、QP22/27/32/37、LBeu半帧，共28项；正式anchor为Current。
根目录 `TS_Predictor_R4_Experiment_Design.md` 为冻结公式和规则。
