# TS predictor 下一轮完整实验协议（R2）

日期：2026-09-18。状态：**四组源码已实现并通过本地短帧验证，未启动正式CTC编码**。
实现/命令见 `TS_Predictor_R2_Implementation.md`，本地验证范围见 `TS_Predictor_R2_Validation.md`。
本文取代 `TS_Predictor_Revision2_Design.md` 的首轮矩阵，加入NoPred候选与严格消融。
不修改正在收集的revision1，不保证正收益。“完善”指目标、因果性、对照及验证更完整。

**唯一正式anchor为Current，沿用原 `scripts/JVET-hhi.xlsm` 的Reference。**
所有主表BD-rate、收益目标和推广门槛均相对Current；NoPred只是候选方法和辅助比较对象，
不替换Reference，不作为第二个正式anchor，也不要求新实验先击败NoPred才有资格进入B验证。

## 1. 证据、目标与四个可证伪假设

现有固定NoPred：LB CE −0.056719%、BCE −0.041705%、RA CD −0.008314%；
固定directional：CE −0.036617%、BCE −0.035706%、RA CD +0.003174%。
revision1的q32/conf2完整CE为+0.030428%/+0.043798%；prev/ewma暂估值仍含补QP22。
这些数字支持将NoPred列入候选，不证明局部选择一定比固定NoPred更好。

- H1：局部重复量化幅值比方向平滑度更适合作为命中对象。
- H2：直接最小化remapping符号成本，比只取重复最多的幅值更合适。
- H3：历史CG能区分“使用Current”与“使用NoPred”，且可能比Current/directional更有效。
- H4：保持候选不变时，更准确的语法/概率评分能显著改善历史选择。

工程目标仍是相对Current的LB BCE平均≤−0.05%，≤−0.08%不错，≤−0.10%可观。
固定NoPred的既有结果用于辅助判断自适应复杂度是否值得，不改变正式收益基准。

## 2. 冻结的核心实验矩阵

| ID | 模式名 | predictor/选择器 | 对照目的 |
|---|---|---|---|
| R2-M | r2_modal | 局部非零幅值严格多数，否则Current | 新预测公式的简单对照 |
| R2-R | r2_risk | 因果邻域remapping成本最小，包含NoPred | 主要低复杂度候选；与M比较准则 |
| R2-N | r2_cn_log | Current/NoPred，沿用A2的log2代理及EWMA | 仅替换旧A2的候选，检验NoPred加入 |
| R2-F | r2_cn_frac | Current/NoPred，相同EWMA，虚拟CABAC CG评分 | 与N比较完整评分机制；高复杂度诊断 |

正式基线仅Current；已有固定NoPred、固定directional和A2 ewma均作为辅助实验对照。
R2-N是有意保留的弱成本模型对照，不宣称四组都比旧方案复杂或优越。
R2-F相对N改变的是整个评分机制（概率、分支预算/语法回放等），不是仅改变小数精度。
禁止从该比较进一步单独归因于parity概率或某一项bin。

后备实验只在下面进入条件满足后做：Current/NoPred/R2-R三候选的fractional-rate历史选择，
沿用同一状态定义和固定优先级，不先堆叠到首轮。

## 3. 所有实验共用的语法与因果约定

Current为p=max(L,U)；NoPred为p=0，沿用其他TSRC语法，不关闭significance/sign/CG编码。
p=1与p=0的remapping等价，候选比较时规范化为0，报表标记为identity。

\[
f(a,p)=\begin{cases}0&a=0\\1&a=p>0\\a+1&0<a<p\\a&a>p\end{cases}
\]

只在现有remapping生效的路径使用；BDPCM和cutoff=0保持原identity，普通transform不改。
预测值仍有正常inverse remapping，不添加mode语法。
不得读取原始像素、原始残差、当前待编码幅值、未来CG、跨TU状态或encoder搜索context来选择模式。
短帧和正式实验都必须是真实闭环TS-RDOQ+Writer+Reader，允许TS选择与q重新变化。

