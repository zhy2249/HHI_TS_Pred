# R13异常点诊断派生数据（2026-10-24）

## 服务器正式结果与300帧日志

本节只登记已存在的服务器数据、派生文件与计算口径。原始工作簿、编码/解码日志不复制到本目录。

| 文件 | 范围与记录数 | 内容 |
|---|---|---|
| `server_formal_anomaly_points.csv` | 4点×R13-1/R13-2，共8行 | Johnny QP27/32/37、KristenAndSara QP32的正式逐QP Y/U/V与6:1:1 BD-rate、加权贡献、实际码率/PSNR、来源单元格 |
| `server_formal_control_points.csv` | 4点×2方法，共8行 | Johnny22、FourPeople27/32、KristenAndSara27，同口径机制对照 |
| `server_formal_point_differences.csv` | 8点 | R13-2减R13-1的Current参考逐QP结果差及分量加权贡献差，单位百分点；不是两方法之间直接计算的BD-rate |
| `server_300frame_summary.csv` | 3个配对，共900个配对POC | Johnny27/32、KristenAndSara32，R13-2对Current的300帧汇总 |
| `server_300frame_windows.csv` | 57行 | 各配对的POC窗口、前缀、实际slice QP、I/B类型与TId分组；窗口相互重叠，不能重复相加 |
| `server_johnny37_independent_check.json` | Johnny37 | 从原始工作簿独立重算的正式单点BD-rate、VBA等价交叉核验、实际RD变化及源文件SHA |
| `server_sources.json` | 6份日志及2个台账CSV | SHA-256、源路径、行定位、有效记录数；不含环境变量或原始日志全文 |
| `source_paths.md` | 源码核验 | 实际配置允许的Y→UV传播路径、源码行号与stage观测口径；配置启用不等于已认定损失原因 |

### 正式逐QP口径

逐QP BD-rate只把目标QP完整RD元组替换为该方法的实测点，其余三个QP使用完整Current参考曲线。各分量分别以PCHIP计算BD-rate，再取`(6*BD_Y+BD_U+BD_V)/8`。加权贡献分别为`6*BD_Y/8`、`BD_U/8`、`BD_V/8`，相加等于该点6:1:1结果。逐QP结果不相加还原完整四点实验BD-rate。

表内四个异常点及四个对照点均为已登记实测，没有本次补点。主数据来源为`docs/experiments/results/qp_bdrate.csv`与`rd_points.csv`；原工作簿为`experiments/ts_predictor_r13/R13_1_JVET-hhi.xlsm`、`R13_2_JVET-hhi.xlsm`，anchor为`scripts/JVET-hhi.xlsm`的Reference。

Johnny37独立核验读取Current四个点以及R13-2的QP37点，两种PCHIP实现一致，并与台账一致；没有上传该QP的逐帧日志，因此不包含QP37帧时序核验。

### 300帧日志口径

六份日志各包含300个编码POC（0–299），并各含10轮解码、3000个解码POC记录；编码帧只按包含bits/PSNR的行计数，重复解码不重复纳入统计。合计1800个编码帧记录、900个配对POC、18,000次解码帧MD5检查；哈希检查均通过。三组工具配置和逐POC的实际QP、slice类型、TId、NAL类型、层号、尺寸均配对一致；日志打印RD汇总与台账对应点一致。

帧PSNR优先读取`xY/xU/xV`精确double，汇总与台账核对时使用日志打印summary。`delta_bits_pct`以窗口内总bits取比；PSNR差为同窗口逐帧差的均值。`aggregate_mse_change_*_pct`先累加各帧`10^(-PSNR/10)`再取比，适用于本次同尺寸、同峰值的配对；不是对平均PSNR取指数，也不是逐帧MSE比的均值。

POC窗口、前缀以及actual-QP/slice/TId分组都是相同300帧的不同观察方式，记录数不能相加作为独立样本量。这里的帧差包含闭环选择与参考帧反馈，不是固定q反事实。服务器耗时不用于本次算法复杂度比较。

生成命令（仓库根目录）：

```bash
python3 scripts/ts_r13_log_diagnosis.py
```

