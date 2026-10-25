# TS predictor 实验记录

最后更新：2026-10-25。这是本项目 TS predictor 研究的统一实验台账；
后续实验在本文件追加和更新，不另建互相冲突的总记录。

仅数值查询见 [实验结果台账](TS_Predictor_Results_Ledger.md) 和 [逐序列/逐 QP 明细](results/README.md)：记录码率、PSNR 与 BD-rate，不含分析。
本文件继续记录实验过程、来源核验、分析与决策；收到新结果时同步更新结果台账。

## R13 双码流审计统计修复 impl2（2026-10-25）

以`1270ad3`为审查基线，确认并修复CU帧内标志混作Slice、summary漏计eligible、部分方法回放误标完整、
分量顺序共享预算和正损失均值未加权问题。保留CABAC回放和真实R13算法；没有运行EncoderApp或视频编码，正式RD/BD/逐QP表未修改。

- schema 2分别保存真实Slice与CU模式；旧快照缺Slice时只能unknown，不重标旧CSV。
- 分量/TU独立观察预算，七方法和均匀位置组先预留再执行；逐层complete、逐方法null/原因和跳过规模可查询。
  快照配额独立保留给分量；原始及派生输出截断可见，缺项不填0、不缩小为隐蔽的共同子集。
- 统一两级权重的准确率、均值、正损失均值、分位与直方图；uniform、富集和极端案例分开。
  新增Slice×CU、KeepHit/空间权重/历史对照表。POC块区间明确不包含完整两级抽样及跨内容不确定性。
- 14项Python单元测试、1440预算分配顺序组合通过；两模式各48个局部语法fixture通过。
  前缀summary/standard分母完全相同；低回放预算、零快照预算、输出截断和无SEI均保持重建，缺额如实报告。
- Johnny27/32与FourPeople32先前32帧观察，再完成双来源各300帧观察：6文件1800个on帧＋1800个off帧均MD5通过，
  114个采样TU原生bins/概率出口/pass/预算一致，7方法/单点/快照/输出完整。3个实际B Slice Intra CU身份及独立快照恢复正确。
- 98条本地包含96正式流＋2验证前缀；全数据集只做96任务dry-run，未全量解码。
  新增共享任务池/指纹续跑和tar.gz打包/异目录验证；源码文档同步Git，二进制与码流归档仍为本地交付，未宣称GitHub可下载。

详情：[实现与对比](TS_Predictor_Dual_Decoder_Audit_Implementation.md)、[schema](TS_Predictor_Dual_Decoder_Audit_Schema.md)、
[本轮验收](results/r13_dual_decoder_audit_impl2_20261025/README.md)。本轮结果只验收条件统计工具，不据此宣布评分模型整体优劣。

## R13 双码流评分审计解码器（2026-10-25，impl1历史）

快进同步至`f603715`，按新双源需求实现`R13-DUAL-DECODE-AUDIT-impl1`。
R13-1/2各用自己的native模式解码；最终q稳定后，在同一入口概率状态上私有回放七个方法。
保存完整概率字段（含stateUsed）、真实bin轨迹、pass/预算及可独立恢复的快照；两来源对角线逐bin核验。
候选历史扩展仅是观察列，没有新增正式编码模式，也没有修改RDOQ或调用EncoderApp。

- 将`experiments/ts_predictor_r13/13_bin`的96条码流复制到`runs/r13_dual_decode_audit_bundle/streams/`，
  167073025字节逐条SHA256一致，原件保留。另收录既有17帧EQ/SP验证前缀及CE01部分真实输入。
- Release编译通过；EQ/SP各48个合成TU通过Writer→Reader→回放→序列化核验，含Rice1–8、预算耗尽、BDPCM、
  历史候选及同映射复用。此处Writer仅作局部语法单元测试，不编码视频。
- 最终固定验收集：17帧前缀及Johnny27/32、FourPeople32两种来源各300帧，共1834个on帧及同数off帧。
  每帧SEI MD5通过且on/off重建一致；前缀观察17帧，另外三对仅观察前32帧，共38个采样TU原生回放精确吻合。
- 8项Python测试、7项运行时验收通过；独立进程快照回放的七个rate与捕获时完全一致。
  预算不足只跳过观察；无SEI如实标缺失，损坏快照/截断码流/错误模式manifest显式失败。
- 只筛选已有样本的尺寸/损失方向接口独立于主抽样；C0/C+分母分开，来源等权且空分母保留null。
- CE01定点最终码流查询返回`not_in_final_bitstream`；旧context CSV缺stateUsed，完整搜索fixture记`missing_fixture`。
  没有为了补齐而重新编码，也没有将落选trial假装成最终码流样本。

服务器编码器/输入/配置身份未知字段仍为null；双来源条件统计不能消除TS/RDOQ选择偏差。
本轮验收样本少，不给评分优劣或新BD-rate结论。源码/文档/小型核验表同步Git，原始码流和可执行包留本地。
详见[实现与交付](TS_Predictor_Dual_Decoder_Audit_Implementation.md)及[验收记录](results/r13_dual_decoder_audit_20261025/README.md)。

## R13 Johnny32 POC16：2.762482 bit 的 predictor 明细（2026-10-25）

只补跑既有EQ 17帧前缀，捕获Y(856,384)8×32被丢弃的TS候选；固定q和入口CABAC状态回放Current/EQ/SP。
全TU只有scan31的pred不同：q1、H=[0,2,1,0,1]；EQ分数p0=840/p2=1144，SP分数p0=1344/p2=1312。
SP将U=2加倍后严格选p2，将当前幅值1映射成2；不是tie-break差异。
scan31增加71587 fractional units，scan35/39的gt1 context传播再增加18934，合计90521/32768=2.762481689453 bit。
真实EQ与重放EQ精确一致；旧整个trial与本次TSRC-only的差值完全一致。

36个合成TU及4项Python检查通过；17帧编码byte-exact且独立解码MD5通过。
仅诊断，不改predictor/搜索规则，不新增或改写正式RD/BD数据。
全部256个系数、候选逐样本评分、bin/context贡献见[定点记录](TS_Predictor_R13_Pred_Rate_Trace_20261025.md)。

## R13 异常续查：解码观察与定点搜索（2026-10-24）

已快进同步至`ea09d6a`，读取新上传指导，并按用户建议优先复用本地`.bin`。
新增默认关闭的decoder CU/TU/CTU、滤波stage及decoder-derived CCP引用/模型观察；
仅对解码定位的Johnny32 POC16 CTU36补编码器控制流追踪。没有改predictor或快搜规则。

- 10组解码观察的90帧on/off共180次MD5通过；两组CCP额外4次，无原图路径额外2次。
  300条分量stage中210条共有stage与旧encoder的SSE和原图/重建hash精确对应。
- Johnny32首帧首个UV变化块保持同模式、q、残差、LMCS scale；其CCCM左下训练区East边亮度引用变化，
  导致实际主CCCM的28个参数变化和预测/重建变化。定位的是传播块，未称为该小块自身损失或全帧全部损失来源。
- Johnny27 POC8 V优势反转发生在CCSAO，裁剪未改变样本；三个方法自身均获改善，SP获益更少。
  K&S32首帧U的ALF差距扩大62737 SSE，普通ALF贡献53297（84.95%）、CCALF9440。
- Johnny32 POC16首个最终划分差定位共同32×32父块`(832,384)`：EQ选BT-V、SP选QT。
  完整搜索进一步发现8×32子候选相同q摘要/失真，SP多付2.762482估计bit；按真实操作数和源码还原的SBT门槛
  恰跨越，EQ继续搜索找到更优SBT，SP跳过，父BT方案因此失去优势。门槛本身未直接插桩或禁用，控制实验仍待做。
- 搜索日志首轮发生8位字段打印成字符和20万条截断，拒绝为完整证据；修正后重跑完整286278/268534条。
  两轮共4×17=68编码帧，所有码流分别与旧同模式前缀byte-exact，68帧解码通过；主要结论只采用严格完整日志。
  15项诊断Python检查＋9项搜索解析/实际C++字段格式检查通过。未运行本地300帧，没有重建视频输出。

结论：已有具体搜索放大、CCCM传播和滤波差距证据，不支持把异常统一归为最终色度TS映射错误。
尚未完成门槛干预及全部300帧归因；优先只控制上述SSE键58候选的SBT cost gate，
不直接全局关闭TSFast/缓存或添加新的经验guard。Current正式基线、已有RD/BD-rate全部不变。

报告：[R13解码续查](TS_Predictor_R13_Decoder_Followup_20261024.md)；
数据：[只读解码/搜索派生结果](results/r13_followup_20261024/README.md)。

## R13-2 异常点诊断（2026-10-24，本地短测已完成）

用户授权源码诊断和本地运行，针对Johnny QP27/32、KristenAndSara QP32，并检查Johnny37。
Current仍为正式anchor，等权R13-1为权重机制对照。正式整体/逐QP数值没有改动或补点。
六份服务器日志各300编码帧＋10遍解码，合计18,000次MD5检查通过，RD与台账一致；
Johnny37逐QP BD611独立复算+0.074675%。本地多个前缀逐bits、hex PSNR、MD5复现对应服务器帧。

实现默认关闭的三层观察：最终Writer真实CG入口context的固定q C/U/S模拟、全TS RDOQ搜索trial局部探针、
各滤波阶段的分量及64×64网格SSE/hash。分开获选TS与落选search人口、固定候选与native候选、CG全零与否。
另实现luma/chroma作用域编码干预，必须编解码一致，独立标识且不写入正式R13曲线；默认all保持原算法。
batch指纹纳入显式诊断/scope，无新观察请求时保持旧R13成功标记兼容。

完成新17组133帧＋冻结旧程序3组15帧，最长17帧，无本地完整300帧重跑，无重建视频输出。
18项Python检查、7组native、全部148帧解码hash通过；native CG replay与原生fractional estimator完全一致。
新观察开关五帧码流byte-exact；frame/tile SSE守恒，final SSE与hex PSNR对应。并发3→6，耗时不用于复杂度比较。

- Johnny32首帧all=luma、chroma=Current（完整码流一致），确认Y路径导致滤波前UV变化，滤波总体缓解。
  U/S前16个完整图像码流相同，首次分叉POC16却无最终TS，UV试验p/q也无改变，指向编码器搜索决策反馈；
  具体首个分支未定位，不宣称CABAC状态泄漏。源码确认TS临时获胜、BT/TT成本及SBT历史能影响后续候选，相关开关已启用。
- Johnny27 POC8 V在CCSAO＋joint clip阶段从优势转为劣势；各轨迹仍各自获益，空间版获益更少。
  POC16无最终TS却比等权多2072bit；17帧平均V未复现全300帧负值，保留此限制。
- K&S32首帧ALF/CCALF扩大U损失；17帧空间对等权+1784bit，平均Y/U转负，最终q的局部U/S remap差却仍仅首帧一个系数。
  首帧局部RD支持空间，后续帧转向等权，不能用首帧搜索量巨大的总平均概括。
- Johnny37首帧三分量均改善，未定位全段损失转折，未用端点位置否定+0.074675%的真实结果。

结论：已定位若干损失路径与权重分叉发生层级，没有发现日志/配置/解码失配；不把这些证据称作完整300帧因果分解。
下一步优先追踪Johnny32 POC16首个真实搜索分支，并做少量同配置搜索控制；继续保持decoder因果性，
不直接把encoder-only RDOQ探针变成正式predictor selector，不立即新增大批阈值或完整CTC实验。

报告：[R13异常点诊断](TS_Predictor_R13_Anomaly_Diagnosis_20261024.md)；
数据：[正式点复核、本地逐帧/stage/Writer/RDOQ及验证记录](results/r13_diagnosis_20261024/README.md)。

## R14 完整CE多维分析（2026-10-24，无新数据）

基于`6c6a2fb`登记的412实测/8缺失结果开展分析，实验2正确部分结果按共同覆盖比较，不补点。
14组完整CE中10最佳−0.093843%，但直接以两方法曲线积分后对R3-1为+0.000250%、对R6-2为−0.000969%，
判断基本持平。对固定等权R13-1的直接增量−0.020708%，去掉RaceHorsesC后+0.002040%；动态增量集中。

PAIR2优于NONE的结论只在部分初态成立：10/1直接−0.110998%，12/3却+0.053615%、14/5为+0.029221%。
G2/G4混合网格和步长变化，PAIR2等权/半权初态还混合初始相位方向性，不能将差异归于单一因素。
10/11的E为12/12相同RD点，分别与R13-1有11/12相同，唯一差点是FourPeople QP22；无自然序列状态计数，
不从RD相同推导状态未转移或码流相同。7为28/28 RD相同，但源码不恒等Current。

9和10的四QP CE均值全为负；3的Y最强却受U/V损失抵消，5主要靠V；Johnny在全部13个有变化的完整R14组均退化，
BQMall仅5改善。10/11/9/13相对Current及历史强方法的内容分化已逐序列记录。
序列配对bootstrap200,000次（seed20261024），10对R13-1区间[−0.069988,+0.012535]%，10/1为[−0.224505,−0.016202]%；
只作未校正多重选择的探索性内容敏感度，不当作视频总体保证或重复运行噪声。

总体Weak，保留10为动态候选、9为固定对照，优先补齐2及检查已有活动统计，不新增算法、参数扫描或启动编码。
没有R14 B及可比计时，不能宣称达到BCE或复杂度目标。正式台账数值未改，新增分析报告、两图、数值/绘图脚本及小体积派生表。
登记生成`--check`通过，直接BD与工作簿公式最大差3.60e−13个百分点；坏输入校验拒绝重复键、混合anchor、非有限值、残缺元组和非实测完整曲线。

报告：[R14 LB CE分析](TS_Predictor_R14_LB_CE_Analysis_20261024.md)；
数据：[配对、分布、bootstrap与留一结果](results/r14_analysis_20261024/README.md)。

## R14 结果补齐与实验2修正（2026-10-24，仅更新记录）

用户确认“14结果已出，2出了部分，现在是正确的”。按当前连续编号读取15份CSV，
得到412/420实测点：除2外14组各28/28；2为20/28，缺七条QP22和PartyScene QP27。
本轮只更新来源与数值记录，不修改编码算法、不启动编码、不新增状态机制推断。

实验2不再按模式编号永久排除。`ts_results_ledger.py`仅保留旧不可靠文件的SHA256拒绝规则；
当前新文件整份20点均按用户确认纳入，其中与旧值相同的6点也纳入，缺失8点不从旧文件补填。
旧SHA为`5437fb0e450889be13d638c3e4ec0d1abcb3779f01438058371295ad2019a5b4`；
新SHA为`8f33be181110a1b1065cf7ac7d4dbeb5339fd9aeea2f41ff67f3ae0995e5d18c`。
旧18点中12点改变、6点相同，另新增FourPeople/KristenAndSara QP27；旧原值可由提交`395f32f`的明细追溯。

全轮新增132个原始数值点，旧280点中268不变、12改变；非2旧262点全部不变。
213个来源中仅15份R14 CSV改变，其余198份不变。未收到R14 B/RA/AI或活动统计。
当前全台账3664个QP位置：3596实测、16历史补点、52缺失；916条序列中856完整、15含历史补点、44缺点、1参考无效。
本轮R14新增98条完整四点曲线；2仍无完整曲线，整体留空。
四轮QP分析948栏中928可算、4参考无效、13缺失、3历史补点目标留空，当前无整组排除。
五张CSV仅R14行变化：逐点150、整体序列105、整体汇总45、QP158、QP汇总95；无键增删，所有非R14记录逐字段不变。

