# R14 v3 实现、观察与局部验收

日期：2026-10-23。基于[冻结设计](TS_Predictor_R14_Experiment_Design.md)及
[工程计划](TS_Predictor_R14_Engineering_Plan.md)，实现 `R14-NF-168-v3` 的15个活动模式。
当前编号身份为 **`compact-15-v1`**，公开MODE连续1..15；这是编号整理，runtime名称和算法参数不变。
本轮没有运行帧/序列编解码，没有新增BD-rate或整编码计时结果。

## 1. 已实现的规则

当前五邻域为L/U/D/LL/UU；n是非零**位置**数，重复幅值仍分别贡献支持。
n<3使用原始Current；n>=3沿用R13的KeepHit整数损失与候选顺序，按
`K*N(p)+r*F(p)`选择predictor。严格小于才替换，保留Current平局优先。
远权为0不删除远邻候选或支持位置。

动态模式生成全部3/5档赢家，但只用当前档的p量化。当前局部q确定后，以
`syntaxCost(remap(abs(q),p_r))`产生目标档；先最小代价，再距当前档最近，最后较大档。
该反馈不是KeepHit重算、真实CABAC估计或完整RD搜索。NONE移动一个r档；PAIR2移动一个s微状态，
输出r=s>>1；中性或无资格位置保留完整相位。PAIR2不是必须连续两次确认。

初始化单位是TU/分量/每次量化trial，**不是CG**。实际目标为TS、TSRC启用且非BDPCM；
RDOQ开关不决定最终Writer/Reader是否启用算法。纯bypass不remap，但仍按完整q更新状态。
没有新模式比特；实验码流必须使用相同R14模式的实验解码器。

固定7/8/9（旧19/20/21）只评分自己的r，不学习、不计算无用的完整网格。7不等于anchor：
Rice=1/range=15/H=(25,26,1,0,0)时，Current=26，而7选择25（3400<3402）；
H=(4094,4096,4095,0,0)时仍可选择远组候选4095。相关反例已加入回归。

## 2. 代码位置及状态安全

| 文件 | 职责 |
| --- | --- |
| `source/Lib/CommonLib/TsR14Prediction.h` | 无副作用prepare、反馈commit；复用R13损失和真实Rice长度实现 |
| `source/Lib/CommonLib/TsFixedPrediction.h` | 15个runtime/config注册、初始化、运行身份和观察参数 |
| `source/Lib/CommonLib/TypeDef.h` | R14宏说明、非法编号及跨轮互斥 |
| `source/Lib/CommonLib/ContextModelling.h/.cpp` | 独立TU状态、入口快照、最终Writer观察及trial分离 |
| `source/Lib/CommonLib/QuantRDOQ.cpp` | allowUp前prepare，signed cLevel确定后commit，CG判零后恢复完整入口状态 |
| `source/Lib/EncoderLib/CABACWriter.cpp` | 每CG单次因果预遍历缓存映射，三遍语法只读缓存；真实Writer与fractional estimator均执行 |
| `source/Lib/DecoderLib/CABACReader.cpp` | 第三遍取得完整幅值后prepare、必要反映射、commit；bypass也提交 |
| `source/Lib/CommonLib/TsR14Stats.h` | 默认关闭、有界维度的最终Writer统计及独立RDOQ trial统计 |

不向旧CG级状态学习分派回写；不在三遍remapping回调中重复学习；不使用动态CABAC状态评分。
Reader尚未恢复的未来幅值、源残差与原始像素不参与prepare。RDOQ CG整体清零时恢复r或完整s，
被丢弃TU/trial的状态随上下文丢弃。普通变换、BDPCM和TSRC-disabled路径保持Current行为。

## 3. 开启与编号

直接修改TypeDef.h，不使用CMake参数选择算法：

```cpp
#define JVET_BJUT_TS_FIXED_PREDICTOR 1
#define JVET_BJUT_TS_R14_MODE 1
```

其它轮次和早期固定/条件模式全部为0。默认R14_MODE=0，所有模式为0时仍为Current。
runtime环境 `TS_FIXED_PREDICTOR` 或batch的 `--fixed-predictors` 显式覆盖宏默认。

