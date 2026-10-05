# R3 / R6：已有等价优化之后的剩余复杂度空间

## 1. 结论、源码更新与边界

本次开始读取 `4421232d2858d47ff3c0f56f55ac86d8315646ac`。分析期间仓库补推实际优化源码，最终重新核查了 `0d1e8b06b130ef7ffa9a376fec3122e9eaaf31a8` 的 `TsR36Exact.h`、公共dispatch及QuantRDOQ。

**仍有明确的等价优化空间，并已从新增源码确认不是只重复提出已实施的去重、前缀评分和Writer缓存。** 本版取代同次分析初稿中“只能看到实施文档、TsR36Exact.h尚未推送”的证据边界。初稿的缺文件描述只对应最初快照，不再代表最终状态。

本次只修改本分析文档，未修改codec、实验编号、候选集、代价、guard、fallback、量化搜索或正式结果。期间其它源码/脚本更新来自新增的上游提交，不是本次分析工具写入。

范围为R3-1、R3-2启用分量和R6-1～7；不扩展到R3-3/4历史自适应，不改变R3-2色度native回退。数学参考没有执行生产C++、完整视频或计时。

## 2. 新内核已经做了什么、仍留下什么

[TsR36Exact.h固定源码](https://github.com/zhy2249/HHI_TS_Pred/blob/0d1e8b06b130ef7ffa9a376fec3122e9eaaf31a8/source/Lib/CommonLib/TsR36Exact.h)已确认：

| 位置 | 已完成 | 剩余空间 |
|---|---|---|
| R36ScoreTable | 有界插入排序、相同幅值共享cost与multiplicity、不可达raised不计算 | 可达raised仍调用syntaxCost；尚未利用CI偶数/Rice商平台 |
| r36Guard | 原候选分数用精确前缀计算，gain用分数差 | 仍无0/1/2直接解；部分R6动作不需要guard时也先完成它 |
| r36Predict的R6-3/4 | 与诊断parent分离、共享cost表 | 每个候选仍扫描全部不同幅值，并同时计算sum/minimum/saving |
| 稀疏分支 | n<3直接处理max/mean/min | 仍先读完五邻域；TU边界和低幅值可有更早的精确出口 |
| QuantRDOQ | action已经在level候选循环外计算 | 非末尾必定零早退前仍先算action；部分无候选依赖的bypass也可省略 |
| Writer | 文档登记同次CG的remapping缓存 | 不重复开发；不等同于跨RDOQ trial缓存 |

R6-3/4的评分阶段目前为O(u²)，u是不同非零幅值数、u≤5；下面的解析式可配合现有前缀变成O(u)。这是评分阶段，不是宣称含排序的整个函数或整编码时间同比变化。

已有文档还登记动作/诊断分离、scan x/y/idx复用、无状态finish早退和原生回归；最新统计规范已改为显式开启。旧二进制和显式环境不会自动随文档改变。

[已有等价优化报告](../experiments/TS_Predictor_R3_R6_Exact_Optimization.md)的局部计时中位数（优化/原实现）：

| 模式 | 合成语法/参考夹具 | 合成TS-RDOQ夹具 |
|---|---:|---:|
| Current未改动对照 | 1.0122 | 0.9993 |
| R3-1 | 0.9317 | 0.7733 |
| R6-2 | 0.9188 | 0.7465 |

这是文档中的已执行合成计时，不是本次重测，也不代表整编码22.7%/25.3%加速。不能把它直接乘到101.4%上。

## 3. 优先项A：预测值不被使用时，避免整个predictor调用

新提交的QuantRDOQ与初始读取版本内容相同。它先求一次action，传入候选循环；因此不能再声称有“将predictor从每个量化候选循环外提”的新收益。

### 非末尾roundAbsLevel=0

`xGetCodedLevelTSPred`中的原逻辑：

```cpp
if (!isLast && coeffLevels[0] < 3) {
    // 保留原zero cost、significance和bin输出更新。
    if (coeffLevels[0] == 0) return 0;
}
```

roundAbsLevel=0时，down=0、up=1、min=1，up不是独立新增候选。若!lastCoeff同时成立，prediction既不影响候选列表，也不被level评分读取。

对无状态R3-local/R6且无额外观察需求的动作路径，可在原action调用前识别并跳过predictor。lastCoeff仍按原“CG末尾且此前无非零”定义提前取得。**不跳过原zero cost/significance/bin更新，不提前改CG判零，不省略其它量化输出。**

不能只看roundAbsLevel=0；最后的隐含非零位置不一定走这个零早退。

### 有限bypass跳过

remRegBins<4时rate不映射，但prediction仍可能让额外up候选进入。因此只有同时满足：

```text
remRegBins < 4
且
(upAbsLevel == roundAbsLevel 或 upAbsLevel == minAbsLevel)
```

才确认没有候选准入和映射依赖。其它bypass位置保留原预测。本次数学检查找到了“所有bypass都跳过”的反例。

初版限R3-local/R6；R7 shadow、其它额外量化搜索、完整诊断需求走原路径。这里测试的是候选/映射依赖签名，仍需完整原生q/CABAC回归。

## 4. 优先项B：0/1/2支持直接解，不再排序和评分

新r36Predict尚无此快路径。当五邻域幅值均≤2，定义：

```math
n_1=\#\{a_j=1\},\quad n_2=\#\{a_j=2\},\quad d=n_2-n_1,\quad c=\max(L,U).
```

n=n1+n2≥3时，只有identity和p=2两种不同动作。原CI为C(1)=1、C(2)=C(3)=3：

```math
S(0)=n_1+3n_2,\qquad S(2)=3n_1+n_2.
```

R3精确解：

```math
p_{R3}=\begin{cases}
2,&c\le1\text{ 且 }d\ge2,\\
0,&c=2\text{ 且 }d\le-2,\\
c,&\text{其它情况}.
\end{cases}
```

差2来自原最大正贡献删除后的H>0，不是新阈值；幅值>2回现有精确通用路径。

| dense模式 | c≤1 | c=2 |
|---|---|---|
| R3、R6-5/6/7 | d≥2则2，否则c | d≤−2则0，否则2 |
| R6-1 | d≥2则2，否则0 | 总是0 |
| R6-2 | d≥2则2；d=1则0；d≤0则c | d<0则0，否则2 |
| R6-3 | d>0则2，否则c | d<0则0，否则2 |
| R6-4 | d>1则2，否则c | d<1则0，否则2 |

n<3保留各组原稀疏处理，Current=1的原整数返回也不随意规范化。例如h=(2,1,1,0,0)，R3返回2，R6-2返回0；不能共用错误查表。这里是相同算法的专用实现，不是低幅值时改用新算法。

## 5. 优先项C：R6-3/4解析评分，替代当前双循环

前提：原整数CI、非identity预测值p来自非零支持。Current=max(L,U)满足；支持外任意Current的通用API不得无条件套用。

### R6-3

每个非identity候选必命中一个样本而映射为1，非零CI最小值为1：

```math
T_3(p)=\begin{cases}
S(0)-\min_jC(a_j),&p\le1,\\
S(p)-1,&p>1\text{ 且 }p\in\{a_j\}.
\end{cases}
```

支持含1时，所有候选减同一个1，排序与Raw一致；保留原Current-first和平局返回整数。

### R6-4

合法CI非减。a=p贡献C(p)-1；a<p被上推，不产生正节省；a>p不变：

```math
T_4(p)=\begin{cases}
S(0),&p\le1,\\
S(p)+C(p)-1,&p>1\text{ 且 }p\in\{a_j\}.
\end{cases}
```

直接复用r36Guard已有的前缀S(p)，无需每个候选遍历min/max。最大项不乘命中次数。**不推广到非单调fractional cost。** 当前小模板u≤5，因此结构减少不保证实际5倍加速；需要测净耗时。

## 6. 其它已从新源码确认可继续检查的点

### R6-1/2的无用guard

新内核目前先完整调用r36Guard再应用fallback。动作路径中：

- n≥3且raw与Current等价：R6-1输出0、R6-2原Current。
- raw严格不同且为identity：两组最终都输出0，无论guard是否通过，可不算G/H。
- raw严格不同且非identity：继续原guard。

完整诊断需要gain/margin时仍算。若raw赢家p>Current且只出现一次，唯一正贡献来自命中p，删除最大贡献后H≤0，可执行原拒绝fallback；不删除候选后另选次优。

### TU首行/首列

这些位置五邻域最多两个同轴值，n<3必然成立。R3-local/R6-1～4直接Current；R6-5～7因L/U不能同时非零而直接0。不是每个CG边界都可这样做，前一CG仍可能提供合法支持。

### CI平台避免第二次syntaxCost

新R36ScoreTable对所有v<largest仍调用syntaxCost(v+1)。可利用：

```math
C(2m)=C(2m+1),\quad m\ge1.
```

偶数a≥2直接复用C(a)。a≥10时若两个Rice商相同，也复用：

```math
(((a-10)\gg1)\gg r)=(((a-9)\gg1)\gg r).
```

不截断高幅值，跨阈值继续原函数。已有至多九次cost是上界，这项可能进一步省重复Rice求值。

### Rice escape循环

保留普通Rice和饱和分支后：

```cpp
while (code > ((2u << prefix) - 2)) ++prefix;
```

严格等价于整数位长：

```math
prefix=\lfloor\log_2(code+1)\rfloor.
```

使用工程整数位长/前导零，不用浮点log2；保留饱和检查和移位范围。只有escape确为热点才列优先项。

## 7. 实施和时间目标

建议先做profile和触发计数，再依次检查：

1. RDOQ无使用依赖的零早退/bypass跳过；
2. 0/1/2直接解；R6-3/4解析分数；R6-1/2identity出口；
3. TU边界、CI平台、Rice位长。

不为这些优化新增R实验编号；逐项保留原模式和工程开关，完整bitstream、q/absSum和CABAC状态一致。不要只以BD-rate接近或重建hash一致代替码流比较。R3-3/4历史状态、其它工具必要回放不动。

重型跨trial缓存暂不优先：键必须含完整支持、mode、Rice/range，键读取和比较可能比现在的小内核更贵；单次Writer缓存已经存在。

文档记录的目标是旧R3-1约101.4%降至100.8%。若它确为同条件无统计基准，需要减少旧R3总时间约0.592%，或额外1.4%开销的42.9%。当前旧值是否含观察未确认，已优化内核也尚无完整视频计时，先测真实起点，不能用合成夹具比值外推。

## 8. 本次验证与文件

本次实际执行Python数学参考：0/1/2动作1,944项；R6-3/4评分149,080项；R6-1/2guard出口30,980项；单个向上赢家拒绝2,235项；CI相邻单调262,136项；偶数平台131,064项；Rice商平台245,755项；Rice循环/位长48,115项；TU边界15,120项；RDOQ依赖签名18,048项。

总计904,477项断言通过。病例并非独立统计样本，数量不证明视频收益或速度。没有运行生产C++或原生视频；这些检查不是TsR36Exact完整集成验收。

完整展开文档、`verify_exact_rules.py`、`validation.json`随会话附件 `R3_R6_Remaining_Optimization_Bundle.zip` 提供。包内脚本只用Python标准库，不调用编码器。本Git文件是分析摘要，不是完整独立复算目录。

## 9. 来源

原语义读取于4421232，最终优化内核读取于0d1e8b0：

- `source/Lib/CommonLib/TsR36Exact.h`：本次新增可见优化内核，blob `3b0efb91d6b76c877624a1aec46963e9de76293c`。
- `source/Lib/CommonLib/TsFixedPrediction.h`、`TsR6Prediction.h`：原CI、Rice、guard与七组fallback。
- `source/Lib/CommonLib/QuantRDOQ.cpp`：blob `d5d8cc712c3ca24b29ed17073e377aaea3f9fa1e`，补推前后未变化；predictor调用、zero早退和allowUp依赖。
- `source/Lib/CommonLib/ContextModelling.h`：新R36提前dispatch。
- `docs/experiments/TS_Predictor_R3_R6_Exact_Optimization.md`：已完成优化、原生回归及局部计时报告。
- `docs/experiments/TS_Predictor_Statistics_Defaults.md`：当前统计开关与重编译要求。
