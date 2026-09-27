# R9 实施验收（2026-09-27）

版本 `R9-20260927-v1`，开发基点 `7e3aad2`。
这是工程正确性/活动检查，不是 CTC 或 BD-rate 实验结果。
实现和已知覆盖限制见 [TS_Predictor_R9_Implementation.md](TS_Predictor_R9_Implementation.md)。

## 1. 构建与规则测试

- Release EncoderApp、DecoderApp、TsRateCodecTest、TsR9QuantTest 均构建成功。
- 独立源码副本仅把 TypeDef.h 的 master 改为0，构建 master-OFF EncoderApp；
  未用 CMake 参数选择算法，未覆盖历史二进制。
- 全部100项 `test_ts_*.py` 通过；最后一次完整运行445.113秒。
  最终活动解析器的补充边界/空输出检查亦单独复验通过。
- Python 独立方程对照 C++：800个含任意非单调成本的邻域×13模式=10,400项。
  检查候选/平局、联合映射评分不高于两种单独映射、组合组四角关系及映射置换。
  此测试中9/10只验证A基础，完整专家验证由下面的原生测试独立检查。
- 13种宏默认和环境覆盖通过；R9与旧fixed、conditional、R2～R8的互斥、
  模式越界、master关闭但请求R9均应报错，测试通过。

## 2. 原生 CABAC 与量化

13组分别通过：262,144项中性上下文长度检查、40,000项旧score等价检查，
160个原生TU、1,491个CG、23,436个未来系数污染检查。
TU含2～32方形/矩形、YUV、Rice1～8、低regular预算、BDPCM、全零CG、幅值边界。
每CG同时比较私有回放和原生 estimator 的 fractional bits、预算、出口CABAC状态，均相等；
私有评估不改变真实入口状态，Writer→Reader系数回环通过。

专家组另有独立参考：直接调用旧R8-12、R2-2、R3-1，独立解算几何/scan验证集，
按历史目标j自身分类取成本；loss、验证数、winner、最终动作均相等。
11/12的公共动作逐点等于R8-12。

原生零一量化测试每组256次：126次合法D提案、173次合法U提案、973个CBF翻转拒绝。
q0、D、U、q0恢复逐点核对；输入源系数不变；两组提案摘要均为
`15348570556161347688`，验证DU并未基于D继续编辑。
这不是完整owner获胜次数；完整owner检查包含在编解码短测中。

## 3. 闭环 smoke

人工64×64、两帧、固定随机种子；AI22、AI0、LB22、RA37、禁TS和BDPCM配置。
AI0额外允许较大TS块；BDPCM配置仍可能包含非BDPCM的普通TS，不代表修改了BDPCM语法。

| 检查 | 结果 |
|---|---|
| 编码/解码hash | 259/259通过 |
| 旧实验回归 | 全58个旧模式在AI22码流bit-exact；4个主要对照另覆盖全部6个case |
| Current与master-OFF | 新Current、新OFF、历史OFF在6个case逐字节相同 |
| 禁TS | 13组均与Current相同 |
| 关闭统计/trace | 13组AI22均与观察开启时相同 |
| 两端CG最终q/动作trace | 8,498条完全一致 |
| 相对主要基础的实际码流活动 | 13/13至少一个case不同 |

其中R9-1/2/6只在AI0人工输入上改变了码流。不能据此声称常用CTC QP一定有活动；
已提供固定内容、QP22/37、8帧的预检命令，没有按这个结果调整冻结公式。
R9-1码流活动与R8-10比较，其余以R8-12作主要基础。
通用在线字段则统一相对R8-12：R9-1的`remap_vs_r8_12`还包含S0/Smax差异，
不能将其全部归因于P1候选扩展。

## 4. 最终提交与搜索人口

活动解析读取78个R9带统计任务，59,174行最终Writer分层、748行搜索分层，
编码日志共7,356,245字节。没有默认逐系数文本。这个体积不能线性推定完整CTC体积；
分层键和观察状态的种类会随内容增加，正式运行前应根据预检测量日志/内存开销。

| 人口 | R9-11 | R9-12 |
|---|---:|---:|
| 内部owner trial | 113,114 | 113,595 |
| 完整D测试 | 77,777 | 78,434 |
| 完整U测试 | 0 | 83,166 |
| owner选择D | 14,746 | 13,964 |
| owner选择U | 0 | 9,632 |
| 最终Writer保留D | 4 | 4 |
| 最终Writer保留U | 0 | 6 |

trial与最终提交是两个人口，不能把局部获胜率当最终覆盖率，也不能根据这几个
人工片段推算BD-rate。R9-11/12的predictor本来就等于R8-12，其`remap_vs_r8_12=0`
是预期；不能以此否定量化编辑活动。最终作用位置仅在`TS_R9_TRACE=1`的
`TS_R9_EDIT`记录中输出。

R9-9/10均真正选择过A/B/C；R9-7/8均有k=1且非identity的动作。
选择后样本内regret=0只是最小化规则检查，不是未来目标预测准确的证据。

## 5. 本地证据和复现

- `runs/ts_r9_smoke_final/validation.json`：全部码流SHA、二进制SHA及逐模式验证结果。
- `summary.csv`、`quiet_summary.csv`：234常规/旧模式任务＋12个OFF对照＋13个静默任务。
- `activity/`：按任务/分层的最终和搜索CSV、日志状态及审计。
- 阶段I dry-run为196个LB CE半帧点；固定内容短测dry-run为56个8帧点，禁用工作簿输出。

```bash
python3 -m unittest discover -s scripts -p 'test_ts_*.py'
python3 scripts/ts_r9_smoke.py --quant-test build/ts-r9/bin/TsR9QuantTest \
  --off build/ts-r9-off/bin/EncoderApp --anchor-off build/ts-r8-all-off/bin/EncoderApp \
  --out runs/ts_r9_smoke_final --jobs 8
python3 scripts/ts_r9_activity.py runs/ts_r9_smoke_final --out runs/ts_r9_smoke_final/activity
```

本次Encoder SHA256：`2b0e5ac05b2482b6f39fb19532c8b75c688aff7bc48651b836548fa0c59a2bd2`。
Decoder：`564d4a322e46f0dcc84b52ef549ee3019dd33c6529575882a169e622c196b10d`。
源码宏、构建环境或源码版本变化后应记录新的SHA，不能复用旧成功标记。

尚未完成：真实内容短测、正式CE/B/RA、速度测量、跨三种历史编码基础的匹配shadow采集、
完整候选反事实CG矩阵。禁止将未测项目记为0或据本次正确性检查宣称收益。
