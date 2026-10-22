# R13 KeepHit：实现、观察与运行

日期：2026-10-22；算法 revision：`R13-KH-168-v1`。实现依据[冻结设计](TS_Predictor_R13_Experiment_Design.md)。
正式 anchor 是 **Current**，机制父对照是 R2-2 `r2_risk`，不是 R3 或 NoPred。
本轮没有序列编码结果、BD-rate 或整体复杂度结论。局部验证与尚未验证项见第5节。

## 1. 实际启用方式

直接编辑 `source/Lib/CommonLib/TypeDef.h`：

```cpp
#define JVET_BJUT_TS_FIXED_PREDICTOR 1
#define JVET_BJUT_TS_R13_MODE        1
```

| R13_MODE | runtime / batch 名称 | 核心区别 | 收件目录 |
| --- | --- | --- | --- |
| 0 | 不选择 R13 | 所有算法模式为0时仍是Current | 不适用 |
| 1 | `r13_keep_hit_uniform` | 五个物理位置权重11111 | `experiments/ts_predictor_r13/r13_1_keep_hit_uniform/LB_CE/` |
| 2 | `r13_keep_hit_spatial` | 五个物理位置权重22111 | `experiments/ts_predictor_r13/r13_2_keep_hit_spatial/LB_CE/` |

两组内部policy为98/99，不要将其写入公开MODE宏。交付源码默认R13_MODE=0，所有算法模式仍为0。
启用一组时，旧固定、条件、R2～R12算法模式必须全部关闭；冲突、越界及master-OFF请求实验均报错。
已有R36/R12等价优化开关不是算法模式，允许保留1。R10的专用cache不可用于R13。

宏修改后重新编译两端；省略runtime时使用宏默认。显式 `TS_FIXED_PREDICTOR` 或batch的
`--fixed-predictors` 强制覆盖编译默认。两组wrapper显式选择两个runtime，因此覆盖宏默认；
若只希望按宏运行，用原 `batch_test.py` 并省略 `--fixed-predictors`。

启动行应包含 `TS R13 revision=R13-KH-168-v1`、公开mode、runtime、`parent=R2-2`、
`rho=21/2`、`score-scale=168`、`weights=11111|22111`、`guard=none` 和实际stats/trace状态。
新算法改变隐式predictor，Encoder/Decoder须使用匹配模式，不宣称兼容未修改的标准解码器。

## 2. 修改位置和不变项

- `TsR13Prediction.h`：独立纯函数评分。五槽位L/U/D/LL/UU，n是非零位置数；n<3原样返回Current。
  n>=3沿用R2-2候选、identity归并和严格小于的tie规则。固定168倍损失、D饱和而U线性尾部；
  identity判断先于邻近命中。按不同幅值缓存C(m)/必要C(m+1)，重复位置累计权重，分数64位。
  实际选择路径不构造诊断分数数组/次优margin；诊断接口用同一内核。
- `ContextModelling.h`：共享五个物理邻居读取与R13分派，负值先扩宽取幅值。
  同一入口供RDOQ、Writer、Reader使用，不读取当前目标原系数、失真或lambda。
- `ContextModelling.cpp` / `TsR13Stats.h`：仅在最终Writer可选观察；Reader仅可选有界trace。
  R13没有跨CG历史，结束后明确退出，不误入旧Current/directional统计。
- `CABACWriter.cpp` / `CABACReader.cpp`：只增加观察用的实际CG入口budget快照；关闭观察时不保存。
- `TsFixedPrediction.h` / `TypeDef.h`：模式、互斥、runtime覆盖、身份与观察参数验证。
- `batch_test.py` / `ts_predictor_naming.py`：模式注册、R13身份记录与续跑指纹；沿用原调度器。

**未修改 `QuantRDOQ.cpp`、实际remapping、TSRC语法或CABAC概率模型。** 但不同p可能改变原有
allowUp候选和最终q，不能说候选集合永远不变。普通TS在纯bypass情况下仍可能改变RDOQ的
up机会；BDPCM分流路径无allowUp且禁用remapping，作为独立局部不变量验证。
新评分是量化机会代理，不是fractional bits或真实RD cost；q代理普通舍入幅值、固定rho、
非命中减一/置零未完整建模等限制，仍按冻结设计解释，不因实现完成而视为得到证明。

## 3. 默认关闭的统计

| 环境变量 | 默认 | 含义 |
| --- | --- | --- |
| `TS_R13_STATS` | 0 | 最终Writer聚合，0/1严格验证 |
| `TS_R13_TRACE` | 0 | 有界系数详情与Writer/Reader CG摘要，0/1严格验证 |
| `TS_R13_DETAIL_LIMIT` | 64 | 进程级详情上限，0～1024；两端CG摘要各自同上限 |
| `TS_R13_POC` | 未设 | 未设全POC；设置必须非负整数，限定一个POC |

