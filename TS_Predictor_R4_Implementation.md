# R4算法实现与使用

版本：R4-20260920-v2。六组接入统一TS-RDOQ / Writer / Reader入口；Current仍是唯一正式anchor。
冻结公式见 `TS_Predictor_R4_Experiment_Design.md` 和 `TS_Predictor_R4_NonAblation_Extension.md`。
本轮只做实现与正确性短测，不启动正式CTC、不改服务器R3结果、不覆盖旧R3程序。
本地验证范围与限制见 `TS_Predictor_R4_Validation.md`。

## 1. 直接用头文件宏选择

编辑 `source/Lib/CommonLib/TypeDef.h`，重新编译Encoder和Decoder：

```cpp
#define JVET_BJUT_TS_FIXED_PREDICTOR 1
#define JVET_BJUT_TS_FIXED_NOPRED 0
#define JVET_BJUT_TS_FIXED_GRADIENT 0
#define JVET_BJUT_TS_FIXED_DIRECTIONAL 0
#define JVET_BJUT_TS_CONDITIONAL_MODE 0
#define JVET_BJUT_TS_R2_MODE 0
#define JVET_BJUT_TS_R3_MODE 0
#define JVET_BJUT_TS_R4_MODE 4 // 1..6选择一组；0表示不选择R4
```

| R4宏值 | 运行模式 | 内部policy ID | 算法 |
|---|---|---|---|
| 1 | r4_identity_only | 17 | 只保留R3已接受的identity分支 |
| 2 | r4_magnitude_only | 18 | 只保留R3已接受的非identity幅值分支 |
| 3 | r4_guard_rescue | 19 | R3拒绝后补查其他H>0候选；接受分支不重排 |
| 4 | r4_directional_risk | 20 | 固定1/2方向加权风险；删除完整加权位置贡献 |
| 5 | r4_causal_models | 21 | 局部因果回看选择R3/Current/NoPred/directional |
| 6 | r4_signed_plane | 22 | 带符号clipped plane，仅通过因果回看后替代R3 |

交付默认master=1、全部模式=0，即Current。**只开master不会启动R4。**
不传实验参数时按宏默认运行；`TS_FIXED_PREDICTOR`环境变量或batch `--fixed-predictors`可显式覆盖。
一个master开启的程序支持全部23个模式（含Current），不必按组编译。
R4与全部旧实验默认互斥；非法值、master关闭却选择实验都会报错，不能靠运行参数绕过编译冲突。
master关闭的程序收到非Current运行请求也会退出报错，不静默退回anchor。

有效日志应同时出现：

```text
EXPERIMENT: TS_FIXED_PREDICTOR=r4_directional_risk; syntax=experimental-v1
TS predictor default: r4_directional_risk; selection: TypeDef.h default
TS R4 revision=R4-20260920-v2; mode=4; anchor=current; scope=YUV; TU-local; stateless; cost=syntax-proxy; signed-view=1
```

宏默认与显式覆盖允许不同，以有效模式banner为准；务必记录二进制SHA。
实验模式不写入码流，Encoder/Decoder须选择同一模式，普通Current解码器不能解码实验流。

## 2. 独立构建

以下CMake仅配置路径与优化，不传递实验宏。不要重编旧 `build/ts-r3/` 影响续跑身份。

```bash
cmake -S . -B build/ts-r4 -DCMAKE_BUILD_TYPE=Release \
  -DNX2_TOPLEVEL_OUTPUT_DIRS=OFF -DNX2_ENABLE_LINK_TIME_OPT=OFF
cmake --build build/ts-r4 --target EncoderApp DecoderApp TsR4CodecTest -j 4
```

程序为 `build/ts-r4/bin/EncoderApp`、`build/ts-r4/bin/DecoderApp`。
修改宏后重新构建同一目录即可；已开始长跑的二进制不要覆盖。
`build/ts-r4-off/`仅为本地macro-OFF验证，头文件恢复master=1后不要随手重编它并继续称其为OFF。

