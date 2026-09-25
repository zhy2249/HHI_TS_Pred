# TS 条件 / 历史自适应实验：实现与外部服务器交接

Revision 1，2026-09-16。**五组源码已实现，CTC 未运行，无新 BD-rate 结论。**
此文件是当前实验身份与运行方式的准则；早期三组 G1/G2/G3 讨论由这里的 N1/N2/A1/A2/A3 替代。

## 1. 固定的实验定义

| ID | 环境变量模式名 | 条件宏值 | 规则 |
|---|---|---:|---|
| N1 | `q32` | 1 | CU QP<=32 用 directional，否则 Current |
| N2 | `conf2` | 2 | 方向分数满足 2:1，用 directional，否则 Current |
| A1 | `prev` | 3 | 前一 CG 的整数收益>0 用 directional，否则 Current |
| A2 | `ewma` | 4 | TU 内近期整数收益状态>0 用 directional，否则 Current |
| A3 | `q32_ewma` | 5 | CU QP<=32 且近期状态>0 才用 directional |

原有 `current/nopred/gradient/directional` 仍可使用，定义不变。
本轮没有 `q32_conf2` 模式，勿与早期第三组联合置信度方案混淆。

Current：p=max(L,U)。directional 在 x>=2,y>=2 时比较
EH=abs(L−LL)+abs(U−D)、EV=abs(U−UU)+abs(L−D)，较小者对应 L/U，平局或邻域不足取 max。
N2 仅在 emax>0 且 emax>=2*emin 时采用 directional。
L/U/D/LL/UU 全部为 decoder 已恢复的因果量化幅值。
N2 可读取当前 CG 内已解码邻居，**不是**历史 CG 模式选择；A1/A2/A3 在当前 CG 内保持同一模式。

Q 是 `tu.cu->qp`（实际 CU luma QP），所有 component 共用，不是命令行 nominal QP，
也不是含 bit-depth offset / chroma mapping / TS clamp 的 QpParam 值。
QP 门控 RDOQ 路径加入检查，若传入量化 QP 与 TU 推导不符则报错，禁止隐式 encoder-only override。
不从 GOP 配置反推出 nominal QP。32 为预先冻结阈值，不声称最佳或等价之前四点组合。

## 2. A1/A2/A3 的确定性更新

每个 component TS TU 创建独立 CoeffCodingContext，状态 S=0。
当前 CG 的选择仅取决于进入 CG 前的 S；S<=0 使用 Current。CG0 因此始终 Current。
CG 最终完成后才更新；全零 CG 的收益为0。A1 将状态置0，A2/A3 执行同样的整数衰减。
单 CG TU 没有利用历史的机会。不跨 TU、component 或搜索候选保存状态。

remap(a,p)：a=0 时0；a=p>0 时1；0<a<p 时a+1；a>p 时a。
成本代理 `C(0)=0; C(t>0)=1+2*floor(log2(t))`，实现使用整数移位，无浮点运算。

`G = sum [ C(remap(a,p_Current)) - C(remap(a,p_Directional)) ]`。
**只在实际所选分支的 remapping 有效位置评分**；BDPCM 与 cutoff=0 bypass 不计入差值。
这使用实际分支相同的有效位置集合，不为两个假设 predictor 单独传播 CABAC context 或预算。
因此 G 是低复杂度代理，不是真实 TSRC fractional rate，不作为最终结论。

- A1：S_next=G，平局回退 Current。
- A2/A3：S_next=clip(S−decay(S,2)+G,−32767,32767)。
- decay(S,2)=sign(S)*floor(abs(S)/4)，负数不依赖编译器右移行为。
- A3 高 QP 即使局部计算到正状态，也不启用 directional；状态在 TU 结束即丢弃。

## 3. 接入与重要同步处理

- `TypeDef.h`：原 master + 新条件默认模式宏。
- `TsFixedPrediction.h`：模式解析、选择器、置信条件、remap 代理及整数状态更新。
- `ContextModelling.h/.cpp`：每个 TU/候选私有状态，统一邻域预测与 CG 完成更新。
- `QuantRDOQ.cpp::xRateDistOptQuantTS`：候选 remapping/rate 原入口沿用统一 predictor；
  CG coded vs all-zero RD 决策完成后调用 `finishTsPredictorCG`。
- `CABACWriter.cpp::residual_codingTS`：整个 CG 编码后更新，包括零 CG。
- `CABACReader.cpp::residual_codingTS`：inverse remapping 和符号恢复完成后更新，包括零 CG。

