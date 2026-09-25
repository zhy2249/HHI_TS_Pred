# R6 使用与复现

算法解释见 `TS_Predictor_R6_Experiment_Design.md`；冻结版本 R6-20260923-v1。

## 宏优先

编辑 `source/Lib/CommonLib/TypeDef.h`，重新编译 Encoder 和 Decoder：

```cpp
#define JVET_BJUT_TS_FIXED_PREDICTOR 1
#define JVET_BJUT_TS_R6_MODE 4 // 1..7任选一个；0为不选R6
```

其余 fixed/conditional/R2/R3/R4/R5 默认模式全部0，编译期已有新旧互斥、范围和master-off检查。
交付master=1、所有模式=0，默认Current，**不是只开master就运行实验**。
不传参数执行宏默认；原 `--fixed-predictors` / `TS_FIXED_PREDICTOR` 仍可覆盖。
没有码流信令，Decoder模式必须一致；首行必须检查有效实验名和 R6 revision/mode，不只看文件夹名。

| R6_MODE | 运行名 | 结果文件夹 |
|---|---|---|
| 1 | r6_dense_nopred | r6_1_dense_nopred |
| 2 | r6_reject_nopred | r6_2_reject_nopred |
| 3 | r6_trim_cost | r6_3_trim_cost |
| 4 | r6_trim_saving | r6_4_trim_saving |
| 5 | r6_sparse_max | r6_5_sparse_max |
| 6 | r6_sparse_mean | r6_6_sparse_mean |
| 7 | r6_sparse_min | r6_7_sparse_min |

## 构建与代码

CMake只指定独立构建目录，不用它选择实验宏，不覆盖旧R3/R5程序：

```bash
cmake -S . -B build/ts-r6 -DCMAKE_BUILD_TYPE=Release \
  -DNX2_TOPLEVEL_OUTPUT_DIRS=OFF -DNX2_ENABLE_LINK_TIME_OPT=OFF
cmake --build build/ts-r6 --target EncoderApp DecoderApp TsR6CodecTest -j4
```

- `TsFixedPrediction.h`：名字、默认、公共policy和banner；原R3函数不改。
- `TsR6Prediction.h`：七个独立纯函数分支与两种对称评分。
- `ContextModelling.h`：公共分派到R6，QuantRDOQ/Writer/Reader原有钩子复用。
- `ContextModelling.cpp`、`TsR6Stats.h`：真实Writer在线聚合；统计关闭或算法未启用时无观察记录。
- `scripts/ts_r6_design_check.cpp` / `ts_r6_codec_test.cpp`：公式、因果、范围隔离与原生编解码检查。
- 原batch只增加模式注册；共享任务池、resume、失败重试、每组完成即写独立XLSM逻辑不改。

## 短测与活动

```bash
g++ -std=c++17 -O2 -Isource/Lib/CommonLib scripts/ts_r6_design_check.cpp -o /tmp/ts-r6-design-check
/tmp/ts-r6-design-check
TS_FIXED_PREDICTOR=r6_trim_saving TS_COND_TRACE=1 build/ts-r6/bin/TsR6CodecTest
python3 scripts/test_ts_fixed_defaults.py
python3 scripts/test_ts_fixed_batch.py
python3 scripts/test_ts_r2_analysis.py
python3 scripts/ts_conditional_smoke.py --r6 \
  --encoder build/ts-r6/bin/EncoderApp --decoder build/ts-r6/bin/DecoderApp \
  --anchor build/ts-anchor/bin/EncoderApp --legacy-encoder build/ts-r5/bin/EncoderApp \
  --out runs/ts_r6_smoke --jobs 4
```

OFF回归需先在头文件master=0下单独构建 `build/ts-r6-off`，恢复master=1后，在最后命令补上
`--off build/ts-r6-off/bin/EncoderApp`。不要恢复头文件后重编OFF目录却继续称其OFF。

固定集合快速预检（54项，无工作簿，单独目录，不能计算CTC BD-rate）：

```bash
TS_R6_STATS=1 python3 -u scripts/batch_test.py --preset LBeu \
  --sequences BasketballDrill,BQMall,KristenAndSara --qps 22,37 --frames 3 \
  --fixed-predictors current,r3_risk_guard,r6_dense_nopred,r6_reject_nopred,r6_trim_cost,r6_trim_saving,r6_sparse_max,r6_sparse_mean,r6_sparse_min \
  --encoder build/ts-r6/bin/EncoderApp --decoder build/ts-r6/bin/DecoderApp \
  --input-dir /home/zhy/videos --jobs 6 --decode-md5 --no-recon --no-xlsm-report \
  --out-dir runs/ts_r6_preflight_3seq
```

若按设计延长16帧，必须换输出目录如 `runs/ts_r6_preflight_16f`；不覆盖三帧点。
原batch已合并stdout/stderr到encode.log；其它服务器脚本也须合并stderr，否则会丢失 `TS_R6_STATS`。

```bash
python3 scripts/ts_r2_activity.py runs/ts_r6_preflight_3seq --revision r6 \
  --out runs/ts_r6_preflight_3seq/activity.csv
```

对6/7要检查 `lu_remap_vs_r3`，仅有普通 `remap_vs_r3` 可能全部来自与5共享的NoPred分支。
诊断关闭用 `TS_R6_STATS=0`；长跑不要设 `TS_COND_TRACE`。不默认记录每个系数。

## 完整 LB CE：先检查计划

首批默认2/4/5，共84项，LB半帧、四QP、10并发、无重建、解码hash、每完成一组立即写它的XLSM：

```bash
bash scripts/run_ts_r6_lb_ce.sh --dry-run
# 快速验证和身份检查通过后正式运行：
bash scripts/run_ts_r6_lb_ce.sh
# 中止后同一命令续跑；不加 --overwrite。
```

将LU消融同时加入同一任务池（140项），**不写多个串行批处理循环**：

```bash
bash scripts/run_ts_r6_lb_ce.sh \
  --fixed-predictors r6_reject_nopred,r6_trim_saving,r6_sparse_max,r6_sparse_mean,r6_sparse_min
```

诊断1/3可用相同脚本覆盖模式，不动公式。跨两次单独启动的脚本不会共享一个池；要全局填满并发，应一次列出所有待跑模式。
普通batch省略 `--fixed-predictors` 才是完全遵循宏默认；这个便利wrapper明确选择首批三组。
输入路径、程序路径、任务数、输出目录均可末尾覆盖，不添加 `--full-sequence`。

回传 `experiments/ts_predictor_r6/r6_<MODE>_<name>/LB_CE/JVET-hhi.xlsm` 与CSV、banner、源码/程序SHA、配置帧数和完整日志；已有flat工作簿布局也支持。
收件目录已建立，不放空白XLSM、不移动旧结果。

```bash
python3 scripts/ts_r2_analyze.py --revision r6 --phase LB_CE \
  --modes r6_reject_nopred,r6_trim_saving,r6_sparse_max \
  --run experiments/ts_predictor_r6 --out runs/ts_r6_results/analysis_611
```

该基础脚本以Current为基线、分量BD后6:1:1、缺点拒绝，不替换anchor。
直接对R3及三曲线共同质量区间须收到完整数据后另作配对积分；不能用对Current的两个百分数相减代替。