局部预测读已恢复的量化邻居；在RDOQ中用当前候选路径已决定的邻居，
不能把一次被抛弃的搜索状态带到另一候选。最终Writer/Reader模式必须逐位置一致。
CG层状态只在该CG最终清零RD决策、decoder inverse remapping和符号恢复后更新。
整TU或候选被抛弃即丢弃全部私有状态。

## 4. R2-M：有支持度的离散幅值预测

固定模板为左L、上U、左上D、左二LL、上二UU。
**仅加入在当前TU内存在且scan已完成的邻居**；不存在的邻居与实际零值区别记录，
不能为了满足样本数伪造边界零。去掉幅值为0的样本得到T+，n=|T+|。
不要求x>=2且y>=2；用真实可用集合，以免完全排除宽或高为2的合法矩形。
少于3个非零样本时保持Current。n=3..5时等权，固定以下规则：

- 若幅值v有严格多数，即2*count(v)>n，取p=v。
- 否则保持Current；无需另外人为设置置信度阈值。
- v=1等价NoPred。p>=2才能改变remapping。

这是从初版“唯一众数重复两次”收紧为**严格多数**，避免2/5样本就被称作共识；
此修订在任何R2编码之前固定，不做2/5与3/5的收益搜索。
风险：即使多数也只是最多5个相关样本，不保证代表当前值；高QP下有效支持度可能很低。
与历史selector不同，它在第一个CG内也可生效，但开头几个系数仍缺少邻居。

## 5. R2-R：remapping风险最小的局部幅值预测

与M使用完全相同的可用模板、n>=3门槛，不使用历史状态或QP阈值。
候选为去重的{0,p_Current}和T+内所有>=2的值；Current来自L/U，故最多6个不同候选。

\[
J(p)=\sum_{a\in T^+} C_{TS}(f(a,p)),\qquad p^*=\arg\min_p J(p).
\]

并列优先Current的等价映射，其次NoPred，再其次较小p。不引入浮点、经验权重或分量专用条件。
零不参与幅值分布拟合，是因为零的remap始终为0；本算法不预测significance。
但“非零邻居条件分布代表当前非零幅值”仍是假设，必须在真实编码中验证。

### C_TS 的固定定义

采用完整regular三遍路径的语法长度近似：context bin均按1单位，bypass按实际长度。
固定使用进入component TU时已知的Rice参数r和dynamic range d，不读当前CG的未来截止位置。
复用codec的 `encodeRemAbsEP` 长度规则，包括cutoff=5和escape分支，不写简化log2替代。

\[
C_{TS}(0)=0,\quad C_{TS}(1)=1,
\]
\[
C_{TS}(t\ge2)=2+\sum_{k=1}^{4}[t\ge2k]
 +[t\ge10]\,L_{Rice}((t-10)>>1,r,d).
\]

基础2为gt1和parity，四项阈值为2/4/6/8。r=1时t=1..11的成本为1,3,3,4,4,5,5,6,6,8,8。
对同一系数固定p比较，significance/sign直接项相同，因此局部准则不计算它们。
**这仍是近似**：非均匀概率、parity取值和预算截止未完全建模，不将J差值称作真实省bit。

特别禁止用当前Writer的可变remRegBins或pass2结果动态构造C_TS：同一p会在三遍调用时改变，
且Decoder在inverse remapping阶段看到的预算不同，容易破坏同步。
成本参数和候选仅由不可变TU信息及因果邻居决定。真实bypass位置仍执行native identity。

NoPred是实质候选：没有足够命中收益时可避免较大p把小幅值上移。
示例T+={8,2,2,2,3}、r=1：J(p=8)=14，J(p=2)=12，J(p=0)=18，选择2。
该例子只检查公式，不作为内容收益证据。风险最小化也可能过拟合小样本，不再叠加另一套未验证阈值。

## 6. R2-N：Current/NoPred，旧评分对照

严格沿用revision1 A2的TU内状态流程，仅将directional换成NoPred：

