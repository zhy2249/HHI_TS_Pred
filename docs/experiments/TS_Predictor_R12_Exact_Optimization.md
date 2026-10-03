# R12 等价复杂度优化

日期：2026-10-03。规格仍为 **R12-POS-01**，不是 R13 或新的 BD-rate 实验。

## 范围与依据

本轮先将 `experiment/ts-predictor-study` 从 `a0f21db` 快进到 `08b7140`，
参考 [复杂度分析](../external_inputs/R12_Complexity_Analysis.md) 和
[等价优化建议](../external_inputs/R12_Exact_Optimization_Notes.md)。外部文档保留原文；
是否实施以本地 R12 实际源码及等价验证为准。

保留任务开始前尚未提交的 R12 实现。优化前源码和原生测试程序另存于
`runs/ts_r12_exact/before/`，没有覆盖原 `build/ts-r12/` 实验程序。

约束是同一 R12 模式的 `(p,k)`、remapping、最终量化系数、CABAC 状态和字节不变。
不增加 predictor、阈值、模式或经验 guard；不改 RDOQ 搜索、CG 最终清零、三遍 TSRC 回放，
不取消 CG 入口 frozen context。本轮不跑帧/序列级编解码，不产生新 BD-rate。

## 已实施

### 1. 动作路径与诊断路径分离

`CoeffCodingContext::r12ActionTS` 服务于 RDOQ/Writer/Reader/replay 的共同入口。
原 `r12PredictionTS`、`r12Experts`、`r12Integer`、`r12Select` 保留为未优化参考及完整诊断路径。
最终 Writer 的 stats、shadow 和 trace 仍使用完整诊断，不改变统计分母、专家编号或历史 loss。

所有可选的 query action 完全相同即可直接返回该动作。比较的是完整 `(p,k)`；
R12-3 必须包含 D，不能仅因 ABC 相同就跳过 D。此处不合并任何专家的历史身份。

### 2. 共享有界候选代价矩阵，移除 A 的冗余诊断评分

新增 `TsR12Exact.h`。所有有效候选仍是原 canonical P0，Current 优先、其余按幅值升序。
对非零历史位置，原映射精确满足：

\[
C(M(a,p))=\begin{cases}
C(1), & a=p,\\
C(a+1), & a<p,\\
C(a), & a>p.
\end{cases}
\]

canonical `p<=1` 为 identity。每种 cost 模型预计算上述三种代价（每个邻域最多 11 次 cost 调用），
然后直接访问最多 6×5 的局部矩阵。最大样本没有更大的可选 predictor，不访问不可达的 `C(limit+1)`。
零位置保持零贡献，非零数量 `n` 不变；重复幅值仍按**原空间位置**保留。

- B 与 C 共用 CI 矩阵。B 的 strict raw winner、旧 C 的 `G-max(0,max d)>0` 原样保留。
- 7/8/11/12 的 weighted C 保留 W=(2,2,1,1,1)、原 raw winner 和对应 0/full/soft penalty。
  最大贡献仍取单位置，不能合并重复值后再取最大。
- A 单独使用 CF 矩阵，目标仍为
  `sum C(M(a,p)) + max(0, max[C(a)-C(M(a,p))])`，以及原 `r8TieLess` 平局规则。
  `n<3` 保留 sparseSmax。仅省去原 `r9Decision(12)` 为返回 `.action` 而额外计算的
  parent、baseScore、最终 diagnostic score，不换评分模型。
- 所有分数仍为原 int64/Q15，未降精度、未假设 CABAC cost 单调。

### 3. 外层先确定精确 CI 候选池，再计算需要的 CF

| R12 模式 | 外层 CF 的必要集合 |
|---|---|
| 9、12 | weighted CI 最小并列集合，使用 weighted CF |
| 10 | CI 最小并列集合，使用 weighted CF |
| 5 | direct L/U CI 唯一赢家直接返回；否则原 CI→CF |
| 7、8、11 | 原 CI 最小并列集合 |
| 1、2、3、4、6，ABC CI 并列 | 只在原 CI 最小并列集合内选，不启用 near/LOO |
| 上述模式，ABC CI 唯一 | 原 near/LOO 规则得到的合法池 |

