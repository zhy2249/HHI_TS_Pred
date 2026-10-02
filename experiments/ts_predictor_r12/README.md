# R12 结果收件目录

规格 R12-POS-01，共12组。默认首批1/2/4/7/8/9；每组目录名含公开数字。
算法和运行说明见 [实施文档](../../docs/experiments/TS_Predictor_R12_Implementation.md)。
正式 Current anchor 不变，R10-3 是机制对照。
2026-10-02已收到全部12组LB CE，每组28/28点，共336实测，无补点；仅汇总，不作分析。
上传结果位于本目录的`R12_<编号>_JVET-hhi.xlsm`和`<编号>.csv`，不是下级收件目录。
表内Reference与Current一致，CSV全部一致；服务器宏/revision、帧范围和hash未核验。
逐序列分量BD-rate和逐QP码率/PSNR见[结果明细](../../docs/experiments/results/r12.md)。

LB_CE、LB_B_sentinel、LB_B 分开收件；缺失不自动补点，正式数据以日志和工作簿核验为准。
请一并提供实际宏/运行名、源码及二进制指纹、配置、帧范围、序列路径标识和解码hash结果。
本轮尚无B/RA/AI登记；不要把合成单元测试或shadow当成真实序列编码结果。
