# R11-6：add_identity

宏：`JVET_BJUT_TS_R11_MODE=6`；运行名：`r11_add_identity`。
其余算法模式及R10缓存为0，master为1。实现见[实施文档](../../../docs/experiments/TS_Predictor_R11_Implementation.md)。
Current是BD-rate基线，R10-3是机制对照。尚无正式结果。

先跑LB_CE；CE≤−0.14%后人工决定B哨兵，哨兵不是完整B平均。不自动启动B。
保留工作簿、summary、运行命令、编解码器/源码身份、配置/帧数、宏/环境和hash核验结果。
源文件不自动上传；不从空目录推断任务完成。
