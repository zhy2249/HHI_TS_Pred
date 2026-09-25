# R4-5 / CB — complete CE results received 2026-09-21

完整28点在上级 `R4_5_JVET-hhi.xlsm`、`R4_5.csv`。
CE −0.065248%，直接对R3-1 +0.028493%；分散度较好但完整均值/低质量门槛未过，保留Weak诊断对照。
报告见根目录 `TS_Predictor_R3B_R4_Results_20260921.md`，远端身份/活动仍待核验。

拟议模式 `r4_causal_models`：在历史目标自身的因果邻域上回看R3/Current/NoPred/directional四规则，
以固定总优势减最大正贡献保护，默认R3；无跨TU记忆、无递归调用新选择器。
设计见根目录 `TS_Predictor_R4_NonAblation_Extension.md`；已接入codec/宏，启用见 `TS_Predictor_R4_Implementation.md`。
正式anchor为Current，R3-1为增量对照；LB CE半帧、QP22/27/32/37，共28项。

本目录用于接收服务器的JVET-hhi.xlsm、配套CSV、源码/模式/输入/配置/帧数/hash元数据和聚合stats。
不生成空白结果，不补缺点，不输出重建文件；分量BD-rate后6:1:1、七序列等权。
