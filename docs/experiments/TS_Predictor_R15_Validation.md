# R15 实现验收（2026-10-26）

结论：**18 个新子实验和 3 个既有对照已实现，并通过数学、原生局部语法、双来源短前缀及输出口径验收。完整 96 流尚未运行，不能据此判断新增映射的总体收益。** 本轮没有运行 EncoderApp，没有修改正式 RD/BD-rate。

设计基于远端 `b56e30a`，实施见 [R15 文档](TS_Predictor_R15_Implementation.md)。派生数据与精确 SHA 位于 [验收目录](results/ts_r15_validation_20261026/README.md)。默认源码宏为 0；本地另保留启用观察的 `build/ts-r15/bin/DecoderAppR15Audit`，`build/ts-r15/bin/DecoderApp` 是重新构建的宏关闭版本。

## 数学与原生语法

| 检查 | 实际覆盖 | 结果 |
|---|---|---|
| 三引擎一致性 | 18,000 个邻域 ×21 方法=378,000 组 NAIVE/PREFIX/FAST 比较 | 分数、候选增量轨迹、root、返回/搜索前缀、最终完整动作一致 |
| 正反映射 | 13,048,128 次检查 | 全通过 |
| 独立 Python/C++ | 516 个邻域，10,836 个方法输出 | 动作和分数完全相同 |
| 局部算术 Writer→Reader | 24 个合成 TU ×22 动作策略=528 次 | 恢复系数、bins/context/value/order、fractional bits、出口状态、pass/预算一致 |
| 因果扰动 | 3,960 次当前及未来系数变更 | 当前动作不变 |
| 新 Python 用例 | 12 项 | 全通过；含缺来源/缺方法/不完整、不同来源NZ的正确等权估计 |
| 旧实现回归 | R13 6项、R14 4项、旧审计统计14项、默认统计开关2项 | 全通过 |

映射测试包含：小域所有长度≤4的有序前缀、合法完整大幅值域的旧单目标一致性，以及 range=8/15/20 下含最大幅值的六目标排列轮换；不是只抽样测试几个小幅值。非法零目标、重复目标、越界、数量和 padding 拒绝。

冻结的三个数值反例及 CE01 的 `n=3` 回归通过；G2/N2 等价独立强制检查。Rice=0..8、稀疏 n=0..5、重复值、等权与22111、大幅值和有限 escape 都在纯函数中覆盖。

局部语法夹具覆盖 Y/Cb/Cr、4～16 的方形和矩形 TU、Rice=1..8、全零 CG、regular 预算耗尽、正/负大幅值、任意六目标动作。它只调用局部算术编码类，没有运行视频编码程序，也不声称已经完成新正式 Writer/Reader 集成。

## 已有码流双来源短测

使用现有 `Johnny_QP32_prefix17` 两份码流，源 R13-1/2 分别以各自原生预测规则解码。

| 来源 | 帧数 | 目标 TS TU | 系数 | 非零 | 原生完整核验 | 全21列 | SEI / 开关重建 |
|---|---:|---:|---:|---:|---|---|---|
| R13-1 | 17 | 10 | 2112 | 41 | 通过 | 完整 | 通过 |
| R13-2 | 17 | 10 | 2112 | 41 | 通过 | 完整 | 通过 |

每来源比较了：宏打开且观察开启、宏打开且观察关闭、宏关闭三种程序状态。各来源内部逐帧 MD5 完全相同，17帧均通过编码端 SEI MD5；不是仅比较两个观察器输出一致。

每个 TU 的原生 bin 值、context id、顺序、fractional bits、完整出口模型、regular budget、pass 边界都与真实 Reader 捕获一致。不同方法始终从相同 TU 入口开始，每个分支独立推进，全部21列完整。由于完全相同动作可复用回放，每来源实际只需29次回放；这不是跳过方法。

