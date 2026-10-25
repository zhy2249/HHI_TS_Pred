# R13 双码流评分审计解码器：impl2 实现与交付

2026-10-25。修复基线：`1270ad3c2b24f9a7e78a19167cb6a55a3194e2e0`。
当前实现 `R13-DUAL-DECODE-AUDIT-impl2`，观察数据/manifest schema 2；
依据[双源需求](TS_Predictor_Dual_Stream_Decoder_Audit_Requirements.md)及本轮用户审查。
[impl1验收](results/r13_dual_decoder_audit_20261025/README.md)保留为历史记录，不能据其CSV的旧Slice标签作新分析。

本轮没有改变R13-1/2的真实候选、评分、预测、RDOQ、反映射或解码语法，没有运行EncoderApp或视频编码。
只修复观察层的统计、采样、完整性及交付。正式RD/BD-rate和逐QP结果文件均不改动。

## 1. 修改前后

| 项目 | impl1 | impl2 |
|---|---|---|
| Slice / CU | 用`intra`把CU模式推断成I/B Slice | 捕获真实`m_eSliceType`；独立`slice_type/is_intra_cu/is_inter_cu` |
| summary分母 | 早退前未计eligible | 全量、目标、回放资格、评分资格先按共同定义统计；summary零Ctx复制/零回放 |
| 部分策略 | 方法循环后段可能缺rate，顶层仍complete | 原生、七方法、单点、快照、输出逐层状态；缺rate为null并给原因 |
| 分量预算 | Y/U/V顺序共享剩余预算 | 分量固定保留1/3，再按采样优先级分给TU；不借其它分量/来源余量 |
| 方法顺序 | 先执行的方法较容易完成 | 替代方法整体预留预算；不足时不执行部分替代方法；原生/同序列缓存只作诊断保留 |
| 位置顺序 | 预算可能只完成前几个位置 | 两个均匀位置为一组预留，再处理富集组；完整性分开统计 |
| 抽样hash | FNV优先级未充分混合 | FNV几何键后作64位avalanche；位置使用独立domain盐；记录sampling revision |
| 正损失均值 | 未加权；与准确率不同口径 | 准确率、均值、正损失均值、分位和损失分布采用同一两级包含权重 |
| 缺观察帧 | 可能用已有summary交集掩盖缺帧 | 共同已解码且请求观察的帧是预期集合；缺summary/方法行使主比较不完整 |
| 原始/派生截断 | 输出存在不等于全部完成 | 原始记录丢弃按kind计数；派生输出按预算写，预留最终metadata，独立output_complete |
| 交付 | 程序、码流主要在开发目录 | 明确的本地tar.gz打包/校验接口，异目录执行验证；不冒称远程已可下载 |

具体源码：`source/Lib/DecoderLib/tsaudit/{Manager,Replay,Offline,Budget}.h`。
CABAC bin计数和公共TSRC三遍回放算法保留。新增`Budget.h`只负责观察配额，完全不影响原生CABAC预算。
Python汇总提取至`scripts/ts_audit_stats.py`，运行/身份/续跑仍由`ts_decode_score_audit.py`负责。

## 2. Slice、CU与快照身份

- `slice_type`直接来自Slice，取B/P/I；本工程另有L时原样记录L，不归作B。未覆盖的L工具组合不宣称已验收。
- `is_intra_cu=(predMode==MODE_INTRA)`，`is_inter_cu=(predMode==MODE_INTER)`；其它模式保留other。
- B Slice中的Intra CU记为`B / intra`，不当作I Slice。
- TU、点、离线replay各自保留字段。frame行使用真实Slice集合（单一类型/mixed/no_TS）及CU计数，
  不给整帧假造一个CU模式布尔值。`strata.csv`分别有Slice、CU及其交叉分层。

