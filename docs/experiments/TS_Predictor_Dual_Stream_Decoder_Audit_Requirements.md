# R13-1／R13-2双码流评分审计解码器：设计与交付要求

- 日期：2026-10-25；需求规格：`R13-DUAL-DECODE-AUDIT-v1`。
- 检查基线：`6f3c0fb00791bb582993dee180477e32143437f5`，分支 `experiment/ts-predictor-study`。
- **状态：待实现的需求文档。本文没有新增源码、编译验证、解码运行或实验收益。** 所有命令接口和资源上限均是本次提出的实现合同，不表示已有可执行程序已经支持。
- 用户目标：后续提交两版代码／码流及可执行解码器，使助手能够直接解码、审计评分并复查反例，不重新执行视频编码。为避免只观察等权轨迹而偏向R13-1，两种来源必须对称分析。
- 简称：`EQ=R13-1=r13_keep_hit_uniform`；`SP=R13-2=r13_keep_hit_spatial`。避免把EQ记为U，与Cb/U分量混淆。
- 与[原RDOQ后审计／历史候选设计](TS_Predictor_PostRDOQ_Score_Audit_History_Mode_Design.md)的关系：该文仍是编码端SEARCH_AFTER_RDOQ与历史候选实现参考；**解码端FINAL_SELECTED审计的来源、对称比较和交付要求以本文为准**，不再以EQ作为唯一数据来源。本文不实现新的历史候选编码模式。

## 1. 范围、已有依据及不能恢复的信息

复用已有代码／文档，不重写另一套语法：

- `source/Lib/DecoderLib/CABACReader.cpp`：`residual_codingTS`入口、三遍子块语法、反映射与最终符号恢复。
- `source/Lib/CommonLib/TsR13Prediction.h`：原候选集合、KeepHit的168倍评分和tie规则。
- `source/Lib/CommonLib/TsRateReplay.h`、`TsR13PredDetail.h`：原生Ctx复制、TSRC回放、真实fractional rate核对的参考。
- [解码续查报告](TS_Predictor_R13_Decoder_Followup_20261024.md)及已有`ts_r13_decode_diagnosis.py`：只读解码、身份和MD5核验。旧观察器尚不等于本需求的双源通用评分审计器。
- [CE01反例](counterexamples/CE01_Johnny32_POC16_8x32.md)、[其逐predictor报告](TS_Predictor_R13_Pred_Rate_Trace_20261025.md)。

可以从码流恢复：最终获选TU的q、因果邻域、原生p、语法及实际概率状态、模式／分量／几何／QP。无需原始视频即可比较固定q的编码估计代价。
不能由最终码流恢复：原始残差、普通舍入值和epsilon、编码器私有lambda／trial、落选TS、剪枝门槛或缓存过程。无原图不计算SSE/PSNR，不能把缺少失真记录为0。

**CE01是落选TS搜索候选，不在最终.bin中。** 必须用已捕获的q与可恢复上下文快照另建离线fixture；解码器找不到它是预期现象，不是审计漏检。不得把fixture当作最终TS的随机样本。

双源审计扩大可观测的两种最终轨迹，不能消除RDOQ及TS选择的全部条件选择偏差，更不是全编码器无偏因果实验。

## 2. 首要公平性要求：来源×评分必须形成完整矩阵

### 2.1 两种码流分别按自身规则正常解码

| 输入来源origin | 主解码模式native_policy | 私有观察分支 |
|---|---|---|
| R13-1.bin | 必须EQ | EQ、SP及相同的其他对照 |
| R13-2.bin | 必须SP | EQ、SP及相同的其他对照 |

不能拿R13-1.bin用SP主规则解码来制造第二组数据；不能拿EQ的q或context替代SP的输入。
原生模式由已核验manifest显式绑定，不根据哪个模式解码后分数更好而猜测。码流未必带有实验编号，不能承诺自动识别所有错误算法revision。

### 2.2 每个来源内部做固定输入比较

对来源o的某TU，恢复q_o、原生TSRC入口X_o，定义：

`T[o,s] = ReplayTSRC(q_o, X_o, predictor_policy=s)`。

