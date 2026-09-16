# TS predictor implementation validation

完成日期：2026-09-11。原版来自 `git archive 16f32500956d74e122e03355e3fc239f974d87cf` 的独立源码快照，路径 `/tmp/ts-pred-original`。三版本都使用 GCC 11.4、Release、LTO OFF。

宏OFF：`build/ts-anchor/bin/EncoderApp`；宏ON：`build/ts-analysis/bin/EncoderApp`；原版：`/tmp/ts-pred-original/bin/release/EncoderApp`。解码用宏OFF构建的原生 `DecoderApp`。

## 结果

| 合成用例（64×64，2帧） | 最终TSRC CG数 | 原版/OFF/ON SHA256相同 | Decoder hash |
|---|---:|---|---|
| AI 420 | 23 | 是 | 通过 |
| LB 420 | 25 | 是 | 通过 |
| AI 444，CCSAO OFF | 13 | 是 | 原版已有第2帧chroma mismatch，三版相同码流 |
| BDPCM enabled | 40 | 是 | 通过 |
| Lossless，适配现有lossless配置 | 768 | 是 | 通过 |
| TSRC-disabled lossless | 0 | 是 | 通过；TU census仍记录TS |
| TS disabled | 0 | 是 | 通过；CG CSV只有header |

总共869个最终TSRC CG。AI/LB/444/BDPCM分别包含7/5/4/13个全零CG；BDPCM样本中17个CG实际启用BDPCM。lossless样本来自283个coded TS TU，覆盖多CG历史路径。

详细逐用例三份SHA256在 `runs/ts_smoke/validation.json`；编码与解码日志、二进制、CG CSV和受限debug均在该目录。该目录为生成产物，已加入gitignore，无需提交测试码流。

实际观察到14种 `(W,H,CG/TU)`：

```text
(2,8,1) (2,16,2) (4,4,1) (4,8,2) (4,16,4)
(8,2,1) (8,4,2) (8,8,4) (8,16,8)
(16,2,2) (16,4,4) (16,8,8) (16,16,16) (32,4,8)
```

这证明采集不局限8×8，也覆盖2样本边长chroma和不同CG/TU；**不代表所有理论可达尺寸在smoke中均已出现**。正式每种尺寸的覆盖仍以size census为准。

## Rate与因果性

每个TU运行内置整数相等检查：Current的CG counterfactual sum = Current continuous-path cost = 原生完整 `CABACWriter::residual_codingTS` 在真实TU-entry context上的 `BitEstimator_Std` cost。869个CG所在TU未触发任何不一致。

Python分析器从以前的CSV行独立重放previous/cumulative/recency/confidence/simple五个selector，验证当前行mode、所选rate、history_nonzero、confidence margin；验证histogram与coefficient count守恒、Oracle最小值、Current path一致。CG0强制Current通过重放自动验证。所有实际scan的左/上邻居因果顺序在编码observer中检查。

受限debug共960条“coefficient × predictor”记录通过独立数学公式检查（不是960个互不重复coefficient）。包括disabled映射与逆映射。下面是lossless TU0/CG0的Current样例；rate为该coefficient跨三pass的fractional cost，包括sign/sig等，不是单独magnitude或独立局部context估计。

| scanPos | q | signed L,U | p | 实际modified | active | fractional bits（÷32768） |
|---:|---:|---|---:|---:|---:|---:|
| 1 | -93 | 0,-91 | 91 | 93 | 1 | 551372 |
| 2 | -91 | -91,0 | 91 | 1 | 1 | 197490 |
| 3 | -89 | 0,-93 | 93 | 90 | 1 | 586573 |
| 7 | -97 | -89,-89 | 89 | 97 | 0 | 589824 |

分别对应under（不改变幅值）、hit（映射到1）、over（幅值+1）以及预算耗尽后bypass-only。此样例只能证明映射/成本采集正确，不能单凭几个coefficient推断总体收益。

## Batch与分析

已用 `runs/ts_smoke/batch_jobs.csv` 对生成的64×64样本跑通现有batch脚本：编码、decode hash、独立CSV、`.done.json`、分析均成功；重复同一命令为 `SKIPPED_EXISTS`。

故障用例故意使用宏OFF二进制但请求statistics：编码本身成功，但无statistics，batch正确报告FAIL且不创建成功marker。随后同目录换宏ON重跑，不能因为旧bitstream存在而跳过。失败与恢复日志分别是 `/tmp/ts-batch-expected-failure.log`、`/tmp/ts-batch-recovered.log`。

分析输出包含条件CG rate、TU连续path rate、Oracle、五selector、transition、confidence探索网格、frame bootstrap、sequence等权分布。正式脚本只接受有完成marker且文件大小匹配的数据；直接smoke需显式 `--allow-unmarked --smoke`。

## 原版限制与结论边界

444在默认CCSAO SIMD路径会报不支持chromaScaleX；统一禁用CCSAO后原版编码成功，但第二帧chroma hash已有不一致。已对**原版生成的码流**额外解码复现；没有把这个case标成decoder通过。正式主要实验使用原有420 CTC配置，444不应在修复原版问题前作为有效率失真样本。

lossless直接叠加到默认有损cfg并不能可靠运行；smoke依据工程legacy lossless cfg关闭相关transform/filter工具，使用本版有效选项名称。它仅用于大CG数与bypass验证，不混入正式QP22/27/32/37有损研究。

未运行正式序列矩阵，也未修改正式decoder predictor、码流syntax或量化算法。合成不同case混合后的gain没有内容泛化意义，不作Promising/Weak/Negative结论。本轮完成的是统计实验工具及验证；正式结论等待用户本地数据。
