# R5 LB CE 结果核对（2026-09-23）

结论：收到的 R5-1、R5-2 各 28 个 LB CE 点，在表格保存精度下的码率及 Y/U/V PSNR 全部与 R3-1 相同。
两组相对 Current 的 CE 加权 BD-rate 均为 −0.093287662%，相对 R3-1 的增量均为 0。
这是本轮新增机制没有观察到 RD 收益的证据，不是 R3-1 收益被否定，也不能直接证明远端码流 bit-exact。

## 1. 数据与完整性

- R5-1：`experiments/ts_predictor_r5/r5_1_margin_first/JVET-hhi.xlsm`，配套 `R5_1.csv`。
- R5-2：`experiments/ts_predictor_r5/JVET-hhi.xlsm`，按同目录配套 `R5_2.csv` 归属；未移动原文件。
- R3-1：`experiments/ts_predictor_r3/r3_risk_guard/JVET-hhi.xlsm`，只取共同 LB CE 点。
- 辅助对照 R4-3：`experiments/ts_predictor_r4/r4_3_guard_rescue/R4_3_JVET-hhi.xlsm`。
- 唯一正式 anchor：`scripts/JVET-hhi.xlsm` 的 Reference。

两份 R5 表各含 7 序列 × QP22/27/32/37，28/28 点，全部状态 pass；本次不补任何点。
两份 Reference 均与 Current 完全一致；配套 CSV 的 B–J 列（含 RD、时间、内存及状态）逐项与工作簿一致。
R5-1、R5-2 分别有 112/112 个 RD 标量与 R3-1 一致，也与 R4-3 一致。

| QP | 每组点数 | 每组与 R3-1 相同 | 每组与 Current 相同 |
|---|---:|---:|---:|
| 22 | 7 | 7 | 0 |
| 27 | 7 | 7 | 0 |
| 32 | 7 | 7 | 1 |
| 37 | 7 | 7 | 2 |

因此不是仅平均值碰巧抵消；也不符合“所有结果简单退回 Current”的表现。
但无法仅凭这些数值排除错误运行 R3、旧结果混用等来源问题，仍须结合日志。

## 2. BD-rate

复用现有 PCHIP 和工作簿算法：各分量分别积分，再计算 (6Y+U+V)/8；CE 为七序列等权，不是 (C+E)/2。
计算前运行现有 self_test；逐分量与 workbook_bdrate 的最大差为 2.04e-13 个百分点以内。

| 模式 | C，4序列 | E，3序列 | CE，7序列 | CE 直接对 R3-1 |
|---|---:|---:|---:|---:|
| R3-1 | −0.142806% | −0.027263% | −0.093288% | 0% |
| R5-1 | −0.142806% | −0.027263% | −0.093288% | 0% |
| R5-2 | −0.142806% | −0.027263% | −0.093288% | 0% |

三者 CE 分量均值：Y −0.057117%、U −0.102373%、V −0.301228%。
加权中位数 −0.082512%，序列样本标准差 0.191358 个百分点，4/7 序列改善。
这轮没有 R5 B 结果，不能将 CE 七序列平均写成 BCE。

| 序列 | R3-1 / R5-1 / R5-2，均对 Current |
|---|---:|
| BasketballDrill | −0.121905% |
| BQMall | +0.018316% |
| PartyScene | −0.468990% |
| RaceHorsesC | +0.001353% |
| FourPeople | −0.082512% |
| Johnny | −0.138684% |
| KristenAndSara | +0.139408% |

新规则未改善原 R3 的退化序列，也未增加优势序列的收益。有限精度下的全零增量不需要额外 bootstrap 来宣称“显著等价”。

## 3. 唯一远端日志证据

`experiments/ts_predictor_r5/r5_1_margin_first/BasketballDrill_22.log`：

