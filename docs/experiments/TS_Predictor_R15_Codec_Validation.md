# R15-CODEC-v1 局部验收（2026-10-26）

结论：18 个 R15 方法已接入真实 TS-RDOQ、CABACWriter/BitEstimator 和 CABACReader，并通过下列局部检查。**没有运行 EncoderApp、没有新视频编码或 R15 BD-rate。** 现有 R13 前缀解码仅用于旧路径回归。

完整小型派生数据、程序/源码 SHA 见 [验证数据目录](results/ts_r15_codec_validation_20261026/README.md)。相同编号的第一阶段固定 q 审计记录另见 [原验证记录](TS_Predictor_R15_Validation.md)，不将两种验证互相代替。

## 实际执行与覆盖

| 检查 | 实际覆盖与结果 |
|---|---|
| 构建 | Release/GCC 11.4/C++17，EncoderApp、DecoderApp、TsR15NativeTest、TsR13NativeTest、TsR14NativeTest 构建通过；2个编译任务，LTO关闭 |
| 默认宏/覆盖/互斥/调度 | 33项Python检查通过；含18个宏默认、完整runtime覆盖矩阵、旧算法/缓存冲突、错误编号、旧程序身份拒绝、哈希/帧数、共享任务池及续跑身份 |
| 旧映射规格 | 12项Python映射/审计检查通过；原三引擎全域测试没有因本次新增接口而改写 |
| 每个R15模式的真实语法 | 180个固定q合成TU，1718个CG；2～32边长的square/rectangular、Y/U/V、I/P/B、QP/Rice变化、大幅值、零CG、低预算/纯bypass、BDPCM |
| 每个模式的量化 | 288个用例；含23份全零输入、40份非零输入最终整TU全零，另覆盖普通变换、TSRC禁用、lossless、RDOQ关闭、2维小块和两种BDPCM；重复清零/重入后的q及输入/上下文无副作用 |
| 量化后语法往返 | 每模式208份符合夹具非零/TSRC条件的量化结果，再进入真实Writer→Reader；不是仅测试数学逆函数 |
| 费用/上下文 | 每CG的独立完整Action回放与真实CABAC BitEstimator fractional bits相等；真实Writer出口context、regular-bin预算和Reader恢复的q相等 |
| 因果性 | 将当前/后续位置替换成极值，当前完整Action不变；活动位置还与NAIVE引擎逐Action比较 |
| 等价对照 | R15-2与R15-6完整记录SHA/长度相等；R15-1与旧NoPred在共同目标范围内相等 |
| 非目标范围 | 全部18个R15模式的非目标记录与Current一致 |
| 统计无副作用 | 18模式各自stats=0/1完整记录SHA相等；没有逐bin/逐系数落盘 |
| master关闭 | 独立关闭总宏构建的TsR15NativeTest与master开启的Current完整记录相等 |
| 旧实现回归 | 保留的旧TsR13NativeTest与新构建逐一比较Current、R2-2、R3-1、R6-2、R13-1/2；q、语法字节、fractional bits、预算和context字段的完整流式SHA/长度相等 |
| 已有码流 | 新DecoderApp解码Johnny QP32的R13-1/2前缀各17帧；逐帧MD5与此前记录一致，全部通过编码端SEI；不写重建视频 |

上表的“288”是用例数：为验证重入，每个用例多次调用量化器，不应将统计输出的人口当成288个最终视频TU。宽高与QP覆盖来自合成夹具，不代表完整CTC分布。旧R14本轮完成构建及宏/调度回归，没有声称其全部15个闭环模式都重跑了视频。

完整记录每次约数百MiB，通过FIFO送入SHA256，最多三个1MiB哈希缓冲；不保存原始记录。最终本地native全套约2分55秒，GNU time记录最大RSS 128928 KiB（约126MiB）。这不是生产编码时间，也不是并发全进程树峰值上界。提交的派生验证文件约70KiB。

## 证明新路径实际活动

以R15-3合成夹具为例（不是视频收益统计）：

- 固定q语法夹具24356个因果检查位置中，12137个返回多目标动作。
- RDOQ合计31776个试验位置，7772个位置的up与原候选不重复，462次满足映射到1而加入up；302个位置相对Current的加入门槛改变。
- 最终Writer regular非零人口5059，1480个实际映射不同于Current。该人口排除零值和纯bypass，不能用来计算整体TS使用率。

全部18组的对应计数见 `activity.csv`。这证明执行路径没有退化成始终Current，但不能证明映射选择带来RD收益。

## 验证中澄清的两个问题

1. 起初把R15-1与旧NoPred的所有工具路径一起要求等价，检查没有通过。定位发现原 `QuantRDOQ::quant()` 的TS分派不会因TSRC禁用自动避开TS-RDOQ，旧NoPred会在这条路径继续改变评分；R15按设计在TSRC禁用时保留Current。改为对共同目标范围要求NoPred等价，非目标范围要求Current等价；二者均通过，未修改旧算法。
2. 旧R14批量测试期待R13未启用诊断时也包含新增DIAG字段，与早已存在的“保留旧成功标记”行为不符。本次仅修正测试：未请求诊断时检查旧字段，显式DIAG时检查完整字段。没有修改该生产规则。

`listed-levels`记录候选列表长度；原RDOQ可以提前返回，因此它不是完成了多少次候选rate评估。`up-added`记录加入列表的次数，不能据其与Current的差异推断量化质量改善。

## 可复现命令与交付范围

正常构建和运行见 [脚本说明](../../scripts/README_ts_r15_codec.md)。本地完整native命令：

```bash
python3 scripts/test_ts_r15_native.py --build-dir build/ts-r15-codec --legacy-build-dir build/ts-r14 --master-off-build-dir build/ts-r15-master-off --output-dir runs/r15_codec_checks
PYTHONPATH=scripts python3 -m unittest test_ts_r15_defaults test_ts_r15_batch test_ts_r14_batch test_ts_r14_defaults test_ts_r13_batch test_ts_stats_defaults
PYTHONPATH=scripts/ts_multi_mapping:scripts python3 -m unittest test_r15
```

两个比较目录只有实际存在相应测试可执行文件时才可使用；脚本不下载/伪造旧二进制。master关闭的构建仅用于验收，隔离目录以 `CMAKE_CXX_FLAGS=-DJVET_BJUT_TS_FIXED_PREDICTOR=0` 构建测试目标；正式实验仍直接修改TypeDef宏或显式runtime覆盖，不依赖CMake选择算法。

本提交交付源码、测试、文档和小型派生证明；本地 `build/ts-r15-codec/bin/` 已有编码器/解码器，其SHA记录在manifest。**不声称新ELF已作为GitHub二进制发布。** 没有新增/复制上传原始视频、码流、重建文件或工作簿。

尚待用户后续运行：R15真实视频短测的hash、完整CTC、编码/解码时间与闭环BD-rate。原有正式结果未修改；固定q潜力与新编码结果继续分别解释。