只有一个合法专家时不必计算外层 CF；否则从原 incumbent 开始，仅 strict CF 改善才替换。
每次 callback 仍对**完整 V0**求和，LOO 仅决定候选池，不删除最终 CF 中的样本。
R12-3 保留 D 的 `0<=gap<=Q`，不将负 gap 纳入；LOO informative 行只看 ABC remapped magnitude 是否不同，
不是比较 CI 是否不同，也不借助 D 增加有效样本。

历史 row 的相同 mapped level 共用该 row 的 CI 值，不合并专家。
A 内部的 CF 不受这项延迟策略影响，外层 CI 唯一时也照常生成 A。

## 未采纳的建议

- **不加跨调用专家缓存**：本轮收益先来自纯函数工作量削减。没有新增失效规则，也没有概率快照、
  RDOQ 分支回滚、q 修改、CG 清零导致缓存过期的风险。
- 不改 CG 最终 q 回放：这是后续 CG frozen context 的语义组成，不能以性能为由省略。
- 不外提 RDOQ 当前 level 循环中的 predictor：源码已经在该循环外计算，不是新增优化空间。
- 不做全局 scan/邻域共享、prefix-sum 评分或同值样本压缩：五点问题未证明值得增加工程复杂度。
- 不因当前 query 的两个专家动作相同就合并二者：历史动作和历史损失仍可能不同。

这些改动没有增加任何持久状态；所有矩阵是当前调用栈内的局部临时量。
空间和时间渐近阶不变，目标是减少常数项和不必要的函数调用。

## 宏与使用

在 `source/Lib/CommonLib/TypeDef.h`：

```cpp
#define JVET_BJUT_TS_FIXED_PREDICTOR 1
#define JVET_BJUT_TS_R12_MODE        11  // 示例；实际仍选所需的原 R12 编号
#define JVET_BJUT_TS_R12_EXACT_OPT   1   // 默认1：等价优化；0：原完整路径
```

其它算法默认宏仍须为 0。**当前仓库保持 `R12_MODE=0`，没有擅自把默认实验改成 11。**
`TS_FIXED_PREDICTOR` / batch `--fixed-predictors` 继续覆盖算法模式，但不覆盖工程优化宏。
启动行增加 `exact-opt=0/1`；切换该宏须重新编译。
宏只影响 R12，Current 和 R10 等其它实验不受影响。原运行脚本、模式编号和结果目录不变。

构建优化版（不通过 CMake 指定算法宏）：

```bash
cmake -S . -B build/ts-r12-exact -DCMAKE_BUILD_TYPE=Release \
  -DNX2_TOPLEVEL_OUTPUT_DIRS=OFF -DNX2_ENABLE_LINK_TIME_OPT=OFF
cmake --build build/ts-r12-exact \
  --target EncoderApp DecoderApp TsRateCodecTest TsR12QuantTest -j4
```

正式任务需明确指向新二进制，不能以重编新目录推断旧程序已更新。
没有修改已有运行结果、工作簿或续跑指纹。若同一任务换二进制，继续遵守原 resume 指纹检查；
计时比较使用单独输出目录，勿把优化前后的耗时混为一组。

## 验证和复现

本轮只执行纯函数、合成 TU 原生语法/量化测试，没有调用视频编码或解码入口。
对照目录 `build/ts-r12-exact-reference-src/` 使用相同测试 harness，只在源文件中将
`R12_EXACT_OPT` 改为 0，再构建至 `build/ts-r12-exact-reference/`；主目录保持 1。
不使用新的 CMake 算法开关。

```bash
python3 -m unittest discover -s scripts -p 'test_ts_r12_exact_formula.py'
python3 scripts/test_ts_r12_exact.py \
  --baseline-exe build/ts-r12-exact-reference/bin/TsRateCodecTest \
  --optimized-exe build/ts-r12-exact/bin/TsRateCodecTest \
  --baseline-quant-exe build/ts-r12-exact-reference/bin/TsR12QuantTest \
  --optimized-quant-exe build/ts-r12-exact/bin/TsR12QuantTest \
  --out runs/ts_r12_exact/paired --jobs 2
```

验证工具使用 `TS_R12_EXACT_PAYLOAD` 保存长度分帧的完整 CABAC bytes 或固定小端 q＋absSum；
比较整个文件，不只比较摘要。输出仅为测试产物，不添加生产 coefficient 日志。
原有独立参考额外逐位置比较 `r12ActionTS` 与 `r12PredictionTS().action()`。

实际完成的验证：