观察可附加于Current、R2-2、R3-1、R6-2和两个R13轨迹；其它轨迹显式报错。
每个最终系数在其轨迹上只统计一次，**同一H同时计算Uniform/Spatial及旧R2**，
不是对未选TS块做无偏抽样。算法必要计算不依赖观察开关。统计时会复制局部CG描述并回放真实
三遍budget，使用无输出sink；没有修改真实coeff、CABAC context或RDOQ状态。

stderr中的 `TS_R13_STATS_HEADER` / `TS_R13_STATS` 为CSV，按轨迹、shadow mode、分量、W/H、
实际CU QP、intra/inter、BDPCM、CG数、cutoff、n及权重和汇总；sequence、配置和nominal QP
由任务身份文件关联。cutoff为10/2/0，分别代表完整regular、仅第一遍regular和bypass；
BDPCM即使cutoff非零也不标为实际remap。零CG没有实际编码的系数，仍保留最终q人口。

每个shadow mode都有完整独立分母，**不能把两mode的TU/CG/系数数相加当总人口**。
`cutoff=n=weight_sum=-1` 是TU/CG计数专用行，不重复加入系数计数。只有coded TSRC调用能观察；
没有残差编码调用的全零TU、未选TS块、TSRC-disabled其它路径不在该人口中。
Current等价、非Current identity、其它选择互斥；另存独立identity标志。
n<3没有score，margin未定义；只有一个候选也没有次优margin。原始分数单位是168，非bits。

`current_tie_broken`表示至少有一个候选与Current在旧cost下平局、而新cost严格更低；
**不表示最终一定改选该候选**。Uniform的旧cost就是R2-2；Spatial使用相同22111权重的旧cost，
它是加权旧评分诊断，不是声称R2-2原来使用空间权重。
hit/down/up表示最终所选非identity p被邻居m=p/m=p+1/m=p-1支持；稀疏区也计实际Current的支持。
它们不是目标系数预测正确率或真实RDOQ命中次数。

提取示例（对已有含统计日志执行，不启动编码）：

```bash
python3 scripts/ts_r13_activity.py runs/path/to/encoder.log \
  --sequence PartyScene --configuration LBeu --nominal-qp 22 \
  --output runs/ts_r13_activity/PartyScene_q22.csv
```

导出保留所有原字段，另给 `mean_margin_per_weight=margin_sum168/(168*weight_sum*valid_margin_count)`；
缺失margin留空。拒绝无统计、截断、重复report及覆盖源日志，不推断文件名标签、不计算BD-rate。
多序列一起导出时不要给一个错误的公共sequence/QP标签。
默认不输出逐系数大日志；调试详情上限以进程计，不是每TU重新计数。

## 4. 构建、测试和服务器命令

从仓库根目录构建，CMake只控制构建位置，不选择算法：

```bash
cmake -S . -B build/ts-r13 -DCMAKE_BUILD_TYPE=Release -DNX2_TOPLEVEL_OUTPUT_DIRS=OFF
cmake --build build/ts-r13 --target EncoderApp DecoderApp TsR13NativeTest -j4
python3 -m unittest discover -s scripts -p 'test_ts_r13_*.py'
python3 scripts/test_ts_r13_native.py --exe build/ts-r13/bin/TsR13NativeTest --jobs 2
```

最后一条仅调用合成TU测试程序，不启动EncoderApp/DecoderApp，不读取视频。
如需重做旧源码对照，用同一个harness在冻结 `c7cb2a438808167ad2c2a37d711d99852235b391`
源码构建，再向runner提供 `--baseline-exe <旧源码同测试程序> --baseline-revision <SHA>`；
未提供时报告明确标记基线对照NOT RUN。生成的小验证报告位于 `runs/ts_r13_native/validation.json`。

先规划（`--input-dir`改为服务器视频路径）：

```bash
bash scripts/run_ts_r13_lb_ce.sh --input-dir /path/to/videos --jobs 10 --dry-run
```

以后获准正式运行及同参数续跑：

```bash
bash scripts/run_ts_r13_lb_ce.sh --input-dir /path/to/videos --jobs 10
```

两组各28项，共56项；QP22/27/32/37、LBeu C/E半帧，INI已为250/300/150等实际帧数，不再除2。
不重跑Current。共享任务池无组间完成屏障、默认不保存重建、解码hash校验；一组全部返回即
独立复制写其JVET-hhi.xlsm，其它组继续。失败不冒充成功，重试后刷新，源Reference只读。
wrapper默认关闭旧轮观察，R13观察默认0但尊重显式设置；正式计时确保全部观察关闭。

