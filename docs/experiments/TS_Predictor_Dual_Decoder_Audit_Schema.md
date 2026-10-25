# 双源解码审计 schema 2

实现：R13-DUAL-DECODE-AUDIT-impl2。所有本文件的rate为TSRC fractional estimate，32768单位=1估计bit。
不是实际码流字节长度，不是BD-rate。主人口是已进入residual_codingTS的最终TU；原图、失真、落选trial均不可恢复。

## 文件与字段

| 文件 | 记录单位与主要字段 |
|---|---|
| manifest.json / build_info.json | spec/实现、评分revision、程序/输入SHA、原生绑定、采样/预算、服务器身份未知项 |
| run.json | 原生模式、实际命令/观察参数、有效limits、二进制/输入/脚本指纹、汇总状态 |
| native_validation.json | 原生逐bin/状态核验、各层complete、各分量请求/完成/预算计数、截断计数 |
| decode_validation.json | 实际/预计帧数、SEI状态、开/关重建检查、分层完整性、输出限额和缺项 |
| census.csv | 每POC/分量廉价完整分母、Slice×CU计数、幅值/支持数数组、selected/每方法/位置/快照完成数 |
| frame_summary.csv | 每POC/分量/方法，C0/C+、完整性门控后的HT量/均值、已知样本描述 |
| tu_policy_matrix.csv | 所有选定TU（含未回放完），真实Slice/CU、q/entry摘要、7方法rate、逐方法原因、预算和快照 |
| strata.csv | sample/分量/方法/分层，Slice和CU分开、幅值/n/面积/边界/分差/冲突/语法路径，以及加权指标 |
| regret_distribution.csv | 同一两级权重的损失直方图，完整均匀样本才给ht_count |
| history_summary.csv | 历史可用、众数1、候选/实际映射新增、选择新增、覆盖收益/相对父策略损失 |
| score_effects.csv | 六组固定对照的signed delta、改善/变差/持平，均匀与富集分开 |
| examples.jsonl | 均匀样本池的有限随机案例与各分量正负极端；保留原sample标签 |
| audit.jsonl | 有上限的TU/点/frame原始结构化记录；不是全片逐系数/逐bin日志 |
| pair_comparison.json/csv | EQ/SP四格矩阵、行内差、来源等权、共同帧/单边几何/缺项 |
| policy_comparison.csv / score_comparison.csv | 七方法两来源及balanced；一侧分母为0或覆盖不足则相应值为空 |
| pair_uncertainty.json | POC块条件区间、有效重复数；明确不含两级抽样和跨内容总体方差 |
| snapshots/*.tsa | 有版本、长度/校验和的完整可恢复q/context/语法快照；磁盘限额独立 |

## 身份和分母

`slice_type`来自真实Slice：B/P/I/L。`is_intra_cu/is_inter_cu`来自CU模式，绝不从CU反推Slice。
`slice_cu_counts`是长度12的数组：B、P、I、L各依次记录intra/inter/other TU数。
`amplitude_counts`为[0,1,2,3–4,≥5]，`support_counts`为n=0..5；均为全遇到TSRC人口（含BDPCM）。
可评分位置只取eligible TU的`a>0,n>=3`，与这些全量辅助直方图分开。

`eligible_*`表示协议支持且非BDPCM，不以score输赢选人口；`scoring_eligible_*`额外检查非零支持数。
`sampling_population_tu`仅在detail模式可能被显式几何过滤，不能当作全量人口。
`point_requested/done`、`coverage.point_requested/done`的两个元素是uniform、disagreement。
其它层的完整定义见[实现说明](TS_Predictor_Dual_Decoder_Audit_Implementation.md)。

## 方法、oracle与对照

方法顺序始终为CURRENT、STATIC_EQ、STATIC_SP、KEEP_EQ、KEEP_SP、KEEP_EQ_H、KEEP_SP_H。
C0是原候选；Cplus仅追加TU扫描前非零幅值众数候选，不增加历史伪样本。
`distinguishable`/`distinguishable_plus`分别表示该候选集合的真实反事实cost是否有至少两个值。
全tie不进入accuracy分母；等价最优集合中任意p都算正确，不按任意唯一oracle标签判断。

完整策略rate和单位置oracle是不同实验，不把各位置delta相加当作整TU增量。
点记录的`direct_sp_eq_frac`＋`propagation_sp_eq_frac`等于该点SP−EQ的完整TU增量；
后继p未变但cost传播不算后继再次误判。

## 权重、缺失和完成状态

主点估计权重w=(TU_population/TU_selected)*(position_population/position_selected)。
`ht_*`是完整均匀样本的扩展量，`accuracy/mean_regret_bits/positive_regret_mean_bits/regret_*`采用同一权重。
正损失均值分母为Σw*[regret>0]；加权分位是逆经验CDF。没有正损失时正损失均值为空。
`sample_unweighted_*`明确为未加权描述；`sample_weighted_*`、`observed_weighted_*`是已保留样本描述，
即使预算不足仍可存在，不得称为原总体估计。富集样本绝不与均匀样本合并算总体频率。

rate总量用TU权重扩展，按全体eligible_tu/eligible_nz归一。未支持/BDPCM人口另报。
balanced先在每origin内估计，再各占1/2；不把两个来源所有系数混合。
空分母null/CSV空值不是0；`policy_missing_reason`、`point_missing_reason`、`snapshot_missing_reason`解释TU缺项。
frame/pair的coverage_complete/rate_complete/score_complete说明完整性，ht分母0说明无相应支持。

`audit_complete`是所有请求层都完成的强合同；summary仅请求census，其回放complete及audit_complete为null。
`decode_complete`可以在审计预算不足时为true。快照缺失不否定已完整的数值比较，但强合同仍为false。
富集未完成可保留完整均匀主估计；主比较必须依赖其所需覆盖，不能只读一个顶层布尔值。
读取派生CSV时必须同时检查decode_validation.output_complete，输出截断不能被解释为空人口。

schema 1快照可离线恢复语法，但未记录的Slice只能为unknown；不允许给旧CSV补猜Slice后混入schema 2。
不同schema/revision/二进制/有效limits不得直接做主双源比较。
