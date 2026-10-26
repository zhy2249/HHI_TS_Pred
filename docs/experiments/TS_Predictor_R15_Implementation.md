# R15：静态整数评分的有序多目标映射

本轮承接远端 `b56e30a` 的 [冻结设计](TS_Predictor_Greedy_MultiMapping_Experiment_Requirements.md)，revision 为 `TS-MG-STATIC-FAST-v1`。用户明确要求原编号 0、2、3 不重新设计；它们复用既有 Current、STATIC_EQ、STATIC_SP，只作为对照列。其余 18 项连续编号 R15-1～18。

状态：**18 组选择/映射、离线审计及后续真实 RDOQ/Writer/Reader 接入均已实现**。本页主体保存第一阶段固定 q 审计合同；该阶段验收见 [原验证记录](TS_Predictor_R15_Validation.md)。用户随后要求完成编码接入，新增 `R15_MODE=1..18`，见 [闭环代码实现](TS_Predictor_R15_Codec_Implementation.md) 和 [局部库验收](TS_Predictor_R15_Codec_Validation.md)。仍未启动视频编码、未登记新 BD-rate；审计全 96 流入口与闭环批量入口分别保留。

## 1. 编号和实验问题

| 本轮编号 | 原编号 | 名称 | 规则 | 深度上限 |
|---:|---:|---|---|---:|
| 对照 | 0 | CURRENT | 既有 max(L,U) | 1 |
| 对照 | 2 | STATIC_EQ | 既有等权单目标评分 | 1 |
| 对照 | 3 | STATIC_SP | 既有 22111 单目标评分 | 1 |
| 1 | 1 | IDENTITY | 恒等映射，所有 n 均生效 | 0 |
| 2 | 4 | G_EQ_K2 | 最优单目标起步，严格正增量 | 2 |
| 3 | 5 | G_EQ_K3 | 同上 | 3 |
| 4 | 6 | G_EQ_K4 | 同上 | 4 |
| 5 | 7 | G_EQ_K6 | 同上 | 6 |
| 6 | 8 | N_EQ_K2 | 允许零增量继续，返回最早最低分前缀 | 2 |
| 7 | 9 | N_EQ_K3 | 同上 | 3 |
| 8 | 10 | N_EQ_K4 | 同上 | 4 |
| 9 | 11 | N_EQ_K6 | 同上 | 6 |
| 10 | 12 | P_EQ_K2 | 强制以 `[1]` 起步，后续严格正增量 | 2 |
| 11 | 13 | P_EQ_K3 | 同上 | 3 |
| 12 | 14 | P_EQ_K6 | 同上 | 6 |
| 13 | 15 | D_EQ_K2 | 最优单目标与 `[1]` 两根分别贪心；平局保留前者 | 2 |
| 14 | 16 | D_EQ_K3 | 同上 | 3 |
| 15 | 17 | X_EQ_K2 | 全部有序前缀的静态评分穷举 | 2 |
| 16 | 18 | X_EQ_K3 | 同上 | 3 |
| 17 | 19 | G_SP_K3 | G，权重 22111 | 3 |
| 18 | 20 | N_SP_K3 | N，权重 22111 | 3 |

各编号收件目录位于 `experiments/ts_predictor_r15/NN_name/`。没有另行发明 CURRENT/STATIC_EQ/SP 的新子实验。R15-2 与 R15-6 理论上返回相同完整映射，保留这项冗余作为强制回归检查。不存在静默跳号。

本轮拆分三个问题：G/X 的分差检验搜索是否不足；同一方法的静态分数与完整 TU fractional rate 交叉检验评分是否不足；P/D 与 G 比较检验第一个目标是否限制后续动作。X 是静态评分最优，不能称为 CABAC oracle。

## 2. 冻结的输入、评分、映射

输入只含已经恢复的 `H=(L,U,D,LL,UU)` 幅值、当前合法 Rice 和动态范围。`n` 是非零位置数，重复幅值分别计数；不同幅值数另记。除 Identity 外，`n<3` 保持 Current。不按当前 a 是否非零提前跳过选择器。

正目标候选为 `{1} ∪ positive(H)`，最多 6 个；优先序为 `Current>1`、`1`、其它不同正幅值升序。候选 1 在搜索期间保留。等权或 22111 的重复观测按总权重合并；所有评分和增量使用有符号 64 位整数。

有序目标 `P=(p1,...,pk)` 的完整映射为：

