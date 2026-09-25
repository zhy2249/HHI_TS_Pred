# R7-1：原R2-2的新评分版

TypeDef.h：master=1、R7_MODE=1、R7_SHADOW=0，其它模式0；runtime `rate_raw`。
候选/n门槛/平局规则不变，整数syntaxCost替换为CG入口冻结CABAC fractional-bit评分；无R3 guard。
旧名称rate_1_raw，内部policy32不是宏编号。
2026-09-25已核验父目录R7_1工作簿及CSV：LB CE 28/28，对Current −0.070549%，对R3 +0.023403%。
来源文件未移动；远端模式/帧数/hash待核验，详见根目录`TS_Predictor_R7_Evidence_for_R8.md`。
