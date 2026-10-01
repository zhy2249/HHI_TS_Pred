# R11 结果收件目录

八组定义、宏、运行命令见[实施文档](../../docs/experiments/TS_Predictor_R11_Implementation.md)。
公开编号1～8与目录名一致；版本R11-20260929-v1。Current为BD-rate anchor，R10-3为机制对照。
2026-10-01已登记八组LB CE，共224/224实测点，无补点；仅汇总，未作效果分析。
本次上传源表位于本目录的`R11_<编号>_JVET-hhi.xlsm`及`<编号>.csv`，而非下级收件目录。
逐序列BD-rate和逐QP码率/PSNR见[结果明细](../../docs/experiments/results/r11.md)。B/RA/AI未登记。

先八组LB CE（224点，半帧），再根据CE≤−0.14%门槛人工决定B哨兵。
每组分别设LB_CE、LB_B_sentinel、LB_B；三点哨兵不是完整四点Class B。
不保存重建视频，不自动新增Current编码，不自动补点；统计数据与编码结果分开。
保留summary、命令、源码/二进制身份、帧数、环境/宏和解码hash信息，原始数据不自动上传Git。