每个序列仍先算Y/U/V PCHIP，再做6:1:1；CE按七序列等权。QP分析每列只替换对应实测RD点，其余用Current，独立于整体BD。
39项台账脚本测试通过；新整体与QP结果经两套公式独立核验，数值差在1e-8个百分点以内。
原CSV和工作簿只读，生成目录通过`--check`。当前完整查询见[总结果台账](TS_Predictor_Results_Ledger.md#15-r14lb-ce-更新结果2026-10-24仅记录)、[R14逐序列/逐QP](results/r14.md)。
旧部分结果报告保持历史性质；当前数据已不适合直接套用旧脚本中“全缺QP22、排除2”的假设。

<a id="r14-qp-before-refresh"></a>

### 修订前的R14 QP子集汇总（保留历史，非当前结果）

以下来自`395f32f`登记版，按当时有效序列等权、Y/U/V先算后6:1:1，单位%；括号为不足7序列的有效数量。
当时所有QP22缺失、实验2整组排除；本表不用于当前方法排名。最新同名表已经在总台账更新。

| 实验 | QP22 | QP27 | QP32 | QP37 |
|---|---:|---:|---:|---:|
| R14-1 |  | -0.009075（6/7） | +0.054528 | +0.004929 |
| R14-2（排除） |  |  |  |  |
| R14-3 |  | -0.052315（6/7） | +0.010707 | -0.005217 |
| R14-4 |  | -0.090606（6/7） | +0.050255 | +0.009835 |
| R14-5 |  | -0.059919（5/7） | +0.014059 | +0.004642 |
| R14-6 |  | -0.035923（6/7） | +0.043363 | -0.000639 |
| R14-7 |  | +0.000000（6/7） | +0.000000 | +0.000000 |
| R14-8 |  | -0.016698（5/7） | -0.004888 | +0.009549 |
| R14-9 |  | -0.003417（3/7） | -0.000166（6/7） | -0.004953 |
| R14-10 |  | -0.014020（3/7） | +0.005706（6/7） | -0.000622 |
| R14-11 |  | +0.024118（3/7） | +0.023401（6/7） | -0.000622 |
| R14-12 |  | +0.027532（3/7） | +0.075245（6/7） | +0.010225 |
| R14-13 |  | -0.035222（6/7） | -0.008349 | +0.006241 |
| R14-14 |  | -0.008327（6/7） | +0.004647 | +0.002105 |
| R14-15 |  | +0.000448（6/7） | +0.006293 | +0.004384 |

## R13 / R14 / R3 / R6 的 QP 汇总登记（2026-10-24）

按用户最新要求及更新后的 codec-experiments skill，将逐QP BD-rate作为正式结果中的QP分析登记。
每个QP分别将该点完整实测RD元组替换入Current四点曲线，其余三个点均为Current；
分别计算Y/U/V PCHIP后6:1:1加权，再按实际有效序列等权汇总。不把四列相加作为整体BD。
本轮仅汇总、不做算法优劣分析或新实验设计；没有修改编码器或执行编解码。

覆盖R13两组、R14十五组、R3四组、R6七组，共28种方法、30个方法/配置组合：
已有LB范围全部登记，并保留R3-1的AI BCE及RA BC。213个原始输入指纹与上次登记完全一致。
948个序列/QP位置中778项可算，4项参考无效，135项目标缺失，3项仅有历史anchor补点，
另R14-2整组28栏排除（18原值不可靠、10缺失）。目标无实测时留空，不登记为0；
R3-1 RA BasketballDrive有失败参考点，四栏均留空。每个QP汇总标注有效数量和具体序列集合。

扩展 `scripts/ts_results_ledger.py` 的catalog选择及QP生成逻辑，新增 `qp_bdrate.csv`、
`qp_group_summary.csv`，并在四轮明细中登记每个序列与各类别的Y/U/V/6:1:1四QP结果。
原 `rd_points.csv`、`sequence_bdrate.csv`、`group_summary.csv` 逐字节保持不变；
没有新增整体曲线补点，不修改原始工作簿或CSV。新增逻辑保持其它实验轮次的计算与记录不变。
38项台账脚本测试通过；使用工作簿公式独立重算全部948项和420条QP汇总，键、状态资格、空值位置一致，
数值最大差约4.15e-13个百分点。原整体BD与新QP结果分别保留，不将完整性相互替代。

数据入口：[总台账QP汇总](TS_Predictor_Results_Ledger.md#qp-analysis)、
[R13明细](results/r13.md)、[R14明细](results/r14.md)、[R3明细](results/r3.md)、[R6明细](results/r6.md)。
复现：`python3 scripts/ts_results_ledger.py --date 2026-10-24 --check`。
独立数值核验输出仅在 `runs/qp_independent_20261024/`；上传范围为登记脚本、派生查询数据和相关文档。

## R14 部分结果与状态作用核验（2026-10-24）

只分析、登记和只读核验源码，未修改算法、未执行序列编解码。按当前连续1～15对应原始CSV，
共280点，其中R14-2的18点由用户确认不准确，保留原值标记`excluded_unreliable`，排除效果和BD计算。
其余262点可用，声明420点范围仍缺140点。所有QP22均缺，不自动补点；无任何完整四点R14曲线。
CSV `pass`不认证实际服务器模式/版本/帧数/hash；没有收到R14活动统计。

固定R14-7的20/20点与Current四元组相同，但该组本来没有状态学习，且算法并非数学恒等Current。
NONE的1/3/4/5/6与固定初态相同点分别6/20、4/20、5/20、7/19、7/20；
PAIR2的10/11/12/13/14/15为10/16、11/16、6/16、12/20、10/20、10/20。
限制到同比覆盖后PAIR2仍更常保持初态输出，E类尤为突出（10/11的7/7、13的9/9）。
这些是报告精度内RD相同，不是码流相同，也不能换算成状态转移率。

源码确认TU/分量初始化、CG全零恢复入口微状态，统计关闭不影响更新；
不同档位反馈仅来自精确命中、C(a)、C(a+1)，当前档位也最优时平局保持。
另有PAIR2相位步、权重跨档但winner不变、实际映射不变、TU剩余作用长度不足等可能。
因此用户观察应记为“部分配置动态增量不明显”，不能直接确认为“状态几乎不动”。
本地纯函数例H=(2,3,10,10,10)说明三种不同层面的无作用；不把合成例频率当作真实视频统计。

补充三点QP27/32/37诊断，按Y/U/V分别PCHIP后6:1:1；无两点拟合、无QP22补点，未写入正式四点台账。
全组共同序列仅BasketballDrill/RaceHorsesC/Johnny；R14-1在该三序列−0.121622%，
自身可算六序列却+0.097340%，显示严重覆盖敏感性，不给完整CE/BCE排名或达标结论。
部分动态组已有变化且局部退化，故不能只以增加转移次数作为优化目标。当前Weak；
优先用已有统计定位same-winner、不同winner反馈平局、相位、有效映射与g_next，不立即扩展参数。

用户异步确认同时登记R13-1新增B的16实测/4缺失，只有RitualDance完整（BD611 +0.056763%）；
BCE仅8/12可用子集−0.056817%，不作为完整BCE。原有R13 CE及全部旧3224条QP/806序列/357组级行逐字段不变。
本次新增440条QP、110序列、48组级行；累计113方法、3664QP、916序列。

报告：[R14部分结果与机制分析](TS_Predictor_R14_Partial_Analysis_20261024.md)；
数据：[总台账](TS_Predictor_Results_Ledger.md)、[R14明细](results/r14.md)、[R13明细](results/r13.md)。
新增`ts_r14_partial_analysis.py`及4项测试；台账CSV主来源/排除规则的31项测试和生成目录`--check`通过。
原始源表只读，不上传工作簿/原始CSV；提交仅包含本轮报告、派生查询数据及对应分析登记脚本。

## R14 连续编号整理（2026-10-23，无新结果）

用户明确要求“调整一下编号，不要跳”，将15组公开MODE按旧
`1,4,7,10,13,16,19,20,21,22,23,24,25,26,27`顺序改为新`1..15`。
算法revision仍为`R14-NF-168-v3`，新增`numbering=compact-15-v1`；runtime名称、参数、评分和状态机不变。
新固定组为7/8/9，NONE为1～6，PAIR2为10～15；阶段A队列为7/1/10/8/9/2/11，
阶段B为3/4/5/6/12/13/14/15，任务数仍196/224。完整旧新表见[实施记录第3节](TS_Predictor_R14_Implementation.md#3-开启与编号)。

宏注册、脚本映射、收件目录和模板同步编号；输出根增加`n15`，不移动旧runs数据。
统计schema首列改为`mode_n15`，避免无编号身份的旧表被误读；旧done和旧启动身份不能冒充当前版本。
Release构建TsR14NativeTest/EncoderApp/DecoderApp成功；21runtime全矩阵按相同runtime
与保留的旧二进制对照，完整bytes/q/context/budget/state逐字节一致。15组观察开关bit-exact及W/R同步通过。
纯核4项、宏5项（205,770例＋1,836转移＋1,200独立参考）、batch 11+8+21项及activity5项通过；
新12实际观察日志导出成功，阶段A实际dry-run为196点。
真实RDOQ非平凡回滚新3/4/12/13各2次、新5/6/14/15各4次，其余0；与旧同方法覆盖一致。
报告`runs/ts_r14_n15_native/validation.json`标记`numbering=compact-15-v1`、`renumber_status=checked`。
未启动视频、不新增BD-rate、不修改结果台账，旧results/runs未重命名。
以下三个R14历史条目中的编号均属于`5279978`及此前的**旧非连续v3号**，保留当时记录，不反向改写。

## R13/R14 源码归档（2026-10-23，无新编码；旧编号）

用户明确要求“将代码也上传”，本次将此前已验收的R14生产接入与所依赖的R13实现一并归档，
包括CMake局部测试目标、两轮批量入口、统计解析和回归测试；沿用`experiment/ts-predictor-study`。
保留Current默认、观察默认关闭及15个R14公开编号，没有改变算法或重跑编码。
`c2d5a76`仅含文档/收件模板；后续源码提交才包含可构建的R13/R14实现。
原始工作簿、外部未跟踪输入、码流和构建产物不在本次上传范围，既有数值台账不变。

## R14 v3 生产接入与局部验收（2026-10-23，无视频结果；旧编号）

用户要求开始修订代码后，实现冻结v3全部15组，保留编号和阶段A/B顺序，未增加新predictor或guard。
详见[实现说明](TS_Predictor_R14_Implementation.md)。TU-local独立r/s，RDOQ局部q后commit/CG清零回滚，
Writer和fractional estimator一次因果预遍历，Reader第三遍恢复幅值后commit；pure-bypass仍学习。
非TSRC/BDPCM/普通变换不改变，统计默认关闭；final-Writer与RDOQ trial分表，新增g_next及相对初始档活动。

205,770纯核案例、1,836转移及1,200独立参考例通过；核心/宏9项、旧宏18项、batch三组11+8+21项、
activity5项通过。构建Encoder/Decoder及两个native目标成功；21runtime每组180合成TSRC TU＋288量化TU通过。
15新模式统计开关完整记录一致、非目标对Current一致；真实RDOQ非平凡回滚在7/10/24/25各2次，
13/16/26/27各4次，其余动态模式未触发，不夸大覆盖。六个旧runtime与保留的pre-R14同一harness
约171 MB/模式完整记录逐字节一致；master-OFF四CPP语法编译通过。

R14-19加入两个非anchor反例，并在局部真实regular路径观察到映射变化；继续保留为独立固定实验。
15组编号收件目录及metadata、共享任务池半帧CE wrapper/逐组写表/hash/no-recon/续跑已准备，A=196点dry-run通过。
未执行视频短测或CE；没有BD-rate和整编码复杂度结论，不改数值台账。源码和脚本依赖此前本地未提交R13实现，
本轮自动同步文档，不把docs-only提交冒充可独立构建的生产源码归档。

## R14 v3 同步与本地工程设计（2026-10-23，无新结果；旧编号）

按用户要求同步当前实验仓库，`6abe8fd`快进至`390ebd2`；远端新增R14方案/参考验证及索引，
未改source/scripts，保留所有本地未提交R13代码和用户文件，没有换分支或重克隆。
按codec-experiments的设计边界，本轮不实现算法、不启动编解码。
采用现行`R14-NF-168-v3`，不恢复v1/v2 TARGET2/DIR2，不重新编号：12动态＋3固定。

新增[工程接入计划](TS_Predictor_R14_Engineering_Plan.md)，对照实际R13、TS-RDOQ和Writer/Reader确认可实施。
沿用KeepHit/候选/tie/n及原round/min/up规则，以近远缓存选当前p，再以已确定q的静态映射代价产生方向；
NONE移动一个权重档，PAIR2移动一个微状态，保留中性事件的最低位。
R13序列互补是研究动机，不当成TU内时序可预测性已经成立。

明确新增逐系数prepare/commit：RDOQ每局部cLevel后提交、CG清零恢复完整r/s；
Writer及fractional estimator单次因果预遍历、三遍查缓存；Reader第三遍反映射后提交，pure-bypass仍学习。
独立状态不混入旧finishCG学习/CABAC回放，BDPCM与TSRC-disabled排除；
lossless/小尺寸/RDOQ-off若仍走TSRC不能停用隐式算法。R13本地实现未提交的身份和补丁hash在计划中单列。

观察增加下一有效位置的同轨迹固定q收益，区别于当前q上选最小反馈代价的即时收益；
仍明确最终选中TS人口偏置、RDOQ反馈与非CABAC性质。单CG TU也可利用历史系数，按有效反馈数分析。
保持冻结15组，首批A仅1/4/22/23/19/20/21共196个CE点，B阶段八组224点须有动态价值或初态瓶颈证据后再决定；
“阶段B”不等于Class B。共享池无组间屏障、半帧/四QP、不写重建、逐组写表与续跑要求沿用，未生成虚假可运行命令。

实际复验R14独立参考通过：512表项、3125邻域、23552赢家、126转移、12000反馈、6000缩放步和21显式案例；
R13六项纯函数测试通过，只编译独立predictor探针，没有构建/运行EncoderApp或DecoderApp。
参考仍不覆盖R14真实Rice组合/原生scan/CG回滚/三遍同步；本轮没有R14生产代码或BD-rate、计时结果。
没有修改数值台账或源工作簿；仅同步本轮工程方案、设计入口和实验记录，不混入此前源码。

## R13 CE 分析与其它轮次新增 B 登记（2026-10-23）

用户报告R13 CE已完成，并明确确认“一并登记，重点分析R13”。只读核验两组各28/28点，
工作簿和同编号CSV全部pass且RD字段一致；Reference与Current源表一致，无缺失、无补点。
各0/28点与Current的RD四元组相同，两组之间也0/28相同；这证明表格有活动，不替代码流/宏身份核验。
逐分量四点PCHIP后6:1:1，CE按七序列等权；与工作簿VBA公式复算最大差约3.56e-13个百分点。

R13-1等权：C −0.081347%、E −0.061971%、CE **−0.073043%**；
R13-2空间权重：C −0.138532%、E +0.082936%、CE **−0.043617%**。
直接重积分而非相减相对Current的BD：R13-1对R2-2为−0.038671%，6/7序列改善；
对R3-1/R6-2/R12-11分别+0.020825%/+0.019783%/+0.088294%。
R13-2对R13-1为+0.029681%，3/7改善；Johnny主要色度退化，KristenAndSara三分量均弱于等权。
等权对Current的绝对收益较集中，去PartyScene与KristenAndSara后为+0.007547%，
但其直接对R2的增量在同一五序列子集仍为−0.043475%。这两个结论不能互相替代。

按序列bootstrap 10000次、seed=20261023，R13-1对Current的95% CI为
[-0.181370%,+0.029060%]，对R2为[-0.121924%,+0.074200%]；均跨零，只视为探索性稳定性检查。
完整四点曲线的低/高质量半区对Current为+0.008773%/−0.153812%，不拟合两QP点BD。
总体暂评**Weak**：保留等权继续验证的价值，降低空间权重优先级，不自动修改公式、加guard或启动B。
没有R13 B，不宣布BCE目标达成；没有同轨迹统计或公平计时，不能推出实际排序分歧或100.8%复杂度。
完整分析、逐QP变化和下一步边界见[R13 CE报告](TS_Predictor_R13_LB_CE_Results_20261023.md)。

按授权同时只登记以下旧轮B，不扩展机制分析、不补缺点：

- R9-9：B四个旧QP22补点被实测替代，B/BCE完整为+0.061087%/−0.047294%；历史暂估保留。
- R10-3：BQTerrace QP22补齐，B/BCE完整为−0.011959%/−0.096015%；旧子集保留。
- R11-2：补齐三个QP22，B19/20点、4/5序列均值+0.034380%；BCE11/12可用子集−0.085559%，仍缺BQTerrace QP22。
- R12-1/2/3/4/6/10/11：B共103实测/37缺失；有效四点曲线依次1/0/1/1/1/1/0条，不报告完整B/BCE。

更新纯数据台账与全部逐点派生文件，新增R13 catalog、严格CSV配对和独立分析脚本。
全局98组、3224条QP、806条序列；新增196条QP，既有13条QP更新（8补点/缺失变实测，5仅CSV核对标记）。
所有旧CE及旧实测RD元组保持不变，历史补点白名单不扩展。26项台账测试、5项分析测试和全量check通过；
源工作簿/CSV只读、指纹不变。分析脚本仅使用六组完整实测CE、168点，并核对共同Current及来源SHA。
未运行编解码、未更改算法或已有未提交的R13源码；本次只同步相关报告、派生查询表及结果维护脚本。
服务器启动日志、actual macro、source/binary SHA、帧范围、统计状态及decode hash仍未完整核验；
未填写metadata模板保持原样，不把表内pass或本地合成TU测试冒充服务器验收。

## R13 两组实现与非序列验收（2026-10-22，无新结果）

用户随后请求“开始修改代码/继续”，按冻结R13-KH-168-v1实现Uniform与Spatial两组。
公开MODE1/2、内部98/99；TypeDef.h直接控制，runtime/batch可覆盖，互斥检查覆盖旧模式及cache。
交付默认仍master=1、所有算法MODE=0，即Current；观察默认关闭。没有修改旧轮算法、实际remapping或QuantRDOQ.cpp。
两组共享生产内核，只差物理11111/22111权重；cache保留重复样本贡献，64位168整数分数，
n<3保持原Current，不增加候选、guard或历史状态。实现说明：[R13实现与验证](TS_Predictor_R13_Implementation.md)。

新增最终Writer聚合和有界trace，同一最终H并排计算旧R2及两组新选择，
按真实三遍budget区分actual remap，不回写真实coeff/context。每shadow分母独立；
Spatial的旧tie为同权重旧cost诊断，稀疏支持不能冒充评分样本，详细限制已写入说明。
复用batch共享池、逐组写表、无重建/hash/指纹续跑；56项LB CE wrapper仅dry-run，无真实编码。
R13任务附规格与binary/config SHA，checkout快照明确不是二进制构建来源证明；旧模式未请求R13时不改变旧观察指纹。

独立评分参考576,788次决策、1024点表/积分及8704项loss检查通过；
18项宏身份、8项R13 batch、21项旧batch、2项统计默认、3项导出检查通过。
master-OFF四关键文件语法编译通过，独立review未发现公式/同步/状态污染错误。
合成TU跨版本字节回归通过：六模式各180个TSRC TU/1718 CG/27032次因果检查和240个量化TU；
观察开关前后完整字节记录相同，四旧模式对冻结c7cb2a4同harness逐字节相同，BDPCM六模式相同。
两新模式相对R2及彼此均有实际语法/量化活动；双shadow统计分母及有界两端trace一致。
UBSan完整纯函数检查通过。首次应用链接因中断留下34个零字节obj失败，已隔离构建残留重编；
EncoderApp/DecoderApp/TsR13NativeTest最终Release构建均通过，两端help身份探测及56项dry-run通过。
局部测试及完整记录hash见实现说明第5节与runs/ts_r13_native/validation.json。
未运行真实帧/序列编解码或CTC、未新增BD-rate和整体耗时、未修改源表或结果台账数值。
按既有授权自动同步相关文档及收件说明；本轮源码/运行与测试脚本保留本地，未混入文档提交。

## R13 两组 KeepHit 评分设计（2026-10-22，设计阶段历史记录）

按用户请求先同步当前实验分支，`0d1e8b0`快进至`a47686d`。新增KeepHit推导指导与R3/R6剩余复杂度建议；
指导核对基线`786da636...`至当前HEAD的source/scripts无差异。保留未跟踪工作簿、外部原稿及附件标记，未纳入本次修改。
依据codec-experiments的“设计”边界，本轮仅形成[冻结方案](TS_Predictor_R13_Experiment_Design.md)，不自动实施算法或启动编码。

R13-KH-168-v1仅两组：R13-1 KeepHit Uniform、R13-2 KeepHit Spatial，物理权重分别11111与22111。
沿用R2-2五邻域、非零位置n、n<3 Current、候选与tie、YUV范围和直接最小化，只换保持/相邻命中损失；
固定rho=21/2、统一168整数尺度，不加guard/fallback、不改实际RDOQ搜索规则。预留MODE1/2、内部98/99，尚未注册。
正式anchor仍Current，R2-2为单因素机制对照，R3-1/R6-2与R12-11为历史性能参考，不自动重跑所有旧实验。

源码审查区分普通TS低budget下的allowUp（仍可随p改变）和独立forwardBDPCM（固定round/min且禁用remap）；
同指定p保持原搜索，不错误承诺换p后实际候选集合不变。最终Writer/Reader共享规则，临时trial不要求等于最终p。
模型省略identity的普通减一收益而奖励相邻命中，可能偏向非identity；固定H下新Uniform的identity获选集合只能不增，
但该结论不约束闭环轨迹占比。q代理普通舍入幅值、uniform舍入和固定rho均标为模型假设，不宣称真实CABAC/RD精确。

只读Python精确有理数完成11,008项闭式/整数表/分段积分/identity检查，全部误差0；
冻结不同权重、旧新严格winner及tie打破三类构造样例，只证明定义与活动，不是自然数据收益。
后续先实现与纯函数/局部语法验收，再在获授权后进行四序列QP22/37短帧活动检查；正式两组LB CE半帧共56项。
复用共享池、无重建、hash、逐组写表及指纹续跑；已有Current不自动重跑，缺点不自动补，复杂度观察关闭。
R3/R6剩余等价优化独立留待处理，不与R13混合。没有改源码、宏、脚本、二进制、源表或结果台账数值，没有运行序列编解码。

## 源码集中交付（2026-10-05，无新实验结果）

用户明确授权提交源码。本次将此前保留在本地的R12十二模式、R12及R3/R6等价复杂度优化、
各轮统计默认关闭、对应批量脚本/模式注册/manifest/测试代码纳入当前experiment/ts-predictor-study分支。
不改变模式默认：算法仍默认Current，R12_EXACT_OPT/R36_EXACT_OPT仍默认1，统计仍默认关闭。
下方旧记录中的“源码未上传/仅文档同步”是各阶段当时的交付状态，不再代表此次集中交付后的状态。

提交前核对源文件与新依赖、Python语法/JSON、差异空白和敏感标记；当前Release目标构建通过。
沿用2026-10-04已通过的166项单元测试及局部字节/量化一致性验证，本次未重跑完整测试矩阵，
没有运行完整帧/序列编解码。工作簿、原始实验数据、runs/build产物及未跟踪外部原稿均不纳入提交。
源码归档不产生新BD-rate，不改结果台账数值。

## 各实验统计统一默认关闭（2026-10-04，无新 BD-rate）

按用户要求，R2～R6、R8/R9在线统计改为未设置时关闭，显式0关闭、1开启；
R10～R12及R7 shadow本就默认关闭，保持不变。这里沿用环境变量接口，不新增算法宏。
包含R2-4的额外真实context观察、R8 owner-search和R9 quant-search统计，未关闭实际搜索或必要算法历史。
TypeDef.h增加集中说明，R3/R6启动行改为stats-default=off。

R6/R8/R9/R10正式wrapper及R8 preflight同时改为默认0、接受外部显式1；
专用shadow脚本仍作为显式观察任务，conditional smoke观察阶段补显式R2～R6_STATS=1，
其无观察对照仍设0。没有运行任何帧级smoke或正式编解码。
batch续跑指纹补齐全部观察环境，保守区分未设置/0/1；旧指纹一次性失效，未改已有结果或marker。

编译EncoderApp/DecoderApp和局部原生测试通过，全量166项单元测试通过；生产统计表达式逐项验证默认/0/1，
包括R2 Writer及R8/R9搜索旁路；wrapper拦截测试与续跑模拟通过。
Current、R3-1/2、R6-1～7共十模式，修改前后×默认/显式关/显式开，
各160合成TU的完整CABAC字节和240 TS-RDOQ用例q/absSum一致；新默认无统计，R3/R6显式1仍有统计，
修改前后的显式开启诊断逐字一致。产物在runs/ts_stats_default_off/native_checks/。
代码审查确认R2/R3自适应状态、R8-22路径权重、RDOQ必要回放与CG清零未受影响。
没有新增或重算BD-rate，不宣称完成完整序列验收。

新默认与使用说明见[统计默认值规范](TS_Predictor_Statistics_Defaults.md)；
下列旧记录中的“默认开启”仅表示当时版本。

## R3 / R6 等价复杂度优化（2026-10-04，无新 BD-rate）

用户确认101.4%是R3-1，所给旧启动行不能判断统计是否开启。
当前TS_R3_STATS/TS_R6_STATS默认开启、仅显式0关闭；TS_COND_TRACE必须unset。
新增实际观察状态启动行，R6 wrapper保留默认统计开启但不再覆盖外部显式0。
公平计时同时关闭原版/优化版统计，不能把关闭统计算作算法优化。

新增TypeDef.h的JVET_BJUT_TS_R36_EXACT_OPT=1；0保留原路径。
覆盖R3-1/2、R6-1～7，重点R3-1/R6-2；R3-3/4不受影响，算法默认仍全0。
共享不同幅值的C(a)/C(a+1)、精确前缀求score、sum按重复次数而guard仍按单位置；
移除动作路径多余诊断、直接使用scan坐标、无观察的stateless CG提前返回；
Writer仅在单次固定q的CG调用内复用regular remap，不跨CG/TU/RDOQ trial缓存。
候选、平局、G/H、稀疏规则、R6-2 fallback、RDOQ搜索/清零和CABAC状态均不改。

Release构建及master-OFF语法检查通过；151项测试通过，新增656,613次predictor及152,963次guard比较。
十模式宏0/1×观察关/开，160合成TU/1,491CG的完整CABAC字节相同；
240合成TS-RDOQ用例完整q/absSum一致，包含HOR/VER BDPCM和清零/恢复。
统计、两端trace、概率状态、fractional bits、budget断言通过，没有运行完整视频编解码。

七轮交替局部TS-RDOQ耗时比（优化/原实现）中位：Current=0.9993、R3-1=0.7733、R6-2=0.7465。
只是合成夹具证据，不是整编码加速，尚不能确认达到100.8%。
详细范围、宏、验证、服务器公平计时要求见[R3/R6等价优化](TS_Predictor_R3_R6_Exact_Optimization.md)。
结果在runs/ts_r36_exact/timed/validation.json；没有新增/重算BD-rate数值。

## R12 等价复杂度优化（2026-10-03，无新 BD-rate）

先同步远端 `a0f21db`→`08b7140`，参考新增复杂度文档，以本地实际 R12-POS-01 实现为准。
保留既有未提交源码和原二进制备份，没有改变模式、候选、阈值、权重、tie 或 guard。
新增 `JVET_BJUT_TS_R12_EXACT_OPT=1` 工程开关；0为完整原路径，不是新实验编号。
R12_MODE默认仍0，启动日志标出exact-opt；其它旧轮及Current不改。

拆分动作/诊断路径；共享B/C代价矩阵，A仅计算原identity-trim动作，不再重复生成parent/base/diagnostic评分；
全部可选query动作相同时提前返回（R12-3包含D）；外层先构造精确CI合法池，再按需计算full-V0 CF。
不加跨调用缓存，不改RDOQ搜索、最终CG清零、frozen context或TSRC回放。
原完整路径继续用于统计和等价对照，不改变stats/trace。

Release编译及master-OFF语法检查通过，143项既有/宏测试＋4项新增纯函数测试通过，
新增811,935次新旧专家/selector核验。12个R12加R10-3的宏0/1、观察关/开完整矩阵中，
每组合160个合成TU/1,491CG的完整CABAC字节相同；180个原生TS-RDOQ测试最终q/absSum相同。
前缀扰动、清零/恢复、快照分支及原生概率/预算检查均通过，诊断和两端trace一致。
原旧二进制另与宏0对照核验stdout和摘要一致，没有把摘要核对冒充完整文件比较。

无并发计时、五轮交替的合成TS-RDOQ中位耗时比（优化/原实现）：
R12-3=0.4653、R12-11=0.3955、R12-12=0.3792；未改动R10-3对照=0.9964。
仅为夹具内局部性能证据，含初始化和回归断言，不是完整编码/解码加速比。
没有运行任何视频帧/序列编解码，也没有新增或重算BD-rate结果台账。

设计、等价条件、宏、复现命令、验证边界见
[R12等价复杂度优化](TS_Predictor_R12_Exact_Optimization.md)。
原生完整结果和计时记录在 `runs/ts_r12_exact/{paired,timed}/validation.json`，不上传原始测试产物。

## R12 CE 与 R11-2 部分 B 结果登记（2026-10-02，仅汇总）

只读核验R12-1～12工作簿和同编号CSV，各28/28实测点，共336点全部一致，Test为pass，
Reference数值及状态与Current一致，无缺失、无补点，84条序列四点曲线可计算。
各分量先算PCHIP BD-rate再6:1:1，CE七序列等权；按模式1～12顺序的CE为：
−0.148089%、−0.145482%、−0.154885%、−0.151557%、−0.114393%、−0.151826%、
−0.125923%、−0.117572%、−0.137122%、−0.144800%、−0.160415%、−0.122824%。
此处仅登记，不作优劣或机制判断。

R11新增B仅属于R11-2：16/20实测点，全部pass，仅RitualDance四点完整，BD611为−0.005882%。
MarketPlace、Cactus、BasketballDrive、BQTerrace各缺QP22，未获补点授权，保持缺失。
B可用子集仅1/5；与原CE组成的8/12可用子集为−0.135569%，均不是完整B/BCE平均。
原R11全部CE逐点数据及曲线不变；2.csv仅核对CE，新增B点标记为仅工作簿来源。

统一台账复算发现R10-3源表也新增BasketballDrive QP22实测：13113.5456 kbps、
Y/U/V PSNR=39.5600/44.2593/45.5812 dB；该序列BD611=+0.041944%。
R10-3 B现19/20点，仅BQTerrace QP22缺失；B四序列子集−0.017388%、BCE十一序列子集−0.105630%。
旧三序列B子集−0.037166%、十序列BCE子集−0.120388%保留在总台账，未改旧实测点。

更新[总台账](TS_Predictor_Results_Ledger.md)、[R12明细](results/r12.md)、[R11明细](results/r11.md)、
[R10明细](results/r10.md)、统一CSV和SHA256记录；新增catalog和严格按编号CSV配对，补点白名单未扩展。
24项台账测试通过，脚本生成与check一致；分量BD-rate与工作簿VBA公式独立转写的最大差为5.15e-13个百分点。
全台账96组、3,028条QP（3,001实测、20历史补点、7缺失）、757条序列、330条类别汇总。
新增356条QP/89条序列/39条汇总；旧记录只改R10-3该点、该曲线及B/BC/BCE三项相关子集，
其余2,671条旧QP、667条旧序列和288条旧汇总逐字段不变。
原始源表/CSV没有改写，未运行编解码。R12服务器实际revision、宏、帧范围和decode hash仍未核验，
模式映射依上传编号对应本地R12-POS-01规格登记；本次不上传旧任务遗留的R12算法源码改动。

## R12 十二组代码实施（2026-10-01，无新 BD-rate）

按用户要求继续当前实验，保留 `experiment/ts-predictor-study` 分支，先同步远端，
由 `e6ba16b` 快进至 `94a3540`。采用新规格 R12-POS-01，不重复克隆基线、不覆盖外部原稿或用户未跟踪工作簿。
Current 为正式 anchor，R10-3 为机制对照；实现1～12全部模式，优先 CE 1/2/4/7/8/9。

改动分为原唯一CI赢家的 near/LOO、直接邻居优先、C 内部位置加权及其 full/soft 删除、外层位置加权。
Q15差距、历史自己的邻域/分类、精确平局保护、n为非零位置数、同CG的V0、槽位W22111均按最新版实现。
TypeDef.h 新增 R12_MODE=0..12 和全部旧轮/缓存互斥；默认0，运行时显式覆盖仍有效。
公共动作同时接入 RDOQ/Writer/Reader/replay；最终Writer统计默认关，最多三组shadow，默认无逐系数文本。

纯公式及原生语法测试已验证独立参考、因果污染、概率/预算、两端摘要和观察开关不改合成码流；
另增加YUV/矩形合成残差的原生RDOQ测试。修复验证中发现的master-OFF unused警告和统计参数影响默认模式探测问题；
RDOQ测试夹具缺失picture header及色度QP表已补齐，不改实际编码器初始化。
具体通过数量、未测项目及复现命令见[验收记录](TS_Predictor_R12_Validation.md)。

复用batch共享池、半帧、无重建、逐组写表和指纹resume；首批dry-run为168点，全12组上限336点。
新增编号收件目录，CE/九点B哨兵/完整B分开。此次没有启动任何序列级编解码，也没有新收益/速度数据，
因此不新增结果台账数值。阶段方案及证伪边界见[实施文档](TS_Predictor_R12_Implementation.md)。

## R11 CE 与 R10-3 部分 B 结果登记（2026-10-01，仅记录）

收到R11-1～8八组LB CE工作簿及编号CSV，各28/28实测点，224点全部与CSV一致、Test为pass，
Reference数值/状态与Current一致。无补点、无缺失；56条序列曲线均可计算。
按分量四点PCHIP后6:1:1，CE七序列等权，八组CE依编号为：
−0.071190%、−0.154095%、−0.017794%、−0.054241%、−0.072855%、−0.056157%、−0.034803%、+0.015666%。
本次只登记，不作优劣、机制或后续实验分析。

R10-3新增LB B的18/20实测点。MarketPlace、RitualDance、Cactus四点完整，
BD611分别为+0.130441%、−0.035423%、−0.206515%；BasketballDrive、BQTerrace缺QP22，
没有本次补点授权，保持缺失、不计算两条四点曲线。B三序列可用子集为−0.037166%，
与CE合并的十序列可用子集为−0.120388%，均不作为完整B/BCE均值。
原CE的28点及−0.156054%不变。3_B.csv只核对14个新增B点，另4点仅见于工作簿，来源标记区分。

已更新[总结果台账](TS_Predictor_Results_Ledger.md)、[R11明细](results/r11.md)、
[R10明细](results/r10.md)、统一CSV及源指纹。脚本catalog新增R11八组、R10-3的明确B补充CSV，
不混入共享目录其它编号CSV，不扩展历史补点白名单；22项台账测试通过。
全台账84组、2,672条QP记录（2,648实测、20历史补点、4缺失）、668条序列记录。
本次新增242实测＋2缺失占位；旧2,428条QP、607条序列、264条汇总记录逐字段不变，
与工作簿BD-rate公式独立转写的最大差仍为5.15e-13个百分点。源表/原始CSV只读，未启动编解码。
服务器宏、帧范围及解码hash未新增核验；R10-7不在本次登记范围，R11 B/RA/AI未登记。

## R11 实施与工程验证（2026-09-29）

先快进同步GitHub至`c9994d1`，按最新R11计划实现八组：无证据回R3、query分类CF平局、
同CG/同TU有界验证扩展、独立加入Current/identity，以及两组预设组合。
机制对照R10-3，正式BD-rate anchor仍Current；未改动外部原稿和既有算法编号。
TypeDef.h增加R11_MODE=0..8及全旧实验/缓存互斥；默认0，不增加CMake算法开关。
新增最终Writer八模式shadow、独立观察预算、因果/几何参考及编号收件目录。

遵循较新的资源计划：完整八组CE共224点，再按CE≤−0.14%及9点B哨兵筛选；
不按旧分析默认同时启动完整B。批量复用共享池、半帧、无重建、逐组写表、resume。
128项单元测试通过；此前已结束的合成短测290任务通过、78个旧模式回归bit-exact、
5,297条两端CG trace相同、观察开关不改码流。R11-5尚无合成码流差异；2/6仅AI0有活动，
不据此预判真实内容效果。独立master-OFF构建通过，本轮OFF码流比较未做。
用户要求不跑完整编解码后未再启动序列编解码，只编译、核验既有证据及整理文档。

详见[R11实施](TS_Predictor_R11_Implementation.md)、[验收](TS_Predictor_R11_Validation.md)。
没有R11 BD-rate数据，不改写既有数值台账或假填结果；真实内容预检/CE/B由用户后续执行。

## R10-1～6 / R9-9 B 结果登记（2026-09-29，仅记录）

收到R10-1～6的LB CE工作簿及编号CSV：1～5各28个实测点，6有26个实测点；
R10-6的PartyScene、RaceHorsesC QP22按用户本次授权暂用Current补点。
R9-9工作簿新增Class B的16个实测点，MarketPlace、Cactus、BasketballDrive、BQTerrace QP22暂用Current补点；
原CE的28个点未变。同目录9.csv仍只覆盖CE，新B点仅以工作簿为来源，不冒充CSV交叉验证。

已更新[结果台账](TS_Predictor_Results_Ledger.md)、[R10逐点明细](results/r10.md)、
[R9逐点明细](results/r9.md)、统一CSV和源指纹；源工作簿/原始CSV只读，不写入补点。
每分量四点PCHIP后6:1:1，CE七序列、B五序列、BCE十二序列等权。
R10-1～6的CE依编号为-0.066211%、-0.086765%、-0.156054%、-0.068129%、-0.025721%、-0.074966%（最后一项含补点）。
R9-9 B/BCE暂估为+0.058640%/-0.048314%；原CE为-0.124709%，未变。
后续补齐时保留本版暂估值；R10-7未登记数值。本次不作效果分析或新增实验建议。

登记脚本新增R10-1～6身份和六个明确补点白名单，准确配对同编号CSV，不扩大其它实验的补点授权。
19项单元测试通过，生成结果可用`python3 scripts/ts_results_ledger.py --date 2026-09-29 --check`复核。
全台账76组、2,428条QP记录（2,406实测、20补点、2缺失）、607条序列记录；
本次新增182实测+6补点，旧2,240条QP记录、560条序列记录、243条汇总记录逐字段不变。
与工作簿BD-rate公式独立转写的最大差为5.15e-13个百分点；未新增远端宏/帧范围/解码hash核验。

## R10 实施更新（2026-09-28）

2026-09-29补记：收到R10-7 BasketballDrill QP22异常日志，内容实际为十次Decoder启动，
无编码/帧输出；与HHI十次解码且未收集stderr的模板相容。缺失码流的本地复现产生类似stdout，
真实错误在stderr。R10-7原生测试及已有LB两帧解码复核通过；尚需服务器命令与stderr确认根因。
未修改算法、未重跑正式编码、未登记BD-rate；详见[R10验收诊断](TS_Predictor_R10_Validation.md)。
随后收到正常对照日志，实际模式为R10-6：250帧编码后执行十次250帧解码，2,500次MD5均OK。
因此十次解码本身正常，R10-7异常的关键是整个编码段缺失且解码零帧；
仍需stderr/退出码区分启动失败、早期异常、路径问题或日志覆盖，不能将对照日志当作R10-7验证通过。

同日最终状态：用户确认R10-7重新运行后结果正常，本次异常排查结束，保持算法不变。
具体故障原因未确认；此条依据用户反馈，未新增重跑日志核验或BD-rate结果，
也不将单次恢复正常等同于全部CTC任务完成。

先快进同步GitHub至`0b08de8`，取得R10计划、R9外部分析及两份匹配/汇总CSV。
按原稿实现R10-1..7和R10-0独立等价缓存，旧R9编号保持不变。
新增目标层loss/regret观察，严格区分验证集最优和未来目标预测表现。
主anchor仍Current，配对R9-9；默认宏全部模式关闭，用户直接改TypeDef.h选择。
批量沿用统一任务池、逐组写表、半帧、无重建、resume；未启动正式CTC，未写入新的BD-rate。
工程验收：120项完整测试及4项最终R10补充测试通过；第一轮308任务、最终170任务通过，
71个旧模式回归bit-exact，master-OFF/Current一致，缓存与观察开关不改变码流。
所有新组有合成活动，但2/4/6仅在AI0活动，先做真实内容短测；不据此预判收益。
实现、运行命令与验证边界见[R10实施](TS_Predictor_R10_Implementation.md)及[R10验收](TS_Predictor_R10_Validation.md)。

## 1. 已确定的目标与评价口径

- 工程目标：**LB、BCE 平均 BD-rate ≤−0.05% 为达标，≤−0.08% 为不错，≤−0.10% 为可观**。
- 每条序列先分别计算 Y/U/V BD-rate，再计算 `(6 BD_Y + BD_U + BD_V)/8`。
- 使用工作簿 `bdrate` 对应的 PCHIP，公共质量区间积分，不外推；负数为改善。
- BCE 按十二序列等权：`(5*BD_B + 4*BD_C + 3*BD_E)/12`，不是类别等权。
- LB CTC **采用 HHI INI 半帧**，用户已确认；正式命令不使用 `--full-sequence`。
- 唯一正式anchor为Current，使用 `scripts/JVET-hhi.xlsm` 的Reference，不安排完整anchor重跑。
- NoPred仅为候选/辅助对照；所有正式BD-rate、用户收益门槛与主结论均相对Current。
- 长时间正式编码由用户执行；分析、验证、计划和结果必须明确区分。
- 不预设正结果；不删除退化序列，不根据验证集结果反复调整公式或阈值。

当前分析使用的 anchor 工作簿 SHA-256：
`3e5dda606666fe38dd37b5597e6ec9cf69a25d5d91e4ec11488fec786d1423f1`。
历史 anchor 完整软件/构建/配置来源未独立复核；半帧已确认不代表全部 provenance 已确认。

## 2. 实验总览

| ID | 实验 | 状态 | 主要结果 / 下一步 |
| --- | --- | --- | --- |
| TS-001 | 固定 anchor 系数的 CE 短帧 counterfactual | 已完成、已分析 | Oracle 有条件潜力，所测 TU-local causal selector 未捕获稳定收益 |
| TS-002 | 新固定 predictor 闭环编解码验证 | 已完成 | 42 个 smoke 任务通过，Current/OFF 与原版 bit-exact |
| TS-003 | LB C/E 半帧，三固定 predictor | 已完成、已分析 | NoPred −0.0567%；gradient +0.0846%；directional −0.0366% |
| TS-004 | 面向 BCE 目标的深入分析 / QP 组合诊断 | 已完成分析，非新编码 | directional 低两档 + Current 高两档的 CE RD 点组合 −0.0993% |
| TS-005 | 补 B：固定 NoPred 和 directional | 已接收外部结果、完成表格审计 | BCE分别−0.041705%/−0.035706%，外部来源仍待日志核实 |
| TS-006 | 条件/历史自适应revision1五组 | 已实现验证、CE初步130/140点 | N1/N2完整CE退化，A1/A2/A3仍有缺失点，见2026-09-18报告 |
| TS-007 | 三固定predictor RA CD | 已接收外部结果、完成表格审计 | NoPred−0.008314%、gradient+0.040742%、directional+0.003174% |
| TS-008 | R2局部幅值预测及Current/NoPred自适应 | 2026-09-27明细核对已112/112实测；R2-4缺点已补齐 | CE：1 +0.068593%、2 −0.033694%、3 −0.011639%、4 −0.005667%（实测；旧补点暂估−0.004392%）；未有本轮B/RA；旧分析保留原日期范围 |
| TS-009 | 固定/条件/R2跨轮多维复核 | 已完成分析，非新编码 | 质量区间、分量、序列及配置差异明显；R2-N高质量区间7/7改善，但低质量损失抵消，尚无整体Promising方案 |
| TS-010 | R3证据保护与分量消融 | 四组CE完整；R3-1 B已20/20实测，R3-2仍缺3点；2026-09-27补登记AI48点、RA35点 | R3-1 LB BCE−0.075521%；R3-2 LB BCE暂估−0.063619%；AI BCE−0.002334%。RA MarketPlace缺QP22、BasketballDrive参考QP37为MD5 fail，对应两曲线不算BD；详见结果台账 |
| TS-011 | R4分支消融、回退补查及非消融扩展 | 六组服务器CE168/168点完整并已分析 | CE依次−0.039815/−0.016843/−0.093288/−0.025079/−0.065248/−0.021221%；3全RD点同R3-1，其他五组均值更差；无组通过冻结扩展门槛，5保留为Weak诊断分支 |
| TS-012 | R5：稳健幅值排序 / Current-only因果否决 | 两组服务器LB CE各28/28点，已核对；远端身份部分验证 | 两组CE均−0.093288%，所有RD点同R3-1/R4-3，增量0；一份R5-1日志确认模式但无活动统计，不能称远端bit-exact；新增RD价值Negative，不扩展B/RA |
| TS-013 | R6：Current偏好 / n<3稀疏区域 | 七组CE各28/28点；2026-09-27另登记R6-2 B20/20实测；远端身份/活动日志缺失 | CE依次−0.012585/−0.092172/−0.026110/−0.007096/−0.048541/−0.029310/−0.016507%；R6-2 B−0.053507%、BCE−0.076061%。本次仅数据登记，不追加机制分析 |
| TS-014 | **R7**：CG-entry CABAC fractional评分、old-R3 shadow、R2/R3评分替换 | 已实现验证；2026-09-25核验外部两组完整LB CE各28点，无补点；远端身份仍待核验 | R7-1/2 CE对Current −0.070549%/−0.017510%，对R3 +0.023403%/+0.076633%；评分×guard有交互线索，增量Weak；此前shadow条件率不是BD-rate |
| TS-015 | **R8**：评分规则交叉、完整候选、小样本分布、路径和量化搜索 | 2026-09-27已从全24组本地源表提取670实测+2补点，并核对配套CSV、复算BD；服务器身份/活动未核验 | 全24组数值及逐QP明细见结果台账；23/24各补PartyScene QP22。原外部转录状态更新为本地数值核验，不等于编解码身份验收 |
| TS-016 | **R9**：候选覆盖、稀疏恢复、保护强度、新映射、因果专家、零一量化 | 十三组CE完整；2026-10-23 R9-9 B补齐20/20实测 | R9-9 B/BCE为+0.061087%/−0.047294%；旧补点暂估留痕。仅汇总；RA/AI未登记 |
| TS-017 | **R10**：因果专家验证与独立等价缓存 | 1～6 CE已登记，6含两补点；2026-10-23 R10-3 B补齐20/20实测；7未登记 | R10-3 B/BCE为−0.011959%/−0.096015%；CE未变，历史子集留痕；仅汇总 |
| TS-018 | **R11**：无证据、query分类、有界验证扩展及专家扩池 | 八组CE共224/224实测；2026-10-23 R11-2 B为19/20点 | B4/5子集+0.034380%、BCE11/12子集−0.085559%；缺BQTerrace QP22，未补点；仅汇总，RA/AI未登记 |
| TS-019 | **R12**：专家内部与外层位置加权、near/LOO及等价优化 | 十二组CE完整；2026-10-23登记1/2/3/4/6/10/11部分B共103/140实测 | 每组B仅0或1条完整四点曲线；无完整B/BCE，不补点、不分析；RA/AI未登记 |
| TS-020 | **R13**：KeepHit Uniform / Spatial | 2026-10-23收到两组完整CE共56/56实测，无补点 | CE−0.073043%/−0.043617%；等权对R2直接−0.038671%，仍不及R3/R6/R12-11 CE；Weak，无B/可靠计时结论 |
| TS-021 | **R14**：近/远邻权重、NONE/PAIR2方向反馈 | v3生产接入，compact-15-v1连续1～15；2026-10-24服务器LB CE累计412/420点，14组完整，2的新20点纳入 | 本地非视频验收历史保留；服务器CSV数值及来源已核验，整体/逐QP结果已登记，2整体因缺点留空；无服务器状态转移计数 |

注意：B与RA新增实验来自外部工作簿，没有本地成功marker，不能把“本地marker为0”解释为未编码。
表格完整性和实际编解码身份/hash验证是不同层级；各轮细节与限制见更新历史。

## 3. TS-001：固定系数的反事实统计

### 配置和方法

- CE 七序列，普通 `--local-preset AI/LB`，QP22/27/32/37，每任务 16 连续帧，共 56 任务。
- 宏 `JVET_BJUT_TS_PRED_ANALYSIS`，在真实 Writer 记录最终选择 TSRC 的非零 TU component。
- 不记录临时搜索候选；整 TU CBF=0 不进入该统计，非零 TU 内的全零 CG 进入。
- 固定最终 anchor q，CG 条件 CABAC 仿真及 TU 连续路径仿真；不改变实际决策或码流。
- 旧候选：M0 NoPred、M1 Current=max、M2 Left、M3 Above、M4 Min、M5 Mean。
- selector：Previous Winner、Cumulative、Recency、Confidence、Simple；历史仅 TU 内保持。

### 结果与限定

- 56/56 完成；60,568 个 TSRC component TU，257,123 个 CG，23 种观察到的 TU 尺寸。
- 条件 CG Oracle 节省约 **1.6242% TSRC rate**，不是整码流 BD-rate。
- Recency 条件 gain 约 **−0.03834% TSRC rate**，capture ratio 约 **−2.36%**。
- 各种 alternative fixed 在该固定-q 条件样本上总体不优于 Current。
- 85.60% CG 的六候选 rate 全部相同，非平凡历史信息稀少。

结论：**该条件样本上的所测 causal selector 为 Negative**，不能据此否定所有真实 predictor 工具。
重要限制有两层：q 已经由 Current rate model 优化；最终 TS 入选本身也受 Current RD cost 影响。
该选择偏差不能仅靠 bootstrap 消除。由此进入真实闭环实验 TS-003。

资料：[原始设计](TS_Adaptive_Predictor_Experiment_Design.md)、
[CE 统计报告](TS_Adaptive_Predictor_CE_Results.md)。
数据：`runs/ts_CE/stats/`、`review_verified/`、`ce_audit/`。

## 4. TS-002：新工具的正确性验证

真实实验宏 `JVET_BJUT_TS_FIXED_PREDICTOR` 与旧分析宏互斥。
统一实验 Encoder/Decoder，通过每进程 `TS_FIXED_PREDICTOR` 选择工具，匹配解码器必需。

| 参数名 | 定义 | 边界 |
| --- | --- | --- |
| current | `max(L,U)` | 缺失邻居为 0 |
| nopred | `p=0`，identity remapping，其他 TSRC 语法不变 | 无额外边界 |
| gradient | `clip(L+U-D,min(L,U),max(L,U))` | 第一行/列用 Current |
| directional | `EH=abs(L-LL)+abs(U-D)`；`EV=abs(U-UU)+abs(L-D)`；EH<EV 取 L，反之取 U，相等取 Current | x<2 或 y<2 用 Current |

L/U/D/LL/UU 分别为左、上、左上、左二、上二的量化系数幅值。
**新 gradient/directional 与旧 M2/M3 不是同一候选，禁止按数字编号混合结果。**

验证：

- TS-RDOQ 候选、CABAC estimator/Writer、Reader 反映射使用一致 predictor。
- AI、LB、LB-High、BDPCM、lossless、TSRC-off、TS-off 七种 case；六个版本/模式共 42 任务。
- 全部 hash 解码通过；Current、宏 OFF 在各 case 与 untouched 原版 bit-exact。
- TSRC-off/TS-off 时三 alternative 与 Current bit-exact；活动 TS case 验证 alternative 确实生效。
- 原生 scan 的 64 个完整形状、1,267,924 个邻居先后检查通过；该形状集包含 TS 尺寸但不全是合法 TS 尺寸。
- 无重建视频输出；synthetic_input.yuv 仅为 smoke 输入。

资料：[真实编码设计](TS_Fixed_Predictor_Coding_Experiment.md)。
证据：`runs/ts_fixed_smoke/validation.json`、`runs/ts_fixed_batch_smoke/`。

## 5. TS-003：LB C/E 半帧真实固定工具实验

### 配置

- HHI `--preset LBeu`，实际为 `encoder_lowdelay_nx2High.cfg`，不同于 TS-001 普通 LB。
- QP22/27/32/37，nopred/gradient/directional 三模式，共 84 任务。
- BasketballDrill、PartyScene 250 帧；RaceHorsesC 150 帧；
  BQMall、FourPeople、Johnny、KristenAndSara 各 300 帧。
- 完整重编码，允许量化、TS 选择、预测/划分、参考重建自然变化。
- 不输出重建视频；保存码流并逐帧核对 hash；原脚本统一任务池、不同组无 barrier。

### 完整性和中断恢复

- 初次检查：nopred 28/28、gradient 28/28、directional 22/28。
- 已恢复前两组 Excel/CSV，Reference 不变。
- directional 剩余 PartyScene/FourPeople/Johnny QP22，KristenAndSara QP22/27/32，后续均完成。
- 最终 **84/84 成功、22,200 个编码帧 hash 核验通过**。
- 根目录 summary/plan 曾因只续跑 directional 而只包含该组；完整分析使用所有模式成功 marker，
  不依赖根目录汇总代表全部任务。

### 主结果（各分量 BD-rate 后 6:1:1 加权）

| 模式 | C | E | CE 七序列均值 | 改善数 | 七序列均值 bootstrap 95% 区间 |
| --- | ---: | ---: | ---: | ---: | ---: |
| nopred | −0.1202% | +0.0280% | **−0.0567%** | 5/7 | [−0.1810%, +0.0412%] |
| gradient | +0.0092% | +0.1852% | **+0.0846%** | 3/7 | [−0.1154%, +0.2795%] |
| directional | −0.1186% | +0.0727% | **−0.0366%** | 4/7 | [−0.1719%, +0.0925%] |

NoPred 固定替换优先补 B；gradient 暂停；directional 总体较弱但保留 QP 结构线索。
CI 跨零代表泛化不确定，不等于低于 0.1% 的收益自动没有工程意义。
没有新模式最终 TS census，不能报告 TS 使用率/CG 数变化，也没有新的 CG capture ratio。

数据：`runs/ts_fixed_LB_CE_half/{nopred,gradient,directional}/`。
报告：[LB CE 结果](TS_Fixed_Predictor_LB_CE_Results.md)。
复现：`python3 scripts/ts_fixed_analyze.py`。
主结果 CSV：`runs/ts_fixed_LB_CE_half/analysis_611/bd_rate_summary.csv`。

## 6. TS-004：目标与 QP 结构分析（非新编码）

### 固定候选达到 BCE 门槛所需的 B 类均值

| 模式 | BCE ≤−0.05% | BCE ≤−0.08% | BCE ≤−0.10% |
| --- | ---: | ---: | ---: |
| nopred | B ≤−0.0406% | B ≤−0.1126% | B ≤−0.1606% |
| gradient | B ≤−0.2385% | B ≤−0.3105% | B ≤−0.3585% |
| directional | B ≤−0.0687% | B ≤−0.1407% | B ≤−0.1887% |

这是条件计算，不是 B 类实测或预测。

### directional 的主要线索

原四点 PCHIP 曲线分段积分后，directional 在 QP22–27 对应区间平均 −0.1963%，
QP27–32 区间 −0.0439%，QP32–37 区间 +0.1508%，存在正负抵消。

冻结的探索性组合：名义 QP22/27 取整次 directional 编码点，QP32/37 取 Current anchor 点，
重新计算四点 BD-rate。CE **−0.0993%**，7/7 序列为负；排除 PartyScene 后仍为 −0.0722%。
同样的 NoPred 组合仅 −0.0525%，不优于全 QP NoPred，不继续增加这条规则。

**−0.0993% 是运行级 RD 点组合，不是已实现的 decoder-synchronous QP 自适应工具结果。**
规则看过 CE 后提出，CE 是发现集；不能据此宣称独立验证成功。
名义 QP 与实际 slice/TU QP 不同，不能直接实现 `sliceQP<=27` 并声称等价。

资料：[目标分析与下一轮设计](TS_Fixed_Predictor_Target_Analysis_and_Next_Experiment.md)。
复现：`python3 scripts/ts_fixed_deep_analysis.py`。
数据：`runs/ts_fixed_LB_CE_half/target_analysis/`。

## 7. TS-005：下一轮执行计划（待用户运行/回传）

### 冻结条件

- B：MarketPlace、RitualDance、Cactus、BasketballDrive、BQTerrace。
- HHI LBeu 半帧；分别 300、300、250、250、300 帧，脚本读取实际 INI。
- QP22/27/32/37，固定 nopred、directional，**新增 40 任务**。
- 不新增 gradient，不修改公式，不重跑完整 anchor，不只挑低 QP 或有利序列。
- 用同一 B 数据验证固定工具，以及已冻结的低两档 directional 组合；不在看到 B 后调切换点。

### 命令

```bash
python3 -u scripts/batch_test.py \
  --preset LBeu --class B,C,E \
  --qps 22,27,32,37 \
  --fixed-predictors nopred,directional \
  --encoder build/ts-fixed/bin/EncoderApp \
  --decoder build/ts-fixed/bin/DecoderApp \
  --decode-md5 --no-recon --jobs 10 \
  --input-dir /home/zhy/videos \
  --xlsm-template scripts/JVET-hhi.xlsm \
  --out-dir runs/ts_fixed_LB_CE_half
```

总计划 96，已有两模式 CE 56 个成功任务在 fingerprint 不变时跳过，新增 B 40 个。
保留原目录名称以复用 marker；不加 `--overwrite`、不加 `--full-sequence`。
结束后这两个模式的 Excel 汇总完整 BCE，各有 48 个 RD 点。

```bash
python3 scripts/ts_fixed_analyze.py \
  --run runs/ts_fixed_LB_CE_half \
  --classes B,C,E --modes nopred,directional \
  --anchor scripts/JVET-hhi.xlsm \
  --out runs/ts_fixed_LB_CE_half/analysis_BCE_611
```

### 完成后必须回填

- [ ] 各模式 B 20/20 完成，帧数、hash、marker 和 Excel 点值一致。
- [ ] 实际使用的二进制/配置/输入/anchor 身份与实验计划一致。
- [ ] B、C、E、BCE 的分量与 6:1:1 BD-rate，是否达到三个门槛。
- [ ] 低/高 QP 结构是否在 B 上复现；组合结果明确标记其性质。
- [ ] 最差序列、内容稳定性、是否出现实现或 anchor 对齐疑点。
- [ ] 决策：固定 NoPred、固定 directional、质量条件启用工具，或停止。

## 8. 关键更正与维护规则

| 事项 | 当前有效决定 |
| --- | --- |
| LB 完整帧还是半帧 | 用户确认本项目 CTC LB 为半帧，以 HHI INI 为准 |
| YUV 6:1:1 | 先分量 BD-rate 后加权；先加权 PSNR 的临时结果仅为 diagnostic，不用于主结论 |
| 条件 Oracle 的解释 | TSRC 固定-q 潜力，不能称为真实 BD-rate 或新编码器收益上限 |
| TS 选择偏差 | 最终 TS 样本有条件性；已以真实闭环固定工具实验补充，未量化分离偏差来源 |
| 小收益的工程意义 | 采用用户 −0.05/−0.08/−0.10% 门槛；同时独立报告稳定性与不确定性 |
| QP 组合 | 探索性复用已编码点，不是已实现的 slice/TU QP 启用工具 |
| Excel 写入时机 | 当前 batch 每组任务全部返回后立即写该组；共享任务池不停，重试后刷新，未变化组不重复写；早期“全部结束写表”记录仅对应旧版本 |

每轮更新本文件时应追加实验 ID 或状态变更，保存原结论适用范围，不把假设改写成实测。
记录配置、候选版本、样本集合、主指标、完整性证据、结果路径和下一步。
长跑开始不能标为完成；缺 B 数据不能给 BCE 实测结论；多次续跑应核对各模式 marker，
不能仅凭最新一次根目录 summary 判断整个实验完成。

### 更新历史

- 2026-09-28：按用户要求仅汇总R9，不作优劣、机制或后续计划分析。
  13份工作簿与按编号配对CSV共364/364个LB CE实测点（7序列×4QP×13组），无缺失/补点；Reference数值/状态与Current一致。
  91条序列曲线均可计算；分量独立PCHIP后6:1:1、七序列等权，与工作簿公式交叉差最大5.15e-13个百分点。
  更新 [结果台账](TS_Predictor_Results_Ledger.md)、[R9明细](results/r9.md) 及统一CSV/来源记录；旧57组明细和汇总数值逐行不变。
  导出脚本新增R9身份/编号配对，38项相关测试通过。未修改编码源码、原始工作簿/CSV，未启动编码；表内pass不代替远端身份/hash核验。

- 2026-09-27：按用户要求扩展可查询的逐序列/逐QP明细，生成 `docs/experiments/results/` 的9轮Markdown、3份CSV和来源核验记录；
  57组方法、469条实验/配置/序列、1876个QP记录（1860实测、14历史anchor补点、2缺失），466条可计算BD曲线。
  Current分量独立PCHIP后6:1:1加权，和工作簿公式独立转写的最大差4.23e-13个百分点。
  R2-4已补齐PartyScene QP22，CE更新为−0.005667%；新增R6-2 B/BCE及R3-1 AI/RA数值登记。
  R3-1 RA MarketPlace QP22缺失不补，BasketballDrive QP37的Current参考为MD5 fail，均不计算对应序列BD。
  R8全24组现已本地复算，不再仅转录外部报告。新增只读导出脚本和13项测试；源表/CSV未修改，未启动编码。

- 2026-09-27：建立 [实验结果台账](TS_Predictor_Results_Ledger.md)，补录固定/条件/R2～R8 共57组方法及已有B/BCE、RA CD数值；
  只记录实验、结果、来源和数据状态，不加入分析。R3-1采用已补齐B的2026-09-24结果；
  R8新增17组按用户上传报告转录，明确未在本轮复算，23/24补点保留标记；R9仍待正式结果。
  未修改源码、工作簿、原始CSV或外部原稿，未启动编码。

- 2026-09-27：文档归档整理。项目设计/实现/验收/分析和本台账集中至 `docs/experiments/`，
  用户外部原稿移至 `docs/external_inputs/` 并保留原文；增加目录索引，同步脚本说明和结果目录README链接。
  源码、运行脚本、结果工作簿及 `experiments/` / `runs/` 数据路径均不变，没有新增编码或分析结论。

- 2026-09-27：按 [R9_Experiment_Plan.md](../external_inputs/R9_Experiment_Plan.md) 完成R9全部13个配置，旧58模式编号和算法保持。
  TypeDef直接选R9_MODE（默认0），新旧互斥与运行时覆盖保留；各组数字目录/metadata/manifest已建。
  7/8共享(p,k)贯通RDOQ、Writer、Reader和回放；9/10只验证同CG已知目标且用其自身分类的入口CF10。
  11/12保留完整q0，独立D/U提案由相同owner入口评估，严格J改善才接受；暂拒绝TU-CBF翻转和联合色度编辑。
  100项Python测试、10,400项独立公式对照、13组原生CABAC/因果测试通过；量化测试每组256次，D/DU提案hash相同。
  259项人工短测全部解码hash通过，58旧模式bit-exact，6case master-OFF同流，13组禁TS/关统计同流；8,498条两端CG trace相同。
  13组均有相对基础的码流活动，但1/2/6仅在人工QP0出现；推荐先做固定内容8帧活动预检，不据此调公式。
  11/12最终编辑分别D4和D4/U6；大量owner获胜未最终提交，搜索与真实Writer计数已分开。
  复用原批量共享队列/无重建/resume/逐组即时写表；阶段I dry-run196点、短测56点通过。
  未运行正式CTC、未改工作簿；文档 [TS_Predictor_R9_Implementation.md](TS_Predictor_R9_Implementation.md) / [TS_Predictor_R9_Validation.md](TS_Predictor_R9_Validation.md)，证据 `runs/ts_r9_smoke_final/`。

- 2026-09-26：按“先将剩余的几个实验代码都设计完成”，补齐R8剩余16组，MODE 1..24全部可运行。
  原八组冻结公式不变，旧policy编号不重排；TypeDef直接选MODE，默认0=Current，旧轮互斥/参数覆盖保留。
  22使用TU-local最终CG路径权重，私有原生预算回放；23/24在Intra/Inter owner层成对完整局部RD比较，非仅扩大RDOQ搜索。
  新增独立search聚合及解析，区分试编码q变化与最终Writer；各组数字目录、manifest、说明同步。
  95项Python测试通过；全部24组native CABAC/因果测试通过；新增6888公式对照，旧24672对照仍通过。
  288项人工闭环hash通过，旧34模式bit-exact，24组关统计/禁TS同流，六case新旧master-OFF同流；历史168份共享码流未变。
  15874个两端CG trace和619个C02权重记录相同；原生量化压力测试23/24各512次、各300次q改变。
  人工编码23/24分别391/2185次试编码q改变、217/1423次q1局部获胜，但六case最终码流均与父法相同；先真实活动短测，不据此宣称BD收益。
  剩余16组LB CE dry-run448点；23/24配对预检dry-run32点。未启动正式CTC、未改源表；原首八组批量默认清单不变。
  详见TS_Predictor_R8_All24_Implementation.md，证据runs/ts_r8_all_smoke_final/；正式baseline仍Current。

- 2026-09-26：只读核验R8七组LB CE（1/4/8/13/15/16/17），各28/28点、无QP22补点；
  CSV与工作簿B–J一致，完整Reference与Current一致，公式交叉验证差<4.24e−13个百分点，源表SHA不变。
  Y/U/V各自BD后6:1:1、七序列等权；CE依次−0.004577/−0.043397/−0.029361/+0.050328/
  −0.053966/−0.027349/+0.056429%。均未超过R3-1的−0.093288%；R8-19未纳入。
  直接父法重积分及四曲线共同质量区间证实稀疏×guard、稀疏×候选补全的闭环交互，不做BD百分比直接相减。
  4/15的Y优于R3但UV抵消，去掉PartyScene后对R3约持平；此诊断不改变正式七序列平均。
  七组低质量段均退化；13固定混合与17当前minimax降优先级，其余Weak，暂不七组全扩B。
  没有服务器宏/配置/帧数/解码hash/活动日志，不能由表格推断TU尺寸、n或复杂度；未改算法、未启动编码。
  报告TS_Predictor_R8_First7_Results_20260926.md；复算scripts/ts_r8_results_analysis.py，派生runs/ts_r8_results_20260926/。

- 2026-09-25：按“开始实现”接入R8首批八组，沿用R8-DESIGN-20260925-v2公式与公开编号。
  TsR8Prediction使用int64固定数组、有限幅值成本预计算；RDOQ/Writer/Reader统一CG入口冻结评分；
  原RDOQ搜索、CG全零判断、正式syntax及BDPCM路径不变。新增最终Writer聚合与可选CG trace。
  TypeDef.h直接选模式，默认0=Current，旧轮互斥，未实现编号报错；batch支持显式覆盖。
  新增LB CE/真实短测包装脚本，dry-run分别224/96项；跨组共享池、逐组写表、半帧、无重建、resume保留。
  人工验证与精确数量见TS_Predictor_R8_Validation.md；尚无正式CTC或R8 BD-rate，不据活动宣称收益。

- 2026-09-25：按“选择8组合适的实验先开始设计”将R8首轮固定为A01/A04/A08/B01/B03/B04/B05/B07，
  公开MODE 1/4/8/13/15/16/17/19不重新编号。版本R8-DESIGN-20260925-v2替代旧首批10组安排，不叠加运行。
  B04提前使候选覆盖×稀疏的四角闭合，并为B07提供同样完整候选的未平滑父法；A09/A10/A11暂缓。
  首轮全YUV、原生TS尺寸、旧量化搜索规则；固定CF10与1:1混合/1:2:1平滑，无新增阈值扫描。
  新增TS_Predictor_R8_First8_Design.md，manifest/收件README/空白元数据版本同步，24组原公式与目录数字不变。
  新数学参考脚本30720次合成决策检查通过，八组均有相对主父法的映射差异反例；不是CTC可达性或收益证据。
  全部84项TS Python测试通过，其中10项R8设计检查，含主父对照/manifest一致性与拒绝分支边界。
  计划短测含四对照96点、完整LB CE新增224点；未修改TypeDef/codec/batch、未编译或编码，不提供伪R8运行命令。

- 2026-09-25：依据用户提供的R8探索计划完成TS-015实施规格，保留A12+B8+C4共24组，
  公开R8_MODE预留1..24，目录统一带对应数字；所有状态明确为not_implemented，未修改TypeDef/codec/batch。
  首批10组分1a六组与1b四组；17帧四序列QP22/37作工程预检，正式CE半帧28点/组，全部上限672点。
  明确P1/Psmooth覆盖、minimax固定候选集、C02最终CG路径更新和C03/4所属搜索层成对RD的同步/回滚要求。
  根据现有代码明确放宽up条件仍最多3候选，无需新增槽位；不把Inter residual SSE一概称像素重建SSE。
  新增数学参考脚本，1287原/1287平滑多重集合覆盖及1287个minimax检查通过，另验证边界、逆映射、候选上界；
  这些不是C++/CABAC/BD验证。探索文档引用的分析/测试附件本地未找到，本次独立核验而非引用其完成声明。
  设计见TS_Predictor_R8_Experiment_Design.md，规格scripts/ts_r8_experiment_manifest.json，目录experiments/ts_predictor_r8/。
  全部79项TS Python测试通过（新增5项设计检查）；未启动R8 smoke/CTC或声称获得新BD收益。

- 2026-09-25：为R8设计复算TS-014已收到的两组R7 LB CE表，各28/28实测、无补点，CSV B–J一致，
  相关CE Reference同Current，所有输入SHA读前读后不变；不核验或使用其它配置结果。
  分量BD后6:1:1、七序列等权：R7-1 −0.070549%，R7-2 −0.017510%；直接对R3分别+0.023403%/+0.076633%。
  R7-1直接对R2-2 −0.036119%，R7-2直接对R7-1 +0.054503%，支持继续研究评分×接受规则，而非宣称guard普遍有害。
  R7-1的5/7改善和更低中位数未转化为超越R3的CE均值；保持Weak增量判断，旧“CTC未收到”状态更新。
  复算scripts/ts_r7_results_for_r8.py，报告TS_Predictor_R7_Evidence_for_R8.md；远端模式/帧数/hash仍不能由表格确认。

- 2026-09-24：按用户要求将TS-014正式命名R7。TypeDef.h新增R7_MODE/R7_SHADOW主名称，
  原RATE宏保留兼容别名、冲突时报错；所有TS实验宏/取值已标明对应历史轮次及具体规则。
  R7-1明确对应原R2-2，R7-2明确对应原R3-1(YUV)，不是原R3-2；runtime名称和统计schema不变。
  新收件目录`experiments/ts_predictor_r7/{r7_1_raw,r7_2_guard,shadow_r3}`；batch新目录带R7公开编号，
  旧rate目录原地resume，多路径歧义报错，不移动结果、不改变算法/已有数值。新增R7说明入口。
  `build/ts-r7`编译通过；宏10项、batch20项、shadow解析4项及三模式native测试通过；
  36项smoke全部解码hash通过，码流与重命名前逐项SHA256一致，记录`runs/ts_r7_naming_smoke/`；未跑正式CTC。

- 2026-09-24：TS-014按用户新请求先研究syntaxCost，暂停原Y稀疏覆盖草案的实现优先级。
  确认旧代理等价完整regular幅值路径的等概率bin数，Rice长度本身没有发现公式错误；
  新CG-entry冻结真实CABAC表避免Writer第一遍/Reader第三遍即时context不一致，Q15评分，候选/guard不变。
  RDOQ私有context仅在CG清零RD完成后回放更新，原xGetICRateTS不改；新增rate_raw/rate_guard，RATE_MODE=1/2。
  三条预定序列LB22/37各3帧，6/6解码通过，全部shadow码流与旧R3 SHA256一致。
  最终Writer 5,614 CG、1,644 eligible位置；raw winner分歧29.32%、guard实际映射分歧6.93%；
  成本差MAE 0.8734→0.5225 bit，排序反转14.69%→11.13%，但new raw对old raw条件率仍+0.009067%。
  cutoff2区域指出路径误差，事后path诊断仅用于定位、未部署；new NoPred winner绕过guard的诊断未支持扩组。
  42项短测全部hash通过，Current/R3/OFF对保留程序bit-exact；3模式各160 native TU同步/上下文/因果测试通过。
  新旧宏默认/覆盖/互斥9项、batch18项、shadow解析4项通过；默认仍Current，不改既有实验数据或anchor。
  报告[TS_Predictor_Rate_Shadow_Results_20260924.md](TS_Predictor_Rate_Shadow_Results_20260924.md)，源码说明[TS_Predictor_Rate_Estimator_Study.md](TS_Predictor_Rate_Estimator_Study.md)；
  数据`runs/ts_rate_shadow_audit/analysis/`。算法增量暂Weak，先同内容自然短测，最多两组完整CE；不声称BD收益。

- 2026-09-24：TS-013收到R6七组完整LB CE共196个实测点；根目录R6_1..7 CSV的B–J列均与对应XLSM一致，
  Reference全同Current。未补点、未移动源文件，排除Excel临时锁文件；没有远端模式/帧数/hash/TS_R6_STATS，不能认证运行身份或TU-size机制。
  按分量先BD后6:1:1、七序列等权，七组直接对R3增量依次为
  +0.080790/+0.001946/+0.067784/+0.086792/+0.045027/+0.064466/+0.076878%，均值/中位数均正，序列bootstrap CI均跨0。
  R6-2去KristenAndSara后+0.086339%，近零均值依赖强收益单序列；Current不对称存在但未证实是应去除的RD缺陷。
  R6-6/7直接对5为+0.019546/+0.032148%，保留max；R6-5 Y为−0.010822%、5/7好，但UV退化使总增量+0.045027%，
  Y高质量区间仍+0.014915%，因此只提出Weak的“仅Y新增稀疏覆盖、UV和稠密继续原R3”验证，不拼接分量曲线预测组合收益。
  七组未通过原冻结B门槛，停止扩大本轮B/RA；2保留Weak诊断，其余本轮新增RD价值Negative，不宣称统计证明全域有害。
  同时复核TS-010：R3-1 B现已20/20实测，B−0.050647%、完整BCE−0.075521%，替代旧补点暂估−0.075273%，
  达到−0.05%目标，距−0.08%差0.004479个百分点；去Party为−0.039751%，来源核验仍待完成。
  R3-1工作簿另有83个非LB点，本轮未分析；R3-2旧缺点结论未更新。
  报告TS_Predictor_R6_LB_CE_Results_20260924.md；下一步设计TS_Predictor_Post_R6_Plan_20260924.md；
  复算scripts/ts_r6_results_analysis.py，输出runs/ts_r6_results_20260924，输入SHA前后不变，工作簿公式差≤3.41e-13个百分点。
  本次只新增分析脚本/测试、报告和计划，未改codec/宏/批量编码脚本，未执行编码。

- 2026-09-23：TS-013实现R6-20260923-v1，针对用户提出的两个问题拆成七组，原R3/R4/R5保持不变。
  确认n是五个因果位置的非零数量，重复幅值计数；Current非零必有匹配，但其它样本幅值候选也有。
  指出sum(cost)-min(cost)对匹配候选都只减1，不能消除样本内优势；保留模式3诊断，模式4统一以identity成本归一、删最大正节省贡献。
  模式1/2只改n≥3的fallback，模式5/6/7只改n<3；无组合、无QP/分量特例、无阈值扫描。
  新TypeDef.h R6_MODE=0..7及新旧互斥；共享公共预测入口、无持久状态；stderr最终Writer活动按n/LU/拒绝原因分解。
  模板458752项、宽幅值因果/符号89600项、原生CABAC每组240TU通过；166项合成短测hash/trace通过，
  Current/OFF各13例对anchor bit-exact，25旧模式QP0回归、7组关闭统计一致；七组均有相对R3实际映射变化。
  7宏/18调度/19基础BD测试通过；84项首批LB CE半帧仅dry-run。共享池/逐组XLSM和6:1:1分析复用原脚本。
  BasketballDrill LB QP22三帧9项通过hash，七组相对R3映射改变171/81/45/138/312/312/317次，七组码流均与R3不同；
  mean/min的LU分支分别2/6次实际映射变化。具体覆盖见TS_Predictor_R6_Validation.md，不用单QP短帧计算BD-rate。
  未启动完整CTC，未修改服务器结果或Current Reference；交付master=1、所有模式0，默认Current。

- 2026-09-23：收到R5-1/2完整LB CE结果，各28点，无补点；各CSV的B–J列与对应工作簿一致，Reference均为Current。
  两组各112个RD标量全同R3-1/R4-3，CE分量BD后6:1:1、七序列等权均−0.093288%，直接对R3增量0。
  R5-2工作簿目前位于ts_predictor_r5根目录，按配套R5_2.csv归属，未移动文件。
  唯一BasketballDrill QP22日志确认R5-1宏默认、版本、250帧和解码hash；没有TS_R5_STATS、R5-2日志或配对码流SHA，
  不能把表格一致称为远端bit-exact，也不能断言新增分支触发为0。日志计时与CSV不同，不作为完整任务manifest。
  本轮新增RD价值Negative，停止扩大两组B/RA长跑；保留原R3-1，不调阈值追求差异。
  见TS_Predictor_R5_LB_CE_Results_20260923.md。本次未修改算法、结果源表或启动编码。

- 2026-09-21：按“继续优化R3_1”实现TS-012两个独立变体，R5-20260921-v1：
  R5-1按H优先/G次优排序原候选；R5-2仅在因果回看证明Current有稳健优势时否决原R3。
  原R3/R4公式、旧二进制及结果不变；TypeDef.h新增R5_MODE=0/1/2，新旧宏互斥；交付master=1、所有模式0。
  共享RDOQ/Writer/Reader纯预测入口，无符号依赖、无持久q或CG状态；最终Writer独立聚合增量活动。
  复用原batch共享池/分组即时XLSM，无重建；编号目录和revision=r5基础分析/活动提取完成。
  3,145,728个小幅值模板与384000个网格目标/模式检查通过，但R5-1重排原R3已接受winner计数0，
  上述测试与R4-3逐项比较也无预测差异（不是全域等价证明），不能把潜在代码路径当有效机制；R5-2人工网格仅否决3次。
  两组各240个人工TU原生CABAC往返与因果检查通过，专门加入regular路径的rescue/veto样例；未改公式追求活动。
  351项合成短帧hash/trace通过，Current/OFF各13例对anchor bit-exact；2项stats-off及23项旧模式回归通过。
  两组13个case全同R3-1、相对R3实际映射0；真实BasketballDrill LB QP22三帧4组hash通过，也全同R3-1。
  **当前不建议两组完整CTC**：R5-1增量依据弱，R5-2真实活动不足；只有正确性结论，没有BD收益结论。
  设计/使用/验证见 `TS_Predictor_R5_*.md`，输出 `runs/ts_r5_smoke/`、`runs/ts_r5_real_preflight/`；
  收件骨架 `experiments/ts_predictor_r5/r5_<MODE>_<name>/{LB_CE,LB_B,RA_CD}`。
  6项宏、16项batch、15项基础分析通过；56项半帧CE计划仅dry-run，不启动正式编码、不生成空白结果表。

- 2026-09-21：收到R3-1/2 B CSV及更新工作簿，分别16/20、17/20点；CE仍完整。
  仅按本次授权用对应Current完整RD点暂代七个缺失B QP22，不改源文件。R3-1/2 B暂估
  −0.050053%/−0.042531%，BCE十二序列等权−0.075273%/−0.063619%，暂过−0.05%目标。
  R3-1距−0.08%还差0.004727个百分点；评级Promising（暂定），优先补点与来源核验，不认证正式达标。
  无QP22的实测三点B诊断仍−0.045677%/−0.044127%，两组B的Y均值为正、色度贡献较大。
  R3-1去Party的BCE十一序列−0.039481%*，收益并非只来自Party，但达标幅度仍受它影响。
  R3-2为Weak分量对照；关闭色度predictor不保证色度BD不变，不据分量表推断直接因果。
  R4六组CE168/168点完整、CSV与表格匹配、Reference同Current。R4-3的28个RD点全同R3-1，
  不冒充码流bit-exact/活动已验证；其他五组均值均不如R3-1。R4-5改善RaceHorsesC/Kristen，
  但削弱Party、恶化BQMall，共同低质量区间退步；六组无一通过事先冻结门槛，不建议全铺B/RA。
  报告 [TS_Predictor_R3B_R4_Results_20260921.md](TS_Predictor_R3B_R4_Results_20260921.md)；复算脚本 `scripts/ts_r34_results_analysis.py`，
  数据 `runs/ts_r34_results_20260921/`；默认严格，显式 `--impute-r3-b-qp22` 才允许本次补点。
  新增9项、连同既有分析23项测试通过；独立VBA最大差2.97e-13个百分点，所有源SHA未变。
  只有结果表，远端模式/半帧/配置/hash/活动与复杂度仍不可独立验证；未修改算法或运行编码。

- 2026-09-20：按用户要求将R4六个收件文件夹改为 `r4_1_identity_only`、`r4_2_magnitude_only`、
  `r4_3_guard_rescue`、`r4_4_directional_risk`、`r4_5_causal_models`、`r4_6_signed_plane`。
  后续新轮次统一“轮次＋对应MODE宏值＋方法名”，数字使用公开宏1..6，不使用内部policy17..22。
  `ts_predictor_naming.py`统一映射，batch新任务/summary/XLSM与分析器同步；运行mode字符串和算法均不变。
  已有无编号运行目录保持续跑兼容，新旧目录并存则报错，避免静默选错数据；未搬移旧短测结果、未重编码。
  调度/编号/表格测试14项、分析新旧/flat目录测试11项通过。

- 2026-09-20：按“开始设计代码”实施TS-011全部六组，冻结R4-20260920-v2公式不变。
  TypeDef.h新增R4_MODE=0..6，与所有旧模式互斥、macro-OFF误配置报错；交付master=1、全部模式=0，即Current。
  TsR4Prediction.h实现六个无状态局部规则；复用RDOQ/Writer公共入口；Reader SP使用已解码sign的只读视图，
  不改语法、不提前改写coeff、不使用encoder-only信息、不维护跨TU历史或依赖q的持久缓存。
  TsR4Stats.h只在最终Writer聚合；新增相对Current/R3的实际映射差异、分支类别、方向/专家/符号等机制计数。
  batch只增加六个mode，复用共享池/逐组写表/无重建；activity及基础BD分析加revision=r4，分量BD后6:1:1不变。
  独立ON/OFF构建成功；325项2帧合成回归hash/trace通过，Current/OFF各13项对旧anchor bit-exact，
  另6项统计OFF bit-exact，17项旧模式对保留R3程序bit-exact。旧R3/anchor SHA未变，头文件master已恢复1。
  每组240个人工TU原生CABAC往返、2254CG、35476次扫描因果/符号视图检查通过，包括C的有效rescue手工反例。
  3145728核心原型组合、32000扩展原型目标与生产公式一致；宏6项、调度11项、BD分析9项测试通过。
  合成最终Writer中R4-3补查1398次、接受1次却相对R3映射改变0，不能把继承R3的77次作用冒充新增覆盖。
  本地另作BasketballDrill/LBeu/QP22/2帧的8组限量预检，8/8成功且hash通过，335行聚合数据，
  不写XLSM、不输出重建、不作RD结论。R4-4/5/6相对R3映射改变5/6/1，码流均不同；
  R4-2与Current同流且对Current映射改变0，R4-3与R3同流且补查159/接受0，仍需更广真实覆盖。
  核对本地输入前两帧数据相同、第三帧不同，不能把此两帧预检当作充分运动验证；未据此改冻结公式。
  实现与验证文档 [TS_Predictor_R4_Implementation.md](TS_Predictor_R4_Implementation.md)、[TS_Predictor_R4_Validation.md](TS_Predictor_R4_Validation.md)；结果在 `runs/ts_r4_smoke/`。
  正式CTC、BCE收益、复杂度和四序列四QP预检尚未完成，未替换任何服务器R3数据或正式anchor。

- 2026-09-20：按用户要求在原三组外增加非消融方法，冻结R4-20260920-v2，R4-1/2/3公式不变。
  数据显示固定directional与R3在不同内容上互补，但不能据序列级表格声称局部赢家可识别；
  BQMall/Kristen的中低质量退化支持检验更好的局部评分，而不是增加序列/QP特例。
  R4-4 DR以1/2方向权重重算风险、删除整个加权位置贡献；R4-5 CB回看历史位置自身的因果预测，
  在R3/Current/NoPred/directional间选择；R4-6 SP引入带符号clipped plane，并由相同因果回看保护，低优先级。
  三组独立，不叠加R4-3补查；只作逐系数局部自适应，不冒充原始整CG历史选择问题已解决。
  Reader的sign要到第三遍结束才写回coeff，SP未来实现需只读sign视图，不能直接读取尚未恢复的数组符号。
  新设计 [TS_Predictor_R4_NonAblation_Extension.md](TS_Predictor_R4_NonAblation_Extension.md)；原型 `scripts/ts_r4_extension_design_check.cpp`
  复用真实R3/remapping/cost，在32000个人工目标上通过保护、边界、当前/未来及自身目标污染、signed范围检查。
  三组映射差异184/6569/7342只是非等价人工例子，不是CTC活动率/收益；尚未验证真实Reader多遍或闭环RD。
  新收件目录已建立；原84项CE外，优先4/5共56项、6另28项；全六组168项，合计最多一组扩展52项，上限220。
  Current唯一正式anchor、R3-1增量对照、LB半帧、分量BD后6:1:1；CE开发集，不冒称独立验证。
  本次未改codec/TypeDef.h/CMake/batch、未覆盖编解码程序或原结果、未启动编码，R3后续测试保持原样。

- 2026-09-20：用户说明R3后续数据仍需等待，要求先基于现有结果设计新实验。
  冻结R4-20260920-v1三组：I/M分别保留R3-1已接受的identity/非identity分支，不重新搜索删减后的候选；
  C保持R3已接受预测，仅在R3拒绝原winner后补查原集合内其他H>0候选，按H/G/identity/较小幅值定序。
  沿用n>=3、G−最大正贡献>0、语法代理cost和YUV范围，不新增QP门槛、不继续扩CG历史/跨TU状态。
  原代码成本例子[L,U,D,LL,UU]=[2,1,10,1,1]、Rice=1：原winner10的G=5/H=−2被拒绝，
  但NoPred有G=4/H=2，构成补查与R3非等价的结构性反例，不是实际收益证据。
  独立代数程序复用真实函数，3,145,728人工模板/Rice组合通过分支分解/接受保持/保护条件检查，2520组合出现rescue。
  文档 [TS_Predictor_R4_Experiment_Design.md](TS_Predictor_R4_Experiment_Design.md)，程序 `scripts/ts_r4_design_check.cpp`，收件目录 `experiments/ts_predictor_r4/`。
  计划LB CE三组84项，最多一个候选经门槛进入RA/B；只是设计，未改codec、宏、CMake、batch或已运行二进制，未启动编码。
  R3继续按原版本测试，后续结果不据此追溯改写；新组只用Current作正式anchor，R3-1/NoPred作为增量/辅助比较。

- 2026-09-20：TS-010收到四组服务器LB CE完整结果，共112个实测点，无填补。
  四份主表Reference与Current一致，配套CSV全部RD点一致；R3-1另有E_.xlsm，规范化标签后Test与主表相同，
  但其他RA/LP Reference有差异，只审计不纳入主计算、不替换anchor。源文件SHA前后不变。
  主口径分量PCHIP后6:1:1、CE七序列等权：RG/RGY/NG/NGY为−0.093288/−0.078682/−0.011663/−0.014754%。
  前两组中位数均−0.082512%，去PartyScene仍−0.030671/−0.032475%；后两组中位数+0.010799%，
  去PartyScene为+0.044599/+0.043040%，未通过冻结的扩展数值门槛。
  R3-1在三方共同质量范围对R2-R低质量改善−0.095395个百分点、高质量收益保留183.8%；
  NG/NGY高质量只保留42.0%/45.9%，低质量减损未转化为稳定净增量。R3-1/2的E全部12点相同，
  因此色度回退本身未消除KristenAndSara退化；不据表格声称bit-exact、CG覆盖或因果机制已经确认。
  R3-1对R2-R、NoPred、directional直接配对BD分别−0.058082/−0.035511/−0.055210%，配对CI仍跨0。
  总体正式评级仍Weak；局部保护优先保留R3-1，历史保护本规则的扩展证据Negative。按协议先核验日志再RA CD，
  RA通过后LB B；不同时扩大同族两组、不调整公式/阈值。R3-1达到BCE−0.05%所需B均值≤+0.01060%，仅为条件计算。
  报告 [TS_Predictor_R3_LB_CE_Results_20260920.md](TS_Predictor_R3_LB_CE_Results_20260920.md)，复算 `scripts/ts_r3_results_analysis.py`，
  输出 `runs/ts_r3_results_20260920/{base,detail}/`；新增共同区间3测试、旧跨轮3测试、分析6测试通过。
  本次只分析，未启动任何编码、未改codec/宏/源表；没有B/RA、复杂度、Oracle/η、TU尺寸/CG活动实测结论。

- 2026-09-19：按“开始修改算法/继续”实施TS-010四组R3，保持R3-20260919-v1公式不变。
  TypeDef.h新增R3_MODE=0..4，与旧实验默认模式互斥；master=1、所有模式=0交付，默认Current。
  统一预测和最终CG更新路径同时服务TS-RDOQ/Writer/Reader；Y-only不学习色度历史，全零CG清除近期证据。
  247项两帧smoke全部解码hash通过，Current/master-OFF对保留anchor bit-exact；4项统计关闭、13项旧模式回归通过。
  四模式各6587个CG/104192次因果预测检查通过，覆盖CG1启用、空CG后禁用和未来系数污染；
  64种原生scan形状1267924项邻居检查通过；原Current/NoPred fractional回放及R2-N/F状态测试保持通过。
  Python宏/调度/分析分别6/10/6项通过。batch仅扩展四个名字，共享池/逐组写表保持；112项LB CE半帧dry-run通过。
  新构建使用 `build/ts-r3/`、`build/ts-r3-off/`；保留的旧build目录二进制未变。
  初次构建曾更新顶层bin/lib构建产物，随后改为隔离目录；请勿将顶层默认程序当作已记录旧实验程序续跑。
  验证 `runs/ts_r3_smoke/validation.json`，文档 [TS_Predictor_R3_Implementation.md](TS_Predictor_R3_Implementation.md)、[TS_Predictor_R3_Validation.md](TS_Predictor_R3_Validation.md)。
  真实序列短帧预检尚未做（默认输入路径缺文件）；未运行正式CTC、未写新结果XLSM或改Current Reference。
  1790行聚合仅是合成输入最终TS条件活动统计；不能解释为BD-rate或对选择偏差的消除证明。

- 2026-09-19：TS-010按跨轮分析设计四组R3，文档 [TS_Predictor_R3_Experiment_Design.md](TS_Predictor_R3_Experiment_Design.md)。
  RG沿用R2-R的模板/cost/winner，仅在固定候选优势G减去最大正贡献B仍>0时离开Current；RGY仅Y启用。
  NG保留R2-N的log代理与EWMA，仅S>0且紧邻上一最终CG的G−B>0时选NoPred；NGY仅Y启用。
  CG0 Current，全零/无有效历史CG清除近期通过证据，不等待两个历史CG，不跨TU；不新增QP阈值。
  四组用来检验小样本/旧证据保护与色度介入范围，不将“删一贡献”称为置信界或交叉验证。
  首轮LB CE半帧四QP112项；最多两组按预设完整CE/质量区间/活动条件进入RA CD，再判断LB B；
  Current是唯一正式anchor，不全套重跑，未生成结果。收件目录 `experiments/ts_predictor_r3/` 已建，仅README占位。
  少量代数例子检查通过，不是codec验证；未添加R3宏/模式，未修改算法、批量脚本或二进制。

- 2026-09-19：TS-009完成固定三组、revision1五组、R2四组跨轮多维分析，未启动编码或修改codec。
  重新读取12份工作簿、461个实测点；沿用既有授权填补缺失QP22，117条可计算曲线复现既有结果，最大差0。
  新增原四点PCHIP的三质量区间分解：R2-N高质量QP22–27对应区间−0.162250%、7/7改善，
  低质量QP32–37对应区间+0.152004%；R2-R对应−0.100019%/+0.051711%。这些不是实际QP门控工具结果。
  BQMall在12种方案整曲线上均退化，但多个方法在高质量区间改善；
  R2-N/F的U均值损失高度集中在KristenAndSara，不能泛称U在多数序列失败。
  R2-N直接相对固定NoPred为+0.044680%（完整CE），证明当前历史选择尚无稳定增量；NoPred仍仅辅助对照。
  B收益集中于Cactus且该序列主要是色度收益；RA的改善也集中，不能从class均值推断分辨率或TU尺寸因果效应。
  报告 [TS_Predictor_Cross_Round_Analysis_20260919.md](TS_Predictor_Cross_Round_Analysis_20260919.md)，脚本 `scripts/ts_predictor_cross_round_analysis.py`，
  输出 `runs/ts_cross_round_20260919/`。三个新增数值测试及全部分段积分重建检查通过，源表SHA不变。
  结论仍Weak；优先补点和定位中低质量失效机制，不依据本次探索性分解反复调阈值。

- 2026-09-19：TS-008接收四组服务器LB CE结果（只分析结果文件，不检查本地编码程序、不重新编码）。
  四份Reference与Current一致，111个实测RD点与配套CSV一致；按用户要求仅把实验4 PartyScene QP22
  的完整RD点用Current暂代，不修改源表。实验1/2/3/4 CE分别为+0.068593%/−0.033694%/−0.011639%/−0.004392%*。
  去掉PartyScene共同六序列分别+0.114901%/+0.007916%/+0.045488%/+0.019731%，均为正；CE bootstrap CI均跨0。
  评级：1 Negative（本CE）、2 Weak且本轮优先、3 Weak、4 Weak/接近零且补点敏感。没有本轮BCE/RA结论。
  实验4完整六序列直接相对实验3改善约−0.024784%，但不稳定，不能据暂估七序列断言复杂评分必然更差。
  先补唯一缺点，不建议四组直接铺开B；不修改公式/阈值。报告 [TS_Predictor_R2_LB_CE_Results_20260919.md](TS_Predictor_R2_LB_CE_Results_20260919.md)，
  可复算输出 `runs/ts_r2_partial_20260919/`。远端编译宏、实际帧数、hash及内部切换不由表格独立认证。

- 2026-09-18：TS-008四组R2实现完成：r2_modal/r2_risk/r2_cn_log/r2_cn_frac，
  共用RDOQ/Writer/Reader入口，TU-local最终CG更新；F使用独立虚拟CABAC，真实上下文只做最终Writer观察。
  TypeDef.h新增R2模式0..4，新旧宏互斥；取消CMake对master的覆盖，误请求实验不再静默Current。
  交付默认master=1、所有模式宏=0，仍为Current。原batch支持四模式，保留共享池/无重建/分组即时写表。
  原生评分对照Current/NoPred各6014个CG零fractional差异，N/F各5718个未来污染/状态检查；
  110项两帧smoke全部hash通过，Current/OFF对旧anchor bit-exact，4项关闭统计及3项旧固定回归通过。
  6宏+9调度+3分析测试通过；645行在线活动汇总不是RD结论。
  新说明 [TS_Predictor_R2_Implementation.md](TS_Predictor_R2_Implementation.md)、[TS_Predictor_R2_Validation.md](TS_Predictor_R2_Validation.md)，结果目录状态已同步。
  LB CE dry-run112项半帧确认；RAeu默认64/32帧单段，外部RA anchor帧数/分段未确认前不能正式比较。
  未运行正式CTC、未生成新正式结果工作簿、未改anchor Reference、未覆盖旧实验二进制。

- 2026-09-18：按用户要求明确R2唯一正式anchor仍为Current，保留原Reference。
  更正此前将NoPred列为“必需基线”的措辞；NoPred保留候选/辅助对照身份。
  取消“不差于NoPred”的B准入硬门槛，正式收益与推广门槛均对Current；
  方法间配对分析仅作复杂度/增量诊断。已同步协议、初版设计、目录说明与元数据模板，未改codec或结果表。

- 2026-09-18：TS-008形成完整R2协议 [TS_Predictor_R2_Experiment_Protocol.md](TS_Predictor_R2_Experiment_Protocol.md)：
  M严格多数幅值、R含NoPred的局部成本最小、N原A2评分的Current/NoPred、F同候选虚拟CABAC评分。
  候选替换与评分升级分开对照；共同使用可用因果邻居，避免旧设计对窄矩形的整窗口限制。
  计划CE28+RA CD32项/组、四组共240项，B仅按预设条件最多两组追加40项。
  宏优先、误配置不得静默Current、完整数据判定、直接相对NoPred BD-rate、作用覆盖与decoder开销纳入规范。
  结果目录骨架 `experiments/ts_predictor_r2/` 已建立；**仍仅设计，未修改codec、未新增可运行模式或启动编码**。

- 2026-09-18：新增revision2设计 [TS_Predictor_Revision2_Design.md](TS_Predictor_Revision2_Design.md)（仅设计、未实现）：
  R2-1因果邻域离散众数；R2-2以TSRC语法成本近似最小化局部remapping风险；
  R2-3保持Current/directional与原A2更新规则，仅将历史评价换成TU-local确定性虚拟CABAC双分支评分。
  不修改正在收集结果的revision1，不预设正收益，不增加QP/分量专用阈值；
  三候选历史组合仅在前置证据成立后考虑。未来宏优先源码控制的用户偏好已纳入设计。

- 2026-09-18：接收TS-006五组LB CE初步表格，实际130/140点；缺9个QP22、A3 PartyScene QP27。
  按用户要求仅用对应anchor替代缺失QP22；不补QP27，A3排除PartyScene。
  N1/N2完整CE为+0.030428%/+0.043798%；A1/A2补点暂估−0.017523%/−0.005227%；
  A3为6序列子集+0.022220%，不可当完整CE比较。去除PartyScene的共同6序列五组均退化。
  源表/CSV数值一致、Reference与原anchor一致，但没有远端模式/配置/hash日志核实；RD点相同不等于码流bit-exact。
  报告 [TS_Conditional_Predictor_Preliminary_Results_20260918.md](TS_Conditional_Predictor_Preliminary_Results_20260918.md)，复现脚本
  `scripts/ts_conditional_partial_analysis.py`，数据输出 `runs/ts_conditional_partial_20260918/`。
  当前N1/N2在CE证据为Negative，A1/A2为Weak，A3证据不足；先补齐，不根据补点结果调参或扩大B长跑。

- 2026-09-16：按用户要求改为按模式组即时写表；组内任务全部返回（含续跑跳过、失败）后，
  立即生成该组 `JVET-hhi.xlsm` 和 summary/failures，其他组继续执行。重试结果变化时刷新，
  终场不重复写未变化的组。Excel采用临时文件完成后替换，失败保留旧表。
  8项batch测试通过，包含跨组写入时机、重试刷新和真实工作簿Reference/失败保护检查；未运行正式编码。

- 2026-09-16：按后续请求扩展 batch CLI 支持五个条件/自适应模式及编译默认值识别，
  增加逐模式编码器/解码器启动探测，新增 `scripts/run_ts_conditional_lb_ce.sh`。
  默认 LBeu C/E 半帧四QP五模式，共140项、10并发、共享队列、无重建、解码hash、保留续跑及分组Excel输出。
  结果目录 `runs/ts_conditional_LB_CE_half/<mode>/`；Excel仍在全部任务结束后生成。
  已通过5项batch测试、宏默认测试及140项dry-run和10次模式支持探测，未启动正式编码。

- 2026-09-16：TS-006 更新为五组闭环规则 N1=q32、N2=conf2、A1=prev、A2=ewma、A3=q32_ewma，
  源码/宏选择已完成，**正式 CTC 尚未编码**。这替代早期 G3=q32_conf2 方案；旧设计保留但注明已被替代。
  历史仅 TU 内保持，在 CG 最终清零决策之后更新；使用最终系数回放 Writer 三遍语法预算，
  不把 RDOQ 的近似预算误作历史评分的有效 remapping 范围。三组历史评分为整数代理，不宣称 CABAC bits。
- 2026-09-16：TS-006 本地验证通过：99项短帧 encode/decode hash、Writer/Reader CG状态一致，
  Current/OFF 对旧anchor bit-exact，五项 trace-off 编码 bit-exact；10项Python测试和C++扫描/状态测试通过。
  详情见 [TS_Conditional_Predictor_Validation.md](TS_Conditional_Predictor_Validation.md)。旧实验二进制未覆盖，未修改批量运行脚本。
- 2026-09-16：建立外部结果收件目录 `experiments/ts_conditional_v1/<mode>/{LB_BCE,RA_CD}/`，
  每目录待放 `JVET-hhi.xlsm`、`run_metadata.json` 和可选 logs；源码运行说明见
  [TS_Conditional_Predictor_Implementation.md](TS_Conditional_Predictor_Implementation.md)。未创建空白结果表，不将计划或 smoke 标成 CTC 结果。

- 2026-09-16：TS-006 条件启用阶段新增首轮设计 [TS_Conditional_Predictor_Experiment_Design.md](TS_Conditional_Predictor_Experiment_Design.md)：
  G1 实际 CU luma QP<=32，G2 方向分数 2:1 置信门控，G3 二者同时满足；
  均选择既有 directional 或 Current，不加入 NoPred 混合。参数为预先声明的工程假设，不是最优阈值。
  三组未来各 LB BCE 48 + RA CD 32 任务，复用统一池；当前仅设计、未实现、未编码。
  G2/G3 可利用当前 CG 内已经解码的因果邻居，不冒充历史 CG 整组 selector。

- 2026-09-16：TS-005 的 LB B 外部编码结果已从各模式 `JVET-hhi.xlsm` 接收并完成数值审计。
  NoPred/directional 各 B 20 点，合并原 CE 后 BCE 各 48 点；加权 BD-rate 分别
  −0.041705%、−0.035706%，均未达到 −0.05% 目标。历史“尚未测试 B”状态至此失效，
  但上方帧数、hash、二进制身份检查项仍未完成，不能用 Excel pass 代替日志审计。
- 2026-09-16：新增 TS-007（RA CD 外部闭环固定 predictor），三个模式各 32 点。
  NoPred −0.008314%、gradient +0.040742%、directional +0.003174%。Reference 与原 anchor 一致；
  实际 RA 配置/帧数/编码二进制未取得，状态为“表格完整、编码来源待核实”。
- 2026-09-16：冻结的 nominal QP22/27 directional + QP32/37 anchor 组合：
  B −0.029567%、BCE −0.070258%，10/12 序列改善；这是曲线复用诊断，不是 TS-006 工具实现。
  判断：固定 NoPred/directional 为 Weak，gradient 为 Negative，低 QP 条件方向为有限 Promising。
  新增 `scripts/ts_fixed_workbook_analysis.py` 和 [TS_Fixed_Predictor_LB_BCE_RA_CD_Results.md](TS_Fixed_Predictor_LB_BCE_RA_CD_Results.md)；
  数据及 SHA256 输出至 `runs/ts_fixed_LB_CE_half/external_analysis_611/`。未启动新编码、未修改 codec。

- 2026-09-13：增加 `JVET_BJUT_TS_FIXED_NOPRED/GRADIENT/DIRECTIONAL` 三个 0/1 默认模式宏，
  最多开启一个，全关闭为 Current；总开关仍独立控制实验能力。
  `--fixed-predictors` 优先覆盖，省略时 batch 从实际二进制探测默认并同步 Encoder/Decoder。
  已通过 6 项独立编译/模式覆盖测试和 4 项批量测试；未重编既有实验二进制。
- 2026-09-13：固定 predictor 宏的默认值移入 `CommonLib/TypeDef.h`（0）；
  CMake 新构建默认 AUTO，ON/OFF 可显式覆盖。运行时 predictor 仍由环境变量/批量参数选择。
  本次未重编既有实验二进制，不改变已记录编码结果或其续跑指纹。
- 2026-09-13：建立统一记录，补录 TS-001 至 TS-004；冻结 TS-005 计划，B 完成证据为 0；
  纳入用户确认的半帧、分量 BD-rate 后加权及三个工程门槛。