至少输出四格：

| 同一输入来自 | 用EQ评分／预测序列回放 | 用SP评分／预测序列回放 |
|---|---|---|
| EQ码流 | T[EQ,EQ]：必须复现原生语法估计 | T[EQ,SP]：只读反事实 |
| SP码流 | T[SP,EQ]：只读反事实 | T[SP,SP]：必须复现原生语法估计 |

两个对角线都必须验收，不能只验EQ。每一行保持q、入口概率、Rice、预算、几何和工具条件相同；各分支私有推进context，不写回真实解码器。

**有效的同条件差额是行内差：** `Delta[o]=T[o,SP]−T[o,EQ]`。
正值表示该来源固定q上SP更贵，负值表示SP更便宜。不能把T[SP,SP]与T[EQ,EQ]之差称为“评分误差”，因为它们可能连q、划分、状态和TS人口都不同。

### 2.3 不强行一一配对不同块

主统计单位为`pair_id + origin + POC + component + TU_identity`。两版最终划分不同，不能按日志第n行或第n个TS块配对。
可额外报告同POC／同几何的交集，并标记q／入口摘要是否相同；交集分析不是主总体，单边才有的TS不能删除而不报。
同一内容来源、配置、帧范围和QP成对。比较范围为共同有效帧集，同时报告各自完整覆盖及缺失原因，不能默默用不同前缀凑对。

## 3. 统计如何汇总才不让某个来源占优势

每个序列／名义QP／分量，先分别报告EQ-origin与SP-origin的全体计数、样本数、准确率、regret、TU差额和不确定性。

对同单位的指标m，补充的对称摘要为：

`m_balanced = (m_EQ-origin + m_SP-origin) / 2`。

先来源内按明确的采样口径估计，再来源各占1/2。不能把两版的所有系数直接拼起来，让TS数量更多的来源占更大权重；也不能把某一来源的空分母当0。缺一侧时balanced为NA。

对于`Delta`建议同时报告各来源的`sum Delta / sum positive_coefficients`（估计bit/非零系数）与估计bit/TU；各自分母完整列出。不同分母不能混成一个平均。
跨内容先按pair_id汇总再作等权摘要，保留逐序列／QP表；Y/U/V不默认混合成6:1:1，选择损失也不是BD-rate。

除来源等权外，输出共同分层下的表现，例如a=1/2、n=3、I/B、TU尺寸。需要标准化时使用事先定义且两边相同的分层权重，只在共同支持层计算并披露排除比例。
同TU、同帧内样本相关，不能以数百万重复系数当独立样本作极小p值；置信区间如计算，应使用说明清楚的帧/内容簇重采样，不夸大少量视频的泛化能力。

结论必须区分：两来源都同向、两来源方向相反、只在某个来源显著。方向相反可能说明评分与各自量化轨迹适配，不强行选择一个“全局正确”评分。

## 4. 解码器的只读架构与准确插入时机

建议模块名仅为规划：`TsDecoderScoreAudit`、`TsAuditReplay`、`TsAuditSnapshot`；优先复用公共预测／回放helper，不复制漂移的实现。

```text
按manifest锁定native mode -> 正常解码到TSRC TU入口
   | 保存该TU首个系数语法之前的原生Ctx与必要参数
   v
正常读取各CG三遍语法 -> 反映射 -> 恢复真实q及符号
   | 实际解码不变；该TU全部q稳定后
   +-> 只读聚合／受控采样
           +-> 固定q的四种评分和历史候选
           +-> 私有上下文重放／单位置干预
           +-> 有界结果与可重读快照
主解码继续使用自己的真实概率、预算、重建和参考图像
```

具体合同：