```
map(0,P) = 0
map(a,P) = j                         if a == pj
map(a,P) = a + k - count(pj < a)      otherwise
```

逆映射：`y=0` 返回 0，`1<=y<=k` 返回 `py`，其余从 `a=y-k` 开始，按目标升序遍历；每遇 `a>=pj` 将当前 a 加一。完整合法幅值域上为双射。

**只在返回时**删除无作用的末目标，反复至末目标有效；内部目标不删，不合并中间搜索状态。例如 `[p,1]` 和 `[p]` 最终等价，但继续搜索的状态并不等价。

评分直接调用 `TsFixedPrediction::syntaxCost`：`S(P)=Σ W(v) C(map(v,P))`。不使用 KeepHit、168 倍评分、真实 CABAC 费用或当前真实幅值来选动作。`C(1)=1,C(2)=C(3)=3,C(4)=C(5)=4,C(6)=C(7)=5`；>=10 的尾部沿用现有有限 Rice escape。

G 遇非正增量停止；N 可以经过零增量平台，但最终同分仍保留最短前缀；P 不回退单目标 B；D 同分保留 B 根。X 不剪除暂时变差的前缀，最终按分数、等价 B、规范化长度、候选优先序裁决。

## 3. 三个实现和复杂度边界

`source/Lib/CommonLib/TsMultiMapping.h` 提供：

- NAIVE：每个候选构造完整前缀并重新评分，不使用增量公式。
- PREFIX：当前 rank、总权重和升序惩罚前缀；精确计算 `W(q)[C(rq)-C(k+1)] - Σ(v<q)W(v)[C(rv+1)-C(rv)]`。
- FAST：在 PREFIX 上按当前成本平台选代表；保留 N 的零收益占位，不做跨轮永久删除。为保持可审计轨迹，首版不使用省略中间步骤的提前终止。

查询使用小型直接映射缓存；冲突只触发重新精确查询。最后一个未选值不查询 `C(Amax+1)`。X 只复用成本查询，没有套用贪心剪枝。默认实际审计采用 PREFIX；是否改用 FAST 以同语义计时结果判断。

操作计数是已插桩的搜索核事件，不等同于整个函数或 CPU 的完整指令计数。选择器基准对同一 H trace 预热、至少 5 次、轮换三个引擎顺序并核验输出 checksum；另测 map/unmap。合成 trace 不代表视频人口；审计回放时间、观察统计时间也不等于部署后的编解码复杂度。

## 4. 第一阶段离线审计的接入方式与宏

离线审计宏位于 `source/Lib/CommonLib/TypeDef.h`；真实编码的 R15_MODE 另见 [闭环实现](TS_Predictor_R15_Codec_Implementation.md)：

```cpp
#define JVET_BJUT_TS_FIXED_PREDICTOR 1
#define JVET_BJUT_TS_R15_ANALYSIS   0  // 提交默认值；需要观察时改为 1 并重编
```

宏允许编入观察器；运行还必须显式 `TS_R15_AUDIT=1`。这不是 `R15_MODE`，不选择新的正式语法模式；18 项在同一次解码中分别私有回放。来源仍用 `TS_FIXED_PREDICTOR=r13_keep_hit_uniform` 或 `r13_keep_hit_spatial`，脚本依 manifest 自动设置。

宏关闭时请求观察会明确报错。R15 观察与旧 sampled audit、corpus、TSCPRED schedule 互斥。其它统计默认保持关闭。不需要给编码器开启任何新模式，也不能用这个观察开关生成 R15 新码流。

主要改动：

| 文件 | 内容 |
|---|---|
| `CommonLib/TsMultiMapping.h` | 有序动作、双射、18 方法/3 对照、3 引擎 |
| `DecoderLib/tsaudit/MultiMapping.h` | 最终 q 和 TU 入口快照、21 完整 TU 私有回放、在线计数 |
| `DecoderLib/tsaudit/Manager.h` | 宏包围的观察器分发 |
| `DecoderApp/decmain.cpp` | 版本探测、未编入时明确拒绝 |
| `scripts/ts_multi_mapping/` | 独立 Python 规格、计划、回放、汇总、验证、计时 |
| `tests/ts_multi_mapping/` | 纯函数三引擎比较及局部算术 Writer/Reader 夹具 |