## 3. 代码结构与同步

- `TsFixedPrediction.h`：只扩展模式名/默认/有效banner，旧R3函数公式不变。
- `TsR4Prediction.h`：六套纯函数和诊断结果；读取回调只访问左/上因果位置，不读目标自身，不维护CG/TU历史。
  CB/SP的历史专家调用固定R3等primitive，不递归调用新选择器，不缓存依赖临时q的预测。
- `ContextModelling.h`：原公共预测入口转入R4；已有QuantRDOQ/Writer钩子自然复用相同函数。
  无需复制RDOQ rate逻辑，无需对真实CABAC context作克隆或写回。
- `CABACReader.cpp`：仅SP在第三遍通过`R4SignView`组合已恢复幅值和已解码sign。
  前CG直接读最终signed q；当前CG按sigBlkPos/signPattern取符号。视图只读、不提前改写数组、不改变sign语法。
  初版在当前CG的小型sigBlkPos表内线性查找符号，尚未作O(1)索引优化；须实测Decoder开销，不能称为免费。
- `ContextModelling.cpp` / `TsR4Stats.h`：独立最终CG观察；不让R4走旧EWMA gain路径，统计无算法状态。
  RDOQ finish钩子立即返回；CG整体清零/放弃不会留下缓存或历史；后续位置从实际系数缓冲区重新计算。
- BDPCM、native bypass/cutoff=0、non-TS、TSRC关闭仍保持原生路径。R4各组作用于YUV，未加入QP开关。

方向权重、支持数、tie-break、H>0均与冻结设计一致。CB/SP内部默认R3不意味着改变正式Current anchor。
`syntaxCost`是统一的语法代理损失，不是实际CABAC fractional bits；历史评分不回放各目标当时的regular/bypass资格。
三组新增方法是逐系数局部自适应，不声称原始“仅凭之前CG选择整CG mode”的研究问题已经解决。

## 4. 默认聚合日志

仅最终Writer输出 `TS_R4_STATS_HEADER` / `TS_R4_STATS`，按policy/component/W/H/CU-QP/intra/BDPCM/CG数/CG位置聚合。
不输出逐系数行，不包含POC键；sequence/config/名义QP从任务元数据关联。
`TS_R4_STATS=0`关闭观察，不改变算法。长跑不要开`TS_COND_TRACE`；后者仅用于逐CG编解码同步审计。

字段分母与含义：

- TU/CG/coeff/nonzero是实际进入TSRC的最终块；CBF0和TSRC-off未经过此入口，不计入。
- `active_count`是显著、非BDPCM CG中的regular位置，包含零系数；`bypass_count`只计剩余位置。
  全零CG和BDPCM只记几何/非零，不把它们当预测活动。
- `p_different`合并p=0/1等价，与旧R3该字段的“原始整数不同”口径不同；优先看`remap_different`。
  `p_vs_r3`、`remap_vs_r3`是**在本实验最终q上**与原R3虚拟预测比较，不是两次真实编码的CG配对。
- `r3_current/identity/other`互斥且和为active；Current等价优先于identity。
  `r3_proposed=accepted+rejected`评价原R3，`suppressed`评价I/M屏蔽分支。
- `attempted/accepted`是R4新增搜索/回看，不包含继承R3的选择；I/M两字段均0。
  `rescue`只在R4-3的补查被采用时计数，不等于实际映射改变。
- support0..5对每个active位置计数；G/H符号与B分桶只对attempted计数。
- DR横/纵/平局/边界覆盖所有active位置；CB/SP的model字段是最终选中的专家（含fallback R3）。
- SP sign分层仅在L/U/D齐备时统计三者同号/混合符号/含零；plane差异和新幅值统计是候选诊断，未必被采用。
- hit/under/over、abs_error、modified0/1/2/high以active为分母。proxy正/负收益只能作事后条件诊断，不能回流选择。

