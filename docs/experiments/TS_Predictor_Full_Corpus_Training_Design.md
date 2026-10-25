# 全序列TS数据集与代价敏感训练

- 规格：`TS-CORPUS-TRAIN-v1`；设计基线：`6beb4504f0aae7f1895f819743a7ad5d3efef01a`。
- 本文替代“只分析Johnny/FourPeople验收表”的研究范围，但不改变原R13/R14算法或正式RD数据。
- 状态：全量导出接口、Python批处理／特征／训练／风险分析参考代码已在本次会话交付；21项纯规则/合成测试通过，生成的浅树C++与Python一致性测试通过。**C++解码器全量接入尚未在原仓库编译验收，96条真实码流未在本次重解，未训练真实数据模型。**
- 完整源码交付包：`TS_Full_Corpus_Training_v1.zip`，SHA256 `4e2c652f22ac64547e1b42aae4abedc52b7f90259625cf646fa010359f5ebd73`，36463字节。它是本次会话附件；本条登记不表示该zip或其全部源码已上传Git。本页是后续Codex接入和验收规范，包内README含完整命令。

## 1. 全量范围不是将旧抽样程序多跑几个序列

以`deliveries/r13_decode_audit_impl2/manifest.json`的全部正式pair为准。目前为12内容×QP22/27/32/37×R13-1/2=96条，额外17帧前缀不重复算训练数据。

内容为BQMall、BQTerrace、BasketballDrill、BasketballDrive、Cactus、FourPeople、Johnny、KristenAndSara、MarketPlace、PartyScene、RaceHorsesC、RitualDance。代码按manifest枚举，不按Johnny收益挑选序列。

必须解码到文件EOF，不能默认只取32帧、也不能假设全部流恰好300帧。旧impl2每POC/分量2个TU、每TU少数点的限额是验收/受控审计设置，不能充当本次全量训练合同。

新增通道：
- 对每个实际进入TSRC的最终TU记账；普通TSRC全部保留q、scan、身份和固定策略rate。
- 对全部`a>0,n>=3`位置生成完整候选代价标签，不抽4个点。零、n不足位置仍存在于完整TU和历史前缀中，不虚造选择准确率。
- BDPCM单列；超出已有协议的尺寸/动态范围显式计数，并阻止“全数据集complete”结论。不静默丢弃。
- 不恢复落选trial；CE01仍是单独的搜索反例，不能从最终码流找回。

## 2. 只读解码和真实标签

来源EQ用EQ主规则，来源SP用SP主规则。读取TSRC首个bin之前保存完整Ctx，反映射/符号恢复后读取最终q；全部TU的native回放逐bin、fractional cost、出口概率和预算必须匹配。

对来源o、位置i、候选p：

`R[o,i,p]=ReplayTSRC(q_o,X_o,P_native中仅第i位置替换为p)`。

固定q使失真相同；rate单位32768=1估计bit。标签包含后继CABAC/预算传播，不以syntaxCost近似标签。相同映射1/a/a+1共享回放，除原生动作外最多两种额外回放。

C0遵循原候选顺序、0/1归并、n<3回退。C+=C0加一个因果历史众数候选。禁止把当前实际a或最近a加进oracle。C0/C+的最优代价分别保存。

每TU另外回放完整固定策略。单点差不能相加冒充整TU差；不同TU从各自来源入口开始，合计是条件TSRC代价，不是整片新码流长度、不是BD-rate，也不改变真实解码。

## 3. 对照动作

动作编号固定为：

| 编号 | 动作 |
|---:|---|
| 0 | CURRENT |
| 1/2 | STATIC_EQ / STATIC_SP |
| 3..7 | KEEP_F0..F4，近权4，远权0..4 |
| 8/9 | KEEP_EQ_H / KEEP_SP_H |

KEEP_F2与原空间评分等价；KEEP_F4与等权等价；Current不等于远权0。
历史仅扩候选，不追加样本、加分或强制回退；历史大于局部最大值的raised cost必须正确计算。

所有来源面对同样动作、同样cost定义。来源/内容名不作为运行时特征。

## 4. 真正可部署的因果特征

使用白名单而非“除了标签以外全喂给模型”：

- 五邻域幅值及可用位置mask；近远非零支持数；幅值1/2数量。
- 非零不同值数量、幅值跨度、组内一致性、近远冲突。
- 等权/空间的赢家及归一化分差，来自同一历史邻域。
- 当前位置之前的非零比例、幅值1/2比例、历史非零众数及支持比例、最近16位置的统计。
- TU尺寸、分量、已知QP、真实Slice类型、CU是否帧内。

