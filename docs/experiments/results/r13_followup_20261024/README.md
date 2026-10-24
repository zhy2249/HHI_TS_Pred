# R13 解码与搜索续查派生数据

日期2026-10-24。说明与结论见[续查报告](../../TS_Predictor_R13_Decoder_Followup_20261024.md)。
C0=Current、EQ=R13-1、SP=R13-2。此目录不是新一轮正式CTC结果，不计算或替换BD-rate。
原始 `.bin`、视频、构建产物和完整诊断日志均留在 `runs/r13_followup_20261024/`。

## 解码数据

完整查询表采用 `decode_verified/` 的10组目标POC：Johnny32 EQ/SP POC16、C0/SP POC0；
Johnny27 C0/EQ/SP POC8；KristenAndSara32 C0/EQ/SP POC0。
解码总帧数90，观察开/关两遍共180次MD5检查。范围重叠，不视为180个独立图像样本。
另两条首帧定点CCP解码，共4次开/关MD5检查。

| 文件 | 内容 |
|---|---|
| `decoder_cases.json` | 10组源marker、命令、模式/scope、码流/程序/输入指纹和独立on/off观察环境 |
| `decoder_validation.csv` | 每组实际解码数、off对照数、与原encoder共有stage精确匹配数 |
| `decoder_stages.csv` | 300条整帧分量stage：SSE、原图/重建hash、域和裁剪标识 |
| `paired_stages.csv` | 六个预设比较的同阶段SSE差与重建是否相同 |
| `filter_stage_split.csv` | 各轨迹每项滤波/裁剪的输入、输出及自身SSE改善；含只读clip-only度量 |
| `filter_controls.csv` | 实际CTU/分量ALF、CCALF、CCSAO、LFCCCM开关及所记录参数摘要 |
| `chroma_ctu_self_gains.csv` | 仅在CTU分量几何与64×64网格完全吻合时匹配的局部滤波SSE改善 |
| `decoder_comparisons.json` | 稳定几何键配对计数，明确相同、不同、新增和缺失块 |
| `first_retained_blocks.csv` | 前8个CU/TU/filter差异和全部不同CTU证据；不是全部变化的叶块清单 |
| `first_blocks.json` | 独立核验的首个保留CU/TU/CTU和共同32×32父节点；保留其原核验日志SHA |
| `ccp_cases.json` | 两个CCP观察的运行身份、指纹及开关对照检查 |
| `first_ccp_reference_chain.json` | 首个UV块实际引用范围、两个返回模型、精确参数及日志行定位 |
| `ccp_field_comparison.csv` | CCP参考及模型逐字段比较 |
| `preliminary_search_audit.json` | 首轮格式/上限不合格搜索日志的明确拒绝状态；码流等价和独立解码另列 |
| `search_cases.json` | 严格重放EQ/SP各17帧的输入、命令、观察身份、程序/码流指纹及byte-exact/解码结果 |
| `search_comparison.json` | 完整286278/268534条轨迹的严格配对摘要；公共前缀、首次数值/控制/历史差和配对限制 |
| `first_search_divergences.json` | 首次数值、控制、历史差及首个完成搜索节点重建差的精简证据 |
| `selected_search_chain.json` / `.csv` | SSE键58的8×32候选、门槛操作数、实际SBT候选和父块结果；门槛由源码及日志重建，未做干预 |
| `validation.json` | 观察开/关、码流、解码、守恒、测试和未测范围 |

10组共有的7个stage×3分量共210条，与上一轮encoder记录的SSE、原图hash和重建hash全部一致。
其余3个stage是本轮新拆分的 clip-only、CCSAO裁剪前、普通ALF输出。
普通ALF输出是每CTU进入真实CCALF前的私有快照拼接，不是禁用CCALF后重新解码。

`first_blocks.json`来自接口开发时的独立块审计；后续 `decode_verified` 重新核验相同块数据。
此前试用接口曾将final_clip取在最终亮度裁剪之前，且包装脚本曾把off环境误登记为on环境。
两项均已修正并重新解码；正式stage表和 `decoder_cases.json` 均使用修正后的 `decode_verified`，
不混用先前 `decode/`、`decode_final/` 的错误字段。独立块审计不使用早期错误stage字段。

程序SHA固定实际运行二进制；源码dirty patch和未跟踪文件摘要是运行时工作树快照，
不宣称独立证明了该二进制所有编译输入。对应实现以本任务提交源码为准，诊断期间不同程序版本保留各自指纹。

## 度量和比较

- SSE针对相同原图，8位源值显式提升到10位内部域，未加权；raw/待裁剪stage不能当合法输出PSNR。
- 没有原图时仍能获得语法、q和重建hash，SSE/原图hash为−1，不记为零。
- CU/TU/CTU hash为FNV语义摘要，不是MD5或无碰撞证明；真正解码验收另使用码流SEI中的逐帧MD5。
- CU/TU阶段可能仍处于LMCS亮度域，stage已经逆LMCS；禁止跨域混比。
- 按POC/CTU/channel/component/几何和所属CU匹配，划分改变的块保留unpaired，不能按日志第n行硬配。
- 每项自身改善 `G = SSE_in − SSE_out`，方法差距的扩大等于参考方法获得的改善减去测试方法获得的改善。
- APS编号相同不代表参数相同；普通ALF完整系数/clip数组尚未记录。
- 最终获选人口不包含落选候选，不能替代编码器搜索轨迹；没有将单块变化当作单块损失或全300帧归因。

复算完整解码查询表（不运行编码、不开工作簿）：

```bash
python3 scripts/ts_r13_decode_analysis.py \
  --root runs/r13_followup_20261024/decode_verified \
  --output docs/experiments/results/r13_followup_20261024
```

解码包装、纯日志配对、搜索重放和严格搜索分析的入口分别是
`ts_r13_decode_diagnosis.py`、`ts_r13_decode_analysis.py`、`ts_r13_search_replay.py`、`ts_r13_search_analysis.py`。
`search_replay`会真正编码，从原成功marker复用完整前缀与配置，要求新输出整码流byte-exact；
不支持把POC16截出来当新I帧，不复用正式实验成功标记，不输出重建视频。

本轮只有两种模式各17帧的完整重放，没有改变任何搜索设置；首轮诊断失败日志保留但不作为完整链证据。
大体积完整搜索差异/未匹配CSV留在 `runs/.../search_review/`，本目录只保留精简事件证据。
复算严格搜索摘要：

```bash
python3 scripts/ts_r13_search_analysis.py \
  --reference runs/r13_followup_20261024/search_complete/j32_eq/encode.log \
  --test runs/r13_followup_20261024/search_complete/j32_sp/encode.log \
  --output-dir runs/r13_followup_20261024/search_reanalysis

python3 scripts/ts_r13_search_chain.py \
  --reference runs/r13_followup_20261024/search_complete/j32_eq/encode.log \
  --test runs/r13_followup_20261024/search_complete/j32_sp/encode.log \
  --output-dir runs/r13_followup_20261024/search_reanalysis
```

不要给正式完整重放加 `--allow-truncated-prefix` 或 `--legacy-byte-fields`；
这两个显式选项仅为审计首轮失败日志保留，不能提升其证据级别。
