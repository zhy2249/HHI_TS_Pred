# R13 结果收件目录

冻结规格：`R13-KH-168-v1`。正式anchor始终为Current；R2-2是机制对照。
两组分别为 `r13_1_keep_hit_uniform`（MODE1 / policy98 / 11111）和
`r13_2_keep_hit_spatial`（MODE2 / policy99 / 22111），固定rho=21/2、score-scale=168。
2026-10-23已接收两组完整LB CE，各28/28实测点，无补点；B/RA/AI尚无结果。
原始文件实际在本目录根层：`R13_1_JVET-hhi.xlsm`/`R13_1.csv`和
`R13_2_JVET-hhi.xlsm`/`R13_2.csv`，按编号严格配对，未移动或改写源表。
逐点登记见[数据明细](../../docs/experiments/results/r13.md)，
解读见[CE报告](../../docs/experiments/TS_Predictor_R13_LB_CE_Results_20261023.md)。
尚未收到服务器启动日志、done/identity，实际宏/编译来源/帧数/hash仍未完整核验。

每组先收 `LB_CE/`：LBeu半帧、7序列×4QP=28点；短帧另放 `short_activity/`，不可混入正式曲线。
后续B须明确获准且使用同一revision，不自动创建或跑B/RA/AI任务。
运行与续跑见 [脚本说明](../../scripts/README_TS_PRED.md)，算法见
[R13设计](../../docs/experiments/TS_Predictor_R13_Experiment_Design.md)。

请按组提供 `JVET-hhi.xlsm`、对应 `summary.csv`、启动/最终摘要日志、成功marker和 `*.identity.json`；
同时保留服务器源码commit/补丁、Encoder/Decoder SHA256、实际命令、framecount/采样、输入版本、
宏与runtime覆盖、解码hash状态以及是否开观察。自动identity只能记录本地checkout快照，
不证明二进制的构建来源；请另外记录实际编译来源。
本目录metadata仅冻结规格，不代表服务器身份已经核验；不要改模板伪造实测指纹。

结果按逐分量BD-rate后6:1:1加权；CE七序列等权。缺点保持缺失，不自动填Current。
原始工作簿、码流、视频和大日志不自动上传；仅说明与小体积派生查询表依项目约定同步。
