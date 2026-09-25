# Conditional predictor revision 1：本地验证

2026-09-16，GCC 11.4 Release，LTO OFF，独立 `build/ts-conditional` 与 `build/ts-conditional-off`。
旧 `build/ts-fixed`、`build/ts-anchor` 二进制未重建。

## 已通过

- 编码器、解码器及 C++ 测试目标编译成功；新宏 OFF 编码器编译成功。
- `test_ts_fixed_defaults.py`：6 tests，通过全部9种模式的编译默认值和81组环境覆盖，非法默认值/组合拒绝。
- `test_ts_fixed_batch.py`：4 tests，旧脚本行为回归通过；批量脚本源码未修改。
- `TsFixedPredictorTest`：QP31/32/33、状态符号、整数衰减/饱和、代理成本/remap、置信条件及邻域边界；
  实际 ROM 中64种完整扫描形状，1,267,924次因果邻居检查通过（扫描形状集合不等于 TS 合法尺寸清单）。
- `ts_conditional_smoke.py --off ...`：11种场景 × 9种模式/构建，共99个两帧编解码任务，全部 decoded-picture hash 通过。
  场景含 q22/q32/q33、no TS、q0、lossless、TSRC off、DQP、BDPCM、LB、RA。
- 11种场景中 Current 与保留 anchor bit-exact，新 OFF 与同一 anchor bit-exact。
- QP22/32 的 q32 与 fixed directional bit-exact，q32_ewma 与 ewma bit-exact；
  QP33 的 q32/q32_ewma 与 Current bit-exact。此处使用关闭 intra QP offset 的合成边界配置。
- TS off 和 TSRC off 下所有新模式与 Current bit-exact。
- 最终 Writer 与 Reader 逐 CG 的状态、选择、收益、剩余预算和最终系数 hash 完全一致。
  所有自适应 TU 的 CG0 均为 state=0、Current。
- 五个新模式在测试集合内均实际改变过 remapped magnitude，而非从未启用。
- 另外5个 q0 编码关闭 `TS_COND_TRACE` 后仍与对应调试版本 bit-exact。
- 无重建视频输出；保留一个合成输入 YUV，整个 smoke 输出约4 MiB。

| 模式 | trace CG数（排除BDPCM路径） | 相对 Current 实际 remap 变化位置数 |
|---|---:|---:|
| q32 | 1477 | 387 |
| conf2 | 1467 | 192 |
| prev | 1446 | 79 |
| ewma | 1446 | 95 |
| q32_ewma | 1446 | 95 |

这些数值只用于证明测试覆盖，不用于判断有效率或工程收益。普通QP小合成内容下历史模式有不少场景
完全不切换，因此额外使用低QP/lossless 检查了真实切换和编码/解码状态一致性；没有据此更改算法阈值。

## 边界

没有运行正式 LB BCE / RA CD，不提供新 BD-rate。没有证明所有输入、所有工具组合或所有 bit depth 都已覆盖。
DQP/BDPCM 场景启用对应工具，不代表每一个内部子分支均有命中覆盖；外部实际配置应先做短帧 hash 检查。
主要 smoke 是8-bit输入、10-bit内部，lossless 为8-bit内部。各服务器应保存模式 banner、配置和解码日志。
旧 anchor 二进制沿用先前已经与原版核对的构建；本轮没有重新归档/重建最初提交的源码。

机器可读本地结果：`runs/ts_conditional_smoke/validation.json`、`summary.csv` 与逐任务编码/解码日志。
复现方式见 `TS_Conditional_Predictor_Implementation.md`。正式长跑勿启用 CG trace。