**不能直接采用 RDOQ 的 remRegBins 评价历史**：RDOQ 逐 coefficient 估算消耗，
Writer/Reader 使用三遍语法顺序，截止位置未必相同。
实现用私有 `m_tsHistoryBins` 从 TU 初始预算出发，对最终 CG 回放真实 pass1/pass2 的整数 bin 消耗，
确定 remapping 生效位置。回放不改真实 CABAC context，不写系数。
Writer/Reader 断言回放预算与真实 remRegBins 一致；RDOQ 保持原有近似量化预算，
仅历史状态改用上述精确语法预算回放。这不声称修正全部原始 TS-RDOQ rate approximation。

RDOQ 试算的状态只在本次局部 cctx 内，候选被抛弃即丢弃状态；Writer 的每次估算也重新构造 cctx。
BDPCM 保持原有 identity，不积累历史；普通 transform 不调用新 CG 更新。
N1/N2 正常运行不计算历史评分；调试 trace 开启时额外回放用于检查。

## 4. 编译与选择方式

推荐一个二进制支持全部实验，先在TypeDef.h开启master，再使用独立输出目录。
下列为新建构建的示例，**不要重编正在运行/续跑的旧实验二进制**；R2使用 `build/ts-r2`。

```bash
cmake -S . -B build/ts-conditional \
  -DCMAKE_BUILD_TYPE=Release \
  -DNX2_TOPLEVEL_OUTPUT_DIRS=OFF \
  -DNX2_ENABLE_LINK_TIME_OPT=OFF \
  -DJVET_BJUT_TS_PRED_ANALYSIS=OFF
cmake --build build/ts-conditional --target EncoderApp DecoderApp TsFixedPredictorTest -j 8
```

示例（自行替换输入与实际配置，不是完整 CTC 批量命令）：

```bash
TS_FIXED_PREDICTOR=ewma build/ts-conditional/bin/EncoderApp \
  -c <encoder.cfg> -c <sequence.cfg> -i <input.yuv> \
  -q 22 -f <frames> -b <output.bin> -o "" --SEIDecodedPictureHash=1
TS_FIXED_PREDICTOR=ewma build/ts-conditional/bin/DecoderApp \
  -b <output.bin> -o "" -dph 1
```

Encoder 和 Decoder **必须使用相同模式和 revision**。mode 不在码流发送，普通 decoder 或错误模式
不保证可解码。每个进程启动时解析环境变量一次，不能在同一进程中途改变。
日志应包含 `EXPERIMENT: TS_FIXED_PREDICTOR=ewma` 与 `TS conditional revision=1`。
大规模运行不要设置 `TS_COND_TRACE`。

若希望通过源码默认值选实验，在 `source/Lib/CommonLib/TypeDef.h` 设置：

```cpp
#define JVET_BJUT_TS_FIXED_PREDICTOR 1
#define JVET_BJUT_TS_CONDITIONAL_MODE 4 // ewma
```

旧NoPred/gradient/directional及R2默认宏须全部为0，否则编译报错。
2026-09-18起CMake不再覆盖master，遗留AUTO/ON/OFF缓存被提示并清除；直接修改TypeDef.h。
环境变量 `TS_FIXED_PREDICTOR` 优先于编译默认。当前头文件master=1，所有模式默认宏=0，仍选择Current。
条件宏仅允许0..5；总开关关闭却请求非Current实验时，编译或启动报错，不静默运行anchor。

最初实现阶段未修改批量脚本；后续按用户要求已扩展 `batch_test.py` 支持这五个模式，
并新增 `scripts/run_ts_conditional_lb_ce.sh`。统一任务池与原有续跑、Excel复制写入逻辑保留。
正式运行前会逐模式探测 Encoder/Decoder，旧实验二进制不支持新模式时提前退出。

### LB Class C/E 批量运行（后续新增）

```bash
# 先只核对计划（140项，不启动编码）
bash scripts/run_ts_conditional_lb_ce.sh --dry-run
# 正式运行，默认10并发；可覆盖输入目录与并发数
bash scripts/run_ts_conditional_lb_ce.sh --input-dir /path/to/videos --jobs 10
# 中断后同一命令续跑；不要加 --overwrite，不要重编或移动二进制
```

