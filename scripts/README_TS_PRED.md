# TS predictor 统计运行说明

统一进度、结果与后续计划见 [实验记录](../TS_Predictor_Experiment_Log.md)。

本文件描述第一阶段的固定系数反事实统计。新的真实固定 predictor 编码实验见
[`TS_Fixed_Predictor_Coding_Experiment.md`](../TS_Fixed_Predictor_Coding_Experiment.md)：
复用 `batch_test.py --fixed-predictors nopred,gradient,directional`，统一任务池、无重建视频输出。
两阶段使用不同构建目录和模式定义，不能混用旧 M2/M3 编号或统计 CSV。

完整定义见根目录 `TS_Adaptive_Predictor_Experiment_Design.md`。正式实验不修改 predictor 或量化决策。需 Python 3.10+，分析仅用标准库。

## 构建

在工程根目录执行：

```bash
cmake -S . -B build/ts-analysis -DCMAKE_BUILD_TYPE=Release -DNX2_ENABLE_LINK_TIME_OPT=OFF -DNX2_TOPLEVEL_OUTPUT_DIRS=OFF -DJVET_BJUT_TS_PRED_ANALYSIS=ON
cmake --build build/ts-analysis --target EncoderApp -j 8
cmake -S . -B build/ts-anchor -DCMAKE_BUILD_TYPE=Release -DNX2_ENABLE_LINK_TIME_OPT=OFF -DNX2_TOPLEVEL_OUTPUT_DIRS=OFF -DJVET_BJUT_TS_PRED_ANALYSIS=OFF
cmake --build build/ts-anchor --target EncoderApp DecoderApp -j 8
```

二进制在各自 `build/*/bin/`，不覆盖 `bin/EncoderAppStatic`。宏ON但不设置TS_PRED_STATS时不启动observer。

## 短帧正式统计

先规划，检查输入和磁盘，删除 `--dry-run` 即执行。AI/LB两配置、5序列、4QP、每项16连续输入帧，任务并行2。

```bash
python3 scripts/batch_test.py --local-preset AI --sequences BasketballPass,BQMall,BasketballDrillText,FourPeople,BasketballDrive --qps 22,27,32,37 --frames 16 --jobs 2 --encoder build/ts-analysis/bin/EncoderApp --decoder build/ts-anchor/bin/DecoderApp --decode-md5 --extra-args='--TemporalSubsampleRatio=1 --PrintHexPSNR=1 --SEIDecodedPictureHash=1' --out-dir runs/ts_pilot/AI --ts-pred-stats-dir runs/ts_pilot/stats/AI --no-xlsm-report --dry-run
python3 scripts/batch_test.py --local-preset LB --sequences BasketballPass,BQMall,BasketballDrillText,FourPeople,BasketballDrive --qps 22,27,32,37 --frames 16 --jobs 2 --encoder build/ts-analysis/bin/EncoderApp --decoder build/ts-anchor/bin/DecoderApp --decode-md5 --extra-args='--TemporalSubsampleRatio=1 --PrintHexPSNR=1 --SEIDecodedPictureHash=1' --out-dir runs/ts_pilot/LB --ts-pred-stats-dir runs/ts_pilot/stats/LB --no-xlsm-report --dry-run
```

输入默认 `/home/zhy/videos`；其它位置加 `--input-dir /path/to/videos`。RA补充使用 `--local-preset RA --frames 32` 与独立RA输出目录。不同配置不得共用同一stats/out目录。不建议第一次就完整CTC；先检查所有任务的 `summary.csv`、actual encoded frames 和统计体量。

重复同一命令自动resume，失败任务无成功marker会重跑。`--overwrite`显式重跑已有成功任务。每任务 `*.encode.log` / `*.decode.log` 留失败信息；保留 `.done.json`，分析默认只接受有此成功标记的CG文件。出现0个TS TU时CSV仅有header，是有效阴性覆盖，不能删去这种任务。

## 分析

```bash
python3 scripts/ts_pred_analyze.py runs/ts_pilot/stats --out runs/ts_pilot/analysis --bootstrap 500
```

首看 `TS_Adaptive_Predictor_Results.md` 与 `analysis.json`，再看 `ts_pred_summary.csv` 的各个dimension。CSV输入rate是1/32768 bit整数；summary的rate是bit。conditional/path分开读；不能把conditional CG Oracle叫做全TU全局最优或BD-rate。confidence exploratory不是验证集最优阈值。

## 手工单任务 / debug

```bash
TS_PRED_STATS=/tmp/ts_single.csv TS_PRED_SEQUENCE=BasketballPass TS_PRED_CONFIGURATION=AI TS_PRED_QP=22 TS_PRED_DEBUG=/tmp/ts_debug.csv TS_PRED_DEBUG_CGS=2 build/ts-analysis/bin/EncoderApp -c cfg/encoder_intra_nx2.cfg -c cfg/per-sequence/BasketballPass.cfg -i /home/zhy/videos/classD/BasketballPass_416x240_50.yuv -q 22 -f 2 --TemporalSubsampleRatio=1 -b /tmp/ts_single.bin -o /dev/null
python3 scripts/ts_pred_analyze.py /tmp/ts_single.csv --allow-unmarked --out runs/ts_single_analysis
```

debug有明确CG上限，正式批量不要设置TS_PRED_DEBUG。主CSV旁的 `.tu.csv` 是所有coded TS residual TU的census，包括TSRC-disabled。

## 重做bit-exact验证

原版必须是未修改commit的源码构建。当前会话已在 `/tmp/ts-pred-original` 生成并编译该快照；该目录是临时验证产物，重启/清理后可能不存在。用自己的原版可执行文件替换 `--original`。

```bash
python3 scripts/ts_pred_smoke.py --original /tmp/ts-pred-original/bin/release/EncoderApp --off build/ts-anchor/bin/EncoderApp --on build/ts-analysis/bin/EncoderApp --decoder build/ts-anchor/bin/DecoderApp --extended
python3 scripts/ts_pred_analyze.py runs/ts_smoke --allow-unmarked --smoke --out runs/ts_smoke/analysis --bootstrap 100
```

合成数据输出只用于验证，不要混入正式 `runs/ts_pilot/stats`。已有文件在同名smoke目录会由该脚本重建。想保留旧验证可换 `--out`。
