# R10：局部因果专家选择实现

日期：2026-09-28；算法标识 `R10-20260928-v1`。
输入为 [外部 R10 计划](../external_inputs/R10_Experiment_Plan.md) 及
[R9 最新分析](../external_inputs/R9_Latest_Results_Analysis.md)。本轮先将 GitHub 快进至
`0b08de8`，同步原稿及其两份 R9 派生 CSV；原稿未修改。
本文件是实现说明，不是新一轮 BD-rate 结果。

## 1. 保留的定义与修正

主 anchor 仍为 Current；主要配对对照为 R9-9。R9 编号/公式保持不变。
R9-9 的历史集合是当前位置五邻域中同 CG、真实存在、非零的至多五个位置，
**不是完整 CG 前缀**。不使用当前目标、未来系数、实际 cutoff、序列名、QP 或尺寸选择策略。
范围统一为 YUV；BDPCM、pure bypass 沿用原路径。

对于当前位置 `i`，`h_i=(L,U,D,LL,UU)`。对验证目标 `j`，先从其更早的 `h_j`
生成纯专家动作，再用已知 `a_j` 计损失。共享逆 scan 表同时检查因果性。
邻域可以来自更早 CG，但验证目标必须在当前 CG；TU 边界外为不存在。

专家 A0=R8-12（在已有纯函数中对应 R9-12 的公共 predictor，不启用量化编辑），
B=R2-2 raw，C=R3-1 guard。B/C共享一次整数候选评估。
A0仍需 CG 入口冻结 CF10 表，不能因为验证使用整数成本就关闭概率快照。
每个历史目标使用 `h_j` 的直接 L/U 非零数分类，不能使用 `h_i` 分类。

`C_I=syntaxCost<<SCALE_BITS`，`C_F=RateTable.cost(cutoff=10)`；均为64位定点。
CF是冻结概率的局部幅值估计，不是完整反事实 CG CABAC 码率，更不等于闭环 `D+lambda*R`。

## 2. 七组实验

| R10_MODE | 运行名 | 变化 |
|---|---|---|
| 1 | `r10_expert_axis_A` | A换成完整R9-3，同轴稀疏恢复；当前/历史同时替换 |
| 2 | `r10_expert_p1_A` | A换成完整R9-2，P1候选补齐；当前/历史同时替换 |
| 3 | `r10_integer_then_fractional` | CI主排序；只在CI并列最小集合中用CF打破平局 |
| 4 | `r10_matched_state_weights` | `z=(n<3,d)`相同的历史目标权重2，其余1 |
| 5 | `r10_delete_one_validation` | 原CI赢家相对A的优势，删最大正贡献后仍须严格大于0 |
| 6 | `r10_protected_mapping_expert` | 增加D=完整R9-7，P1与固定保护1；比较完整`(p,k)` |
| 7 | `r10_axis_A_tiebreak` | 预设组合：1+3；与R9-9/1/3构成四角比较 |

最终平局顺序 A→B→C→D；空验证集返回A；当前位置所有规范化完整动作相同也返回A。
R10-5不重新搜索另一个“能过guard”的专家，也不换成NoPred。
R10-6的D不是对其它专家的p简单加k=1：完整复用R9-7的候选搜索、稀疏规则和评分。

映射为：`p<=k+1`或`a<=k`时不变；`a==p`映射到`k+1`；
`k<a<p`映射到`a+1`；其它不变。不能仅比较p忽略k。

## 3. 宏与运行选择

在 `source/Lib/CommonLib/TypeDef.h` 直接设置：

```cpp
#define JVET_BJUT_TS_FIXED_PREDICTOR 1
#define JVET_BJUT_TS_R10_MODE        1 // 按上表改为1..7；0=不选择R10
#define JVET_BJUT_TS_R10_CACHE       0 // 独立等价缓存开关，非算法模式
```