- Release 构建 EncoderApp、DecoderApp、TsRateCodecTest、TsR12QuantTest 通过；
  master-OFF 的 `ContextModelling.cpp` 严格告警语法编译通过，宏选择/非法值检查通过。
- 143 项既有及宏回归测试通过；另新增 4 项纯函数测试通过，共 **811,935 次** mode 级新旧比较：
  小值穷举 303,264 次、随机非单调 64-bit cost/极值 300,625 次、随机 selector 208,000 次、
  定向边界 46 次。同时验证 lazy CF 的调用集合，禁止评估被排除专家。
- 12 个 R12 模式＋R10-3，各比较宏 0/1 × stats/trace 关/开四种组合。
  每组合 160 个合成 TU、1,491 个 CG，**完整 CABAC bytes 逐字节相同**。
  两端复原 q，完整上下文、估计 fractional bits 和最终 regular budget 的既有断言通过。
- 每 R12 组合另有 29,544 次独立动作核验；每组原生测试 23,436 个当前/未来系数污染测试，
  覆盖 prefix 修改、清零、恢复、context 分支及冻结快照恢复。
  R12-3 包含 395 次 ABC 动作相同而 D 不同的参考调用。
- 每组合 180 个原生 TS-RDOQ 合成残差测试，**所有最终 q 和 absSum 精确一致**，
  包括 14 个原始全零和 14 个非零输入量化清零，以及输出污染/清零分支后恢复。
- 优化前保存的原测试程序与新宏 0 对照，在全部 13 模式的 stdout、原生字节摘要和 q 摘要一致。
  这项额外核验只比较摘要；上面的宏 0/1 核验比较完整 payload，不混淆二者。
- stats/trace 两端记录和优化前后诊断均完全一致。

结构化结果在 `runs/ts_r12_exact/paired/validation.json`，含四个程序的 SHA256 和逐模式结果。
原二进制 SHA256：native `ebc76406e8278b9361d0e119e05d0cb75a5f66573e085dac2f8304d8de74c044`；
quant `69119825939d24f78911d72705d6bd79f6a198404678106a7371db8ba7768321`。
本轮不以合成测试代替真实序列字节验收。

## 局部复杂度证据（不是整编码速度）

相同 Release 设置、GCC 11.4.0、同机同输入，关闭统计和 payload I/O，热身后五轮串行交替。
计时与编译/功能测试不并发。下表是逐轮 `优化/原实现` 耗时比的中位数；括号为五轮最小～最大。
包含夹具初始化、进程启动、回归断言；native 项还含大量未优化的独立参考计算。

| 模式 | 合成 native TU 测试 | 合成 TS-RDOQ 测试 |
|---|---:|---:|
| R10-3，未改动对照 | 1.0041（0.9884～1.0137） | 0.9964（0.9947～1.0268） |
| R12-3 | 0.7513（0.7437～0.7604） | 0.4653（0.4586～0.4770） |
| R12-11 | 0.7305（0.7259～0.7390） | 0.3955（0.3920～0.4025） |
| R12-12 | 0.7234（0.7217～0.7276） | 0.3792（0.3783～0.3865） |

R12-11 的该组合成 TS-RDOQ 测试耗时约下降 60.5%，说明此次工作量削减在原生量化路径上确实有效；
**不代表整编码器下降 60.5%**，更不等于真实序列 decoder 加速或生产服务器的计时。
全编码/解码速度及优化版相对 Current 的开销仍未测。
原始五轮数值及程序 SHA256 保存于 `runs/ts_r12_exact/timed/validation.json`。

可在上述 runner 命令追加以下参数复现（默认不计时）：

```bash
--benchmark-repeats 5 --benchmark-modes r10_integer_then_fractional \
  r12_current_near1 r12_c_distance_softtrim r12_c_and_validation_distance
```

纯函数 probe 另有 `--benchmark` 接口，CF 为非单调 hash 人工模型；本轮未运行也未拿它作 CABAC 性能证据。

## 交付边界

本轮没有改变 R12 算法结论，因此不新增/重算 BD-rate 台账。此前 R12 CE 结果仍是原实验结果。
正式推广前建议在获准时进行同机、同配置、同输入的优化前后短序列完整字节比较及交替计时；
计时关闭 stats/trace/shadow，分别报告优化版/原 R12、优化版/Current，以及 decoder 耗时。
这一步尚未执行，不宣称所有实际序列已验证 bit-exact。