\[
G_g=\sum_{i\in\mathcal E_g}[C_{log}(f(a_i,p_C))-C_{log}(a_i)],
\]
其中C_log(0)=0，C_log(t>0)=1+2*floor(log2(t))，E_g为**实际分支**的有效remapping位置。
有效位置必须由CG最终系数回放Writer三遍预算得到，不取RDOQ近似预算。

TU开始S=0；CG开始时S>0取NoPred，否则Current；CG结束后：

\[
S\leftarrow clip(S-sign(S)\lfloor |S|/4\rfloor+G_g,-32767,32767).
\]

CG0为Current，全零/无有效评分CG按原A2规则以G=0衰减；小整数|S|<4的衰减为0，明确保留此量化效应。
不在该组改变为“跳过无信息更新”、不改变初始状态、K或置信阈值，避免与候选替换混淆。
旧A2 vs R2-N是候选改变的闭环对照；系数与TS选择随编码改变是算法效果的一部分。

## 7. R2-F：Current/NoPred，完整CG虚拟fractional评分

与N相同候选、CG0 Current、S符号选择、K=2、TU重置和更新时机。
但评分改为对每个最终CG进行两分支完整语法回放，各自更新概率、预算和Rice/remainder：

\[
G_g=R_g^{C,virtual}-R_g^{N,virtual}.
\]

### 确定性虚拟状态 V

1. component TU开始，V使用codec初始化函数：QP=Clip3(0,MAX_QP,cu.qp)，固定I初始化表；
   预算=(TU面积*7)>>2，significant-group历史为空，fractional计数器清零。
   这是额外模型的定义，不复用实际slice CABAC table search、temp CABAC加载或跨TU实际context。
2. CG完成，从同一个V深拷贝两份，分别用Current和NoPred回放整个CG。
   包括CG significance/inference、coefficient significance、sign、gt1、parity、greater-than、Rice/bypass；
   CG索引、已完成q、TU几何和工具标志均为decoder-known。
3. 两分支成本取各自计数器增量；上下文更新必须与codec概率模型实现一致，不能只累加静态bin数。
4. 只保留Current分支结束后的V作为下一CG共同起点，不按winner或实际模式决定参考状态。
5. S使用64-bit native fractional units，饱和范围为±(32767<<SCALE_BITS)，按相同比例衰减。
   选择前不舍入为整数bit；最终模式只影响下一个CG。

空CG仍回放相同的significance事件并令G=0；不以“没有正收益”跳过虚拟状态推进。
状态克隆包含概率模型和语法预算/CG历史，不能只复制rate counter。
RDOQ、Writer和Reader使用相同公共回放实现，避免CommonLib依赖EncoderLib造成分层循环。
建议将纯事件/代价回放放CommonLib，仅依赖context模型、扫描、q和decoder-known参数。

### 必须明确的限制

- 这是codec概率模型下的**虚拟条件rate**，不是实际码流bits或可实现收益上界。
- 固定I先验/Current规范历史不是实际状态；需记录与真实Writer估算的差异，不能用“真实CABAC”掩盖这点。
- NoPred分支结束预算不传播到下一虚拟CG，因此不是整TU始终NoPred的连续rate模拟，也不完整计入释放预算的后续收益。
- 两分支固定本轮q，不重新量化历史CG；最终有效性仍由每种算法独立闭环编码检验。
- Decoder增加两次回放与状态克隆，复杂度可能不可接受。此组是评分机制诊断，不能因微小收益直接进入正式工具。

## 8. TU尺寸、分量和作用范围

不写死TU尺寸集合，覆盖源码允许并实际出现的TS尺寸，含矩形、亮度/色度、intra/inter。
M/R只依赖可用邻居，因此单CG TU也可能生效；N/F单CG TU完全没有历史机会。
不能把M/R称作“仅历史CG选择”，二者会使用当前CG内已解码邻居。
初版对Y/U/V执行同一规则，不因现有U退化直接屏蔽U，不按序列、class或RA/LB标签选择方法。
BDPCM保持identity，不学习该路径；TSRC关闭和普通transform bit-exact。
记录双树、DQP、chroma映射，但不将encoder-only lambda或原始残差传给selector。