TSAUDIT schema 2新增真实Slice/Inter CU字段；其余q、scan、概率状态、bins、pass/budget显式字段不变。
仍可读取schema 1快照，旧`intra`只解释为CU模式，缺失Slice为unknown、Inter CU为-1；不能推断成I/B。
旧观察CSV不能改个schema就直接合并；主比较拒绝非schema 2、不同revision/二进制/采样参数。

## 3. 分母定义

观察入口仍为`CABACReader::residual_codingTS`，即实际送入TSRC、带残差的最终TU。
未进入该函数的普通变换、CBF=0或其它残差编码路径不在这个人口中；不把此计数称为全部编码搜索TS候选。

| 字段 | 定义 |
|---|---|
| tu / coeff / nz | 观察范围内遇到的全部TSRC TU/系数/非零数，包含BDPCM |
| target_tu / target_coeff / target_nz | 排除BDPCM后的目标人口 |
| eligible_tu / eligible_coeff / eligible_nz | 目标人口中快照协议支持的几何/动态范围；不依赖某评分的输赢 |
| scoring_eligible_tu / scoring_eligible_nz | eligible中至少一个/全部满足`a!=0 && n>=3`的评分位置 |
| sampling_population_tu | eligible经过显式detail几何过滤后的人口；summary/standard无此过滤时等于eligible |
| selected_tu | 帧结束时hash抽中的TU，不等于临时槽替换次数 |
| native_verified_tu / all_policy_tu / policy_done_tu[7] | 原生验证、全部七方法、每方法完成的TU数 |
| point_requested / point_done | `[uniform, disagreement]`两种位置样本各自请求/完成数 |
| unsupported_tu / capture_skipped | 协议外目标TU、缓存捕获异常缺额 |
| 各类skipped_budget | 原生、方法组、位置、快照分别统计，不合并成一个不明原因的0 |

summary也完整累计共同廉价分母：只读取最终q和五邻居支持数，不生成候选分数、复制Ctx或执行CABAC回放。
这些分母在同范围summary/standard必须一致。目标TU与真正有评分位置的TU不能混为一个数。
细节见[输出schema](TS_Predictor_Dual_Decoder_Audit_Schema.md)。

## 4. 预算与公平性

每origin/POC仍最多96次回放、125000次实际系数语法遍访问；每分量最多2个TU，每TU最多2均匀＋2富集位置。

1. 三分量独立保留回放/访问配额：96→32/32/32；125000的余数随POC轮换，不固定优待Y。
2. 每分量按抽样hash排序，再把该分量配额均分给其最终保留TU。只保留一个TU时可用本分量全部配额。
3. 不借空分量、较小TU或另一来源的剩余额度。仅观察Y时也沿用Y配额，避免改变样本定义。
4. 从同一真实入口验证原生。随后计算缺少的不同完整predictor序列数，按每分支`3*TU_area`上界预留全部方法。
   能容纳才执行全组，否则未完成rate为null。严格保守预留可能放弃本可勉强容纳的分支；真实访问也逐遍计数。
5. 单点oracle对不同remapping复用；均匀组整体预留在先，富集组随后。结果不能反过来决定采样或资源。
6. snapshot磁盘64MiB同样分量独立保留；文件按确切序列化长度检查，缺失仅影响可离线恢复性。
   缓存总量仍64MiB，原始JSONL8MiB，core32MiB，on/off纯日志合计8MiB。

主方法比较要求同一原始采样人口的七种方法全有结果，因此不会拿“早处理方法更多的样本”与其它方法比较。
原生完成但方法组不完整的TU仍在矩阵中，只有诊断用途，不重新归一化假装总体样本。
跳过TU的面积/系数/非零/分量、预算、每方法状态均可从TU矩阵和census核查。
impl2抽样优先级有变化，不能按impl1日志行号逐一配对；共同几何仍可明确定位。

## 5. 完整性合同

`decode_validation.json`和原生核验文件分别记录：

