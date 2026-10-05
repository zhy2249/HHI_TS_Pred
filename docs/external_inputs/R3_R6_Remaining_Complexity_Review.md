# R3 / R6：已有等价优化之后的剩余复杂度空间

## 1. 结论与读取边界

读取固定快照 `4421232d2858d47ff3c0f56f55ac86d8315646ac`，分支 `experiment/ts-predictor-study`。本次只新增分析，不改codec、实验编号、候选集合、代价、guard、fallback、量化搜索或正式结果。

**仍有优化空间，但不应重复把去重、前缀评分和Writer缓存当成新方案。** 最新文档已记录本地完成这些优化。后续优先级应为：预测值不被使用时避免计算；0/1/2幅值域的精确直接解；R6-3/4的整数代价专用化简；CI平台与Rice整数位长复用。

证据边界：Git同步了实施报告，`TsR36Exact.h` 在本次提交返回404；报告也说明优化源码、测试脚本保留本地工作树。因此可独立核对的是已提交原R3/R6和QuantRDOQ，新内核细节只能按文档判断。以下待检查项不等于断言本地内核一定没有覆盖；先对照本地实现，已有项不重复开发。

范围为R3-1、R3-2启用分量和R6-1～7；不扩展到R3-3/4历史自适应。保留R3-2色度native回退。Python参考只验证代数及代码路径契约，不是生产C++、完整CABAC、视频或速度认证。

## 2. 已经记录的优化与局部结果

见[已有R3/R6精确优化](../experiments/TS_Predictor_R3_R6_Exact_Optimization.md)：

- 非零幅值去重、共享C(a)及可达C(a+1)、精确前缀评分；真实Current=max(L,U)下dense路径至多九次cost调用。
- predictor动作路径与完整诊断分离，不再为一个最终整数输出反复计算parent、hit、score等字段。
- 直接使用scan已有x/y/idx和R3/R6提前分派；无状态路径避免无用finish诊断调用。
- 一次Writer子块调用内用栈数组/bitmask复用regular remapping，不跨量化trial缓存。
- 宏保留原路径对照，已登记局部payload和q/absSum一致性检查。
- [最新统计设置](../experiments/TS_Predictor_Statistics_Defaults.md)说明各轮统计改为显式开启；旧文档的默认开启不再代表当前本地版本，旧二进制/外部环境也不会自动变化。

文档记录的计时中位数（优化/原实现）：

| 模式 | 合成原生语法/参考夹具 | 合成TS-RDOQ夹具 |
|---|---:|---:|
| Current未改动对照 | 1.0122 | 0.9993 |
| R3-1 | 0.9317 | 0.7733 |
| R6-2 | 0.9188 | 0.7465 |

这些是已报告的合成局部计时，不是本次重测或整编码加速。不能把22.7%/25.3%的量化夹具降幅直接乘到101.4%上，也不能宣布已到100.8%。

## 3. 优先项A：先证明预测值会被使用

### 3.1 不重复做已完成的量化循环外提

已提交`QuantRDOQ.cpp`在候选循环外调用一次`magnitudeActionTS`，再将prediction/protect传给`xGetCodedLevelTSPred`。后者循环只做映射和rate计算。不能把“每个候选改为只算一次predictor”作为新的优化收益。

### 3.2 roundAbsLevel=0且非末尾：避免无用predictor

原路径先算action，再进入如下早退：

```cpp
if (!isLast && coeffLevels[0] < 3) {
    // 仍需执行原来的zero cost、significance和bin输出更新。
    if (coeffLevels[0] == 0) return 0;
}
```

roundAbsLevel=0时，down=0、up=1、min=1，up不是独立新增候选。若!lastCoeff成立，prediction既不影响候选集合，也不会被当前level评分读取。

对无状态R3-local/R6、无额外观察需求的动作路径，可在原调用之前判定该条件并跳过predictor。lastCoeff按原“CG末尾且此前无非零”条件提前求得。**不跳过零代价/significance/bin输出，不提前改变CG判零，不跳过原量化更新。**

不能仅检查roundAbsLevel=0：受隐含非零约束的最后位置可能仍比较候选，必须保留原逻辑。

### 3.3 bypass也必须检查allowUp依赖