| 当前MODE | 旧v3号 | runtime | K | 更新 | 初始r/s | 首批 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 1 | r14_g2_none_equal | 2 | NONE | r=2 | A |
| 2 | 4 | r14_g4_none_equal | 4 | NONE | r=4 | A |
| 3 | 7 | r14_g2_none_half | 2 | NONE | r=1 | B |
| 4 | 10 | r14_g4_none_half | 4 | NONE | r=2 | B |
| 5 | 13 | r14_g2_none_zero | 2 | NONE | r=0 | B |
| 6 | 16 | r14_g4_none_zero | 4 | NONE | r=0 | B |
| 7 | 19 | r14_fixed_near_only | 2 | fixed | r=0 | A |
| 8 | 20 | r14_fixed_quarter | 4 | fixed | r=1 | A |
| 9 | 21 | r14_fixed_threequarter | 4 | fixed | r=3 | A |
| 10 | 22 | r14_g2_pair2_equal | 2 | PAIR2 | r=2/s=5 | A |
| 11 | 23 | r14_g4_pair2_equal | 4 | PAIR2 | r=4/s=9 | A |
| 12 | 24 | r14_g2_pair2_half | 2 | PAIR2 | r=1/s=2 | B |
| 13 | 25 | r14_g4_pair2_half | 4 | PAIR2 | r=2/s=4 | B |
| 14 | 26 | r14_g2_pair2_zero | 2 | PAIR2 | r=0/s=0 | B |
| 15 | 27 | r14_g4_pair2_zero | 4 | PAIR2 | r=0/s=0 | B |

“旧v3号”是`5279978`源码、`c2d5a76`文档使用的非连续编号。旧宏值不能直接照搬，
例如旧4必须改为新2；runtime字符串不变。旧数字没有别名兼容，16及以上报错；
TARGET2/DIR2旧runtime继续拒绝。内部policy=99+当前MODE（100..114），不用于目录编号。
启动行包括v3、`numbering=compact-15-v1`、MODE、runtime、K、update、r0/s0、score-scale和target；固定模式的`grid=0..K`
表示合法档范围，其实际评估网格在manifest中为单个r0。观察/算法旧轮误接会明确报错。

## 4. 统计格式与分析界限

默认 `TS_R14_STATS=0`、`TS_R14_TRACE=0`；详情/trace上限默认64，最多1024；
`TS_R14_POC`未设置代表全部，设0只观察POC0。DETAIL仅最终Writer输出；TRACE的Writer/Reader各自受上限控制。

- `TS_R14_STATS_HEADER`/`TS_R14_STATS`：最终Writer，每最终位置一份。
  key为mode_n15、component、W/H、CU QP、intra、BDPCM、target、每TU CG数、cutoff、n、入口s/r、入口权重。
  TU/CG计数使用cutoff/n/state/weight=-1的哨兵行。cutoff=-1为全零CG、0为bypass、2/10为实际regular路径。
- `TS_R14_TRIAL_HEADER`/`TS_R14_TRIAL`：独立RDOQ CG试编码次数、最终零CG次数、回滚了非平凡状态的次数。
  `zero_cg_count`包括本来全零的CG；`rolled_back_state_count`才证明曾推进后被恢复。
- `TS_R14_DETAIL`：有界H、各档赢家、a、p、入口/出口state及目标方向。
- `TS_R14_TRACE`：有界每CG的q/p/state/cutoff摘要、真实预算、入口/出口状态，W/R应一致。

STATS与TRIAL首列均用`mode_n15`明确连续编号，解析器内部仍统一称`mode`。
旧表首列`mode`不自动重解释为新号；旧无当前编号身份的日志拒绝，应保留原版本解析或明确迁移。

主表不按POC/坐标无限增加key；具体POC/CG位置在有界trace/detail中保留。
序列、配置、标称QP来自外层任务身份，不能把cu_qp当作标称QP。
非目标和稀疏/零/缺组原因可重叠，不能相加当互斥人口。

`p_vs_current`、`actual_remap_vs_current`及`tu_with_pdiff`是相对Current；
`p_vs_initial_weight`、`actual_remap_vs_initial_weight`在相同最终H/a上比较当前档和固定初始档，
用于观察状态学习的实际作用。两者都不是另一路闭环量化的反事实结果。

g_next在下一**有效**反馈位置，以该位置相同H和a比较上次更新前后档的赢家。
记录正/零/负、整数cost和、跨CG配对、p/实际映射变化。有效中性事件仍计入；
相位改变但权重不变的配对必须收益0。全零CG不清pending观察，TU末无下一事件则未配对，不能补0。
`eligible=next_pair+next_unpaired`；固定模式没有动态eligible。

