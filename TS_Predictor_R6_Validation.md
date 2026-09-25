# R6 本地验证（2026-09-23）

版本R6-20260923-v1。以下是正确性与活动测试，**不是完整CTC或BD-rate收益结果**。
源码/测试/二进制指纹及原生测试输出见 `runs/ts_r6_smoke/native_validation.json`。

## 1. 构建与回归

- 独立Release `build/ts-r6`，CMake仅设输出路径/编译类型，不选择实验宏。
- 在TypeDef.h master=0时构建 `build/ts-r6-off`，随后恢复master=1、所有模式=0，默认Current。
- 原R3/R5/anchor二进制保持不变，源码R3 guard未改，旧结果工作簿和Reference未改。
- ON Encoder SHA：`b1356cc713c1efde42d24734e5879e383e72587f02da342cff5257f08c0f5ed7`。
- ON Decoder SHA：`bab606c9237910b0f0ec91d7b4878fab4ee8cbecc9f9a68f7fd8df74f1263064`。
- OFF Encoder SHA：`1169acd11e6491eadbaa01c6d72d29d7b88a88637f7139dd4c6757506aee3240`。
- OFF Decoder SHA：`75702fcfbaeb445d6236f3c2d47b13051c22f558e8fd55e71da48437d6fffd62`。

## 2. 独立规则与因果性

`ts_r6_design_check.cpp`：五幅值0..7、Rice1/4，共 **458752** 个模板/模式检查。
独立实现raw trim和归一化saving评分，验证候选/平局、n计数、全部边界及remap逆变换。
七组都有相对R3的非等价预测与实际映射样例；不是仅观察到继承的R3变化。

- 密集四组n<3严格保持R3；稀疏三组n≥3严格保持R3。
- 两fallback模式都保留R3已接受结果；模式2不改变无优胜者分支。
- n=0无实际改变；LU-only三种预测器中max保持Current，mean/min有区别样例。
- 正样本集合中的每个幅值候选确实有最小cost=1；含幅值1时raw trim退化为原总cost排序，独立断言通过。
- 定向例(3,2,2,0,0)：原R3 Current=3、winner=2、H=0，MODE4选2，验证重复支持没有被全部消除。
- 200个8×8 signed网格、七组，共 **89600** 个宽幅值规则/因果/符号检查。
  幅值包含0/1、语法边界、255/32767，Rice1..4、range15/20；当前/未来读取由回调断言禁止。

这是公式和输入约束验证；复用的C本身仍是语法代理，不将其当CABAC损失模型的独立验证。

## 3. 原生CABAC往返

`TsR6CodecTest`每组240个人工TU，七组共 **1680 TU**，每组2257个CG。
宽/高2、4、8、16、32的方形及矩形，YUV、intra/inter、BDPCM、Rice1..4、大幅值、稀疏和全零CG。
人工几何覆盖不等于真实配置观察到这些TU尺寸。

- 原生Writer/BinEncoder与Reader/BinDecoder逐CG系数、regular预算、整TU完全一致。
- 每组35524个预测位置检查native grouped scan因果性、未来系数污染不变性、幅值-only Reader视图不变性。
- 七组各有针对性regular-path映射改变样例，不以函数触发但实际bypass冒充覆盖。
- mean/min的针对性样例强制为LU-only布局，而不是仅触发三组共享的稀疏NoPred规则。
- 所有持久state/recentMargin保持0，未引入跨CG/TU历史或RDOQ搜索缓存。
- 初次测试程序构建的misleading-indentation告警已用花括号修正；未更改算法或降低警告等级。

## 4. 合成端到端

`runs/ts_r6_smoke/validation.json`：**166项独立编码**，每项2帧64×64。
13个case覆盖QP0/22/27/32/33/37、TS-off、lossless、TSRC-off、DQP、BDPCM、LB、RA。
每case有七组R6＋Current＋R3-1＋原anchor＋新OFF；QP0额外覆盖其余23个旧模式。