- `decode_complete`：本文件正常解码，帧/hash记录有效；已知expected_frames时还须匹配。
- `native_replay_complete`：所有选定TU原生回放验证完成，未丢失捕获。
- `policy_complete[7]`：每方法在所有选定TU均完成；同完整预测序列可共享已核验结果。
- `point_oracle_complete`：七方法组及两种请求位置样本都完成。
- `snapshot_complete`：选定TU均保存并重读快照；缺额另计。
- `output_complete`：原始/派生数据和所要求日志未截断，元数据成功写出。

standard/detail的`audit_complete=true`要求上述全部成立；summary不请求回放，相关字段及audit_complete为null，
另给`census_complete`，不能把null解释成“七方法验证通过”。空detail查询单独返回not_in_final_bitstream。
未知服务器预计帧数保留null；decode_complete描述本次输入文件成功解码，不认证其一定包含原始任务全部帧。

主rate比较采用`rate_complete`：完整原生＋七方法＋输出＋未漏采样人口；不需要快照文件一定保存成功。
主准确率采用`score_complete`，还要求全部均匀位置完成。富集位置不参与主准确率。
因此仅缺快照时audit_complete=false，但已完成的rate比较仍可用；这不是忽略缺失，而是明确不同指标所需状态。
只缺富集组时也可保留完整均匀估计。所有使用者必须同时读validation，不能只看CSV里是否出现数字。

双源比较以共同已解码且请求观察的帧为预期集合，检查每帧、每分量、全部方法的行。
任何一侧相关覆盖不完整，相应主来源估计/来源等权balanced为null；不将缺帧悄悄缩小成有利交集。
空分母保持null。已有成功数据与资源不足的状态都保存，源码/设置不变的resume不会偷换预算修复结果。

## 6. 加权、分层与解释

均匀位置的两级权重：`w=(TU_population/TU_selected)*(position_population/position_selected)`。
当前真实代价最优集合仍来自固定q、原生入口、单位置override的完整TSRC回放；C0/C+ oracle分开。

- accuracy=`Σw*correct / Σw`，mean_regret=`Σw*regret / Σw`，均以可区分真实代价样本为分母。
- positive_regret_mean=`Σ(w*regret) / Σ(w*[regret>0])`，不再混用未加权均值。
- 总体损失分布使用同一权重；加权分位采用加权经验CDF的逆。未加权描述均显式带`sample_unweighted_`前缀。
- TU rate总量用TU包含概率扩展，再除完整eligible TU/非零分母；协议外目标人口另列，不偷偷纳入分母。
- 富集样本的加权量只作保留样本的条件描述，不提供主HT估计；最坏案例不重新参与任何频率。
- 输出区分实际0、未请求、资源不足、空分母。`sample_known_*`及`observed_weighted_*`只描述已保存样本。

增加`score_effects.csv`：STATIC_SP−STATIC_EQ、KEEP_EQ−STATIC_EQ、KEEP_SP−STATIC_SP、KEEP_SP−KEEP_EQ、
两个历史扩展−其父策略，报告改善/变差/持平及有符号代价。幅值1/2、n=3、近远冲突、小分差、Slice/CU分层仍保留。
`history_summary.csv`包含候选/映射新增、覆盖收益及选择损失；点明细仍区分当前直接bin差与后继传播。
逐bin导出只在显式单TU离线replay中执行，不默认输出全片逐bin日志。

POC块bootstrap继续使用配对两来源、块长8、2000次、固定seed。至少各来源2个非零支持帧才给区间。
**该区间条件于已经保留的TU/位置样本，不包含完整两级抽样方差或跨内容总体不确定性。**
JSON明确写`includes_two_stage_sampling_uncertainty=false`；少量序列不能据此作普适显著性结论。
这些指标仍是最终获选TS、各来源固定q/context上的条件评分比较，不是重新RDOQ后的RD或BD-rate。

## 7. 实际验收