1. 在`CABACReader::residual_codingTS`中、首个CG flag或系数bin前捕获TSRC入口，不在pass3结束后倒用已更新概率。明确排除边界外的CBF/TS flag等语法；所有native／replay使用相同范围。
2. 观察读取的a必须是反映射后的真实幅值，不是pass1/2的部分level；有符号q在恢复符号后用于完整回放。
3. 保存原生Ctx深拷贝与该版本实际需要的概率模型字段、Rice、动态范围、初始regular预算、CG大小/扫描、sig flags及工具门控。公开hash不是可恢复快照。
4. 私有分支使用原生上下文更新；CG边界不重置CABAC，预算不从源分支中途状态借用。subblock、纯bypass、BDPCM与sign等遵循本版本原语法。
5. 所有p_s(i)从q中原规则允许的因果邻域生成；事后持有全TU数组不等于可以用未来位置投票。
6. 不能为了观察更换全局`TS_FIXED_PREDICTOR`或其它影响主解码的policy。回放helper显式接收观察policy；不同输入可分进程或完全重置独立解码实例。
7. `audit=off`时不复制context、不生成文件；`audit=on`不得影响原生语法、重建、CABAC、参考图像或输出哈希。失败不得回退成另一种解码算法。
8. 中段POC筛选只限制观察，仍从合法随机访问点解码必要前缀；不把POC16字节切片当成新I帧，不假定可以直接seek到任意帧。

## 5. 原生概率代价核验：不是读取了多少字节

解码器没有encoder的`getEstFracBits()`结果，需给原生decodeBin路径增加只读计数：保留该bin更新前的概率模型，得到真实bin后累加其原生`estFracBits(value)`；EP按实际旁路bin数累加。
可以hook底层bin或等价语法接口，但必须避免`decodeRemAbsEP`与其内部调用重复计数。TSRC范围外的终止、对齐等不混入该范围。

主度量为int64/uint64的fractional units，32768单位=1估计bit；有符号差先安全转换再相减。原生概率量化表为准，不在Python重新用-log2(P)替代而声称逐位精确。
不能以bitstream字节指针的位移给每个系数记账，算术编码的缓冲／重整化不支持这种归因。

每个已采样TU的native-policy回放应当与主解码的原生bin顺序、值、ctx id、fractional总额、末状态和预算一致；多余的语法遍边界／cutoff也须核对。
两来源都核对。首次不一致保存有限反例并把本次审计标为invalid，禁止把不一致的rate继续纳入统计。解码本身的成功与审计成功分开记录。

这验证的是正常解码路径上的真实语法概率代价。没有原始encoder trial上下文时，不声称它逐TU复现编码搜索时的全部RDO成本。

## 6. 比较评分与单位置准确性

### 6.1 两来源使用完全相同的方法集合

| 方法ID | 损失 | 权重 | 候选 |
|---|---|---|---|
| CURRENT | 不评分，max(L,U) | 无 | 原动作 |
| STATIC_EQ | 原syntaxCost映射代价，统一尺度 | 11111 | C0 |
| STATIC_SP | 同上 | 22111 | C0 |
| KEEP_EQ | 原R13保持/相邻命中168损失 | 11111 | C0 |
| KEEP_SP | 同上 | 22111 | C0 |

C0与原R13相同：0/1等价、重复值去重、Current优先的旧候选顺序、只接受严格更小、n<3直接Current。不加R3/R6保护，不在某个来源中改变门槛。
不同评分的原始总分不能直接比大小；分差诊断用`(second−best)/(168×weightSum)`，仍不能叫预测bit节省。

### 6.2 单位置的真正比较对象

对来源o、位置i，保持其原生预测序列P_native(o)的其它位置不变，仅覆盖i的预测值：

`R[o,i,p] = ReplayTSRC(q_o, X_o, P_native(o) with p_i=p)`。

同一来源的所有评分方法面对同一候选代价表；覆盖要作用于该位置全部相关语法遍，不能只改gt1。
定义最优集合`O[o,i]={p∈C0 : R[o,i,p]=min_C0 R[o,i,p]}`，
`regret[o,i,s]=R[o,i,p_s]−min_C0 R[o,i,p]`。

真实cost并列最优均算正确；不能只把native p或某个任意tie规则定为正确答案。实际a不在C0时，不偷偷把p=a或最近值加进oracle。
主准确率只在候选真实cost存在区别的样本计算，另外报告零值、全tie、同映射和非评分位置；这些无区分样本不得虚增准确率。