g_next仍是已选中TS的同轨迹固定q静态语法代理，不能解释为CABAC节省或BD-rate。
同一a即时最小化的收益也不能证明历史可预测。真实效果以独立闭环编码为准。

## 5. 本地验收

### 5.1 生产接入验收历史（非连续编号）

以下为`5279978`归档实现对应的已完成验收，表内实验数字均为**旧v3号**；
不将旧报告冒充连续编号版本的新验收。对应runtime和方法含义见第3节对照表。

Release构建完成：EncoderApp、DecoderApp、TsR14NativeTest、TsR13NativeTest。
产物在`build/ts-r14/bin/`。本机使用GCC11.4、LTO开启（链接并行6），没有测整编码复杂度。

| 检查 | 已完成结果 |
| --- | --- |
| 纯评分/反馈 | 205,770个prepare/commit案例＋1,836个状态转移；真实Rice=0..8、range=15/20；独立Python参考1,200例 |
| 新核心/宏 | 9项测试通过；15宏默认及运行覆盖、空洞编号/旧轮互斥/master-OFF/观察误接 |
| 旧宏默认 | 原18项测试通过，保留已有默认/运行覆盖行为 |
| 原生合成语法 | 每模式180 TU、1,718 CG、27,032位置；真实Writer/Reader、fractional sink及BitEstimator的q/context/budget/状态核对通过 |
| 低预算/零/小TU | 每模式75个低预算TU、60个纯bypass TU、168个零CG、68个小尺寸TU；未来系数扰动不改变当前prepare |
| 原生量化 | 每模式288 TU，覆盖BDPCM、lossless、RDOQ-off、TSRC-disabled、普通变换、小尺寸及独立trial重置 |
| 统计隔离 | 全15组观察开/关的完整字节/q/context/budget/state记录一致；有界W/R trace每组7对一致，trace-only亦核对 |
| 非目标 | 全15组的非目标完整记录与Current一致 |
| 真实RDOQ非平凡回滚 | 7/10/24/25各2次，13/16/26/27各4次；1/4/22/23该合成集合未触发，固定模式不推进；不将手动restore测试冒充生产分支覆盖 |
| 旧模式回归 | Current、R2-2、R3-1、R6-2、R13-1/2六组；保留的pre-R14旧二进制与新构建同一旧harness的约171 MB/模式完整记录逐字节相同 |
| master-OFF | 四关键CPP按真实构建参数追加总开关0执行`-fsyntax-only -Werror`通过；不是OFF整码流测试 |
| batch | R14 11项、旧R13 8项、通用batch 21项通过；假任务/临时工作簿验证跨组调度、逐组写表、Reference保持、身份和续跑 |
| activity | 5项fixture/schema/守恒检查通过；实际mode24观察日志成功导出，Writer/trial分开 |

以上native覆盖21个runtime（15新＋6旧），没有启动视频应用进行帧编码。临时完整比较记录核对后删除，
仅保留小日志、SHA和`runs/ts_r14_native/validation.json`；master-OFF另有同目录JSON。
对所有动态模式，最终Writer有效事件8,630、下一事件配对8,508、跨CG配对1,161；
与TU尾未配对数守恒，相位事件g_next恒0。数字只是合成覆盖，不代表自然序列分布或收益。
旧19（现7）在真实regular路径确有映射变化，不能按anchor跳过实验。

冻结r=K/K/2对R13等价已在纯评分验证；不扩大为所有工具条件下完整码流等价。
尚未完成服务器短帧/CE hash验收、正式BD-rate或实际计时，因此不能宣称R14优于R13。

### 5.2 连续编号核验

本次只调整注册/宏编号、身份、目录及统计schema，公式、runtime、参数和状态规则不变。
已按同一runtime核对重编号前后完整字节/q/context/budget/state，不能按碰巧相同的数字比较两种不同方法。

