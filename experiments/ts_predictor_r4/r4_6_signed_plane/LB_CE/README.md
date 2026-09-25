# R4-6 / SP — complete CE results received 2026-09-21

完整28点在上级 `R4_6_JVET-hhi.xlsm`、`R4_6.csv`。
CE −0.021221%，直接对R3-1 +0.072323%，未通过扩展门槛。
报告见根目录 `TS_Predictor_R3B_R4_Results_20260921.md`，远端身份/活动仍待核验。

拟议模式 `r4_signed_plane`：带符号clipped plane生成幅值，与R3作局部因果回看比较后决定是否采用。
探索性次优先；Reader需要已解码sign的只读邻居视图，不可直接依赖第三遍coeff数组的符号。
设计见根目录 `TS_Predictor_R4_NonAblation_Extension.md`；已接入codec/宏，启用见 `TS_Predictor_R4_Implementation.md`。
正式anchor为Current，R3-1为增量对照；LB CE半帧、QP22/27/32/37，共28项。

本目录用于接收服务器的JVET-hhi.xlsm、配套CSV、源码/模式/输入/配置/帧数/hash元数据和聚合stats。
不生成空白结果，不补缺点，不输出重建文件；分量BD-rate后6:1:1、七序列等权。
