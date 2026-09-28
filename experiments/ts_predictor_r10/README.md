# R10 结果收件目录

实施方案：[TS_Predictor_R10_Implementation.md](../../docs/experiments/TS_Predictor_R10_Implementation.md)。
R10-1..7算法版本 `R10-20260928-v1`；Current为anchor，R9-9为主要配对对照。
本目录无正式结果。R10-0仅等价缓存bit-exact/计时，不新增BD-rate组。

第一阶段1/2/3/4/7（140个LB CE半帧点），第二阶段5/6（56点）。
对应编号目录的`LB_CE/`中放服务器工作簿和日志。
每次同时保留summary.csv、命令、源码提交、Encoder/Decoder SHA256、配置、帧数、
`TS_FIXED_PREDICTOR`、`TS_R10_CACHE`、`TS_R10_STATS`、`TS_R10_TRACE`及hash核验结果。
实验模式编码在文件夹名，不能只靠工作簿名判断。原始数据不自动上传Git。

入口脚本 `bash scripts/run_ts_r10_lb_ce.sh`；命令在仓库根目录执行。
YUV先分别算BD-rate再6:1:1；CE七序列等权。不授权补点、不提前填0或引用旧组冒充新结果。
