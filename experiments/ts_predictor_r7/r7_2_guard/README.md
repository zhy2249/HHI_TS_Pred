# R7-2：原R3-1（YUV）的新评分版

TypeDef.h：master=1、R7_MODE=2、R7_SHADOW=0，其它模式0；runtime `rate_guard`。
仅更换评分及G/H，保留原R3-1候选、n<3回Current和H>0 guard；不是原R3-2，也不叠加R3_MODE。
旧名称rate_2_guard，内部policy33不是宏编号。待接收正式结果，当前没有本组新CTC结论。
