# R5 结果收件与状态

版本R5-20260921-v1，Current唯一正式anchor，原R3-1增量对照。
2026-09-23已收到两组服务器LB CE各28/28点，全部RD数据同R3-1；CE均−0.093288%，新增收益0。
R5-1工作簿在编号目录根层；R5-2工作簿暂在本目录根层，按配套R5_2.csv归属，未移动源文件。
唯一R5-1远端日志确认该运行的有效模式，但无活动统计；其他运行身份及全组bit-exact尚未认证。
详见根目录 `TS_Predictor_R5_LB_CE_Results_20260923.md`；不继续扩展两组B/RA。
设计/使用/验证见根目录 `TS_Predictor_R5_Experiment_Design.md`、`TS_Predictor_R5_Implementation.md`、`TS_Predictor_R5_Validation.md`。

| R5_MODE | 文件夹 | 运行名称 |
|---|---|---|
| 1 | r5_1_margin_first | r5_margin_first |
| 2 | r5_2_current_veto | r5_current_veto |

两组独立，不组合；全模式0为Current。TypeDef.h宏优先，显式batch参数可以覆盖。
初步活动不足：R5-1人工枚举未出现已接受R3重排；两组合成短测均未改变相对R3的实际映射/码流。
只保留可复现实验，不建议未经有效活动检查直接完整跑CE/B；不放宽阈值强行制造效果。

每组按LB_CE/LB_B/RA_CD收件，保留 `JVET-hhi.xlsm`、配套CSV、有效模式banner、源码/二进制SHA、
输入/配置/帧数、解码hash与聚合 `TS_R5_STATS`。不要输出或上传重建YUV，不创建空白结果表。
统计须先分量BD后6:1:1，CE七序列/BCE十二序列等权，不把类别均值等权混合。
运行端继续复用原batch共享池和每组即时写表逻辑；目录编号是R5_MODE，不是内部policy23/24。
