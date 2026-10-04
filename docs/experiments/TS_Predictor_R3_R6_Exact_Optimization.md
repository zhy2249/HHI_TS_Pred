# R3 / R6 等价复杂度优化

日期：2026-10-04。重点为 R3-1、R6-2；不是新 predictor 实验，不改变旧算法 revision。

## 目标、身份及限制

用户报告 **R3-1** 编码时间约为 Current 的 101.4%，希望降至 100.8% 以内。
这相当于减少约 42.9% 的额外 1.4% 开销，或减少原 R3 总时间约 0.592%。
目前不知道该 101.4% 是否包含统计开销，不将它当作已核验的无统计基准。

本轮沿用 `experiment/ts-predictor-study`，任务开始时 HEAD 为 `df1fe525b81778fcc434e2e50666b81c5fb55ffb`，
保留已有 R12 等未提交改动。原 R3/R6 路径保存在 `build/ts-r36-reference-src/`，其工程宏为 0；
对照与优化版使用相同合成测试夹具。备份不是一个新的 Git 基线提交，不能仅凭上述 HEAD 重建当前工作树。

只减少实现工作量：候选集合、整数 `syntaxCost`、平局、G/H、fallback、RDOQ 搜索和最终 CG 清零全部不变。
不把 R3-1 换成 R7 或更精确 cost，不合并实验身份，不修改既有结果。
本轮没有运行任何完整帧/序列编码或解码；局部原生 Writer/Reader/量化测试不等于完整视频验收。

## 统计状态核验

用户提供的旧日志：

```text
EXPERIMENT: TS_FIXED_PREDICTOR=r3_risk_guard; syntax=experimental-v1
TS predictor default: r3_risk_guard; selection: TypeDef.h default
TS R3 revision=R3-20260919-v1; anchor=current; guard=G-max-positive>0; recent=immediately-previous-CG; scope=YUV; TU-local
```

只能确认 R3-1、YUV、宏默认选择，**不能确定统计是否开启**。当前源码中：

- `TS_R3_STATS` / `TS_R6_STATS` 未设置时默认开启；只有值恰为 `0` 才关闭。
- `TS_COND_TRACE` 只要存在就开启，设为 `0` 也不会关闭，应 `unset`。
- `TS_R3_STATS_HEADER` / `TS_R3_STATS ...` 在 stderr；仅保存 stdout 的服务器日志可能看不到。
- 原 R6 wrapper 强制 `TS_R6_STATS=1`，已改为尊重外部显式值，未设置时仍默认 1。

新增启动行显示实际 `exact-opt`、`stats`、`trace`，不改变原模式及 revision 行。
公平计时须优化前后都关闭统计/trace/shadow；不能把仅关闭统计的收益归为算法等价优化。
旧二进制若来自不同 revision，仍须核对那一版本的环境变量语义。

## 实施内容与等价依据

### 1. 共享幅值代价与精确前缀评分

新增 `source/Lib/CommonLib/TsR36Exact.h`。原五点邻域仍为 `L,U,D,LL,UU`，
`n` 仍是非零**位置**数，不改为不同幅值数。仅对相同幅值共享 cost，并保存重复次数。

记非零幅值为 a，C 为原 `syntaxCost`。原 remapping 精确满足：

\[
C(M(a,p))=\begin{cases}
C(1)=1,&a=p,\\
C(a+1),&a<p,\\
C(a),&a>p.
\end{cases}
\]

`p<=1` 的实际 remapping 均为 identity；稀疏路径仍保留原返回整数，不随意把 1 规范化为 0。
最多五种不同幅值，用有界插入排序后计算 C(a) 和可达的 C(a+1)。
实际 Current 为 max(L,U)，属于非零支持或为 0，因此 dense 路径最多九次 cost 调用；
独立函数也支持 Current 不在支持中的情况，不依赖这一附加性质才能正确。

对幅值候选 p：

\[
S(p)=S(0)+\sum_{a<p}N_a[C(a+1)-C(a)]+N_p[1-C(p)].
\]

按升序累加精确前缀，代替对每个候选重新计算所有 remap/Rice cost。
不假设 C 单调，不改变任何整数精度。先以 Current 为 incumbent，再 identity，再升序幅值，
只接受严格较小 score，保留原 Current → identity → smallest 的平局行为。

R3 的 G 由精确总分差得到，最大正贡献仍是**一个位置**的贡献：

\[
H=G-\max(0,\max_i d_i).
\]

总分乘重复次数，max/min **不乘重复次数**，否则会错误改变重复邻居的保护能力。
R6-3/4 的 symmetric score 也复用共享 cost，但保留原删一个 min / 加一个 max-saving 的语义。
R6-2 仍仅在严格更优 raw winner 被 guard 拒绝时返回 NoPred；Current 平局不改为 NoPred。

### 2. 动作路径与诊断路径分离