所有最终TS内部统计仍有条件选择偏差，不替代闭环BD-rate或解释为Oracle/η。

```bash
python3 scripts/ts_r2_activity.py runs/ts_r4_LB_CE_half --revision r4 \
  --out runs/ts_r4_LB_CE_half/activity.csv
python3 scripts/ts_r2_analyze.py --revision r4 --run runs/ts_r4_LB_CE_half \
  --phase LB_CE --out runs/ts_r4_LB_CE_half/analysis_611
```

基础RD分析扩展R4模式，保留Current Reference检查、缺点拒绝、分量PCHIP后6:1:1、七序列等权。
直接对R3的重新积分及三方共同质量区间，需结果齐全后做跨轮分析，不能用两个对Current的BD相减代替。

## 5. 批量入口只增加模式名

复用`batch_test.py`，共享池、续跑、不输出重建、每组完成即写该组XLSM逻辑不变。
下面是先检查计划的命令，不会开始正式长跑；优先新增4/5，共56项LB CE半帧：

```bash
python3 -u scripts/batch_test.py --preset LBeu --class C,E --qps 22,27,32,37 \
  --fixed-predictors r4_directional_risk,r4_causal_models \
  --encoder build/ts-r4/bin/EncoderApp --decoder build/ts-r4/bin/DecoderApp \
  --input-dir /home/zhy/videos --jobs 10 --decode-md5 --no-recon \
  --xlsm-report --xlsm-template scripts/JVET-hhi.xlsm \
  --out-dir runs/ts_r4_LB_CE_half --dry-run
```

六组全跑时仅替换模式列表为：
`r4_identity_only,r4_magnitude_only,r4_guard_rescue,r4_directional_risk,r4_causal_models,r4_signed_plane`，共168项。
不传`--fixed-predictors`则只运行宏默认一组；不添加Current任务、不重跑整套anchor。
不要加`--full-sequence`；真实输入存在、版本可比、四QP短帧和hash通过后，用户自行决定去掉dry-run。
收件位置为 `experiments/ts_predictor_r4/r4_<R4_MODE>_<方法名>/LB_CE/`，不生成空白结果XLSM。
例如mode `r4_directional_risk`对应文件夹 `r4_4_directional_risk`；六组映射见收件目录README。
从本轮起，后续新轮次均按“轮次＋公开MODE宏值＋方法名”命名，不用内部policy ID。
新batch输出同样采用编号文件夹，summary/失败日志/XLSM与码流放在同组目录。
运行参数仍用原mode字符串，不加数字；分析器与续跑兼容已有无编号目录。
若同一根目录新旧名称并存，会明确报错要求核对归并，不自动覆盖或猜测使用哪一份。
旧 `runs/ts_r4_smoke/`、`runs/ts_r4_real_preflight/` 的已完成数据未搬移。

## 6. 正确性回归入口

```bash
python3 scripts/test_ts_fixed_defaults.py
python3 scripts/test_ts_fixed_batch.py
python3 scripts/test_ts_r2_analysis.py
for r4_mode in r4_identity_only r4_magnitude_only r4_guard_rescue r4_directional_risk r4_causal_models r4_signed_plane; do
  TS_FIXED_PREDICTOR="$r4_mode" build/ts-r4/bin/TsR4CodecTest
done
python3 scripts/ts_conditional_smoke.py --r4 \
  --encoder build/ts-r4/bin/EncoderApp --decoder build/ts-r4/bin/DecoderApp \
  --anchor build/ts-anchor/bin/EncoderApp --off build/ts-r4-off/bin/EncoderApp \
  --legacy-encoder build/ts-r3/bin/EncoderApp --out runs/ts_r4_smoke --jobs 4
```

OFF程序须先按验证步骤实际构建，不能拿旧ON程序改文件夹名冒充。独立原型程序现在同时检查生产实现是否符合冻结公式。
本地合成短测不是远端真实内容预检，不是BD-rate/复杂度基准，也不是任意输入都正确的数学证明。