其它 fixed/conditional/R2～R9 默认模式全部设0；有编译期互斥与范围检查。
编解码器必须相同设置。显式 `TS_FIXED_PREDICTOR` 或 batch `--fixed-predictors`
仍覆盖宏默认；不传参数即运行宏选定实验。仓库提交默认保留所有算法模式为0（Current）。
没有新增 CMake 算法开关。环境、日志中内部ID71～77不是公开模式编号。

R10-0工程对照：`R9_MODE=9, R10_MODE=0, R10_CACHE=1`，或用同一二进制
`TS_FIXED_PREDICTOR=r9_expert_integer TS_R10_CACHE=0/1`。它不登记为BD-rate实验。
缓存也可用于R10-1..7；错误模式搭配会在启动时报错。

## 4. 修改位置与编码闭环

- `TsR10Prediction.h`：纯专家、完整动作、state分类、loss matrix选择和guard。
- `ContextModelling.{h,cpp}`：共享因果邻域、同CG验证、概率表、缓存及最终Writer观察。
- `TsFixedPrediction.h`、`TypeDef.h`：宏、运行名、启动标识、dispatch和CF依赖。
- `TsR10Stats.h`：独立观察汇总，不修改真实上下文或系数。
- 复用 `QuantRDOQ.cpp` 的 `magnitudeActionTS`、私有CG概率回放和`protect`感知的
  up-level候选条件；复用Writer/Reader相同action路径，无需复制新语法实现。

因此新专家不只改变最终Writer remapping，也可能改变RDOQ候选/最终q、CG清零及TS获选。
正式收益必须重编码，不能从anchor最终TS人口上的观察直接外推BD-rate。

## 5. R10-0缓存安全边界

每个CoeffCodingContext只缓存当前CG各位置的专家动作，不缓存selector赢家或完整前缀损失。
缓存长度来自实际CG scan范围，不写死16。
键含位置、完整五邻域幅值和专家池模式；动态范围/Rice为该context的不变量。
CG切换与每次概率快照冻结清空缓存。复制context时同步复制快照与缓存；
RDO分支、q编辑、CG清零导致的support变化会重新计算。历史目标loss始终用当前已知a重新计算。
不是仅凭scanPos命中，也不依赖外部修改系数时主动发送失效通知。

开关默认关闭。只有通过bit-exact及受控计时才评价工程价值；即使算法等价，缓存也不保证更快。
内部会多做support读取/比较及vector操作；不能用并发CTC耗时推断缓存加速。

## 6. 目标层面统计（新增）

`TS_R10_STATS=1`启用，仅最终Writer聚合；默认核心统计关闭，正式批量封装默认开启。
`TS_R10_TRACE=1`为编解码核验每CG摘要，正式运行关闭。
计时时关闭全部统计/trace。没有默认逐系数文本。

stderr输出`TS_R10_STATS_HEADER`和`TS_R10_STATS`CSV行；运行身份、sequence/配置/QP
由batch summary关联。分层包含YUV、真实W/H、CU-QP、intra/inter、BDPCM、CG数量/位置、
n/n1/d、实际cutoff、V大小、有效样本数、distinct完整动作、selected和target-best专家。

各专家输出当前最终目标的CI、CF10、冻结表下实际cutoff的CF，以及CI/CF10 target regret；
另有所选专家loss/regret、CI平局、guard拒绝、相对R9-9/A的实际remapping变化、k=1活动。
所有cost字段为Q15累加（不是bit单位）。`best_target_*`平局按专家编号，不代表唯一oracle。
有效样本=至少两个专家对该历史目标的**实际映射幅值不同**；不是不同p数量。
即使当前所有动作相同，仍观察真实V，选择仍按规定回A；这与旧R9诊断短路字段的分母有区别。
BDPCM/pure-bypass只做人口计数，不填虚构的prediction收益；D字段只在模式6有效。

