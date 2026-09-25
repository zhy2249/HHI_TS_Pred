# R3算法实现与使用

四组已接入统一TS-RDOQ、CABACWriter、CABACReader预测入口。
2026-09-20已收到服务器完整LB CE结果，见 `TS_Predictor_R3_LB_CE_Results_20260920.md`；B/RA尚未收到。
规则见 `TS_Predictor_R3_Experiment_Design.md`；Current是唯一正式anchor。

## 1. 宏优先选择

编辑 `source/Lib/CommonLib/TypeDef.h`，重新编译Encoder和Decoder：

```cpp
#define JVET_BJUT_TS_FIXED_PREDICTOR 1
#define JVET_BJUT_TS_FIXED_NOPRED 0
#define JVET_BJUT_TS_FIXED_GRADIENT 0
#define JVET_BJUT_TS_FIXED_DIRECTIONAL 0
#define JVET_BJUT_TS_CONDITIONAL_MODE 0
#define JVET_BJUT_TS_R2_MODE 0
#define JVET_BJUT_TS_R3_MODE 1 // 选择1、2、3或4；0表示不选择R3
```

| R3宏值 | 模式 | 算法 |
|---|---|---|
| 1 | r3_risk_guard | R2-R winner通过G−最大正贡献>0才采用，Y/U/V |
| 2 | r3_risk_guard_y | 同1，仅Y；U/V为Current |
| 3 | r3_cn_guard | S>0且紧邻上一CG的G−最大正贡献>0时选NoPred，Y/U/V |
| 4 | r3_cn_guard_y | 同3，仅Y；U/V为Current |

交付默认master=1、所有模式=0，即Current。不要误将“master开启”当作已选择某个实验。
旧fixed、revision1、R2、R3默认互斥；宏越界、master关闭但选择实验都会报错。
仍支持 `TS_FIXED_PREDICTOR` 或batch `--fixed-predictors` 显式覆盖宏默认；不输入参数时使用宏默认。
一个master开启的程序支持全部17个模式（含Current），无须为各模式分别编译。
编码器/解码器必须选择相同模式；没有新增传输模式的bitstream语法，不能使用普通Current解码器解码实验流。

有效日志示例：

```text
EXPERIMENT: TS_FIXED_PREDICTOR=r3_risk_guard; syntax=experimental-v1
TS predictor default: r3_risk_guard; selection: TypeDef.h default
TS R3 revision=R3-20260919-v1; anchor=current; guard=G-max-positive>0; recent=immediately-previous-CG; scope=YUV; TU-local
```

## 2. 独立构建

下面的CMake选项只控制构建目录/优化，不选择实验算法。旧实验构建目录不要重编，以免续跑指纹改变。

```bash
cmake -S . -B build/ts-r3 -DCMAKE_BUILD_TYPE=Release \
  -DNX2_TOPLEVEL_OUTPUT_DIRS=OFF -DNX2_ENABLE_LINK_TIME_OPT=OFF
cmake --build build/ts-r3 --target EncoderApp DecoderApp \
  TsFixedPredictorTest TsR2RateTest TsR3StateTest -j 4
```

程序为 `build/ts-r3/bin/EncoderApp`、`build/ts-r3/bin/DecoderApp`。
要做宏OFF回归，临时在头文件把master改0，独立构建 `build/ts-r3-off` 的EncoderApp/DecoderApp，
构建完成后恢复头文件master=1。不要同时编译两个依赖不同头文件宏的版本。

## 3. 实现细节

- `TsFixedPrediction.h`：新增模式13–16（外部R3宏仍是1–4），局部guard复用原R2-R的winner、成本和tie-break。
  `LocalGuardResult`返回winner、实际predictor、G和最大正贡献，便于统计核对，不修改输入样本。
- `ContextModelling.h/.cpp`：`m_tsRecentMargin`初始0，R3历史模式仅在最终CG更新为G−B。
  所有CG内的预测调用读取同一CG入口S/H，更新只在结束后发生。空CG明确写入H=0，不保留更早的证据。
- 原 `QuantRDOQ.cpp` 的公共预测钩子同时作用于候选level和rate；原最终CG清零决策后的更新位置继续复用。
  不在暂时产生单个level时更新历史，不改变被放弃TU的外部状态。
- Writer/Reader复用同一个预测与状态实现；Reader恢复最终系数后更新，private budget与原生三遍预算核对。
- Y-only在分量入口回到Current，色度不学习历史；但整个闭环的色度PSNR不保证与anchor相同。
- BDPCM、native bypass/cutoff=0继续identity，普通transform不引入新预测。NG/NGY单CG TU必为Current。
- 没有新增QP阈值、跨TU状态、CABAC状态克隆或更换R2-N评分；G/B/H单位是代理成本，不是实际CABAC bits。

NG保留旧EWMA：S←clip(S−trunc(S/4)+G,±32767)。即使空CG后小正S不衰减，H=0也会阻止下一CG选NoPred。
保留这一行为是为了隔离guard的作用，不声称已经解决全部历史预测失败原因。

## 4. 统计与复用分析工具

