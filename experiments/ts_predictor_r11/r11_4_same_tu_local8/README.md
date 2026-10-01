# R11-4：same_tu_local8

宏：`JVET_BJUT_TS_R11_MODE=4`；运行名：`r11_same_tu_local8`。
其余算法模式及R10缓存为0，master为1。实现见[实施文档](../../../docs/experiments/TS_Predictor_R11_Implementation.md)。
Current是BD-rate基线，R10-3是机制对照。2026-10-01已登记LB CE的28/28实测点，无补点。
源表位于上级目录的`R11_4_JVET-hhi.xlsm`及`4.csv`；[逐点与逐序列结果](../../../docs/experiments/results/r11.md#r11-4)仅作汇总。B/RA/AI未登记。

先跑LB_CE；CE≤−0.14%后人工决定B哨兵，哨兵不是完整B平均。不自动启动B。
保留工作簿、summary、运行命令、编解码器/源码身份、配置/帧数、宏/环境和hash核验结果。
源文件不自动上传；不从空目录推断任务完成。