报告每种评分的regret均值、分布、正损失均值，以及同位置`R[o,i,p_SP]−R[o,i,p_EQ]`。这项比较是已实现q上的条件选择质量，不证明重新RDOQ后的最优动作。

对少量高损失样本可增加`continuation_policy=EQ/SP`两种固定后继序列作敏感性复查，两来源采用同样设置；默认主统计均用自身native后继，不伪装成全部位置独立编码。

### 6.3 减少计算，保留传播

固定a、入口和其余预测序列后，同映射等级的p共享回放；至多是1/a/a+1三类，所以已有native分支外通常最多两类额外重放。
全TU重放为正确基准；经过逐bin验证才可优化成快照后缀。三遍语法不可当成“每个系数一次完成全部bins”而错误截断。
单位置干预总差可含后继context／预算效应；直接bin差额和传播另报。后继p没改变但rate变贵，不算后继位置又发生了一次评分误判。
单位置差额一般不能相加还原整TU策略差额，因为多个变化相互作用；两类输出分开。

## 7. 历史众数候选：只影子比较，并对两种评分对称扩展

复用原设计的首版定义：同TU／同分量、当前扫描前的非零q幅值（含1，不含当前/未来、不计符号）；精确累计众数，频数相同取较小幅值；1归并为已有NoPred。
来源EQ和来源SP分别维护自己的q前缀，不能把EQ历史当成SP历史。无历史、重复候选和n<3仍按原设计处理。

观察增加`KEEP_EQ_H`和`KEEP_SP_H`两列，在两种来源都计算；C+=C0∪{p_hist}，历史只是候选，不是伪样本或加分。新增候选排在旧候选后，最多7个。
真实解码仍用原EQ/SP，不因影子历史候选更好而改变反映射。

分别记录：历史有效率、历史众数为1/≥2、候选新增率、实际不同映射新增率、被评分选中率、映射变化率、覆盖收益`min_C0 R−min_C+ R`及最终选择差。C0/C+ oracle分开，不能通过扩候选抬高某方法的评分能力结论。
已知raised-cache假设需修正：历史候选可大于局部最大幅值，C(m+1)缓存条件必须依据扩展候选最大值；数组、循环、schema扩到7并做边界测试。

CE01在scan31前的非零历史为5个1、1个2，众数1已等价p0，因此纯候选扩展不应修复该反例。此项作逻辑回归，不引入历史奖励来强行达成修复。

## 8. 对称采样、计算预算与数据规模

### 8.1 全量廉价统计＋有界精确重放

两来源的POC范围、分量、分层、seed、配额、精度、重放范围和方法集合一致；不得只采SP出错位置或给EQ更多回放预算。

建议默认值（实现时全部写入manifest）：

- 解码全部必要前缀；对所有最终TS保留廉价分母与幅值/支持数等计数。BDPCM及非目标路径单列，不伪造可比较的预测效果。
- 每个origin、POC、分量最多均匀选择2个TS TU快照。采用固定seed的reservoir/哈希优先级；在不知道方法输赢前决定采样。公共几何键的随机优先级可在两来源共享，但不同树不强行配对。
- 每个采样TU：完整策略回放所有主方法；另最多4个位置做单点oracle，2个从合法非零评分位置均匀抽取，2个从未重复的评分分歧位置抽取。
- 均匀抽样与分歧富集分别标记并报告；误判率以有明确包含概率的代表性样本为主。TU均匀不等于系数均匀，保留两级包含概率、分母和估计权重。
- 每origin、每POC最多96次TU回放、125000次实际系数遍历；所有语法遍都计入遍历预算。快照缓存上限64MiB。上限只减少审计，不影响主解码。
- 预算可能造成与TU大小相关的缺失：必须记录`selected/audited/skipped_budget`和规模分布；被截断样本不能冒充原先随机总体。两来源预算相同不等于自动无偏。
- 不把另一来源的剩余配额转给本来源；缺帧／无TS／未达配额不填0。报告共同完整覆盖的主比较和全部可用的补充比较。
- 详细例子每origin均匀保留128条；每origin×component分别保留SP−EQ正/负两个方向各32条极端例。两来源总计最多640条。最坏样本用于解释，不计算代表性频率。