`r36Predict` 只生成编码真正需要的 predictor；旧 `guardedLocalPredict`、`r6Predict` 完整保留，
用于宏 0、原统计和独立对照。R6 不再为了返回一个整数额外生成 current-hit、parent、score-tie 等诊断字段。

`ContextModelling.h` 对 R3-local（1/2）和 R6 提前分派；仍先执行分量范围检查，
R3-2 的 U/V 仍用 native Current。邻居位置直接使用原 scan 已保存的 x/y/idx，
省去重复的整数除法/取余，不改变扫描或因果邻域。

`finishTsPredictorCG` 仅在 R3-local/R6 且调用者既不请求 report 又不请求 trace 时提前返回。
原路径在此条件下也不更新状态，只是之前需要经过多轮 dispatch/诊断条件判断。
R3-3/4 历史状态、其它轮次及其 final-q replay 不受影响。

### 3. Writer 单次 CG 内复用 remapping

原 TSRC 多遍 coding 会对相同最终 q 重复调用 predictor。现在只对 R3-local/R6，
在**一次 `residual_coding_subblockTS` 调用内**用栈上数组和 bitmask 保存已求得的 regular remap。

- 只在该 CG 调用存活，跨 CG/TU/RDOQ trial 不保留；没有堆分配或全局缓存。
- 同次调用 q、邻域、Rice/range 不变，后续 pass 可精确复用。
- 零 level、BDPCM、pure bypass 先直接返回原 level，不读取 regular 缓存。
- RDOQ 不做这类跨量化候选缓存，不跳过它仍可能用于 `allowUp` 的 predictor。
- stats/shadow 原本的计算仍保留；不更改真实 CABAC state、fractional bits 或 regular-bin budget。

## 宏、构建与计时使用

工程开关在 `source/Lib/CommonLib/TypeDef.h`：

```cpp
#define JVET_BJUT_TS_R36_EXACT_OPT 1  // 默认1，等价优化；0保留原路径
```

仍用原实验选择宏，两组分别编译时示例：

| 实验 | FIXED_PREDICTOR | R3_MODE | R6_MODE | R36_EXACT_OPT |
|---|---:|---:|---:|---:|
| 优化 R3-1 | 1 | 1 | 0 | 1 |
| 原 R3-1 对照 | 1 | 1 | 0 | 0 |
| 优化 R6-2 | 1 | 0 | 2 | 1 |
| 原 R6-2 对照 | 1 | 0 | 2 | 0 |

表头均省略 `JVET_BJUT_TS_` 前缀，其它算法默认宏必须为 0。
当前工作树仍保持 R3_MODE=R6_MODE=0，没有擅自切换默认实验。
`TS_FIXED_PREDICTOR` / batch `--fixed-predictors` 仍覆盖实验选择，但不覆盖编译时工程开关。
R3-3/4 不使用本优化，已有 R12_EXACT_OPT 语义不变。

构建命令（CMake 仅负责构建，不用它指定算法宏）：

```bash
cmake -S . -B build/ts-r36-exact -DCMAKE_BUILD_TYPE=Release \
  -DNX2_TOPLEVEL_OUTPUT_DIRS=OFF -DNX2_ENABLE_LINK_TIME_OPT=OFF
cmake --build build/ts-r36-exact \
  --target EncoderApp DecoderApp TsRateCodecTest TsR36QuantTest TsR6CodecTest -j4
```

正式计时命令前应设置（同样应用于原实现）：

```bash
unset TS_COND_TRACE TS_PRED_STATS TS_R9_TRACE TS_R11_TRACE TS_R12_TRACE
export TS_R3_STATS=0 TS_R6_STATS=0 TS_R11_STATS=0
export TS_RATE_SHADOW=0 TS_RATE_RDOQ_SHADOW=0
```

然后沿用原编码参数或 batch 命令，明确指向新构建二进制。关闭无关观察选项，
使用新输出目录；不要复用不匹配二进制指纹的成功 marker，也不要混合新旧耗时。
R6 wrapper 现在接受 `TS_R6_STATS=0 bash scripts/run_ts_r6_lb_ce.sh ...`，其原默认实验集合没有改变。
多实验共享池适合吞吐，不适合作为 0.6% 级加速的公平计时环境；配对计时应控制同机负载、线程、频率和运行顺序。

## 实际验证与复现

没有运行 EncoderApp/DecoderApp 的帧级流程。已完成：

- Release 构建两套局部测试程序及优化版 EncoderApp/DecoderApp。
- master-OFF 下 `ContextModelling.cpp`、`CABACWriter.cpp` 严格告警语法编译通过。
- 151 项脚本/宏/公式测试通过；含非法工程宏、默认/覆盖模式、实际统计状态 banner。
- 新纯函数测试：32,768 组小邻域穷举、40,189 组随机及 Rice/limited-escape 边界；
  九个模式共 **656,613 次 predictor 整数比较**，另含独立 Current 的 **152,963 次 guard 全字段比较**。
  覆盖 Current=1、重复支持、Current tie、accepted/rejected nonzero/NoPred、稀疏 max/mean/min。
