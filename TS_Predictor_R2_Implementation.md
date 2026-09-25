# R2 实现与运行说明

日期：2026-09-18。四组已接入真实TS-RDOQ/Writer/Reader；只运行短帧正确性验证，不运行正式CTC。
设计公式和预注册判据见 `TS_Predictor_R2_Experiment_Protocol.md`，验证结果见 `TS_Predictor_R2_Validation.md`。

## 1. 基线与四组实验

**唯一正式anchor为Current**，继续使用 `scripts/JVET-hhi.xlsm` 的Reference，不重跑完整anchor。
主结果先计算Y/U/V各自BD-rate，再按6:1:1加权；目标仍是LB BCE −0.05/−0.08/−0.10%。
NoPred是候选/辅助对照，不替换Reference。新实验会改变码流，必须配套相同模式的decoder。

| R2宏值 | 模式 | 实现 |
|---|---|---|
| 0 | current（其它默认宏也须为0） | 原始max(L,U) |
| 1 | r2_modal | 可用L/U/D/LL/UU非零样本，n≥3时严格多数幅值，否则Current |
| 2 | r2_risk | 同一模板/门槛，最小化实际remapping后的三遍语法长度近似，含identity候选 |
| 3 | r2_cn_log | TU内Current/NoPred，前序CG的旧log代理评分，EWMA K=2 |
| 4 | r2_cn_frac | 同候选/更新规则，独立虚拟CABAC完整CG评分，native fractional精度 |

R2-M/R没有跨CG历史，第一个CG也可能生效；R2-N/F在CG0为Current，之后才可能选择NoPred。
没有新增QP、分量、class门控，不共享跨TU状态；BDPCM不学习，普通transform/TSRC off路径保持原逻辑。

## 2. 用头文件选择，不用CMake选择

编辑 `source/Lib/CommonLib/TypeDef.h`：

```cpp
#define JVET_BJUT_TS_FIXED_PREDICTOR 1
#define JVET_BJUT_TS_FIXED_NOPRED 0
#define JVET_BJUT_TS_FIXED_GRADIENT 0
#define JVET_BJUT_TS_FIXED_DIRECTIONAL 0
#define JVET_BJUT_TS_CONDITIONAL_MODE 0
#define JVET_BJUT_TS_R2_MODE 4 // 示例：R2-F；1/2/3对应其余三组
```

交付头文件为master=1、所有模式默认=0，即Current。选好后重新编译，直接运行便使用宏默认。
旧固定默认、revision1默认、R2默认互斥，并与旧analysis宏互斥；master关闭却请求实验会报错。
CMake不再产生master的ON/OFF编译定义，旧AUTO/ON/OFF缓存会提示并移除。
不要自行在编译器flags中再添加同名宏，避免人为覆盖头文件。

`TS_FIXED_PREDICTOR`环境变量和批量脚本的 `--fixed-predictors` 仍可显式覆盖编译默认。
一个master开启的二进制支持所有旧模式和四个R2模式；无须为四组分别编译。
日志同时打印有效模式、宏默认、选择来源及 `TS R2 revision=2`，两端必须一致。

新建独立构建目录，避免旧实验续跑指纹失效。以下CMake仅设置构建选项，不控制实验模式：

```bash
cmake -S . -B build/ts-r2 -DCMAKE_BUILD_TYPE=Release \
  -DNX2_TOPLEVEL_OUTPUT_DIRS=OFF -DNX2_ENABLE_LINK_TIME_OPT=OFF
cmake --build build/ts-r2 --target EncoderApp DecoderApp TsFixedPredictorTest TsR2RateTest -j 4
```

## 3. 数据流与评分隔离

- `TsFixedPrediction.h`：默认/override校验、候选公式、Rice长度、整数/小数EWMA。
- `ContextModelling.h/.cpp`：TU局部状态、邻域读取、最终CG更新与私有预算。
- `TsVirtualCoding.h`：CommonLib纯语法事件回放，直接用codec概率模型更新，无EncoderLib依赖。
- `QuantRDOQ.cpp`：已有公共预测入口作用于候选level和rate；CG整体清零RD决策之后才更新历史。
- `CABACWriter/Reader`：三遍语法保留，使用相同预测/更新入口；Reader完成inverse remapping/符号恢复后更新。

R2-F的Ctx延迟创建，使用I初始化表和Clip3(0,MAX_QP,cu.qp)。每CG深拷贝同一起点，
分别回放Current/NoPred；两分支都更新概率和预算。仅保留Current分支结束状态。
CG significant历史来自各分支共同的已完成q，和predictor无关；不会预读未来CG。
状态为64-bit fractional units，范围±(32767<<15)，CG结束才更新，下一CG才读取新状态。

R2-F成本是**虚拟条件rate**，不是实际码流bits；它和真实slice上下文的差异不会反馈给selector。
最终Writer额外从真实CG入口上下文克隆两次用于诊断，导出两组成本，真实上下文不被修改。
这部分只在最终Writer执行，不在RDOQ搜索或decoder中执行，可用 `TS_R2_STATS=0` 关闭。
R2-F两分支重放增加decoder复杂度，不能仅凭微小收益当正式候选。