禁止作为输入：当前真实幅值/系数、未来q、原始残差或epsilon、oracle成本、码流来源、序列名、POC、绝对坐标、当前语法结果决定的pass/cutoff。当前幅值可以在事后诊断表分层，但不能由模型偷看。

当前系数作为状态更新观测时，也必须先确定当前p，再读取a推进下一步；测试需要修改当前或未来q，确认当前特征和p不变。

## 5. 不训练一个只追求命中率的分类器

主标签为候选代价向量，而非唯一“正确p”类别。并列最优均正确；错误的幅度必须被保留。

训练损失示例：

`loss_i(action)=regret_i(action)+beta*max(R_i(action)-R_i(Current),0)`。

其中regret相对合法候选或明确声明的动作集合计算。不能只将多数时候微小改善、少数时候大损失的策略评为好策略。

分析报告保留：相对Current、等权、空间的signed delta；改善/退化频率；正损失均值及尾部分位；直接损失/传播；按内容/来源的方向反转。条件特征关联不冒充因果效应。

## 6. 两个低复杂度模型族

### 6.1 代价敏感浅树

最大深度1/2/3，叶子只选择Current或五档远权；每叶需最小样本数和至少两个训练内容支持。分裂直接最小化加权代价，而不是Gini分类错误。

树输出可导出整数C++头文件。部署只需少量比较，不需要numpy/神经网络；实际工程还需按同一特征定义接入，并删除未被树使用的特征计算。

### 6.2 方向状态更新

18个预注册配置：初始远权0/2/4 × 每档1/2微状态 × 3种反馈。

反馈分别为精确命中、固定a的静态映射成本、静态成本无方向时补充全候选归一分差。

状态更新只用双方可恢复的当前a和缓存邻域代价，不用昂贵的native反事实标签。后者只用于离线评价与选择参数。

每次最多推进一个内部状态，权重不跨档；双状态不是额外的同目标缓冲。TU内维护、每TU重置；参考实现按完整final-q前缀推进。未来接入RDOQ仍需CG清零/分支回滚，不能因离线成功忽略同步。

归一分差反馈只在全候选存在严格更好的静态动作时，用`nN*deltaF-nF*deltaN`给出方向，避免必须已有档位赢家改变才触发。但它是否更好由数据验证，不预设“更频繁更新必然改善”。

## 7. 分组训练，防止两版码流互相泄漏

外层按视频内容留一验证：12折，每折11内容开发、1内容测试。一个内容的所有QP、两来源、所有帧和块必须处于同一折。禁止随机按系数拆分。

树的深度/beta仅用外层训练内容中的3组内层验证选择；状态规则为固定预注册算法，参数只在外层训练内容选择。所有训练阈值不得看留出标签。

训练权重先按内容、QP、来源平衡；样本少的一侧不被另一来源吞没。空来源不填0；记录缺支持。分量单独报告，Y上有效不等于U/V上也有效。

输出每折训练内容、留出内容、模型规则、源数据与代码指纹。schedule生成再次检查待测试内容不在训练名单中。外层评估后修改规则，必须承认已使用测试结果，不能继续称同一独立验证。

参考原则见scikit-learn官方分组交叉验证与嵌套交叉验证说明；本包树与状态机是针对本项目编写的独立参考实现，不依赖scikit-learn。

## 8. 完整策略复评必须做第二遍解码

单位置标签只能作为学习目标，不能把其和当成新算法实际代价。

训练后对每个内容用其外层留出模型生成完整TU的p序列：一条树策略、一条状态策略。每个位置只读取因果特征，状态在当前q已恢复后更新。

第二次解码原.bin，原生主路径不变；每TU固定原生q和入口，回放这两条完整策略并与全部固定对照比较。schedule检查几何、q哈希、入口context哈希、长度及未消费项。无额外原图/编码任务。

主要放行指标是留出内容上完整TU的增减bit，以及相对Current/EQ/SP的最坏退化。点级好但整TU差，不能跳过这个事实；平均好但某类内容严重恶化，不能只报总均值。

此处仍是固定最终系数、固定来源入口的条件评估，不能直接宣称新编码器BD-rate改善。

## 9. 参考代码与运行阶段

本次交付包内容：

