# TS predictor 统计运行说明

统一进度、结果与后续计划见 [实验记录](../TS_Predictor_Experiment_Log.md)。

R3的Current偏好/稀疏支持独立实验已实现为R6：
[设计与逻辑审查](../TS_Predictor_R6_Experiment_Design.md)、[宏/运行命令](../TS_Predictor_R6_Implementation.md)、
[验证](../TS_Predictor_R6_Validation.md)。`JVET_BJUT_TS_R6_MODE=1..7`；默认仍Current。
运行入口仍为 `bash scripts/run_ts_r6_lb_ce.sh --dry-run`，支持共享队列/逐组写表和 `--revision r6`，日志需保留stderr。
2026-09-24已收到七组完整服务器LB CE，均未超过R3，不建议继续扩大本轮B/RA。
新收到的根目录 `R6_N_JVET-hhi.xlsm` / `R6_N.csv` 使用专门只读审计脚本，不必搬动文件：

```bash
python3 -m unittest discover -s scripts -p 'test_ts_r6_results_analysis.py'
python3 scripts/ts_r6_results_analysis.py --out runs/ts_r6_results_20260924
```

缺点/失败/CSV不一致即报错，不补anchor点，不写入XLSM。Current为正式anchor，R3仅增量对照。
详见[R6结果](../TS_Predictor_R6_LB_CE_Results_20260924.md)与[后续计划](../TS_Predictor_Post_R6_Plan_20260924.md)。
计划尚未实现新宏或新运行模式。

R3-1的两组独立细化已实现为R5，见 [设计](../TS_Predictor_R5_Experiment_Design.md)、
[宏启用与使用](../TS_Predictor_R5_Implementation.md)、[验证及低活动结论](../TS_Predictor_R5_Validation.md)。
`JVET_BJUT_TS_R5_MODE=1/2`，与旧实验互斥；结果目录为`r5_1_margin_first`、`r5_2_current_veto`。
batch仍使用原共享池/逐组写表；分析与活动提取增加`--revision r5`。
合成和限量真实短测相对R3未见增量映射，暂不建议直接两组完整CTC；代码可运行不等于已改善BD-rate。

R3四组证据保护实验见 [R3实现与使用](../TS_Predictor_R3_Implementation.md)。
仍由TypeDef.h选择默认，batch参数可覆盖；Current是唯一正式anchor。
R3服务器LB CE结果及复算命令见 [2026-09-20分析](../TS_Predictor_R3_LB_CE_Results_20260920.md)。
最新R3-1/2部分B及完整R4 CE见 [2026-09-21分析](../TS_Predictor_R3B_R4_Results_20260921.md)。
复算：`python3 scripts/ts_r34_results_analysis.py --impute-r3-b-qp22`；
仅该显式参数允许R3-1/2缺失B QP22暂用Current，R4不补点，源CSV/XLSM不修改。
补齐后省略参数严格分析；指定新 `--out` 目录可保留本次快照。旧R3 CE快照脚本不适用于已合并B的工作簿。
下一轮三组分支消融/回退补查见 [R4设计](../TS_Predictor_R4_Experiment_Design.md)。
另有 [R4-4/5/6非消融扩展](../TS_Predictor_R4_NonAblation_Extension.md)：方向条件风险、因果规则选择、带符号平面；
六组已接入codec与宏，使用见 [R4实现](../TS_Predictor_R4_Implementation.md)，验证见 [R4验证](../TS_Predictor_R4_Validation.md)。
六组收件目录在 `experiments/ts_predictor_r4/`，已收到168/168个CE点并分析，不影响R3正在进行的测试。
R4及后续新轮次目录按“轮次_MODE宏值_方法名”命名，如 `r4_4_directional_risk`；运行mode仍为 `r4_directional_risk`。
新batch/报告使用编号目录，续跑和分析兼容已有旧目录；映射见 `ts_predictor_naming.py`。

## 当前轮：R7 rate estimator / shadow（2026-09-24）