每项R13任务记录 `.identity.json`，包括固定规格、实际命令、帧数、配置SHA256、两端二进制SHA256、
本地checkout提交及tracked补丁摘要。**本地checkout不是二进制构建来源证明**，明确保存
`binary_build_origin_verified=false`；还需服务器保存实际源码/未提交补丁与输入版本。
未跟踪源码名称仅提示不完整身份，不替代其内容归档。R13环境、配置或二进制变化会使其旧done失效；
没有显式R13环境的非R13任务保留旧观察指纹格式，不无故令历史任务重跑。

本地只做dry-run，不执行上面的正式命令。短帧活动集合和是否进入B仍按冻结设计逐阶段授权。
结果分析继续逐分量BD-rate后6:1:1加权，CE七序列等权；不自动补缺点，无结果不登记虚构台账数值。

## 5. 本地验证状态

已完成纯函数与脚本检查：

- 576,788次生产决策对独立无缓存参考，包括n、物理权重、候选、排序、tie、分数和诊断；
  Rice0/1/4/8与15/20动态范围穷举及极值随机，覆盖稀疏、重复和最大幅值。
- D/U生产表1024项对独立Fraction积分，单点loss8704项对积分；设计中的三类活动样例通过。
  同H下Uniform不能把旧非identity赢家改成identity的性质通过。6个纯函数测试通过。
- 宏/默认/runtime覆盖18项；100种模式默认与覆盖、R13互斥、master-OFF及观察非法输入检查通过。
- R13 batch8项、旧fixed batch21项、统计默认2项、活动导出3项通过；shell语法/diff检查通过。
  mock测试验证跨组调度、分组即时写表、fingerprint失效；真实wrapper只dry-run，56项且无重建。

上述纯函数穷举/随机另用UBSan完整执行，576,788次决策通过，无未定义行为报告。
master-OFF使用实际构建参数，对ContextModelling、QuantRDOQ、CABACWriter、CABACReader
四文件执行`-fsyntax-only`通过；它是关闭总开关的编译检查，不冒充OFF整码流验证。

合成TU测试已完成，六个模式为Current、R2-2、R3-1、R6-2、R13-1、R13-2：

- 每模式180个TSRC TU、1718个CG、27032次未来位置扰动因果检查。宽高覆盖2/4/8/16/32的
  25种组合、Y/U/V、Rice1～8、QP0～63、低budget及pure-bypass、HOR/VER BDPCM；
  人工构造覆盖不意味着这些几何/组合均在当前CTC配置中可达。
- 真实Writer/Reader解回同一q、每CG预算和全部context相同；独立语法replay的fractional bits
  与原生BitEstimator逐CG相等。此项验证语法回放，不把KeepHit评分变成CABAC bits。
- 每模式240个QuantRDOQ TU，19个全零输入、32个非零输入最终清零、HOR/VER BDPCM各30个；
  清零后恢复原输入得到相同q/absSum，原输入和传入CABAC context不变。
- 六模式观察关/开的约171MB完整记录（CABAC字节、q/absSum、概率状态、预算等）逐字节一致。
  四个旧模式另与冻结c7cb2a4源码、同harness的完整记录逐字节一致；不只是比较一个hash。
- 六模式BDPCM记录完全相同。两个R13模式彼此且相对R2的记录不同，证明合成夹具有实际活动；
  不将人为夹具的频率或字节差解释为自然视频收益。
- 每模式双shadow的TU/CG/系数分母精确吻合，各7对Writer/Reader有界trace相同；
  Uniform的trace-only对照不产生聚合统计且字节一致。临时完整记录自动清理，保留小日志/JSON。

复核产物：`runs/ts_r13_native/validation.json`。测试程序SHA256为
`86ee4938c94767c725fc8f7738f9603b03f44b995da9f0cc40c6e406ab61c795`；
基线同harness程序SHA256为`eb77025bedc76f7ac3b1aa260fe81511a23dabf8c19823811f2999e37c4934f7`。
这些是本地测试程序身份，不是服务器EncoderApp身份。

验证边界：上述语法固定q测试和量化测试是两个独立层面，不是帧级闭环。
未运行所有旧模式字节矩阵、总开关OFF完整字节对照、非RDOQ/lossless及TSRC-disabled专门运行矩阵，
也未运行任何真实帧/序列编解码、短帧hash、CTC或公平整体计时。
EncoderApp、DecoderApp、TsR13NativeTest的Release构建均通过；实际应用`--help`身份探测
确认两端默认Current、可显式选择两组R13。用新二进制完成56项wrapper dry-run，无编码执行。
首次链接因此前中断留下34个零字节目标文件失败，隔离这些构建残留并重编后通过，未因此修改算法。

本轮按项目授权自动同步实验文档/收件说明，源码和运行/测试脚本修改保留本地工作树，未混入文档提交。
没有上传工作簿、视频、码流、构建产物或原始日志。