默认模式 q32,conf2,prev,ewma,q32_ewma；可追加 `--fixed-predictors prev,ewma` 只运行指定组。
默认 QP22/27/32/37，LBeu、C/E、半帧；不要加 `--full-sequence`。
每组28项，共140项；C: BasketballDrill250、BQMall300、PartyScene250、RaceHorsesC150；
E: FourPeople/Johnny/KristenAndSara各300帧。统一池，不等待上一整组全部完成才调度下一组。
shell 入口关闭 TS_COND_TRACE，不写重建视频，运行 Decoder 检查 hash，不重新运行 anchor。

输出 `runs/ts_conditional_LB_CE_half/<mode>/JVET-hhi.xlsm`、各模式summary与逐任务日志/完成标记；
根目录保留总summary、failure列表及experiment_plan。**每组计划任务全部返回后立即生成该组 Excel**，
并更新该组summary/failures；其他组在共享任务池继续运行，不增加组间等待。
续跑跳过的成功任务也计入该组完成数；失败任务会保留失败状态，不把“任务结束”当作“全部成功”。
开启重试时，新结果返回后刷新对应组；最终不重复写入未变化的组。
表格先写临时文件、完成后替换正式文件，刷新失败时保留原表。
Reference保留，Test写LB CE；本轮不包含B，不能称为BCE完整结果。
此输出目录可直接用于后续分析，无需覆盖此前 `runs/ts_fixed_LB_CE_half`。

## 5. 正确性验证

```bash
python3 scripts/test_ts_fixed_defaults.py
python3 scripts/test_ts_fixed_batch.py
build/ts-conditional/bin/TsFixedPredictorTest
python3 scripts/ts_conditional_smoke.py --jobs 4 \
  --anchor build/ts-anchor/bin/EncoderApp \
  --off build/ts-conditional-off/bin/EncoderApp
```

其中 OFF 构建同上但目录为 ts-conditional-off、master=OFF；anchor 为之前保留且验证过的旧宏 OFF 二进制。
smoke 是64×64两帧合成内容，不是批量 CTC 工具，也不是性能评估数据。
覆盖 AI、LB、RA、QP边界、低QP、DQP、BDPCM、lossless、TSRC off、TS off。
启用 `TS_COND_TRACE=1` 输出每 CG 的状态、选择、代理收益、回放预算、系数 hash，
脚本逐行比较编码器最终输出路径和解码器；RDO 搜索试算不会写这些 trace。
只在小输入调试使用此开关，避免正式编码大日志。
smoke 输出 `runs/ts_conditional_smoke/validation.json`；其记录与测试结果见实验日志最新条目。
本轮已通过99项编解码任务和另外5项trace-off编码；详细范围见 `TS_Conditional_Predictor_Validation.md`。
高 QP / TS off 的 bit-exact 检查与有效切换检查同时存在，避免“从未启用也通过”的假验证。

## 6. 结果目录与外部服务器要求

预建目录：`experiments/ts_conditional_v1/<mode>/{LB_BCE,RA_CD}/`。
每目录放 `JVET-hhi.xlsm` 和 `run_metadata.json`，尽量提供 `logs/`；
元数据模板为根目录 `run_metadata.template.json`。没有创建空结果工作簿。
工作簿及 logs 默认不加入 Git；README/模板保留，复制仓库即可保留收件目录。

LB BCE 48点/组（半帧），RA CD 32点/组（与 anchor 实际帧数一致），五组共400点。
保留原 Reference，记录源码 commit/dirty patch、二进制 hash、配置及输入身份、实际帧数和模式。
不需要重建视频。不要使用旧实验目录覆盖固定 predictor 结果。
读取时按 mode/config 区分，缺外部日志时只能验证工作簿，不声称验证源码和解码一致性。

## 7. 评价与证伪

各分量 PCHIP BD-rate 后6:1:1加权；LB BCE 12序列等权，−0.05/−0.08/−0.10%门槛不变。
报告各class、各序列、Y/U/V、序列bootstrap和leave-one-out。RA 单独作为回归检查，不混入 LB 平均。
比较 N1/N2 对固定规则、A1/A2 对固定 directional/NoPred、A2 对 A1、A3 对 N1/A2。
若 A3 只等于 N1，不能将收益归功于历史学习。
若 A1/A2 失败，只能否定这两个代理评分与更新规则，不推断所有历史预测无效。
不以 anchor 固定-q 条件统计淘汰新工具，也不从合成 smoke 数据推断 RD 潜力。
本轮冻结阈值和整数代理，不增加多个衰减/门控阈值以追逐最佳点。