native分支及相同映射/完整预测序列可复用已核验回放，不能改变cost定义。具体耗时未知，审计开启不用于正式解码复杂度结论。

### 8.2 输出最小集合

| 文件 | 必要字段／用途 |
|---|---|
| `run.json` | 需求/实现revision、pair_id、origin、native_policy、源码/程序/码流hash、全部参数、环境、资源计数、完整性与校验 |
| `decode_validation.json` | 期望/实际帧数、返回码、SEI校验、on/off重建一致性、native/replay一致性和首个失败 |
| `frame_summary.csv` | origin/POC/分量/方法、真实及采样TU/系数分母、tie/改选/误选、regret、native和反事实TSRC差额 |
| `strata.csv` | 预注册边际与少量交叉层；低幅值/支持数/分差/尺寸/I-B/预算路径，不输出巨大笛卡尔积 |
| `tu_policy_matrix.csv` | 采样TU几何、origin、q摘要、native入口摘要、全部策略rate、原生验证、采样权重 |
| `history_summary.csv` | 历史重复/新增/获选/覆盖/选择损失，区分C0和C+ |
| `examples.jsonl` | 有界样本的定位、H、候选分数/p、实际q、映射、分支rate、直接/传播差额、样本类型 |
| `pair_comparison.json`/`.csv` | 双来源四格矩阵、两行差、来源等权摘要、单边/共有覆盖、缺项和方向冲突 |

所有rate内部保留整数fractional units，导出bit另列；不要只输出四舍五入后的分数。JSON不使用NaN，缺失用null并附原因，CSV有明确schema/单位。

核心聚合与明细文件合计默认≤32MiB/stream，审计纯日志另限8MiB；可选可恢复快照另限64MiB/stream。写盘预算预留最终manifest，不静默截断，标记停止细节的原因。不得对全片默认输出每个bin/完整Ctx/所有256位置大表。

主分层建议：a=0/1/2/3–4/≥5，n<3/3/4/5，I/B，Y/Cb/Cr，TU面积≤16/17–64/65–256/>256；边界缺邻与真实零邻分开。评分归一分差桶沿用旧设计。重点交叉只保留低幅值×n×近远冲突×小分差，统计桶不是新编码门限。

## 9. 可恢复快照与离线复查

程序必须支持`capture -> replay`：从已解码TU保存有限快照，后续不重解整片即可换统计口径或打印选定bin。快照必须包含：

- q有符号数组、TU/CG扫描与几何、分量、原生policy、码流定位与revision；
- TSRC入口完整所需概率模型状态及自适应参数，初始预算、Rice、动态范围、相关工具参数；
- 原生语法摘要、fractional总额、出口概率/预算校验；
- schema/version、字节序/整数宽度、长度和校验和。

不得保存Ctx/C++对象的裸指针或依赖结构体padding的内存转储；用有文档的显式字段序列化，并验证重读后对每个有效模型的0/1 cost及状态更新一致。序列化字段不足时fail closed，不能只凭hash看起来一致就继续。

CE01以`population=SEARCH_FIXTURE`单独交付。正常解码样本统一为`FINAL_SELECTED`；fixture不并入公平主表。CE01真输入快照缺失时标`missing_fixture`，不能用最终.bin重建不存在的trial或人工伪造入口概率。

最少应提供离线字段导出模式，便于用Python分析而不再次修改decoder。完整精确语法回放由同版本native helper承担，不用普通CSV里几个概率摘要近似替代。

## 10. 面向助手的命令行接口合同（待实现）

可由Python包装已有DecoderApp，也可新增独立工具；必须有明确的help、版本、非交互、绝对/相对路径和退出码。以下命令是**目标接口示意，当前尚不可直接运行**：

```text
python3 scripts/ts_decode_score_audit.py inspect --manifest bundle/manifest.json
python3 scripts/ts_decode_score_audit.py decode-pair --manifest bundle/manifest.json --pair Johnny_QP32 --profile standard --output runs/j32_audit
python3 scripts/ts_decode_score_audit.py replay --snapshot <snapshot-file> --policies KEEP_EQ,KEEP_SP --output runs/replay
python3 scripts/ts_decode_score_audit.py detail --manifest bundle/manifest.json --origin R13-2 --poc 16 --component Y --tu 856,384,8,32 --output runs/detail
python3 scripts/ts_decode_score_audit.py compare --reference runs/j32_eq --test runs/j32_sp --output runs/pair
```

