# R5 实现与使用

版本 R5-20260921-v1；设计见 `TS_Predictor_R5_Experiment_Design.md`。
原 R3/R4 公式和旧二进制保持不变；两个新模式已接入 TS-RDOQ/Writer/Reader 共用入口。
**目前仅正确性/活动预检，未证明增量收益。先读验证报告，不建议直接两组完整 CTC。**

## 1. 直接由 TypeDef.h 选择

编辑 `source/Lib/CommonLib/TypeDef.h`，重新编译 Encoder 和 Decoder：

```cpp
#define JVET_BJUT_TS_FIXED_PREDICTOR 1
#define JVET_BJUT_TS_FIXED_NOPRED 0
#define JVET_BJUT_TS_FIXED_GRADIENT 0
#define JVET_BJUT_TS_FIXED_DIRECTIONAL 0
#define JVET_BJUT_TS_CONDITIONAL_MODE 0
#define JVET_BJUT_TS_R2_MODE 0
#define JVET_BJUT_TS_R3_MODE 0
#define JVET_BJUT_TS_R4_MODE 0
#define JVET_BJUT_TS_R5_MODE 1 // 1或2；0不选择R5
```

| R5_MODE | 名称 | 内部policy | 结果目录 |
|---|---|---:|---|
| 1 | r5_margin_first | 23 | r5_1_margin_first |
| 2 | r5_current_veto | 24 | r5_2_current_veto |

交付仍为 master=1、所有模式=0，即 Current；**只打开 master 不会启用实验**。
不传实验参数时执行宏默认；`TS_FIXED_PREDICTOR` 或原 batch `--fixed-predictors` 可显式覆盖。
新旧默认全部互斥；非法 R5 值、master关闭却选实验、与旧反事实统计同时启用均报错。
运行覆盖不能绕过编译宏冲突。实验mode不写入码流，编解码器必须使用一致有效模式。

应核对 banner，例如模式2：

```text
EXPERIMENT: TS_FIXED_PREDICTOR=r5_current_veto; syntax=experimental-v1
TS predictor default: r5_current_veto; selection: TypeDef.h default
TS R5 revision=R5-20260921-v1; mode=2; anchor=current; parent=r3_risk_guard; scope=YUV; TU-local; stateless; cost=syntax-proxy; rule=Current-only-causal-veto
```

## 2. 构建

只用 CMake 指定独立构建目录，不用它选择实验宏，不覆盖正在长跑的旧程序：

```bash
cmake -S . -B build/ts-r5 -DCMAKE_BUILD_TYPE=Release \
  -DNX2_TOPLEVEL_OUTPUT_DIRS=OFF -DNX2_ENABLE_LINK_TIME_OPT=OFF
cmake --build build/ts-r5 --target EncoderApp DecoderApp TsR5CodecTest -j 4
```

对应程序 `build/ts-r5/bin/EncoderApp`、`build/ts-r5/bin/DecoderApp`。
`build/ts-r5-off` 只用于本轮 macro-OFF 回归；恢复头文件后不要随手重编它并继续称其为 OFF。

## 3. 代码与统计

- `TsFixedPrediction.h`：新增两个模式名、默认和有效 banner；原 `guardedLocalPredict` 不变。
- `TsR5Prediction.h`：两组纯函数；复用冻结的 R3 因果 primitive 与五偏移，无递归R5、无持久q缓存。
- `ContextModelling.h`：公共预测分派，原 RDOQ/Writer/Reader 钩子自然复用；不修改 sign 或 syntax。
- `ContextModelling.cpp` / `TsR5Stats.h`：仅最终 Writer 在线聚合，RDOQ finish 不记录历史；debug私有预算回放不参与预测。
- 不依赖系数符号，因此 Reader 原有幅值路径即可，未增加 sign 视图或新的码流标志。

默认日志 `TS_R5_STATS_HEADER` / `TS_R5_STATS`；`TS_R5_STATS=0` 关闭，不改变编码。
长跑不要设置 `TS_COND_TRACE`，它只用于短测的逐CG同步诊断。
正常日志无 coefficient 行，无 POC 键，按分量、真实 W/H、CU-QP、intra/BDPCM、CG数量/位置在线聚合。