remRegBins<4时rate不应用remapping，但prediction仍可能影响额外up候选是否进入搜索。安全的另一条件是：

```text
remRegBins < 4
且
(upAbsLevel == roundAbsLevel 或 upAbsLevel == minAbsLevel)
```

此时没有独立up候选，也没有bypass映射依赖，才可省略predictor。不能一律跳过bypass预测；本次数学测试已找到这种错误改法的反例。

初版限于R3-local/R6，额外量化搜索、R7 shadow或完整诊断需求走原路径。参考验证只比较候选与会读取的映射签名，完整原生q/CABAC回归仍需工程实施。

## 4. 优先项B：0/1/2域可以直接解出原算法

当五邻域幅值均≤2，定义：

```math
n_1=\#\{a_j=1\},\quad n_2=\#\{a_j=2\},\quad d=n_2-n_1,\quad c=\max(L,U).
```

对n=n1+n2≥3，只有identity与p=2两种不同动作。原CI为C(1)=1、C(2)=C(3)=3：

```math
S(0)=n_1+3n_2,\qquad S(2)=3n_1+n_2.
```

原R3精确结果：

```math
p_{R3}=\begin{cases}
2,&c\le1\text{ 且 }d\ge2,\\
0,&c=2\text{ 且 }d\le-2,\\
c,&\text{其它情况}.
\end{cases}
```

差2来自原H>0，不是新门控。无需候选排序和Rice评分；支持出现>2时回现有通用精确实现。

R6各组必须保留独立语义：

| dense模式 | c≤1 | c=2 |
|---|---|---|
| R3、R6-5/6/7 | d≥2则2，否则c | d≤−2则0，否则2 |
| R6-1 | d≥2则2，否则0 | 总是0 |
| R6-2 | d≥2则2；d=1则0；d≤0则c | d<0则0，否则2 |
| R6-3 | d>0则2，否则c | d<0则0，否则2 |
| R6-4 | d>1则2，否则c | d<1则0，否则2 |

例如h=(2,1,1,0,0)，R3返回2，R6-2按拒绝后NoPred返回0；不能共用一个错误表。n<3仍按原稀疏规则，Current=1的原整数返回也应保留。这是原公式专用实现，不是改变低幅值算法；收益取决于真实试算覆盖及新增分支成本。

## 5. 优先项C：R6-3/4不必逐候选重新求min/max

前提：原整数CI，非identity预测值p来自非零支持。Current=max(L,U)满足这一条件；若独立通用函数传入支持之外的Current，必须回通用实现。

### R6-3

每个非identity候选命中至少一个样本，映射为1；CI的非零最小代价为1：

```math
T_3(p)=\begin{cases}
S(0)-\min_jC(a_j),&p\le1,\\
S(p)-1,&p>1\text{ 且 }p\in\{a_j\}.
\end{cases}
```

支持含1时，所有候选统一减1，排序与Raw一致；仍保持R6自己的Current-first和平局整数返回，不把Current=1自动改成0。

### R6-4

合法原CI非减。候选命中a=p提供C(p)-1正节省；a<p被上推不提供正节省；a>p不变：

```math
T_4(p)=\begin{cases}
S(0),&p\le1,\\
S(p)+C(p)-1,&p>1\text{ 且 }p\in\{a_j\}.
\end{cases}
```

无需每个候选重扫最大节省；max项仍不乘重复次数。**不能推广到可能非单调的fractional cost。** 本次测试含合法幅值、Rice1～8和range15/20随机/边界；原生集成仍需确认所有实际range及limited escape。

## 6. 其它精确优化

### R6-1/2省去不影响最终动作的guard

n≥3：raw与Current等价时，R6-1直接0、R6-2原Current；raw严格不同且为identity时，两组无论guard结果如何都返回0；只有raw严格不同且非identity才必须做guard。完整诊断需要G/H时仍算原字段。

若raw赢家p>Current且只出现一次，则唯一可能正贡献来自命中p，删最大贡献后H≤0；可直接执行各自的拒绝fallback，不能改成剔除该候选后重新选次优。

### TU边界

TU首行/首列的支持最多两个同轴位置，n<3必然成立。R3-local/R6-1～4直接Current；R6-5～7因L/U不可能都非零而直接0。**不能把每个CG边界当TU边界**，前一CG仍可提供合法邻居。分量和BDPCM检查保持原样。