该命令在`runs/r13_diagnosis_20261024/log_audit/`生成详细审计；本目录保存其中小体积可查询派生表。正式点和独立QP37核验的来源及定位见各CSV/JSON。本节不登记未完成的本地短测，也不以短帧结果替代正式BD-rate。

## 本地已完成的短测

全部20组、148编码帧通过逐帧解码MD5校验：修改前冻结程序3组×5帧；新诊断17组共133帧。
最长单组17帧，无完整300帧本地重跑。所有输入前缀均从POC0开始，TemporalSubsampleRatio=1；不保存重建视频。
重叠前缀和多轨迹不构成独立样本，也不与正式四点曲线混合。

| 文件 | 内容 |
| --- | --- |
| `local_runs.csv` | 20组任务的序列、名义QP、模式、scope、帧数、码率、Y/U/V精确均值、实际码流长度/SHA及解码核验数 |
| `local_frames.csv` | 148帧的bits、精确Y/U/V PSNR、实际slice QP、重建MD5及日志行号；保留重复前缀的独立case身份 |
| `local_sources.json` | 20份实际命令、启动身份、日志/marker SHA；不包含继承的环境变量 |
| `local_stages.csv` | 新诊断133帧×7阶段×3分量，共2793行整帧SSE/hash；SAO/BIF标记待clip |
| `local_writer.csv`、`local_writer_by_poc.csv` | 最终TS获选人口的逐运行/逐POC固定q CG估计；无对应分量行表示没有最终TS，不能理解成没有搜索trial |
| `local_rdoq.csv`、`local_rdoq_by_poc.csv` | 全TS搜索trial局部探针，含落选TU；保留实际CG是否清零，D为内部缩放域 |
| `local_same_history_uniform_spatial.csv` | 同一轨迹、同历史的U/S局部配对；固定候选与原生候选分开 |
| `local_paired_frames.csv`、`local_paired_stages.csv`、`local_pair_review.json` | 已完成闭环轨迹之间的帧/stage对照与首次分叉；与固定q反事实严格分开 |
| `local_validation.json` | 冻结程序/源码/输入SHA、native语法/量化bit-exact、分量干预、五帧纯观察、服务器前缀复现和实际完成记录 |
| `johnny32_bitstream_prefix.json` | U/S17帧码流首个不同字节及本工程NAL边界核验；16个完整图像前缀byte-exact |
| `plot_stage_deltas.csv`、`stage_deltas.png` | 三个指定帧/分量的同阶段对照图及数值；不是独立滤波器开关实验 |

`case_root + case`标识任务；模式与scope均不可省略。`scope=luma/chroma`是改变编码决策的诊断消融，
不是正式R13-2结果；scope必须在Encoder/Decoder一致。统计开关默认为关闭。

Writer的C/U/S分支固定最终q，每CG从真实入口context和budget重新开始；其代价不包括向下一个CG的替代context传播。
RDOQ每个probe从真实历史、context、残差和lambda开始；`trial_cg_zero`是实际轨迹CG决定，
没有为每个probe重新运行CG全零或后续CU模式决策。不同轨迹总trial数可能不同，不能跨轨迹相减局部J总分。
RDOQ的`delta_rd_over_lambda`是逐位置归一后的和，不能拿聚合D除以平均lambda重新构造。

复算本地查询表（原始运行仍在本机时）：

```bash
python3 scripts/ts_r13_collect_diagnosis.py \
  --case-root runs/r13_diagnosis_20261024/probe5 \
  --case-root runs/r13_diagnosis_20261024/diag_probe \
  --case-root runs/r13_diagnosis_20261024/diag_followup \
  --output-dir docs/experiments/results/r13_diagnosis_20261024

MPLCONFIGDIR=/tmp/ts-r13-mpl-cache python3 scripts/ts_r13_plot_diagnosis.py \
  --output-dir docs/experiments/results/r13_diagnosis_20261024
```

解析各单日志的更细分表使用`ts_r13_diagnostic.py`；阶段配对使用`ts_r13_frame_diagnosis.py`。
任务成功还需collector重新核对独立解码日志，未完成任务不纳入；无成功marker、码流长度不符、非零返回码和MD5失配均拒绝。
完整解释、源码改动和未解决范围见[诊断报告](../../TS_Predictor_R13_Anomaly_Diagnosis_20261024.md)。
