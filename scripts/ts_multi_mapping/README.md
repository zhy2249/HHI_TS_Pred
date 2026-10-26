# R15 操作说明

在仓库根目录执行；Python >=3.10 标准库、CMake >=3.13、GCC/G++ 11（本地验证版本）和 make。Linux x86_64，当前工程构建最低 SSE4.1，AVX2 路径由工程运行期分派。没有 EncoderApp 调用，没有视频输入要求。

先将 `source/Lib/CommonLib/TypeDef.h` 中 `JVET_BJUT_TS_R15_ANALYSIS` 从默认 0 改成 1，保留 `JVET_BJUT_TS_FIXED_PREDICTOR=1`。CMake 只构建，不选择实验。来源模式由 manifest 决定，18 个新方法与 3 个既有对照会一起回放。

```bash
cmake -S . -B build/ts-r15 -DCMAKE_BUILD_TYPE=Release -DNX2_TOPLEVEL_OUTPUT_DIRS=OFF -DNX2_ENABLE_TRACING=OFF -DNX2_OPT_TARGET_ARCH=
cmake --build build/ts-r15 --target DecoderApp -j2
build/ts-r15/bin/DecoderApp --ts-r15-version
```

纯函数、独立 Python 和局部语法验收（不启动视频编码）：

```bash
python3 scripts/ts_multi_mapping/validate.py validate --build-dir build/ts-r15 --output runs/r15_validation
```

双来源 17 帧短前缀，保存最多两个小 TU 夹具并核验开关重建。各输出目录用新名字；不能将不同版本结果混合续跑。

```bash
python3 scripts/ts_multi_mapping/run.py plan --prefix --output runs/r15_prefix/plan.json
python3 scripts/ts_rule_lab/bounded_run.py --receipt runs/r15_prefix/resources.json --cache-root runs/r15_prefix -- python3 scripts/ts_multi_mapping/run.py replay --plan runs/r15_prefix/plan.json --decoder build/ts-r15/bin/DecoderApp --output runs/r15_prefix/replay --jobs 1 --verify-off --fixtures
python3 scripts/ts_multi_mapping/validate.py snapshots --input runs/r15_prefix/replay --native runs/r15_validation/bin/syntax --output runs/r15_prefix/snapshot_checks
python3 scripts/ts_multi_mapping/run.py report --index runs/r15_prefix/replay/dataset_index.json --output runs/r15_prefix/report
```

选择器计时（默认固定合成 H trace，5 次轮换；不代表视频平均复杂度）：

```bash
python3 scripts/ts_multi_mapping/validate.py benchmark --native runs/r15_validation/bin/selectors --output runs/r15_benchmark --repeats 5
```

后续正式 96 条既有码流全量解码审计，先 dry-run。读取至各文件 EOF；两来源、公平方法全集、四 QP 不变。没有动作 schedule 的第二遍解码需求。`--verify-off` 会额外做一次关闭观察器的解码，只用于重建副作用验证。

```bash
python3 scripts/ts_multi_mapping/run.py plan --output runs/r15_full/plan.json
python3 scripts/ts_multi_mapping/run.py replay --plan runs/r15_full/plan.json --decoder build/ts-r15/bin/DecoderApp --output runs/r15_full/replay --dry-run
python3 scripts/ts_rule_lab/bounded_run.py --receipt runs/r15_full/resources_01.json --cache-root runs/r15_full -- python3 scripts/ts_multi_mapping/run.py replay --plan runs/r15_full/plan.json --decoder build/ts-r15/bin/DecoderApp --output runs/r15_full/replay --jobs 1 --resume
python3 scripts/ts_multi_mapping/run.py report --index runs/r15_full/replay/dataset_index.json --output runs/r15_full/report
```

中断续跑使用相同程序/源码/目录及 `--resume`；包装 receipt 改为 `resources_02.json` 等新名字。输入、源码、目录、程序或输出摘要不匹配会拒绝，不能强行复用。失败 attempt 保留；成功条目按摘要跳过。目录锁防止重复任务。最多 `--jobs 2`，先依据资源记录判断。

若码流交付目录不同，给 `plan --manifest /path/to/manifest.json`；文件路径相对该 manifest 解析。默认读取 `deliveries/r13_decode_audit_impl2/manifest.json`。LFS 指针、流 SHA/长度不符、错误来源模式、缺列或不完整回放均报错。

主要输出为 `method_summary.csv`、`by_sequence_qp.csv`、`by_stream_component.csv`、`strata.csv`、`mapping_activity.csv`、`score_rate_disagreement.csv`、`worst_cases.csv`、`selection_report.csv` 及 manifest/receipts。数据是固定最终 q 的条件 fractional bits；不写入正式 BD-rate 台账。详细字段和边界见 [实施文档](../../docs/experiments/TS_Predictor_R15_Implementation.md)。
