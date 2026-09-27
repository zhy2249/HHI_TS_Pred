# R8 全部 24 组：剩余 16 组实现说明

日期：2026-09-26。算法规格仍为 `R8-DESIGN-20260925-v2`，本次接入版本 `R8-ALL-20260926-v1`。
本次完成剩余 MODE **2/3/5/6/7/9/10/11/12/14/18/20/21/22/23/24**，不修改原先八组定义，不据已收到的七组 CE 结果调参。
**代码可运行不等于实验有收益。没有启动新的正式 CTC。Current 仍是唯一正式 anchor。**

## 1. 新增模式

CF10/CF2 是同一 CG 入口冻结 CABAC 概率下的两种 regular 路径幅值估计；不是完整实时码率。
P0 为 identity 加历史非零幅值，P1 额外包含合法 a+1 断点；五点 L/U/D/LL/UU 的非零位置数为 n。
S0 表示 n<3 用 Current；Smax/mean/min 表示仅 n=2 且直接 L/U 都非零时用相应幅值，其余 identity。

| MODE | 运行名（`TS_FIXED_PREDICTOR` / `--fixed-predictors`） | 相对父方案的唯一主要改动 |
| --- | --- | --- |
| 2 | r8_raw_sparse_mean | 1 的稀疏 L/U 分支用 `(L+U+1)/2` |
| 3 | r8_raw_sparse_min | 1 的稀疏 L/U 分支用 min |
| 5 | r8_guard_sparse_mean | 4 的稀疏 L/U 分支用 mean |
| 6 | r8_guard_sparse_min | 4 的稀疏 L/U 分支用 min |
| 7 | r8_dense_nopred | R7-2 的所有 dense 未接受出口用 identity，含 raw=Current |
| 9 | r8_trim_cost | P0/S0，各候选比较 `sum(loss)-min(loss)` |
| 10 | r8_trim_saving | P0/S0，相对 identity 删除最大正节省贡献；无额外 guard |
| 11 | r8_reject_sparse_max | 8 + Smax |
| 12 | r8_trim_sparse_max | 10 + Smax |
| 14 | r8_mixed_guard | 13 的 CIq+CF10 评分，加原 H>0 guard |
| 18 | r8_minimax_complete | 17 的 minimax regret，P0 换 P1 |
| 20 | r8_smoothed_all_support | 19 的平滑评分延伸到所有 n>=1，不用 Smax 捷径 |
| 21 | r8_dual_path | P1/Smax/raw，固定 CF10+CF2 |
| 22 | r8_causal_path | 21 的双路径权重由已完成 CG 因果更新 |
| 23 | r8_r3_dual_quant | **原 R3-1 整数 predictor** + owner 层成对量化搜索 |
| 24 | r8_raw_dual_quant | **原 R8-1 predictor** + 同样成对量化搜索 |

所有幅值先按 remapping 等价性把 p<=1 归为 identity；平局 Current-equivalent、identity、最小幅值。
19/20 平滑保留原始位置作为样本单位，n 不因展开三点而增加；minimax 的删一情景不删除候选。
旧内部 policy 0..41 不重排，新模式追加为 42..57；宏必须填写上表公开 MODE，而不是内部 policy。

## 2. MODE 22 的因果状态

- 每个 CoeffCodingContext/TU 独立初始化 `w10=w2=1`。CG 内全部候选使用相同冻结权重和概率快照。
- CG 最终 q（含 CG 全零 RD 决策）完成后，以原生三 pass replay 统计非零 regular 位置 N10/N2。
- 两者都零则不更新，否则分别 `w=max(1,w/2+N)`；零系数和 pure bypass 不计入，BDPCM 不更新。
- 权重不跨 TU；上界由实际 CG coefficient 数导出并断言，不引入可调阈值。
- RDOQ 使用私有最终 q replay 的预算，不使用逐点近似 `remRegBins` 推测最终路径。
- Writer estimator 各试编码对象独立，Reader 完成当前 CG 反映射后只更新一次；观察开关不控制算法状态。
- CG0 与 21 完全相同；一个 CG 的 TU 不可能获得历史校准增量。