必须区分：

- `remap_different`：相对 Current；包含继承自 R3 的作用。
- `remap_vs_r3`：本实验最终q上相对原R3的映射差异，才是本轮增量活动诊断；不是两次编码CG配对。
- `accepted_parent_reordered`：仅R5-1，原R3已接受但被重排。
- `fallback_rescued`：仅R5-1，原R3回退位置改成其他预测。
- `veto_identity/veto_other`：仅R5-2，原R3的identity/其他幅值被Current否决，两者之和为veto。
- mode1 accepted是H>0的非Current winner；mode2 accepted是Current否决成功，不能混用其比例。
- hit/under/over、modified分布、代理损益均是最终TS条件样本；不能当Oracle/η或真实CABAC rate。

```bash
python3 scripts/ts_r2_activity.py runs/ts_r5_smoke --revision r5 \
  --out runs/ts_r5_smoke/activity.csv
```

## 4. 批量与分析复用

没有新写一套批量调度器。原 `batch_test.py` 已注册两模式和编号目录，继续保持共享任务池、
不输出重建、resume、失败重试、每组完成即写自己的 XLSM；不等待另一组全部完成。
活动和基础BD分析脚本新增 `--revision r5`，保留 Current Reference 与完整点检查、分量BD后6:1:1。

以下只检查将来的56项LB CE半帧计划，不启动编码；本轮尚未满足增量活动准入，不建议直接去掉dry-run：

```bash
python3 -u scripts/batch_test.py --preset LBeu --class C,E --qps 22,27,32,37 \
  --fixed-predictors r5_margin_first,r5_current_veto \
  --encoder build/ts-r5/bin/EncoderApp --decoder build/ts-r5/bin/DecoderApp \
  --input-dir /home/zhy/videos --jobs 10 --decode-md5 --no-recon \
  --xlsm-report --xlsm-template scripts/JVET-hhi.xlsm \
  --out-dir runs/ts_r5_LB_CE_half --dry-run
```

只运行宏默认时省略 `--fixed-predictors`。不加 `--full-sequence`；不重跑完整 Current anchor。
返回文件放 `experiments/ts_predictor_r5/r5_<MODE>_<name>/{LB_CE,LB_B,RA_CD}/`，不得只交无模式身份的表格。

```bash
python3 scripts/ts_r2_analyze.py --revision r5 --run experiments/ts_predictor_r5 \
  --phase LB_CE --out runs/ts_r5_results/analysis_611
```

目前无正式结果，运行上述分析会明确报缺点，不生成伪完整平均。相对R3直接BD与三曲线共同质量区间仍需完整结果后重新积分。

## 5. 验证入口

```bash
g++ -std=c++17 -O2 -Isource/Lib/CommonLib scripts/ts_r5_design_check.cpp -o /tmp/ts-r5-design-check
/tmp/ts-r5-design-check
TS_FIXED_PREDICTOR=r5_margin_first build/ts-r5/bin/TsR5CodecTest
TS_FIXED_PREDICTOR=r5_current_veto build/ts-r5/bin/TsR5CodecTest
python3 scripts/test_ts_fixed_defaults.py
python3 scripts/test_ts_fixed_batch.py
python3 scripts/test_ts_r2_analysis.py
python3 scripts/ts_conditional_smoke.py --r5 \
  --encoder build/ts-r5/bin/EncoderApp --decoder build/ts-r5/bin/DecoderApp \
  --anchor build/ts-anchor/bin/EncoderApp --off build/ts-r5-off/bin/EncoderApp \
  --legacy-encoder build/ts-r4/bin/EncoderApp --out runs/ts_r5_smoke --jobs 4
```

最后一条要求OFF程序已按头文件master=0单独构建，再恢复master=1。
`validation.json` 分别报告正确性和 `r5_incremental_activity_covered`；后者为false时不能把前者的PASS称为本轮有新增有效作用。