## 9. 正确性门槛：不过关不长跑

1. master OFF和Current与保留anchor逐码流一致；旧NoPred/directional路径无回归。
2. 宏/环境实际身份明确：请求实验而master关闭或不支持时必须报错，不能静默退化Current。
3. TypeDef.h为首要控制源；实现时移除CMake对实验master的ON/OFF编译定义覆盖，旧缓存不得改写源码选择。
   旧fixed、revision1、R2默认模式和旧统计宏互斥；环境变量仍可显式覆盖默认。
4. remap/inverse在合法level、p范围往返；p=0/1 identity；整数cost与实际emit的bin数一致。
5. 当前真实scan覆盖小尺寸/矩形/边界、重复样本、多数平局、零样本、动态范围和Rice escape。
6. F在任意给定相同起点/q/mode下与独立codec estimator对照一致（fractional整数容差应为0）；
   与真实路径不同起点的rate不要求相等，但要解释差异。
7. 每CG/每位置trace核对RDOQ、最终Writer/Reader模式和状态；禁止用两个同源错误实现相互一致作唯一证据。
   RDOQ试算trace与最终选中TU需建立对应，不混入被抛弃候选。
8. CG最终清零、全TU清零、候选回滚、bypass预算耗尽、DQP、BDPCM、lossless、bit depth、TSRC off smoke。
9. 每个新模式必须有真实remapping改变的非空样例，所有流解码hash通过；调试开关开/关bit-exact。

## 10. 正式实验安排

### Phase 0：来源与数据完整性

保留原anchor Reference，不安排全套anchor重跑。记录源码commit/patch、编解码binary SHA、
宏配置、有效模式banner、输入/配置身份、实际帧数、hash状态与重试失败列表。
源身份不能核对时先解决可比性，不能仅凭Excel pass确认远端实验。
revision1缺失点继续补齐；anchor替代QP22只用于原先的暂估，不用于R2正式判定。

### Phase 1：四组固定开发集合

- LB CE：C四序列、E三序列，QP22/27/32/37，项目CTC半帧，每组28任务，共112。
- RA CD：C四序列、D四序列，相同四QP，帧数必须与RA anchor一致，每组32任务，共128。
  运行核查发现原RAeu默认仅64/32帧单段，不能直接视为完整CTC；外部RA anchor帧数/分段来源确认后才开跑。
- 四组共240新任务，任何一组的失败/退化都保留报告，不删除序列，不重选阈值。
- 无重建视频，decode hash，共享任务池，无组间屏障，每组全部返回就写独立Excel。
- 不混用RA/LB，不按class等权替代sequence等权。

辅助对照NoPred等结果只有软件/配置/输入/帧数可比时复用。身份有疑点时少量哨兵验证属于校验，
不是新增一轮完整anchor；须另行说明，不悄悄改Reference。

### Phase 2：最多两组进入B验证

先看完整CE与RA CD，再锁定候选，不按B结果调公式。
优先进入条件：相对Current的LB CE为负、RA CD均值不为正，收益不完全依赖PartyScene。
不设置相对NoPred的硬性准入门槛；NoPred只用于附加说明收益与复杂度的权衡。
这是保守的资源分配规则，不是证明未通过者在BCE必然失败。
至多选择一个最佳M/R和一个最佳N/F；若都不通过则停止B长跑。
每组B五序列四QP半帧20任务，最多40项；最终BCE12序列等权评估用户目标。
B内容此前已经看过旧算法结果，不能称作完全未见的独立内容验证；通过后仍需未用于设计的内容/条件确认。

### Phase 3：仅有证据才考虑三候选组合

R2-R和R2-F相对Current均有效，且R2-F比R2-N存在明确增量时，
才设计Current/NoPred/R2-R三候选版本。初始化仍Current，候选优先级Current→NoPred→R2-R，
任何新增置信/保留无信息状态规则另立实验编号，不能混入同一组结果。