## 4. 统计与分析

R2默认在最终Writer在线聚合，进程正常退出时输出 `TS_R2_STATS_HEADER`/`TS_R2_STATS` 行到编码日志。
按policy/POC/component/W/H/CU-QP/intra/BDPCM分组，包含TU/CG/系数数、非零数、有效remap位置、
模板支持、多数次数、预测/映射改变次数、NoPred CG数、评分正零负与虚拟/真实入口fractional成本。
这是最终进入TSRC residual coding的活动诊断，不包含CBF=0或TSRC关闭的TU，
不是无偏收益估计；正式收益必须看整次闭环编码BD-rate。

`active_count`仅指显著CG内实际regular/remapping位置，包含零系数；全零CG不计active/bypass。
BDPCM单列几何/非零计数，不计预测活动。`p_current`含p=0/1等价映射；`p_different`为原始p数值不同。
fractional成本除以 `1<<15` 得bit；真实入口和虚拟成本只在非BDPCM的R2-F行比较。
不默认写每系数文本。空间上每个聚合键只有计数器；长跑不要设置 `TS_COND_TRACE`。

```bash
python3 scripts/ts_r2_activity.py runs/ts_r2_LB_CE_half \
  --out runs/ts_r2_LB_CE_half/activity.csv
python3 scripts/ts_r2_analyze.py --run runs/ts_r2_LB_CE_half --phase LB_CE \
  --out runs/ts_r2_LB_CE_half/analysis_611
```

分析脚本也接受 `experiments/ts_predictor_r2/<mode>/<phase>/JVET-hhi.xlsm`，
`--phase LB_BCE`合并LB_CE和LB_B；缺QP只输出missing.csv，不补anchor、不把部分序列冒充完整CE/BCE。
输出分量及加权PCHIP、cubic敏感性、mean/median/std/P10/P90、序列bootstrap、leave-one-out和审计。
Excel Reference必须逐点与Current一致。表格pass不能独立证明远端二进制、实际帧数或hash来源。

## 5. 复用原批量入口

未另建调度器；`batch_test.py`新增四个模式，原共享任务池、断点续跑、每组返回后写Excel均保留。
LB CE四组112项，不新增anchor；LB仍半帧，不传 `--full-sequence`。

```bash
python3 -u scripts/batch_test.py --preset LBeu --class C,E --qps 22,27,32,37 \
  --fixed-predictors r2_modal,r2_risk,r2_cn_log,r2_cn_frac \
  --encoder build/ts-r2/bin/EncoderApp --decoder build/ts-r2/bin/DecoderApp \
  --input-dir /home/zhy/videos --jobs 10 --decode-md5 --no-recon \
  --xlsm-report --xlsm-template scripts/JVET-hhi.xlsm \
  --out-dir runs/ts_r2_LB_CE_half --dry-run
```

先检查规划再去掉 `--dry-run`。续跑同一命令、不加overwrite、不更换二进制。
如果每个服务器使用不同宏默认，可省略 `--fixed-predictors`，但先确认banner不是Current。
RA CD不能仅把preset改成RAeu就当作完整CTC：本项目旧RAeu默认是segLen单段，C/D为64或32帧。
本次RA dry-run仅确认128任务和无重建输出，**不认可该默认帧数与外部RA Reference可比**。
先核对RA anchor实际帧数/分段方式；若确为逐序列全帧，再对RA单独使用 `--full-sequence`，
若为其它帧数则用匹配的INI/manifest。LB仍禁止使用该全帧选项。RA来源未确认前先运行已明确的LB CE。
结果归档到已创建的四组 `experiments/ts_predictor_r2/` 子目录，同时保留元数据和日志，不覆盖旧实验表。

## 6. 本地复核命令

```bash
python3 scripts/test_ts_fixed_defaults.py
python3 scripts/test_ts_fixed_batch.py
python3 scripts/test_ts_r2_analysis.py
build/ts-r2/bin/TsFixedPredictorTest
TS_FIXED_PREDICTOR=current build/ts-r2/bin/TsR2RateTest
TS_FIXED_PREDICTOR=nopred build/ts-r2/bin/TsR2RateTest
TS_FIXED_PREDICTOR=r2_cn_log build/ts-r2/bin/TsR2RateTest
TS_FIXED_PREDICTOR=r2_cn_frac build/ts-r2/bin/TsR2RateTest
python3 scripts/ts_conditional_smoke.py --r2 \
  --encoder build/ts-r2/bin/EncoderApp --decoder build/ts-r2/bin/DecoderApp \
  --anchor build/ts-anchor/bin/EncoderApp --off build/ts-r2-off/bin/EncoderApp \
  --legacy-encoder build/ts-conditional/bin/EncoderApp --out runs/ts_r2_smoke --jobs 3
```

`build/ts-r2-off`仅为单独把TypeDef.h master设0后编译出的验证构建；编完恢复master=1。
不重编旧anchor/conditional/fixed二进制。外部服务器应先做自己配置的短帧decode-hash验证再长跑。