[源码与运行说明](../TS_Predictor_Rate_Estimator_Study.md)，
[已完成的shadow结果及后续计划](../TS_Predictor_Rate_Shadow_Results_20260924.md)。
[R7编号/宏对照](../TS_Predictor_R7_Experiment_Design.md)：R7-1对应原R2-2新评分，R7-2对应原R3-1新评分。
本轮先评价cost精度，不把条件CG率当BD-rate。没有新增predictor、经验guard或阈值。

- `run_ts_rate_shadow.sh`：原R3实际编码，预定PartyScene/BQMall/KristenAndSara，LB22/37、3帧；无重建、不写短帧XLSM。
- `ts_rate_shadow_analyze.py`：聚合排序、tie、guard、真实CG率误差与独立搜索探针；可用`--reference-summary`校验bit-exact。
- `ts_rate_smoke.py`：六种短测，原R3/Current回归、两新模式及可选`--off`；不是CTC。
- 新模式`rate_raw`/`rate_guard`由TypeDef.h的`JVET_BJUT_TS_R7_MODE=1/2`选择；旧RATE_MODE兼容，runtime名称不变；共享池、resume、分组即时写表均保留。
- 统计需要TypeDef.h `JVET_BJUT_TS_R7_SHADOW=1`及原`TS_RATE_SHADOW`环境开关；正式新模式不需要shadow。
- 新收件目录`experiments/ts_predictor_r7/{shadow_r3,r7_1_raw,r7_2_guard}/`；旧rate目录不移动、续跑仍识别，完整CTC暂无新结果。

本地观察版为`build/ts-rate`，当前默认交付版为`build/ts-rate-final`。新代码默认仍Current，运行时参数可以覆盖宏默认。

## 历史阶段入口

R2真实编码实验见 [实现与运行说明](../TS_Predictor_R2_Implementation.md)。唯一anchor仍为Current。
2026-09-18起，实验master由TypeDef.h控制，CMake不再覆盖；旧构建请勿随意重编。
下面的旧counterfactual统计构建须先把头文件master设为0，否则与统计宏的互斥检查会拒绝编译。

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

## 条件与历史自适应实验（2026-09-16）

当前五个新模式、编译/运行方式和结果收件目录见
[`TS_Conditional_Predictor_Implementation.md`](../TS_Conditional_Predictor_Implementation.md)。
后续已扩展 batch CLI 支持五个新模式；LB CE 入口为 `bash scripts/run_ts_conditional_lb_ce.sh`。
其默认输出为 `runs/ts_conditional_LB_CE_half/<mode>/JVET-hhi.xlsm`，140任务、半帧、无重建。
每组任务全部返回即写入该组 Excel，其他组继续编码；重试结果更新会刷新表格。
新模式仍由编解码进程的 `TS_FIXED_PREDICTOR` 环境变量选择，由 batch 同步设置。
结果放 `experiments/ts_conditional_v1/<mode>/{LB_BCE,RA_CD}/JVET-hhi.xlsm`。

## R8 设计检查（2026-09-25，仅规格，尚未实现编码模式）

24组设计与分阶段运行范围见 [R8 实验设计](../TS_Predictor_R8_Experiment_Design.md)。
首轮现固定八组MODE 1/4/8/13/15/16/17/19，替代旧10组安排，见[首轮八组设计](../TS_Predictor_R8_First8_Design.md)。
`ts_r8_experiment_manifest.json` 是开发规格，不是 `batch_test.py --manifest` 的任务CSV。
当前不要向 batch 传预留的 `r8_*` 模式，也不要把 R8_MODE 写入尚未支持它的源码后冒认为生效。

```bash
python3 scripts/ts_r8_design_check.py
python3 scripts/ts_r8_first8_reference.py
python3 scripts/ts_r7_results_for_r8.py --out runs/ts_r8_design/r7_evidence
python3 -m unittest discover -s scripts -p 'test_ts_r8_design.py'
```

前两项只检查数学规格；第三项复核本地已有R7 CE表格，不启动编码、不补点、不修改源表。
结果收件目录为 `experiments/ts_predictor_r8/r8_<MODE>_<name>/`，存在目录不等于完成实验。