| 连续编号检查 | 实际结果 |
| --- | --- |
| Release构建 | TsR14NativeTest、EncoderApp、DecoderApp成功 |
| 重编号前后完整回归 | 21个runtime（15个R14＋6个旧模式）全矩阵；与保留的旧`TsR14NativeTest`完整记录逐字节一致 |
| 观察隔离与同步 | 15组统计开关前后bit-exact，Writer/Reader状态与trace同步通过 |
| 纯核/宏 | 4＋5项通过，覆盖205,770例、1,836项转移与1,200项独立参考；当前1..15身份和范围外拒绝通过 |
| 脚本 | R14 batch 11项、旧R13 batch 8项、通用batch 21项、activity 5项通过；阶段A实际dry-run为196点 |
| 日志提取 | 新MODE12的实际合成观察日志成功导出，最终Writer与trial人口分离 |
| 真实RDOQ非平凡回滚 | 新3/4/12/13各2次、新5/6/14/15各4次，其余0；与旧同方法覆盖一致 |

报告：`runs/ts_r14_n15_native/validation.json`，`numbering=compact-15-v1`、
`renumber_status=checked`。对照二进制为`runs/ts_r14_renumber_before/TsR14NativeTest`，
完整回归使用`--renumber-before-exe`显式指定它；旧运行输出和结果未重命名。
本次没有执行视频编解码、修改BD-rate或更新数值台账，局部记录一致不替代服务器视频验收。

复现当前纯核/宏及日志分析：

```bash
python3 -m unittest discover -s scripts -p 'test_ts_r14_predictor.py'
python3 -m unittest discover -s scripts -p 'test_ts_r14_defaults.py'
python3 -m unittest discover -s scripts -p 'test_ts_r14_batch.py'
python3 -m unittest discover -s scripts -p 'test_ts_r14_activity.py'
python3 scripts/ts_r14_activity.py 编码日志.log --output-dir runs/r14_activity
```

分析器输出final_writer.csv、final_writer_summary.csv、state_residence.csv、rd_trial.csv、
rd_trial_summary.csv、summary.md；支持sequence/configuration/nominal-qp标签。
缺统计不当作零活动；重复日志/header、截断行、非法状态和人口不守恒会报错。

## 6. 本地构建与服务器命令

在仓库根目录运行。下面CMake只选Release和独立产物目录，算法仍由头文件/runtime决定：

```bash
cmake -S . -B build/ts-r14 -DCMAKE_BUILD_TYPE=Release -DNX2_TOPLEVEL_OUTPUT_DIRS=OFF
cmake --build build/ts-r14 --target EncoderApp DecoderApp TsR14NativeTest TsR13NativeTest -j 6
python3 scripts/test_ts_r14_native.py --jobs 2
```

默认阶段A顺序7/1/10/8/9/2/11，7组×7序列×4QP=196点。LBeu配置已是半帧，不再次减半。
Current使用既有anchor，不重复编码；R13-1/2是既有固定比例机制对照。

```bash
bash scripts/run_ts_r14_lb_ce.sh --dry-run --allow-missing-input
# 由用户在服务器发起正式编码；与续跑使用同一命令/输出目录
bash scripts/run_ts_r14_lb_ce.sh --input-dir /实际视频目录 --jobs 10
```

阶段B为3/4/5/6/12/13/14/15八个初态消融（224点），需要先有动态价值/初态瓶颈证据，再加`--phase B`；不是Class B。
同一共享任务池跨组调度，每组完成即写独立工作簿；不开重建，保留decode hash；二进制、配置、协议、
观察环境变化使done指纹失效。正常续跑不用`--overwrite`。保留了缺点/失败日志，不伪补QP22。
当前默认输出根为`runs/ts_r14_nf168_v3_n15_LB_CE_half`，与旧非连续编号任务分开；
不移动或覆盖旧runs结果。当前收件目录数字前缀同步为新MODE。

结果收件路径及metadata见[目录说明](../../experiments/ts_predictor_r14/README.md)。
在完整CE前建议按冻结的PartyScene/RaceHorsesC/BQMall/KristenAndSara、QP22/37、17帧做活动/hash短测，
初始1/10/7三组；短测另目录，不能写入半帧结果曲线。本轮未执行该短测或正式编码。

## 7. 归档边界

先前`c2d5a76`仅归档实施文档与收件模板，不包含生产实现。
2026-10-23用户明确要求上传代码，随后在同一实验分支归档R14及其依赖的R13生产实现、
CMake局部测试目标、批量/分析脚本及测试。宏默认仍为Current，统计默认关闭。
本次只归档已完成验证的代码，不改变算法或另启编码；不上传用户原始工作簿、外部未跟踪输入或构建产物。
没有新结果，所以不改数值结果台账。