第一阶段提交 `5b6d5fc` **没有修改** R13/R14 predictor、量化候选、RDOQ、真实 Writer/Reader 反映射。后续闭环接入新增 R15 专用分支；旧模式仍保持原规则。已有 `replayRateCG` 源码未改，通过完整 Action 的 ADL remap 接口复用其三遍语法。

## 5. 回放与文件合同

新映射通过结构化 `Action{count,targets[6]}` 在内存中传递。动作在访问事后当前幅值前选择；不用虚拟单 pred 拟合某一个当前值。每个分支复制同一 TU 入口上下文，CG 之间连续更新上下文、regular-bin budget 和 pass 边界；纯 bypass/cutoff=0 使用真实幅值。

每个 TS TU 都核验来源原生 bins/value/context/order、fractional bits、出口概率模型、三遍边界和预算。BDPCM 排除计数保留，不支持几何使任务不完整。Current/STATIC_EQ/STATIC_SP 在每位置与旧选择器核验；G2/N2 每 TU 核验完整动作相同。任何失败不产出完整结果。

本版选择**原生程序内生成动作**，不落盘或加载全片 schedule，因此不需要另跑一次生成展开动作。旧 TSCPRED 文件被明确拒绝。`TS-MG-ACTION-v1` 仅用于限量验收夹具：每流最多 2 个 TU，动作字典及 21 列 id 序列，包含来源、几何、q/scan/入口摘要、Rice/range、评分 revision；外层 receipt 绑定输入、程序、源码、方法目录 SHA256。快照可在新进程重建同一 21 列 rate。

默认逐 TU 记录仅经过管道即时汇总，不写原始 CSV/JSONL。每流保存：

- `summary.json`：分量、Slice、CU 模式、尺寸的独立边际汇总；完整方法费用、分数与 rate 交叉计数；全量廉价活动计数；每方法最多 3 个损失及 3 个收益反例。
- `done.json/request.json`：完整性、身份、输入/程序/源码 SHA256、运行范围、计时、重建摘要；失败存入独立 attempt，不与成功结果混合。
- 每次 attempt 最多 1 MiB 正常日志；若做 off 比较，再最多 1 MiB。只保存帧 MD5 列表，不保存重建视频。

汇总文件默认上限 4 MiB/流；可选夹具每 TU 最多 4 MiB 快照 + 2 MiB 动作文件，最多 2 个 TU/流。默认不启用夹具。每任务目录独占锁；复用受控包装的 3 GiB 子进程地址空间和 2 GiB 树 RSS 监测。监测是每秒采样，不宣称瞬时硬限制。

没有逐位置 CABAC oracle 标签；静态评分更低/整 TU rate 更高的计数只说明策略级不一致，不能归因当前系数。SP 交叉表用 STATIC_SP 的同权分数和 rate，其余用 STATIC_EQ；总体主要比较仍同时给 Current、STATIC_EQ、STATIC_SP。

## 6. 估计与运行顺序

先运行数学/C++/Python一致性与局部语法测试，再 paired prefix 开关、快照重载；通过后才能完整 96 流 EOF 回放。命令见 [脚本 README](../../scripts/ts_multi_mapping/README.md)。默认 1 个 worker，硬上限 2；阶段顺序执行，避免同时启动两个完整流程。

全量主指标：每来源 `(R_ref-R_method)/NZ`，双方各 1/2，内容内 4 QP 等权，最后 12 内容等权。直接相加 Y/U/V 的费用，不使用 BD-rate 的 6:1:1。来源缺失、NZ=0 或未齐四 QP 时相应均衡值为空；短前缀报告不输出伪完整均值。既有 96 流参考人口为 26,000 来源帧、754,151 TU、125,949,812 系数、3,856,051 非零；不一致必须解释。

报告同时保留 pooled 原始 bits、各来源方向、序列/QP/分量/尺寸、改善/持平/变差 TU、正损失总量及限量两向反例。正损失分布为固定对数分箱，输出 p50/p90/p99 所在区间；末箱右端无界，空人口为空，不能声称精确分位。没有把大量 TU 当成独立内容样本估计极窄 CI。留一内容选组是开发集描述，不是盲测。

放行规则沿用冻结设计：重点看相对 STATIC_EQ 的新增收益和尾部；最多挑 2～3 个方案。若 X 只改善分数却恶化真实费用，应优先否定评分；若 G 达不到 X 才讨论搜索。FAST 未更快则保留 PREFIX。正式 RDOQ 联合接入及 BD-rate 仍需后续阶段授权与实现，不把本轮条件 rate 结果当成闭环收益。
