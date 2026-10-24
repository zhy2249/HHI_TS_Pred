# R14 CE 分析派生数据（2026-10-24）

分析报告：[R14完整CE与实验2部分结果](../../TS_Predictor_R14_LB_CE_Analysis_20261024.md)。
正式Current结果仍见[逐序列记录](../r14.md)；本目录补充分析，不重定义正式anchor，不回填缺点。

| 文件 | 内容 |
|---|---|
| [numeric_summaries.csv](numeric_summaries.csv) | 各组均值、中位数、sample SD、极值、p10/p90、改善/持平/退化数及分量/类别均值 |
| [numeric_sequence_matrix.csv](numeric_sequence_matrix.csv) | 七序列完整BD611矩阵；实验2没有完整四点曲线，留空 |
| [numeric_pair_differences.csv](numeric_pair_differences.csv) | 两方法相对Current的BD差，单位**百分点**；不是直接方法间BD |
| [numeric_direct_pair_sequences.csv](numeric_direct_pair_sequences.csv) | 两方法实际曲线重新积分的逐序列分量和6:1:1 BD，单位**%**；reference列定义该配对参考 |
| [numeric_direct_pair_summary.csv](numeric_direct_pair_summary.csv) | 直接配对的C/E/CE均值、有效集合与改善/持平/退化数 |
| [numeric_bootstrap.csv](numeric_bootstrap.csv) | 两种指标分开保存的95%序列bootstrap区间，不能混淆metric列 |
| [numeric_leave_one_out.csv](numeric_leave_one_out.csv) | 每次删除一条序列后的均值，区分直接BD和相对Current差 |
| [numeric_qp_summary.csv](numeric_qp_summary.csv) | 各组C/E/CE的四QP分量和6:1:1结果、有效数 |
| [numeric_qp_signs.csv](numeric_qp_signs.csv) | 每组每QP在实际可用序列上的分布和正负数 |
| [numeric_r14_2_matched_qp.csv](numeric_r14_2_matched_qp.csv) | 只在实验2已测覆盖上比较各方法；QP27为六条，QP32/37七条 |
| [numeric_meta.json](numeric_meta.json) | 五个输入CSV指纹、种子、重采样数、单位和适用范围 |

整体曲线只接纳完整实测的LB CE序列，不使用历史补点。每个序列Y/U/V分别PCHIP后6:1:1；
QP每列仅替换该实验点，其余三点使用Current，四列不能相加还原整体BD。
配对数据的公共质量区间按每个序列/分量重新求交集，可能与两组各自相对Current的区间不同。

bootstrap按七条序列配对重采样200,000次，seed=20261024，不拆开四QP曲线。
未分层、未校正多重候选筛选，只用于探索性内容敏感度；不是重复编码误差区间或总体性能保证。
符号计数容差1e−10，不代表工程意义门槛。缺点为空，不写零。

从仓库根目录复算到临时目录：

```bash
python3 scripts/ts_r14_results_analysis.py --output-dir runs/r14_analysis_20261024
```

当前快照与登记提交`6c6a2fb`匹配；后续源数据补齐后，应连同分析报告重新审核，不静默把本快照当最新结果。
原始视频、工作簿和服务器日志不在本目录。
