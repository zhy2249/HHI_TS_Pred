# TS 实验统计默认关闭

更新：2026-10-04。本说明取代历史文档中的“R2～R6、R8/R9 默认开启统计”约定。
只修改观察默认值，不修改算法、模式编号、predictor、必要历史状态或码流语法。

## 当前行为

| 范围 | 统计接口 | 默认 | 显式开启 |
|---|---|---|---|
| R2～R6、R8～R12 | 对应 `TS_Rn_STATS` 环境变量 | 关闭 | `TS_Rn_STATS=1` |
| R7 shadow | `JVET_BJUT_TS_R7_SHADOW` 编译宏＋`TS_RATE_SHADOW` 环境变量 | 均关闭 | 宏为1且环境设1 |
| R7 RDOQ shadow | 同一编译宏＋`TS_RATE_RDOQ_SHADOW` | 关闭 | 宏为1且环境设1 |
| 最初固定 q 分析 | `JVET_BJUT_TS_PRED_ANALYSIS`＋`TS_PRED_STATS` 输出路径 | 关闭 | 沿用专用分析流程 |

上述 Rn_STATS **不是新增的 C++ 宏**，仍是已有运行时接口。
不需要为了关统计将 `*_MODE` 或 `*_EXACT_OPT` 设为 0。
`TypeDef.h` 实验开关区域已增加集中说明，R3/R6 启动信息显示 `stats-default=off` 和实际状态。

R2/R3/R4/R5/R6/R8/R9 的未设置状态由开启改为关闭，显式 0/1 行为不变。
R10/R11/R12 本来默认关闭，保持不变。只建议使用明确的 0/1，不依赖旧接口其它字符串的兼容语义。

修改入口：

- `source/Lib/CommonLib/ContextModelling.cpp`：各轮最终 Writer 统计入口。
- `source/Lib/EncoderLib/CABACWriter.cpp`：R2-4 的额外真实 context 观察也默认关闭。
- `source/Lib/EncoderLib/TsR8Search.h`、`source/Lib/CommonLib/TsR9Quant.h`：搜索统计同样默认关闭，
  **实际 R8/R9 搜索、trial 与 RD 决策并未关闭**。
- `source/Lib/CommonLib/TsFixedPrediction.h`：R3/R6 实际状态 banner；原 R11/R12 开关仍在此处。

trace 保持独立、默认关闭。`TS_COND_TRACE` 的旧接口按环境变量是否存在判断，值为 0 仍开启，关闭须 unset。
已有 shell 环境显式导出的 STATS=1/TRACE/SHADOW 仍会生效；“默认关闭”不是强制禁止观察。

## 脚本

R6/R8/R9/R10 的正式 LB CE wrapper 以及 R8 preflight 改为默认 STATS=0，并尊重外部显式 1。
R11/R12 wrapper 已默认关闭，不改实验队列、帧数、输出目录、逐组写表或重建策略。

需要统计时显式请求，例如：

```bash
TS_R6_STATS=1 bash scripts/run_ts_r6_lb_ce.sh --dry-run
TS_R8_STATS=1 bash scripts/run_ts_r8_preflight.sh --dry-run
```

上面的 dry-run 只用于检查命令，真正采集需在获准运行时去掉它。普通直接编码、batch 运行均沿用原参数，
不设置 TS_Rn_STATS 即默认不采集；关闭统计后的日志不能再被当作含 activity 数据的日志。

例外不是正式计时入口：`run_ts_rate_shadow.sh` 的目的就是显式采集 shadow，仍开启 TS_RATE_SHADOW；
各观察正确性测试也显式开启其需要核验的统计。不得以它们的耗时代表纯算法复杂度。
依赖旧默认值的 conditional smoke 观察阶段改为显式启用 R2～R6 统计，其关闭分支仍保持 0。

## 续跑与更新二进制

源码默认值变更需重新编译服务器的 EncoderApp/DecoderApp，旧二进制不会因更新脚本自动改变直接运行时的默认值。
编译继续使用项目已有 Release 命令，无新 CMake 算法开关。

`batch_test.py` 指纹新增完整观察环境快照，含之前遗漏的 R2～R6 STATS 和 TS_COND_TRACE。
未设置、显式 0、显式 1 保守区分，不改变实际任务环境继承。
旧指纹会安全失效一次，因此不要直接对已有整组结果目录启动续跑而假设全部任务都将跳过；
统计设置或二进制变化建议新建输出目录，保留旧结果。未修改任何现有 marker、日志或工作簿。

## 验证范围

全量 166 项单元测试通过，包含生产开关表达式的未设置/0/1 检查、启动 banner、wrapper 和续跑指纹；
编码器/解码器及局部测试编译通过，十模式的修改前后×默认/关/开完整 CABAC 字节和最终 q/absSum 一致。
具体完成情况登记于统一实验记录。没有运行完整帧/序列编解码，没有新增 BD-rate 或整编码性能结论。

新增回归检查：`scripts/test_ts_stats_defaults.py`（生产开关表达式）、
`scripts/test_ts_stats_wrappers.py`（截获exec及smoke环境，不启动编码）、
`scripts/test_ts_stats_fingerprint.py`（模拟续跑）。这些均纳入原 unittest discovery。

本轮只自动同步本说明、索引、脚本 README 与实验记录。源码和脚本修改保留本地工作树，
不自动混入此前未提交源码或上传原始实验数据。