- 166项全部解码picture hash通过，Writer/Reader逐CG trace系数hash及预算一致。
- Current与OFF各13例均对原anchor bit-exact；关闭TS/TSRC时各模式一致。
- 额外25个旧模式QP0对保留R5程序bit-exact；额外七组关闭trace/统计后码流一致。
- OFF Decoder另外解码QP22 OFF码流，2/2 picture hash OK；不输出重建文件。
- 最初153项，随后复用完成任务补13项OFF；不是153+166项。额外观察关闭和旧二进制回归不计入166。
- 合成数据是输入YUV，未输出重建YUV；共有3011条R6聚合记录，日志不是逐系数导出。

| MODE | active位置 | 相对R3映射改变 | 其中LU-only改变 |
|---|---:|---:|---:|
| 1 | 10625 | 2562 | 0 |
| 2 | 10560 | 799 | 0 |
| 3 | 10430 | 634 | 0 |
| 4 | 10685 | 1504 | 0 |
| 5 | 9992 | 1737 | 0（规则要求） |
| 6 | 10214 | 1785 | 11 |
| 7 | 10141 | 1798 | 25 |

模式5/6/7的改变分别全在n1/n2：584/1153、595/1190、590/1208；n0与n≥3全部0。
密集四组n0/1/2新增映射全部0；逐行统计恒等式也经过检查。
注意各模式闭环q与TS集合不同，不能直接用这些数量比较效率或用模式6减5的数量当精确LU因果贡献。
`r6_incremental_activity_covered=true`只证明本次短测有新增机制覆盖，不证明RD收益。

## 5. 限量真实预检

本地另运行BasketballDrill、LBeu、QP22、3帧，Current/R3-1/七组R6共9项，**全部编码及解码hash通过**；结果目录 `runs/ts_r6_real_preflight/`。
单序列单QP短帧不用于BD-rate，不代表完整纹理/运动/分辨率覆盖，也不据此重新排序候选或修改公式。
完整结果和聚合审计在该目录的 `validation.json`；1754条R6聚合记录，未输出重建YUV或新工作簿。

| MODE | active位置 | 相对R3映射改变 | 其中LU-only改变 |
|---|---:|---:|---:|
| 1 | 9302 | 171 | 0 |
| 2 | 9845 | 81 | 0 |
| 3 | 9938 | 45 | 0 |
| 4 | 9395 | 138 | 0 |
| 5 | 10075 | 312 | 0 |
| 6 | 9585 | 312 | 2 |
| 7 | 10117 | 317 | 6 |

七组码流SHA均不同于R3；5/6/7彼此也不同。mean/min有实际LU分支变化，但仅2/6次，不能夸大覆盖。
三帧中码率和PSNR都变化，不能拿码率降低的百分比当成同质量收益；本轮仍无BD-rate结论。

## 6. 脚本

- 7项宏测试通过：32个ON默认＋OFF、1024次显式覆盖、R6与所有旧默认冲突、非法范围、master-off误请求。
- 18项batch测试通过：七新模式共享池、编号目录、原逐组报告时机、resume/失败重试保护。
- 19项基础BD分析测试通过：R6编号/flat目录、分量BD后6:1:1、缺点拒绝和Current Reference保护。
- 全部analysis测试共31项通过。测试中的模拟FAIL/RETRY是故障注入，测试结论为OK。
- 首批2/4/5共84项LB CE半帧dry-run通过，实际帧数250/300/150，解码hash、无重建、逐组XLSM参数正确。
- 加入6/7的140项计划及三序列两QP三帧的54项快速计划也通过dry-run；未执行这两份编码计划。
- 未启动正式CTC、未创建虚假结果工作簿、未改变已有服务器结果。

结论：本轮已具备可运行实验和有效增量活动；是否解决偏置或改善稀疏区域RD，仍须完整闭环结果回答。
