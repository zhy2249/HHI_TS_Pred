# 61组TS规则与状态转移：本地测试设计

日期：2026-10-25。规则 `TS-RULE-SUITE-v1`，执行接口 `TS-RULE-LAB-v1`。
设计基线 `b789da4f4f67002aa8da9f90d5343c8aa14196b5`；原生审计依赖impl2。

本次用户要求：规则及代码上传Git，用户在本地测试后把结果上传Git。此次交付不执行新视频编码，不把CE01局部结果当作全序列收益。

**实际代码入口：[scripts/ts_rule_lab/README.md](../../scripts/ts_rule_lab/README.md)。** 所有核心脚本、依赖、原生接入候选源码、测试和小型CE01系数fixture均在Git，不再要求用户从旧会话附件寻找代码。

## 1. 统一比较范围

12序列×4QP×R13-1/R13-2，共96条正式码流，由既有manifest枚举；全部读到EOF，不限定Johnny/FourPeople，不默认截到299帧。
同一来源解码器使用其正确原生规则；所有候选方法只在私有副本中回放。真实解码、量化系数、原生context和重建不变。

每个最终目标TS TU完整导出q、scan、元数据和10固定策略rate。各规则用同q及同一个来源入口生成完整预测序列并回放整个TU，包含CG间context和regular-bin预算传播。

R13-1与R13-2分别评价，不将一侧系数替代另一侧。既不要求两侧TU几何相同，也不按日志行号强行配对。
CE01为落选搜索TU，继续单独用于规则回归，不能由最后.bin恢复或混入最终TS总体人口。

## 2. 全部61组定义

`python3 scripts/ts_rule_lab/rule_suite.py`输出完整机器可读清单，顺序也是schedule列顺序。

| 类别 | 数量 | 名称或组合 |
|---|---:|---|
| 固定对照 | 10 | CURRENT，STATIC_EQ/SP，KEEP_F0..F4，KEEP_EQ_H/SP_H |
| 当前邻域规则 | 6 | GUARD_EXTRA_NEAR，SINGLE_NEAR_F3，NEAR_AGREEMENT_ONLY，MARGIN_1_64/16/4 |
| 纯状态 | 36 | K=2/4 × 初态zero/half/equal × P1/P2 × hit/cost/margin |
| 状态＋接受保护 | 6 | HYBRID_K4，3初态×P1/P2，margin反馈＋额外近邻票保护 |
| Current/EQ/SP历史信用 | 3 | EXPERT_DEBT_B2/B4/B8 |

这些是61个参数配置，不是61种独立原理。不得按首先出来的结果重命名或悄悄调整参数。需要新规则时另起revision并与原61组分开。

## 3. 固定评分与候选

H=(L,U,D,LL,UU)，零样本不计损失，n仍为有效非零位置数。原Current=max(L,U)，n<3原样返回Current；0/1候选在有评分时等价归并。

原候选顺序为Current等价候选、其余候选按原identity/幅值顺序；只在严格更小分数时替换。历史仅增加一个TU内前缀非零众数候选，包含幅值1、频数并列取较小值；不当作额外观测或奖励。

`S(p;K,r)=K*N(p)+r*F(p)`，N为L/U损失和，F为D/LL/UU损失和，采用原168倍KeepHit表。
固定网格取K=4，r=0..4；r=2等价22111，r=4等价11111。Current不等于r=0。
静态两对照使用168*C(f(m,p))，不含KeepHit近邻量化修正，其余规则相同。

## 4. 当前邻域规则

### 4.1 额外近邻票稳定性

pE为等权赢家，pr为当前加权赢家；d_j=ell(m_j,pE)-ell(m_j,pr)，零样本贡献0。

`G=K*(dL+dU)+r*(dD+dLL+dUU)`。

只有`G>(K-r)*max(0,dL,dU)`才接受pr，否则返回pE。它撤销一个近邻的额外权重，而不是删除该真实观测。
GUARD_EXTRA_NEAR固定K=2,r=1；混合版本则使用其当前状态输出的K/r。
这个两候选稳定性判据不保证实际CABAC最优，也不保证不会错失单近邻正确预测。

### 4.2 单近邻温和加权

SINGLE_NEAR_F3：有效非零近邻数等于1时用近4远3，否则用近4远2。无新增状态。

NEAR_AGREEMENT_ONLY：L/U同时非零且相等才使用空间赢家，否则等权。

### 4.3 小分差保护

SP相对EQ的评分优势为G，空间有效权重和为W。当`G/(168*W)<=tau`时返回EQ，否则SP。
tau固定取1/64、1/16、1/4三组；运行时交叉相乘，不需要浮点。这不是实测CABAC bit阈值。
以上规则可能立即改变采用的预测方式，不能声称实际权重也遵守逐级变化。

## 5. 纯状态机

K∈{2,4}；每档内部状态数h∈{1,2}。

`s∈[0,(K+1)*h-1]`，`r=floor(s/h)`。