4 个限量快照在**新进程**加载，21组动作和 rate 与捕获时逐项相同。动作字典由独立 Python 重算核验；错误协议、q、scan、目标、方法列和动作 id 共6类拒绝。线上实现不读旧 TSCPRED 或全片外部动作 schedule。

短前缀高度稀疏，仅验证流程及副作用，不足以覆盖真实内容分布、评价复杂度或得出 R15 的优劣。更多边界由合成夹具补足，不将合成覆盖说成真实视频出现过。

## 文件、内存与计时

最终短测默认1个 worker，受控包装记录约 **304 MiB** 树 RSS 采样峰值，3 GiB 每进程地址空间上限、2 GiB 树 RSS 监测阈值，未触发停止。早期其它验收运行最高约306MiB。没有全片逐系数/逐bin落盘；每流 summary 约0.2MiB，Git 中本轮小型派生资料约0.11MiB。完整96流尚无实测内存峰值。

选择器微基准：同一4096行固定合成 H、CPU亲和性0、每引擎1次预热和5次轮换。所有 checksum 相同。以下是每位置中位数 ns；只用于同语义实现选择，不代表真实编码时间。

| 新编号 | 原编号 | NAIVE | PREFIX | FAST |
|---|---:|---:|---:|---:|
| R15-2 G_EQ_K2 | 4 | 276.9 | 189.0 | 220.8 |
| R15-3 G_EQ_K3 | 5 | 358.1 | 221.0 | 272.5 |
| R15-5 G_EQ_K6 | 7 | 432.5 | 243.5 | 295.5 |
| R15-9 N_EQ_K6 | 11 | 444.1 | 248.5 | 299.0 |
| R15-13 D_EQ_K2 | 15 | 412.7 | 280.8 | 317.0 |
| R15-16 X_EQ_K3 | 18 | 4267.6 | 3479.7 | 3569.7 |

FAST 的平台代表筛选仍有开销，本机该 trace 上没有超过 PREFIX，因此当前审计默认 PREFIX。完整操作计数、各次时间及独立 map/unmap 时间保留在 CSV。不据该表推算生产编码/解码复杂度；没有跨机器或视频人口的复杂度承诺。

## 可复现入口与当前边界

```bash
# 新的输出目录；编译/宏操作详见 scripts/ts_multi_mapping/README.md
python3 scripts/ts_multi_mapping/validate.py validate --build-dir build/ts-r15 --output runs/r15_validation
python3 scripts/ts_multi_mapping/run.py plan --prefix --output runs/r15_prefix/plan.json
python3 scripts/ts_rule_lab/bounded_run.py --receipt runs/r15_prefix/resources.json --cache-root runs/r15_prefix -- python3 scripts/ts_multi_mapping/run.py replay --plan runs/r15_prefix/plan.json --decoder build/ts-r15/bin/DecoderAppR15Audit --output runs/r15_prefix/replay --verify-off --fixtures --jobs 1
python3 scripts/ts_multi_mapping/validate.py snapshots --input runs/r15_prefix/replay --native runs/r15_validation/bin/syntax --output runs/r15_prefix/snapshot_checks
```

`DecoderAppR15Audit` 是本地留存的已开启程序；其它环境按脚本 README 将宏设1并构建后，使用其 `DecoderApp` 路径。未上传新程序，源码和构建命令可复现；已有96条R13码流交付目录不变。

全96流计划和 dry-run 已通过，输入为12内容×4QP×2来源，按各文件 EOF；完整命令见[脚本README](../../scripts/ts_multi_mapping/README.md)。严格相同输入/程序/源码/方法的 resume 已验证；缺列/缺来源不填0，范围不足不输出伪完整均衡值。

待完成：正式96流总体/尾部结果、视频内容的 selector 计时、可选单点 oracle 及任何闭环 RDOQ/BD-rate。当前没有“Promising/Weak/Negative”的新效能结论，不自动重算旧结果，也不因实现通过就进入正式编码工具。