- `native/Corpus.h`：全TU捕获、全部位置原生标签、十策略与外部OOF序列回放；待原工程编译验收。
- `scripts/apply_native_overlay.py`：受控dry-run/显式apply，相关文件有未提交修改或anchor不匹配就拒绝；修复Manager扫描/光栅联合计数。
- `scripts/ts_corpus.py`：plan、collect、pack、train、schedules、report-eval。
- `scripts/ts_learning.py`：因果特征、整数评分、浅树、状态族及C++树导出。
- `scripts/ts_risk_report.py`：条件风险、正尾部、双来源方向。
- `tests/`、`validation.json`：21项纯规则及合成测试范围。

解压到仓库根`ts_full_corpus_v1/`后，先检查apply dry-run并完成原生验收，再构建新的DecoderApp。旧impl2二进制没有全量接口，不能通过放大日志限额冒充支持。

关键命令（详细构建与安全说明见包内README）：

```bash
python3 ts_full_corpus_v1/scripts/ts_corpus.py plan --manifest deliveries/r13_decode_audit_impl2/manifest.json --expect-sequences 12 --output runs/ts_corpus_plan.json
python3 ts_full_corpus_v1/scripts/ts_corpus.py collect --plan runs/ts_corpus_plan.json --decoder build/ts-full-corpus/bin/DecoderApp --jobs 4 --verify-off --resume --output runs/ts_full_corpus
python3 ts_full_corpus_v1/scripts/ts_corpus.py pack --index runs/ts_full_corpus/dataset_index.json --output runs/ts_training_arrays
python3 ts_full_corpus_v1/scripts/ts_risk_report.py --dataset runs/ts_training_arrays --output runs/ts_feature_risks
python3 ts_full_corpus_v1/scripts/ts_corpus.py train --dataset runs/ts_training_arrays --min-leaf 64 --memory-gib 8 --output runs/ts_loso_models
python3 ts_full_corpus_v1/scripts/ts_corpus.py schedules --index runs/ts_full_corpus/dataset_index.json --models runs/ts_loso_models --output runs/ts_oof_schedules
python3 ts_full_corpus_v1/scripts/ts_corpus.py collect --plan runs/ts_corpus_plan.json --decoder build/ts-full-corpus/bin/DecoderApp --schedule-dir runs/ts_oof_schedules --jobs 4 --resume --output runs/ts_oof_native
python3 ts_full_corpus_v1/scripts/ts_corpus.py report-eval --index runs/ts_oof_native/dataset_index.json --output runs/ts_oof_native_results.csv
```

默认读EOF，不截299；全量任务未完成不能用三对验收结果替代训练。所有命令是参考接口，原生编译/验收未完成前不能写成已可运行的现有二进制能力。

## 10. 数据体积与原生验收

数据不保存每个bin或每个Ctx，只保存紧凑TU/标签流并即时gzip；一次处理当前TU，训练数组memmap。RAM及每流原始JSON大小有显式限额，超限停止并标失败，不自动抽样后宣称全量。断点续跑检查流/程序/脚本/schedule/输出指纹。

精确标签可能耗时：每个不同映射需要完整TU回放，是离线训练准备开销。可优化经验证的后缀快照，不得偷换成静态proxy。训练复杂不等于部署复杂，最终规则应保持少量比较和状态增减。

必须新增真实验收：
1. Corpus.h编译；两来源每个目标TU的native bins/context/预算一致。
2. on/off重建MD5一致；native生成的10动作与Python逐位置完全一致，包括高幅值/Rice/历史超局部max。
3. CE01的扫描联合计数为7，不是0；CE01仍需独立搜索fixture，不从最终.bin伪造。
4. 每流全量census、labels数、EOF帧数和完成记录一致；缺流/unsupported/预算触限拒绝完整声明。
5. schedule设成原生p时，第二遍rate逐TU等于原生；错几何/q/context、缺/多行均拒绝。
6. 21项现有测试只验证参考逻辑；不得将其写成已经完成96流训练或已经获得模型收益。

## 11. 本次交付边界

已经完成：全量研究方案；native接入候选源码；可运行的Python数据/训练/风险代码；21项参考测试和生成树编译小测试；本设计同步。

尚未完成：原仓库native接入编译、真实96条全量导出、真实模型训练、第二遍完整TU评估及任何编码闭环。

这并不否定把解码TS作为数据集：它正是本方案的主体。只是把“最终TS条件下可以训练和验证的内容”与“码流不包含的落选搜索、重新量化和未来闭环收益”分开，避免把训练分数直接当成视频编码收益。