实现：`ContextModelling.h/.cpp`。`TS_R8_PATH` 是可选调试记录，含 N10/N2 和下一 CG 权重；正式运行不逐 CG 打印。

## 3. MODE 23/24：真正的 owner-RD 成对搜索

不能把这两组实现为仅扩大 QuantRDOQ 的候选后直接保留结果。本次加入 `EncoderLib/TsR8Search.h`，在原搜索器的同一 TS trial 入口执行：

1. q0：原 round/min/up 搜索，up 仍要求原条件。
2. 从同入口 TU、CABAC、信号状态恢复；q1：round>0 时允许合法且不重复的 up，不再要求 remap(up,p)=1。
3. 每条分支重新量化整块，重建后继预测、全零 CG 决策、残差/重建和所属搜索器的语法及失真。
4. 用原 owner 的 `J=D_owner+lambda*R_owner` 选择，平局 q0。q0 获胜时从入口重跑 q0，断言 cost 和最终 q 完全复现。

支持原有帧内 luma、独立 chroma、联合 transform、JCCR，以及帧间独立分量和 JCCR 六个 evaluator 入口；不另造 RD 口径。
其中联合 transform 的 owner=2 在当前 `trTypesJnt` 中仅含 NST，没有 TS，因此当前不触发成对搜索；这不是漏测一个可达 TS 路径。
原始 chroma 权重、LMCS、BIF、残差域/重建域失真、owner 的 CBF0 竞争和有效性检查均留在原 evaluator。
BDPCM、非 TS、noResidual 不启用成对试验；原编码器自身不执行 RDOQTS 的情况（例如小于等于 2 的边长、lossless、工具关闭）仍沿用其原路径，不强行开启 RDOQ。

保存的是有独立存储的 coefficient/sign、TU 元信息，以及目标分量相关 reco/resi/pred/orgResi/picture-reco 缓冲。
帧内 luma 的 CUCtx/CUCtxIntra 也回到相同入口；滤波/变换临时输出由选中分支的原 evaluator 重新生成。
双分量路径一起恢复 Cb/Cr；`puiZeroDist` 在成对选择结束后只累计一次。没有向 decoder 传递 encoder-only RD 信息。
分支请求为 TU 上的短生命周期 encoder-only 字段，结束时关闭，不复制成码流状态。Decoder 只运行该组固定 predictor。

原 zero early exit、幅值上限及最多三个不同量化候选不变。保证仅是 **同入口局部目标不劣于 q0**，不是全序列 BD-rate 保证。
搜索代价最多两次试编码，加 q0 获胜时的一次重演；可能明显增时，应先检验有效活动。

## 4. 开启方式

优先修改 `source/Lib/CommonLib/TypeDef.h`，重新编译两端：

```cpp
#define JVET_BJUT_TS_FIXED_PREDICTOR 1
#define JVET_BJUT_TS_R8_MODE       22 // 举例；0=Current，1..24选一组
```

固定 NoPred/gradient/directional、CONDITIONAL_MODE、R2..R7_MODE 全部为0；建议 R7_SHADOW=0。
本次交付默认仍为 **R8_MODE=0**。不添加新的算法开关；旧轮互斥、master-off、非法值检查继续有效。
不通过 CMake 选实验；以下仅指定构建目录和编译选项：

```bash
cmake -S . -B build/ts-r8-all -DCMAKE_BUILD_TYPE=Release \
  -DNX2_TOPLEVEL_OUTPUT_DIRS=OFF -DNX2_ENABLE_LINK_TIME_OPT=OFF
cmake --build build/ts-r8-all --target EncoderApp DecoderApp TsRateCodecTest TsR8QuantTest -j8
```

原 batch 省略 `--fixed-predictors` 时使用实际二进制的宏默认；提供参数时强制覆盖。
不要只看服务器源码宏：检查 Encoder/Decoder 的 `EXPERIMENT`、公开 `mode` 和 `revision` banner。
23 的 banner 明确 integer-R3；21/22 明确双路径；23/24 的搜索诊断与最终 Writer 统计分开。

## 5. 批量脚本和结果目录