默认仅最终Writer在线聚合，退出时输出 `TS_R3_STATS_HEADER` 和 `TS_R3_STATS` 到编码日志。
按policy/component/W/H/实际CU QP/intra/BDPCM/CG数/CG位置分组，去掉POC键避免逐帧膨胀。
来源sequence/config/nominal QP由任务日志路径和metadata关联，勿用CU QP冒充测试QP。

字段包括实际TU/CG/非零数、regular/bypass位置、predictor/remap改变、局部提出/接受/拒绝、
模板非零支持0–5、G/H正零负与B分桶、S正CG数、NoPred CG数、证据阻止CG数、空CG与无有效位置数。
`gain_positive_sum`、`gain_negative_abs_sum`、`best_positive_sum`是NG代理贡献累计，不是bit。
前两者分别累计正/负CG净优势（不是逐系数正/负贡献总量）。
当前尚未单列局部winner的Current/identity/other三分类；现有提出/接受/拒绝与实际映射计数不可冒充该分类。
局部统计按每个有效位置计数，历史统计按CG计数，不能混用分母。
`active_count`包含显著CG内regular位置的零系数；全零CG不记active/bypass。BDPCM只统计几何/非零，不学习。
`p_different`比较原始预测值，p=0/1可能等价；实际作用优先看 `remap_different`。
局部候选支持等诊断是选中TS样本上的条件统计，不能作为无偏编码收益估计。

`TS_R3_STATS=0`关闭观察，不改变算法；长跑不要设置 `TS_COND_TRACE`。
后者额外输出逐CG `TS_COND`、`TS_R3_CERT`，仅用于小输入的编码器/解码器状态逐行核对。

复用现有脚本，增加 `--revision r3`，默认R2行为不变：

```bash
python3 scripts/ts_r2_activity.py runs/ts_r3_LB_CE_half --revision r3 \
  --out runs/ts_r3_LB_CE_half/activity.csv
python3 scripts/ts_r2_analyze.py --revision r3 --run runs/ts_r3_LB_CE_half \
  --phase LB_CE --out runs/ts_r3_LB_CE_half/analysis_611
```

也可读取 `experiments/ts_predictor_r3/<mode>/LB_CE/JVET-hhi.xlsm`。
主分析严格检查Current Reference、四QP及完整分组；不自动补anchor，不把部分序列标成完整CE/BCE。
该基础分析器计算逐分量/加权PCHIP、cubic、分布与序列bootstrap；协议中更深入的父方法共同质量区间消融
需结果齐全后另作跨轮分析，当前没有伪造这些结果。

## 5. 原批量脚本只扩展模式列表

共享任务池、续跑、无重建、逐组完成写Excel逻辑保持不变。以下只是正式实验规划命令，尚未运行正式编码：

```bash
python3 -u scripts/batch_test.py --preset LBeu --class C,E --qps 22,27,32,37 \
  --fixed-predictors r3_risk_guard,r3_risk_guard_y,r3_cn_guard,r3_cn_guard_y \
  --encoder build/ts-r3/bin/EncoderApp --decoder build/ts-r3/bin/DecoderApp \
  --input-dir /home/zhy/videos --jobs 10 --decode-md5 --no-recon \
  --xlsm-report --xlsm-template scripts/JVET-hhi.xlsm \
  --out-dir runs/ts_r3_LB_CE_half --dry-run
```

确认112项、半帧及路径，先完成服务器真实内容短帧预检后，用户自行决定去掉dry-run长跑。
本地默认输入路径没有对应真实序列，当前验证为合成短帧；不要将dry-run当作输入存在性认证。
省略 `--fixed-predictors` 则只跑宏选择的一组。
不要对LB使用 `--full-sequence`；不要把测试用 `build/ts-r3-off` 当作实验程序。
结果目录已备好；B/RA仍按设计门槛另行决定，不在此命令中启动。

## 6. 本地回归入口

```bash
python3 scripts/test_ts_fixed_defaults.py
python3 scripts/test_ts_fixed_batch.py
python3 scripts/test_ts_r2_analysis.py
build/ts-r3/bin/TsFixedPredictorTest
TS_FIXED_PREDICTOR=r3_risk_guard build/ts-r3/bin/TsR3StateTest
TS_FIXED_PREDICTOR=r3_risk_guard_y build/ts-r3/bin/TsR3StateTest
TS_FIXED_PREDICTOR=r3_cn_guard build/ts-r3/bin/TsR3StateTest
TS_FIXED_PREDICTOR=r3_cn_guard_y build/ts-r3/bin/TsR3StateTest
python3 scripts/ts_conditional_smoke.py --r3 \
  --encoder build/ts-r3/bin/EncoderApp --decoder build/ts-r3/bin/DecoderApp \
  --anchor build/ts-anchor/bin/EncoderApp --off build/ts-r3-off/bin/EncoderApp \
  --legacy-encoder build/ts-r2/bin/EncoderApp --out runs/ts_r3_smoke --jobs 4
```

短帧为合成64×64输入，不是CTC效果或复杂度基准。校验结果和限制见 `TS_Predictor_R3_Validation.md`。