- 上述纯函数 ASan+UBSan 通过。环境的 LSan/ptrace 限制导致需关闭 leak 检查，**没有宣称泄漏检查通过**。
- Current、R3-1/2、R6-1～7 共十个模式，各比较宏 0/1 × stats/trace 关/开。
  每组合 160 个合成 TU、1,491 CG；完整 CABAC payload **逐字节相同**，不是只比较摘要。
  原生概率状态、fractional bits、预算、复原 q 断言通过；每组合有 23,436 次当前/未来系数污染检查。
- 九个 R3/R6 模式各对应 1,424 对 Writer/Reader trace CG；Current 不输出 trace。
  两端及优化前后统计、trace 完全一致。
- 每组合 240 个原生 TS-RDOQ 用例，最终 q/absSum 全量相同；包含 180 个非 BDPCM、
  30 个 HOR、30 个 VER，YUV/矩形尺寸、intra/inter、QP 10～47、Rice 1～8。
  包括 19 个全零输入、32 个非零输入量化清零，以及污染/清零分支后恢复。
- 既有 `TsR6CodecTest` 的七个模式额外通过：每模式两套程序各 240 TU、2,257 CG、
  35,524 次因果/sign/poison 检查，stdout 完全一致、stderr 为空，含人工 regular-path 活动见证。
- 未优化模式 R10-3、R12-3/11/12 与此前 `build/ts-r12-exact` 比较，各 160 TU 的完整 CABAC 字节及 stdout 一致。
  补充结果位于 `runs/ts_r36_exact/other_modes/validation.json`。

复现局部验证，以下路径为本轮已构建的原路径/优化路径，不用另开完整编码：

```bash
python3 -m unittest discover -s scripts -p 'test_ts_r36_exact_formula.py'
python3 scripts/test_ts_r36_exact.py \
  --baseline-exe build/ts-r36-reference/bin/TsRateCodecTest \
  --optimized-exe build/ts-r36-exact/bin/TsRateCodecTest \
  --baseline-quant-exe build/ts-r36-reference/bin/TsR36QuantTest \
  --optimized-quant-exe build/ts-r36-exact/bin/TsR36QuantTest \
  --out runs/ts_r36_exact/recheck --jobs 2
```

runner 复用 `test_ts_r12_exact.py` 的完整 payload 比较函数，新增 `TS_R36_EXACT_PAYLOAD` 测试接口，
不添加生产 coefficient 日志。结构化结果包含四个二进制的 SHA256，位于
`runs/ts_r36_exact/timed/validation.json`，原始 payload/日志不上传。

## 局部计时证据：不等于整编码时间

GCC 11.4、相同 Release 配置，stats/trace 和 payload I/O 关闭，热身后七轮串行交替，
编译/其它重测试不并发。量化测试每次重复相同 240 输入 30 轮，避免只测几毫秒进程；
检查每次运行确认重复次数且摘要相同。native 项含未优化的参考计算和断言。

下表为逐轮“优化 / 原实现”耗时比的中位数，括号为最小～最大。

| 模式 | 合成原生语法/参考测试 | 合成 TS-RDOQ 测试 |
|---|---:|---:|
| Current，未改动对照 | 1.0122（0.9918～1.0341） | 0.9993（0.9927～1.0337） |
| R3-1 | 0.9317（0.9135～0.9583） | 0.7733（0.7645～0.7929） |
| R6-2 | 0.9188（0.8876～0.9267） | 0.7465（0.7311～0.7701） |

该组 R3-1 量化夹具耗时约下降 22.7%，R6-2 约下降 25.3%，Current 接近不变。
它们含夹具/断言开销，且合成残差分布不是正式 CTC；**不能直接把 101.4% 乘以此比例，
也不能宣布已达到 100.8%**。新旧耗时原数、配对比及程序指纹均在上述 validation.json。

在 runner 命令追加以下参数可复现计时，默认只验等价不计时：

```bash
--benchmark-repeats 7 --benchmark-inner-repeats 30 \
--benchmark-modes current r3_risk_guard r6_reject_nopred
```

后续服务器验收：在用户授权运行时，同输入/配置/编译设置，原与优化版都关闭统计，
先比较完整序列码流，再至少三轮交替计时，报告优化/原实现、优化/Current 和逐序列变化。
若达不到 100.8%，先定位剩余热点；不以改变 predictor、guard 或 RDOQ 搜索换取“等价优化”。

## 交付边界

本轮依据 codec-experiments 规范区分局部与帧级验证、保留旧算法和独立对照，未扩大为新 RD 实验。
不新增 BD-rate 台账数值，旧 R3/R6 的 RD 结果不会因本轮工程优化被替换。
本轮自动同步实验文档；源码与测试脚本留在本地工作树，不把既有未提交源码一并自动上传。