24 组均已注册到原 `batch_test.py`。保留共享跨组任务池、逐组完成即复制/写表、失败日志、resume 和无重建功能。
原首八组包装脚本默认清单**不变**，避免用户续跑 19 时误启动其余 16 组。新增组使用同一个脚本的显式覆盖即可。

例如先 dry-run 稀疏配对组（不重跑完整 anchor）：

```bash
bash scripts/run_ts_r8_lb_ce.sh \
  --encoder build/ts-r8-all/bin/EncoderApp --decoder build/ts-r8-all/bin/DecoderApp \
  --fixed-predictors r8_raw_sparse_mean,r8_raw_sparse_min,r8_guard_sparse_mean,r8_guard_sparse_min \
  --out-dir runs/ts_r8_remaining_LB_CE_half --input-dir /你的/YUV目录 --jobs 10 --dry-run
```

确认后去掉 `--dry-run`。LBeu/CE/四 QP 和半帧读取原 INI，不二次除2；不输出重建文件。
所有剩余组的名称见上表。不要将新程序写入旧实验续跑目录；二进制变更会触发 resume 指纹检查。

23/24 推荐先用原预检脚本，只覆盖模式、二进制及输出目录，保留预注册四序列、QP22/37、17帧：

```bash
bash scripts/run_ts_r8_preflight.sh \
  --encoder build/ts-r8-all/bin/EncoderApp --decoder build/ts-r8-all/bin/DecoderApp \
  --fixed-predictors r3_risk_guard,r8_raw_sparse_max,r8_r3_dual_quant,r8_raw_dual_quant \
  --out-dir runs/ts_r8_quant_preflight --input-dir /你的/YUV目录 --jobs 10 --dry-run
```

真实长编码由用户执行。本次没有据短测临时挑有利序列，也未改动已收到的工作簿。
收件目录全部沿用 `experiments/ts_predictor_r8/r8_<MODE>_<name>/{smoke,LB_CE,LB_B,RA_CD}/`。

## 6. 日志和分析边界

默认 `TS_R8_STATS=1` 在线聚合；`TS_R8_TRACE=1` 仅调试。每系数不写文本。
原 `TS_R8_STATS` 只反映最终进入 TS residual Writer 的样本，仍有工具选择偏差。
20 在 n=1/2 也有真实 score；17/18 有 regret；21/22 的 score 尺度含双路径权重，不能与单份 CF 直接横比绝对值。

23/24 新增独立 `TS_R8_SEARCH_HEADER/TS_R8_SEARCH`：

- 键：mode/component/W/H/CU-QP/intra/joint/owner；owner 0..5 对应上述六个 evaluator。
- pairs、extra_up_candidates、q_changed、chosen_q1、ties、both_valid、j0_sum、j1_sum、local_gain_sum。
- q_changed 是**同入口、CG及owner全零决策后的试编码 q0/q1 差异**，不是最终保留 TS TU 的变化率。
- local_gain 只在两条分支都有效时累计；J0/J1 为原 owner 单位，不是 CABAC bits。
- 未记录分支 DeltaR/DeltaD 分解、临时 coefficient-level q、最终 trial 存活关联；这些是 **not_measured**，不能填0。

```bash
python3 scripts/ts_r8_activity.py runs/ts_r8_quant_preflight \
  --out runs/ts_r8_quant_preflight/activity
```

新增 `search_by_stratum.csv` / `search_by_job.csv`；不把 search trial 数并入最终 TU/CG 分母。
结果 BD-rate 仍按 Y/U/V 分量分别计算后 `(6Y+U+V)/8`，CE 七序列等权；不把 C/E 两类简单各赋一半。

## 7. 本地验证与下一步

验证结果及局限见本文件后续验收节。初轮人工输入的 23/24 已有搜索 q 改变和 q1 局部获胜，
但最终码流仍与 R3-1/R8-1 一致。这不是宏未生效，也不是正式实验有效性的证据。

建议顺序：先 2/3/5/6 补齐稀疏配对；再 7/9/10/11/12/14；随后 18/20；21/22 必须成对看。
23/24 先查真实短测的最终有效活动和增时。如果局部试编码获胜始终不能改变最终输出，应停止完整 CTC 铺开。
实现所有预注册组不意味着全部具有同等研究优先级；不因已有负结果悄悄改变本轮公式。