### CI平台复用

```math
C(2m)=C(2m+1),\quad m\ge1.
```

偶数a≥2可直接复用C(a)作为C(a+1)。a≥10时若下列Rice商相同，也可复用：

```math
(((a-10)\gg1)\gg r)=(((a-9)\gg1)\gg r).
```

其它边界照旧调用，不裁剪高幅值。已有九次cost是上界，这项可能继续减少重复Rice求值；不是对实际时间的百分比承诺。

### Rice前缀整数位长

保留普通Rice及饱和分支后，原循环：

```cpp
while (code > ((2u << prefix) - 2)) ++prefix;
```

精确等价于：

```math
prefix=\lfloor\log_2(code+1)\rfloor.
```

用工程整数位长/前导零实现，不用浮点log2；保留饱和判断、移位宽度及code+1范围。小幅值不会走这里，只有确认escape是热点才优先做。

## 7. 实施优先级和时间目标

先核对本地TsR36Exact.h，已实施项不再重复。优先顺序：

1. 测调用覆盖，验证RDOQ确实不使用prediction的零早退/bypass状态；保持所有原输出更新。
2. 0/1/2精确快路径；R6-3/4解析分数；R6-1/2identity出口。
3. 视热点加入TU边界、CI平台、Rice位长。每项单独开关与计时，净开销更高的分支不强留。

重型跨trial缓存不列第一优先：需匹配完整支持、mode、Rice/range，缓存键读取和比较可能比现在的小内核更贵。原Writer单次CG缓存已做，不重复估算收益。

文档记录的目标是旧R3-1相对Current约101.4%降至100.8%。如果二者是同条件、无统计基准，则需要减少旧R3总时间约0.592%，或减少额外1.4%开销约42.9%；不能将两种百分比混淆。目前旧101.4%是否含观察未确认，新精确优化尚无完整视频计时，应先测真实起点。

最终要求同模式完整bitstream逐字节一致，q/absSum、重建和CABAC状态一致；不是只看BD-rate接近。双方关闭统计/trace，控制编译、线程、负载及顺序。R3-3/4历史状态和其它工具必要回放不动。

## 8. 本次数学验证与交付

本次执行Python标准库参考脚本，以下检查全部通过：

| 检查 | 案例数 |
|---|---:|
| 0/1/2精确predictor | 1,944 |
| R6-3/4完整评分化简 | 149,080 |
| R6-1/2guard出口 | 30,980 |
| 单个向上赢家的拒绝 | 2,235 |
| 合法CI相邻单调性 | 262,136 |
| 偶幅值平台 | 131,064 |
| 同Rice商平台 | 245,755 |
| Rice循环/位长 | 48,115 |
| TU边界predictor | 15,120 |
| RDOQ候选及映射签名 | 18,048 |

合计904,477项断言案例。案例不是独立统计样本；数量不能证明视频收益或速度。已找到blanket bypass skip的反例。没有运行原生C++或视频，本次不是TsR36Exact的完整集成验收。

完整展开文档、`verify_exact_rules.py`与本次`validation.json`随会话附件`R3_R6_Remaining_Optimization_Bundle.zip`交付；本仓库文件是分析摘要，不是独立完整复算目录。运行包内脚本只需Python标准库，不会调用编码器。

## 9. 原始依据

固定读取版本：`4421232d2858d47ff3c0f56f55ac86d8315646ac`。

- `docs/experiments/TS_Predictor_R3_R6_Exact_Optimization.md`：已有优化、局部计时和未推送源码边界。
- `docs/experiments/TS_Predictor_Statistics_Defaults.md`：当前本地统计默认值与更新二进制要求。
- `source/Lib/CommonLib/TsFixedPrediction.h`：原R3、CI/Rice、Current平局、guard。
- `source/Lib/CommonLib/TsR6Prediction.h`：七组R6独立fallback与对称目标。
- `source/Lib/CommonLib/QuantRDOQ.cpp`：action位于候选循环外、zero early return、allowUp与bypass依赖。
- `source/Lib/CommonLib/CommonDef.h`：COEF_REMAIN_BIN_REDUCTION=5。