- Encoder 及 Decoder banner 均明确 `r5_margin_first`、`TypeDef.h default`、`R5-20260921-v1; mode=1`。
- TransformSkip=1、RDQTS=1、ChromaTS=1；实际编码 250 帧（该序列半帧）。
- 汇总为 2277.5984 kbps，Y/U/V = 41.5925/43.8253/44.8247 dB，与表中该点一致。
- 一个编码段、十个解码段，每段 250 帧，共 2500 个 MD5 OK；这是重复解码，不是十次独立编码或 2500 个视频帧。
- 日志计时与 CSV 计时不完全相同，不能把它视为完整任务 manifest，也不据此比较复杂度。
- 没有 `TS_R5_STATS` 或 `TS_COND` 行，无法据此计算重排/补查/映射改变次数。

这份日志支持“至少该 R5-1 运行确实选择了实验模式”，不支持断言整组或 R5-2 都已核验。
统计输出在当前源码写向 stderr，缺行可能来自未合并 stderr、显式关闭统计等，不能推断 TS 未出现或新增触发数为零。
没有远端二进制 SHA、配对 R3 码流或 R5-2 日志，不能认证远端全部模式身份、源码一致性或 bit-exact。

## 4. 对设计的解释与后续决定

R5-1 只把原候选的 G 优先改为 H 优先，没有改变样本、候选或代理损失。
此前约 314 万个小模板及宽幅值网格未观察到已接受 R3 winner 被重排，且与 R4-3 没有预测差异；本轮完整 CE 的零增量与该反证一致。
有限测试不是全域等价证明，不能宣称两公式必然等价。

R5-2 先要求当前 R3 偏离 Current，再要求历史回看中 Current 的总优势在扣除最大单项优势后仍为正。
后一个条件至少需要两个正贡献，而历史 R3 与 Current 相同的位置贡献为零。这种叠加限制可导致活动极少。
此前人工网格只有三次否决，本地视频短测没有增量映射；它解释了本轮相同结果的可能机制，但不能替代远端活动统计。

即便 predictor 数值变了，当前幅值的 remapping 仍可能相同，或所在位置已走 bypass；不能把“表格相同”直接解释为“选择函数从未触发”。

本轮结论：**相对 R3-1 的新增 RD 价值为 Negative（本次 CE、表格精度范围内）；全体远端运行身份仍未完全核验。**
停止扩大 R5-1/2 的 B/RA 长跑，不放宽门槛只为制造差异。保留原 R3-1；下一轮若设计新算法，应改变评分或样本信息，并先证明相对 R3 的有效映射活动，再进行长编码。
如需确认机制，可回收已有完整 stdout/stderr、R5-2 banner 和码流 SHA，不必重跑整套 CTC。

## 5. 来源指纹

| 文件 | SHA256 |
|---|---|
| Current workbook | 3e5dda606666fe38dd37b5597e6ec9cf69a25d5d91e4ec11488fec786d1423f1 |
| 当前 R3-1 workbook | f36c9069bf330c3b3f3803620a64f672a7593532043accb2307579be63b86ddb |
| R4-3 workbook | 09459384bb5b74b16cb85d312e8dcade432dd3e9f605acc447aea8ef81709b8a |
| R5-1 workbook | e72b90b78522313925d291f82261848c8bd17fdcae3525166625e10485e607e5 |
| R5-1 CSV | e0a05632c5b165ba26a9c17bdfbbc0bfd35256003662f387e25278f21a9480fb |
| R5-2 配套 workbook | f71ddf0dc2b3f48992474ed6ba29a5a9fe5ed5140d394a5bace195d8982f07b5 |
| R5-2 CSV | d9d1e9d39f171241eeb892e13c9e2e128867b98564f721932bfa40e409c56d95 |
| R5-1 远端日志 | 4c97882ba4d52caffc625380a6426b2c217f303c621073c7067b2be0ab386b3a |

只更新本报告和实验记录；未修改算法、源工作簿、CSV、日志或移动用户结果。