[impl2记录与可查询数据](results/r13_dual_decoder_audit_impl2_20261025/README.md)。

- 静态：14项Python测试；1440种预算/POC/槽数/分量顺序组合；两模式各48个局部Writer→Reader→回放fixture。
  Writer仅用于合成TU语法检查，没有EncoderApp、帧编码或CTC。
- 前缀：两来源17帧standard、summary、低回放预算、零快照预算、截断输出、零回放预算和无SEI派生流。
  共同分母相同，开/关MD5相同；部分完成时主balanced留空。6个捕获快照由新进程重放，7种rate逐一对应。
- 正式：Johnny QP27/32、FourPeople QP32先观察前32帧，之后观察完整300帧。
  最终6文件共1800个on帧＋同数off帧，每帧SEI与on/off检查通过，114个采样TU原生逐bin/概率出口/pass/预算完全吻合。
  七方法/单点/快照/输出完整，无预算跳过；这些计数不重复叠加前32帧开发验证。
- 实际B Slice Intra CU共3个：Johnny27两来源POC168 `(608,316,16,4)`；Johnny32 EQ来源POC26 `(864,704,32,16)`。
  元数据为B和is_intra_cu=1；独立进程快照重放也保留此身份。
- 错误输入：损坏快照、截断码流、错误native绑定、LFS指针均明确拒绝；schema1快照不编造Slice；匹配resume不重复解码。
- 只做96条正式输入的dry-run，不全量解码96条；不将本轮小范围验收当作数据集评分结论。

限制：单层串行CABAC观察；快照≤64×64/4096系数、动态范围8–20。多层、并行slice、L工具组合和全位深未验收。
总宏关闭只做观察头独立编译，未声称完成整个宏关闭构建。CE01完整搜索fixture仍missing_fixture。

## 8. 构建、运行与交付

Linux x86_64，实际最低编译ISA为SSE4.1，运行时有更高ISA分派；没有`-march=native`。
本机GCC11.4/glibc2.35，动态依赖libstdc++/libm/libgcc_s/libc等记在build_info.json。
需要Python3.10+标准库。其它系统/ABI必须重新构建或先验证，不宣称已跨发行版验收。

```bash
cmake -S . -B build/ts-decode-audit -DCMAKE_BUILD_TYPE=Release \
  -DNX2_OPT_TARGET_ARCH= -DNX2_ENABLE_TRACING=OFF
cmake --build build/ts-decode-audit --target DecoderApp -j 6
python3 -m unittest discover -s scripts -p test_ts_decode_score_audit.py
```

使用TypeDef.h原有`JVET_BJUT_TS_FIXED_PREDICTOR`能力；没有新的算法宏或CMake算法开关。
审计默认关闭。wrapper从manifest固定两来源模式，清理外部TS变量，实际生效限制写入run.json。

当前本地包：`runs/r13_dual_decode_audit_impl2_release/`，96条正式码流＋2条验证前缀，原件及impl1包保留。
整理其它路径：

```bash
python3 scripts/ts_decode_score_audit.py prepare \
  --source experiments/ts_predictor_r13/13_bin \
  --decoder build/ts-decode-audit/bin/DecoderApp --output runs/r13_bundle_new
# 也可用 --from-manifest <旧manifest> 复制真实已验指纹输入并保留已知身份。
```

直接执行（输出目录必须为新目录）：

```bash
python3 scripts/ts_decode_score_audit.py inspect \
  --manifest runs/r13_dual_decode_audit_impl2_release/manifest.json
python3 scripts/ts_decode_score_audit.py decode-pair \
  --manifest runs/r13_dual_decode_audit_impl2_release/manifest.json \
  --pair Johnny_QP32_prefix17 --first-poc 0 --last-poc 16 --verify-off \
  --output runs/r13_impl2_prefix_new
python3 scripts/ts_decode_score_audit.py batch \
  --manifest runs/r13_dual_decode_audit_impl2_release/manifest.json \
  --pairs all --jobs 4 --first-poc 0 --last-poc 299 --verify-off \
  --output runs/r13_all_impl2 --dry-run
```

