# R7-2：原R3-1（YUV）的新评分版

TypeDef.h：master=1、R7_MODE=2、R7_SHADOW=0，其它模式0；runtime `rate_guard`。
仅更换评分及G/H，保留原R3-1候选、n<3回Current和H>0 guard；不是原R3-2，也不叠加R3_MODE。
旧名称rate_2_guard，内部policy33不是宏编号。
2026-09-25已核验父目录R7_2工作簿及CSV：LB CE 28/28，对Current −0.017510%，对R3 +0.076633%。
来源文件未移动；远端模式/帧数/hash待核验，详见根目录`TS_Predictor_R7_Evidence_for_R8.md`。