## 11. 必需输出与分析

主指标：每个实验相对Current，先计算每分量四点PCHIP公共质量区间BD-rate，再取(6Y+U+V)/8；负值好。
工作簿Reference始终为Current，各实验（包括固定NoPred）仅写入Test，不覆盖Reference。
输出序列、class、CE/RA CD及最终BCE；mean/median/std/P10/P90、改善数、最差序列、
leave-one-out与10000次序列bootstrap。小样本CI仅作内容变异描述，不用巨量coefficient宣称工程显著。
缺任一QP的正式曲线不得用anchor冒充实测；可单列暂估，但不触发进入B的决策。

主表统一列出各方法相对Current的结果。必要时另列新算法与固定NoPred、M/R或N/F之间的配对诊断，
直接重算共同质量区间，不能用两个Current-relative BD-rate简单相减冒充direct BD-rate。
这些配对诊断不是正式anchor结果，不用于替代用户收益目标。
固定NoPred相对Current的BCE约−0.0417%：若自适应收益相近，需讨论其额外复杂度是否值得。

在线聚合而非默认coefficient文本：

- POC、component、W×H、intra/inter、实际QP、TU数、CG数、单CG/多CG占比；
- 可用模板数、非零支持n、多数存在率、p选择（Current/identity/其他幅值）；
- predictor不同次数、真正remap不同次数、regular/bypass占比；
- N/F的G正/零/负、全零CG、无有效评分CG、状态符号、切换、选NoPred比例与first-CG成本份额；
- F的context拷贝次数/时间、估算时间、Decoder总时间及内存；同机重复短benchmark，
  不用不同服务器单次编码时间比较复杂度。

rate/selector trace只对指定POC小样例开启；在线聚合是作用范围诊断，仍是最终TS条件样本，
不能当作全编码无偏收益。虚拟Oracle可以作为辅助诊断，但不以其拒绝或确认真实闭环工具。

## 12. 预先定义否定与推广条件

- 完整CE/RA不优于Current：降低该候选优先级。
- R比M更复杂却无增量：保留更简单M，否定风险模型的工程必要性。
- N不如固定NoPred：作为选择复杂度未体现增量的辅助证据；不改变N相对Current的正式结论。
- F不如N：目前没有证据支持昂贵评分；不能继续默认问题只是proxy太粗。
- F有效但Decoder开销过大：只保留为诊断，后续整数近似必须单独闭环验证，不直接集成正式工具。
- 收益只来自某序列、极少尺寸或某缺失点补齐假设：不评Promising。
- 原型真正Promising要求相对Current的完整BCE达到目标、RA无系统性回归且没有来源/同步问题。
  ≤−0.08/−0.10%的评价照用户门槛；不把CE达标当BCE达标。
- 自适应是否值得优先实现，另看它相对简单固定候选的增量与复杂度，不混同于相对Current是否达标。
- 未来若整数近似与F高度mode一致但BD-rate退化，仍以闭环结果为准；不能用mode agreement替代收益。

所有阈值、样本模板、tie、候选集及更新规则在本轮编码前固定，修改即新revision。
不承诺更复杂或更“准确”就能达到−0.1%；若证据负面，应明确停止或转向固定NoPred研究。

## 13. 交付与结果目录

实现已包含公共prediction/score模块、三路径接入、宏互斥/有效身份校验、单元与smoke测试、
沿用现有batch并按组写表、在线聚合及相对Current的BD分析脚本。
辅助的任意方法间direct BD配对未做专用CLI，可复用现有积分函数；正式主表始终以Current为基准。
预留 `experiments/ts_predictor_r2/<mode>/{LB_CE,RA_CD,LB_B}/`，各目录只含README，
未来放 `JVET-hhi.xlsm`、`run_metadata.json`、`logs/` 和可选aggregate统计。
R2模式与revision1分开，不覆盖旧表；无正式结果时不复制空白Excel冒充完成。