dry-run已核对为48对/96解码任务（不含额外前缀）；去掉`--dry-run`才开始批量。
各来源任务共用一个pool，`--jobs`是最大同时解码进程数，无实验组屏障；每对完成立即比较。
续跑同请求增加`--resume`，指纹检查二进制、输入、脚本、统计脚本、模式和全部观察设置。
不匹配时拒绝复用；相同指纹的失败尝试归档到failed_attempts再重试，不覆盖旧失败记录。
POC参数只限制观察，仍读取完整文件和参考关系；默认不输出YUV。

本地便携归档接口：

```bash
python3 scripts/package_ts_decode_audit.py build \
  --manifest runs/r13_dual_decode_audit_impl2_release/manifest.json \
  --output runs/delivery/r13_decode_audit_impl2.tar.gz
python3 scripts/package_ts_decode_audit.py verify \
  --archive runs/delivery/r13_decode_audit_impl2.tar.gz \
  --output runs/r13_archive_check --smoke-pair Johnny_QP32_prefix17
```

归档只收manifest列出的流、明确程序/脚本/文档；带SHA256SUMS和归档SHA256 sidecar。
所有运行路径相对包根目录；verify安全解包到新目录，核验实际字节（拒绝LFS指针），可实际执行双来源smoke。
本轮不取消.gitignore、不把.bin/程序/快照/原始YUV/工作簿/大日志提交到Git。
初次交付时仅源码/小型核验文档上传Git，程序与码流只在本地归档；以下追加记录覆盖最新交付状态。
异目录运行验收的实际记录和归档指纹见本轮验证目录；同机搬移不等于另一OS/CPU环境已通过。

最终本地归档已生成（183428639字节），源码对应 `22e61ae`；
[归档指纹与交付状态](results/r13_dual_decoder_audit_impl2_20261025/delivery.json)和
[实际异目录双源执行验收](results/r13_dual_decoder_audit_impl2_20261025/package_validation.json)已保存。

## 9. 用户例外授权后的实际 Git 交付

2026-10-25，用户明确授权“本次是个例外将13的bin文件也上传一份”。
已将96条正式流＋2条验证前缀、配套Linux解码器/脚本/manifest以真实Git文件放入
[`deliveries/r13_decode_audit_impl2/`](../../deliveries/r13_decode_audit_impl2/README.md)，交付提交 `01d62c9`。
这是独立交付副本，不修改原96条来源、全局.gitignore或后续默认上传规则；不使用LFS，不上传YUV、重建、工作簿或运行日志。

通过GitHub SSH全新克隆验证112个交付文件SHA256（含98条实际码流），并用下载的程序执行两来源17帧smoke：
SEI/on-off MD5、原生回放和全部七方法通过。当前环境的远端实际下载已验证，
不把同机运行扩展解释成其它OS/ABI兼容认证，也不声称已测试GitHub连接器的二进制接口。
详见[远端交付验收](results/r13_dual_decoder_audit_impl2_20261025/remote_delivery.json)。
归档本身的旧SHA和“本地归档”历史记录保留；此次远端交付形态是可直接检出的目录，不重复上传175MiB tar.gz。

取得仓库后可以直接运行：

```bash
python3 deliveries/r13_decode_audit_impl2/scripts/ts_decode_score_audit.py inspect --manifest deliveries/r13_decode_audit_impl2/manifest.json
python3 deliveries/r13_decode_audit_impl2/scripts/ts_decode_score_audit.py decode-pair --manifest deliveries/r13_decode_audit_impl2/manifest.json --pair Johnny_QP32_prefix17 --first-poc 0 --last-poc 16 --verify-off --output runs/r13_uploaded_prefix
```