## 8. 2026-09-26 实际验收

| 检查 | 已执行结果 |
| --- | --- |
| 构建 | 独立 Release Encoder/Decoder、TsRateCodecTest、TsR8QuantTest；旧二进制保留 |
| Python | **95 项通过**；含模式注册/宏互斥/默认覆盖、原批量调度写表、数学规格与统计解析 |
| 全24公式 | 新增 **6,888** 个 C++/独立 Python 对照；旧八组 **24,672** 个对照继续通过 |
| native CABAC | 每组160 TU、1,491 CG、23,436个当前/未来位置污染检查；24组全部通过 |
| C02 专项 | TU reset、CG0等于21、整数权重递推、空/bypass排除、未来CG污染、Writer/Reader权重一致 |
| 父 predictor | 23 与原 R3-1 remapping 等价；24 与1相同；BDPCM独立排除 |
| 原生量化压力测试 | 23/24各512次，人工概率状态；各300次 q0/q1不同，31次全零输入不变；两分支重复运行稳定、输入未改 |
| 闭环 smoke | **288 个 encode/decode 任务全部 hash 通过**；2帧64×64，AI22/0、LB22、RA37、禁TS、启BDPCM |
| 两端追踪 | **15,874 个 CG trace + 619 个 C02 path record 一致** |
| 旧模式 | 旧34种模式与旧R7程序bit-exact；与首八组历史验收共有的168份码流全部一致（含12份OFF对照） |
| master关闭 | 隔离源码副本直接改TypeDef master=0构建；六个case与旧OFF以及Current同流 |
| 无TS / 无观察 | 全24模式禁TS与Current同流；AI22分别关stats/trace后仍与开启时同流 |
| 批量 dry-run | 剩余16组LB CE共448点；23/24加两个父对照的真实预检32点；**都只生成任务清单** |

人工完整编码中额外量化搜索的聚合（排除 quiet 重复）：

| 模式 | 成对试编码 | 额外up候选 | q改变的trial | q1局部获胜 | 最终码流相对父法变化 |
| --- | ---: | ---: | ---: | ---: | --- |
| 23 | 118,289 | 693,478 | 391 | 217 | 六个case均无 |
| 24 | 119,494 | 759,331 | 2,185 | 1,423 | 六个case均无 |

说明搜索并非死代码，但这些获胜不足以改变本次最终输出。未跟踪每个trial的最终存活归属，不能声称已逐一证明其被哪项工具淘汰。
实际观测 owner 为0/1/3/4/5，与可达 TS 路径一致；owner2仅NST。其余新增14组均在至少一个case相对父法改变码流。
人工概率压力测试证明分支可执行，不证明该状态在CTC出现；本表也不是性能收益或独立样本显著性分析。

最终证据保留于 `runs/ts_r8_all_smoke_final/{validation.json,summary.csv,quiet_summary.csv,activity/}`，不上传原始码流/大日志。
观察汇总144个R8任务、19,506个分层行、120个有TS统计、10个有成对搜索统计；其余禁TS任务无统计段属正常。
初轮聚合约5.2 MiB final分层CSV、252 KiB search分层CSV，没有逐系数文本。

复现命令：

```bash
python3 -m unittest discover -s scripts -p 'test_ts_*.py'
python3 scripts/ts_r8_smoke.py \
  --encoder build/ts-r8-all/bin/EncoderApp --decoder build/ts-r8-all/bin/DecoderApp \
  --native-test build/ts-r8-all/bin/TsRateCodecTest --quant-test build/ts-r8-all/bin/TsR8QuantTest \
  --off build/ts-r8-all-off/bin/EncoderApp --out runs/ts_r8_all_smoke_final --jobs 8
```

`--off` 使用本地独立master关闭程序，`--legacy`/`--anchor-off`可指定其它服务器保留的旧程序。
未取得旧程序时可先执行本地 native/公式测试，但不得把缺失对照标成bit-exact已验证。