最后那个8×32定位来自落选反例，普通detail找不到时应返回`not_in_final_bitstream`，不能假装找到；CE01应走replay fixture入口。正式帮助中也要解释这一差别。

支持按POC/范围、分量、TU几何/尺寸、正负损失筛选；`summary`只廉价统计、`standard`有界回放、`detail`单目标逐bin限流。原图参数可选，无原图正常运行核心审计。
所有运行禁止调用EncoderApp或启动视频RDOQ/CTC任务；私有TS语法概率回放不产生新视频码流。单元验证可链接公共熵估计代码，但不能因此悄悄重编码源视频。

`--verify-off`对每一来源分别执行观察开/关解码并比较重建；默认不保存YUV。SEI存在时逐帧验证；不存在时明确`SEI_not_available`，用同版本审计关闭的重建哈希作一致性参考，但不称为与编码端逐帧MD5验证通过。
下载、安装、构建与调用均显式；不在程序启动时自动访问网络或执行未登记shell脚本。

## 11. 上传代码、.bin和可执行程序时的交付内容

建议逻辑包结构如下，路径可适配仓库既有约定，但manifest必须给出真实位置：

```text
r13_dual_decode_audit/
  manifest.json
  README_run.md
  build_info.json
  bin/DecoderAppAudit
  lib/                         # 必要动态库，或无外部依赖说明
  scripts/                     # 包装、聚合、离线重放与测试入口
  streams/<pair_id>/R13_1.bin
  streams/<pair_id>/R13_2.bin
  fixtures/CE01/               # 已捕获的真实q/context，可单独缺省登记
  validation/                 # 最小两来源烟测、native核对和on/off结果
```

manifest最低合同：

- schema/spec_version、实现提交、评分revision、score_scale=168、rate_scale=32768；
- binary路径/SHA256、编译器/构建类型/架构/CPU最低要求/库依赖与运行方式；
- pairs列表：pair_id、序列、配置、名义QP、分辨率、位深/色度格式、帧率、FrameSkip/TemporalSubsample/预期帧数；
- 每个origin的bin路径/SHA256、编码源码/程序身份（未知必须null）、native_policy、scope、原始配置指纹、SEI状态；
- 源内容指纹（有就提供）、两来源配对核验状态与未知项；同名视频不能自动证明输入相同；
- 观察policy集合、采样种子/规则/配额/限额、fixtures与预期结果；
- 程序版本不匹配、单边缺失、unsupported bitstream feature的处理。

不能把历史未测字段填成猜测值；例如码流文件hash不同是正常，要求相同的是输入/配置身份而不是两版码流hash。

首选交付Linux x86_64可移植程序及对应源码/构建方法，避免只有Windows exe或特定服务器指令集的`-march=native`产物。声明实际最低ISA、运行库版本，并提供baseline构建或经过说明的运行时分派；不预先锁死某个未来执行环境的glibc版本。无GPU必要性，不硬编码用户服务器路径。
源码/小型派生表按项目文档与scripts约定提交；用户后续授权上传的.bin用单独明确路径/清单，不取消全库忽略规则、不顺带上传原图/重建/凭据。可执行产物交付可使用独立归档或Actions artifact，并记录下载定位、SHA与有效性。

**GitHub上存在文件不等于当前连接器已经把二进制挂载到执行环境。** 源码读取与二进制取得分开验收：小型bin、LFS指针、artifact各按实际下载能力处理；下载后验证真实字节数与SHA，不能把LFS指针文本当码流。连接器无法交付某二进制时保留结果状态，并可由用户将同一归档直接附到会话；不许声称已经解码不可访问的文件。

最小可运行包应有一个真正可解码的EQ/SP配对前缀。随后上传完整Johnny QP27/32两版，以及同配置FourPeople等正向内容两版，避免所有诊断都从负面样本出发。其它QP/内容按已有码流补充，不为本需求启动新编码。