初始化r0分别为0、K/2、K。r0=K时s0取最高状态，其余取r0*h。每个TU/分量重置。
先由旧s选择当前唯一p；当前真实a已恢复后取得方向d，执行`s<-clip(s+d)`。每次最多一步，绝不直接跳目标档位。
双状态只增加相位，既没有待确认目标，也没有另一个方向缓冲；跨档边界一次反向反馈仍可能立即退回，不能称严格两次确认。

a=0、n<3、近/远任一组没有非零样本时不更新。中性反馈保留完整s，不清最低位。

### 5.1 hit

各档只获得`p=a>=2`的精确命中奖励；没有虚构NoPred命中。目标并列按当前优先、距离最近、远权较大排序。按目标方向推进一步。

### 5.2 cost

用固定已恢复a计算各档赢家的`C(f(a,p_r))`，使用相同tie；目标只决定方向。它是部署可用的静态成本反馈，不是离线真实CABAC oracle。

### 5.3 margin

先执行cost规则。有方向就采用；没有方向时，从原候选中找一个静态映射成本严格更低的目标t。
真实成本打平优先当前p，然后当前加权score和旧候选顺序。
令deltaN=N(t)-N(p)，deltaF=F(t)-F(p)，nN/nF是两组有效位置数：

`Z=nN*deltaF-nF*deltaN`；方向为`-sign(Z)`，边界处饱和。

这是归一化候选分差对远权的方向，不需要除法；不能保证第三个候选胜出后整体更好，所以必须完整TU复评。

## 6. 混合与Current历史信用

HYBRID使用K4的margin状态，当前输出还经过第4.1节保护。状态反馈依据原状态网格，不根据保护后的p重写反馈。
**它保留逐级内部状态，但可以即时回退到EQ，是额外接受机制。** 要求实际远权也逐级时，应只选state类别，排除hybrid和causal_gate。

EXPERT_DEBT：Current信用固定0，EQ/SP各维护一个[-B,B]的累计静态成本差：

`debt_j <- clip(debt_j + C(f(a,p_j))-C(f(a,p_Current)),-B,B)`。

当前决策只看旧debt，取最小者；平局顺序EQ、Current、SP。所有debt初始0、TU重置。B=2/4/8是代理成本单位，不是真实bit。
仅a>0,n>=3时更新；不增加真实RDOQ，不使用当前a决定当前选择。

## 7. 两遍测试及收益定义

第一遍收集所有TS q/scan和固定对照；默认不计算额外单点oracle，省去不影响整TU比较的开销。需要后续特征训练时添加`--with-labels`，为全部a>0,n>=3位置标注合法候选代价。两种模式必须标明，不能混称。

Python在完整因果扫描上生成61组p序列，并用schedule绑定TU几何、q摘要、入口context摘要、方法清单及SHA。
第二遍仍解码原.bin，只在私有副本回放61条完整策略。完全相同预测序列共享回放。前10个Python固定策略与C++固定对照必须逐TU相等。

`gain_X = R_X - R_method`，正值为节省；同时报告相对Current/EQ/SP。
增码TU数、节省TU数、总正损失、总收益和最坏TU损失分别保留，不能只看净均值。
各TU从自身原生入口开始，因此这些bit的加总是固定来源入口的条件TSRC代价，不等于整片改码后的比特、实际字节或BD-rate。

双来源先各按自身非零系数数归一，再等权平均；各内容内QP等权，各内容再等权。零分母保持null并报告支持数。
全量表可以描述“本数据集哪个规则最好”；另以其它内容选择规则，再评价留出的整个内容，所有QP和两来源一并留出。已用于人工开发的内容不是全新盲测。

## 8. 结果回传与安全边界

按[代码README](../../scripts/ts_rule_lab/README.md)运行。报告目录含9份CSV/JSON：

- all_methods_by_stream_component.csv
- paired_source_metrics.csv
- by_sequence.csv
- all_content_descriptive_ranking.csv
- leave_one_content_selection.csv
- worst_TU_cases.csv
- methods.json
- run_receipts.json
- report_scope.json

用户完成后上传整个小型report目录和真实验收README到`docs/experiments/results/ts_rule_lab_<运行标识>/`。
不要只回传最佳一组；保留全部61组、全部序列/来源、失败/缺项和程序/输入身份。原始corpus/schedule/大日志留在runs，不默认提交原始视频或重复码流。
当前C++collector是接入候选：先编译、原生回放/on-off/hash/预算验收，再执行96流。用户本地适配后的代码和测试记录应同步，否则结果无法对应原规则。

## 9. 本次实际核验

28项Python纯规则/合成协议测试通过，包括当前/未来信息不泄漏、合法候选、单步状态、双来源互换、缺方法拒绝、全内容/QP/来源完整性、schedule身份和有界最坏案例输出。
CE01正确可评分非零位置为7；使用该小型已记录fixture检查扫描索引，不是重新从码流恢复落选候选。
未完成原仓库C++编译、任何新真实解码、全序列收益选择或编码闭环。没有更改生产预测器或正式实验台账；integrate默认dry-run，需本地显式apply。