actual-path CF仍不更新假想候选的CABAC状态/regular预算，禁止标成全CG反事实码率。
target在最终确定后才观察；不会进入同一位置的专家生成/评分。选中target regret一般不为0；
旧验证集最优loss或regret=0不再当成预测能力证据。

```bash
python3 scripts/ts_r10_activity.py runs/ts_r10_precheck --out runs/ts_r10_precheck/activity
```

输出`final_by_stratum.csv`、`final_by_job.csv`、`log_status.csv`及`audit.json`；
缺少统计是“未观察/无TS”，不是零活动。未接收R10正式结果，结果台账不添加虚构数值。

## 7. 构建及推荐运行顺序

在仓库根目录执行，CMake仅选择构建目录/Release，不选实验：

```bash
cmake -S . -B build/ts-r10 -DCMAKE_BUILD_TYPE=Release \
  -DNX2_TOPLEVEL_OUTPUT_DIRS=OFF -DNX2_ENABLE_LINK_TIME_OPT=OFF
cmake --build build/ts-r10 -j 8 --target EncoderApp DecoderApp TsRateCodecTest
python3 -m unittest discover -s scripts -p 'test_ts_*.py'
python3 scripts/ts_r10_smoke.py --jobs 8 --out runs/ts_r10_smoke
```

先做固定预检：BQMall、RaceHorsesC、Johnny、KristenAndSara，QP22/37，8帧；
覆盖既往互补、退化及改善内容，不据新结果更换测试集合。

```bash
TS_R10_STATS=1 bash scripts/run_ts_r10_lb_ce.sh \
  --sequences BQMall,RaceHorsesC,Johnny,KristenAndSara --qps 22,37 --frames 8 \
  --fixed-predictors r10_expert_axis_A,r10_expert_p1_A,r10_integer_then_fractional,r10_matched_state_weights,r10_delete_one_validation,r10_protected_mapping_expert,r10_axis_A_tiebreak \
  --no-xlsm-report --out-dir runs/ts_r10_precheck
```

正式第一阶段1/2/3/4/7，共140点；第二阶段5/6，共56点：

```bash
bash scripts/run_ts_r10_lb_ce.sh --input-dir /path/to/videos --jobs 10
bash scripts/run_ts_r10_lb_ce.sh --input-dir /path/to/videos --jobs 10 \
  --fixed-predictors r10_delete_one_validation,r10_protected_mapping_expert
```

若决定同批启动七组，将第二条`--fixed-predictors`改为预检中的全部七个运行名即可，
共享同一任务池；组间没有等待整组结束的屏障。LB按HHI INI半帧，不使用`--full-sequence`。
不重复编码Current。复用既有resume、失败重试、完成一组即复制并写入其`JVET-hhi.xlsm`，
不等七组全部完成；不输出视频重建文件。参数变化、二进制变化、统计或缓存开关变化纳入resume身份。
`--dry-run`先核对计划。观察量较大时先测预检日志大小，可显式`TS_R10_STATS=0`关闭。

接收目录 `experiments/ts_predictor_r10/r10_<编号>_<名称>/LB_CE/`。
上传时保留工作簿、summary、编码日志、源码提交、二进制SHA及运行环境开关；模板见该目录README。

## 8. 验证与后续评价

工程结果见 [验收记录](TS_Predictor_R10_Validation.md)。预检/合成输入只证明实现活动，不能预报收益。
之后逐序列重新积分Current、R9-9及直接对照，先算各分量BD-rate再作6:1:1加权；
CE主均值为7序列等权`(4*C+3*E)/7`，不是`(C+E)/2`。不补点除非得到明确授权。
同时看C/E、三条E序列、BQMall、质量分段以及target loss/regret是否与闭环表现对应。
R10-1/3/7必须形成四角比较；R10-5检验风险控制，R10-6检验保护1能否被因果验证识别。
若只有历史最小化更好而当前目标/闭环无改善，不能据此扩大矩阵或宣称可预测性。