## 12. 验收：公正性、正确性和可用性必须同时满足

### 12.1 原生解码与只读性

- 两种来源分别正确解码；audit off/on逐帧重建一致，有SEI则两边均核验。不存在SEI不能写成SEI通过。
- EQ-origin的KEEP_EQ、SP-origin的KEEP_SP回放都与真实bin计数／末状态／预算一致；源policy混淆、snapshot格式错误时明确失败。
- q、主Ctx、Rice统计、预算、模式与参考图像不被观察分支改变；多线程统计不影响实际调度结果，分层/seed可复现。
- 稀疏／密集、0/1等价、全零CG、n不足、Rice/动态范围、边界、长矩形块、regular预算耗尽、pass边界变化、BDPCM/非目标路径均覆盖。

### 12.2 公平性与统计

- 同一个快照分别以不同origin标签做纯聚合测试时，非原生核验部分的policy rate不应因标签改变；交换EQ/SP两来源的显示次序不改变结果。
- 对称摘要两来源等权，缺项NA；相同预算/方法集合，抽样在看结果前确定；正负极端样本都保留。
- 不把全tie/零值计入可区分准确率；oracle最优集合处理正确；同映射候选复用与朴素逐候选重放一致。
- 划分不同保留单边样本，不能依日志序号硬配；无TS人口不虚构记录；重复运行/不同观察层不重复计数。
- 单点差与整TU差不强行相加；任何balanced指标明确单位、分母及采样估计。预算截断必须可见且不得报告为全覆盖。

### 12.3 历史扩展与反例

- 历史众数逐前缀与暴力统计一致；先预测后计当前a；不同origin/TU/分量独立，tie和去重正确。
- 历史候选大于局部最大值时raised缓存正确，最多7候选；候选未扩展时结果等价旧对应EQ/SP。
- CE01真实fixture：256个q、14非零/absSum15；scan31评分EQ 840/1144、SP 1344/1312；直接71587、传播18934、总90521 fractional units。
- CE01中仅scan31覆写p2与完整SP回放差额一致；scan35/39只标传播；历史众数1不改变候选。没有fixture就标未测，不能用手填期望值替代测试。
- 序列化→重新加载后原生与各反事实结果完全一致，不能依赖曾经进程地址空间。

### 12.4 交付与运行

- 干净工作目录可构建／运行，README的实际命令经过测试；不需要服务器私有绝对路径、编码器进程或原始YUV。
- Linux可执行及依赖检查、帮助和版本输出、合法小码流、损坏/截断码流、缺文件、错误manifest、超资源上限均有明确结果。
- 每个测试的输入、命令、退出码、预期/实测摘要可查询；只把完成的测试写为passed。未测的大尺寸/多层功能明确unsupported，不冒充通用支持。

## 13. 实施顺序与最后应交付的分析答案

1. 先实现正确的TSRC入口快照、原生解码bin计数和两个来源的对角线一致性；不先做复杂统计。
2. 加入各评分整TU回放，输出双源四格矩阵；再加入单位置oracle、抽样和分层。
3. 加入有限快照导出/离线回放、CE01 fixture及正负案例表，最后再接历史候选影子列。
4. 在已有两版短码流上验收，完成便携包和manifest后交付；不自动重编码、不改正式BD-rate台账。

最终报告必须能回答：
- 某评分在EQ-origin与SP-origin上是否都更好，还是仅在自身轨迹占优？
- 误判主要来自空间权重、KeepHit修正、候选缺失，还是实际概率/后继context传播？
- 幅值1/2、n=3、小分差、近远冲突是否在两来源都反复出现？损失是高频小错还是少量大错？
- 历史候选是重复已有动作、补足覆盖，还是增加了新误判？
- 哪些结论只适用于FINAL_SELECTED，哪些必须回到搜索fixture或编码端，不能由.bin回答？

双源对称审计是更公平的条件比较，不是重新编码收益证明；不得从固定q的估计bit变化直接推导新BD-rate，也不因某一列好看而隐藏另一来源的负面结果。
