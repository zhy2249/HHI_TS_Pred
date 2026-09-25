# R7：CABAC fractional-bit 评分替换实验

本轮原名“Rate estimator”，现正式编号R7；**仅统一命名，不修改算法或已有实测数值**。
算法版本仍为`RATE-20260924-v1`，正式anchor仍为Current。

## 编号与原实验的对应关系

| R7_MODE | 实验 | 原实验对照 | 唯一算法变化 | runtime名称 | 新结果目录 |
|---|---|---|---|---|---|
| 0 | 不启用R7 | — | 可另选旧实验；所有模式0时Current | — | — |
| 1 | R7-1 | **R2-2/R2-R/r2_risk** | 整数syntaxCost换成CG入口冻结CABAC fractional-bit评分；仍无R3 guard | rate_raw | r7_1_raw |
| 2 | R7-2 | **R3-1/r3_risk_guard，YUV** | 同样更换评分及G/H；保留原候选、支持门槛、fallback及H>0 guard | rate_guard | r7_2_guard |

R7-2不是R3-2。原R3-2/3/4没有新评分版本。R7_MODE与旧R2/R3/R4/R5/R6等模式宏互斥，不是叠加开关。

## 宏设置

所有TS实验宏及每个取值的历史对应说明已写在`source/Lib/CommonLib/TypeDef.h`顶部。
运行R7-2示例：

```cpp
#define JVET_BJUT_TS_FIXED_PREDICTOR  1
#define JVET_BJUT_TS_R3_MODE          0
#define JVET_BJUT_TS_R7_MODE          2
#define JVET_BJUT_TS_R7_SHADOW        0
// 其它固定/条件/R2/R4/R5/R6模式全为0。
```

改宏后重新编译Encoder/Decoder，不通过CMake选择算法。R7_SHADOW仅控制观察能力，不选择R7-1/2：
需要保持原R3-1编码做shadow时，使用R3_MODE=1、R7_MODE=0、R7_SHADOW=1，并设置运行环境`TS_RATE_SHADOW=1`。
可选`TS_RATE_RDOQ_SHADOW=1`观察RDOQ搜索；正式R7编码不设置这两个环境变量。

旧`JVET_BJUT_TS_RATE_MODE/TS_RATE_SHADOW`保留为兼容别名；与新宏同时给值时必须相同，否则编译报错。
平时只改R7主宏，不编辑别名。默认master=1、所有模式0、shadow0，仍为Current。

runtime名称保留`rate_raw/rate_guard`，避免旧命令和结果读取失效。
`--fixed-predictors rate_raw,rate_guard`仍可覆盖宏默认；Encoder/Decoder启动日志新增：

```text
TS R7 experiment=R7-1; parent=R2-2; runtime=rate_raw; algorithm=RATE-20260924-v1
TS R7 experiment=R7-2; parent=R3-1-YUV; runtime=rate_guard; algorithm=RATE-20260924-v1
```

每次只出现实际所选组；原`EXPERIMENT`行、`TS RATE`版本行和`TS_RATE_*`统计schema保留兼容。

## 目录与资料

新收件根目录：`experiments/ts_predictor_r7/`，下设`r7_1_raw`、`r7_2_guard`、`shadow_r3`。
batch新任务使用`r7_1_raw/r7_2_guard`子目录；既有`rate_1_raw/rate_2_guard`或未编号目录继续原地resume。
同时存在多个候选目录时明确报错，不合并或搬移数据。已编译的旧二进制和旧结果不覆盖。

- [完整源码、公式、实现与运行命令](TS_Predictor_Rate_Estimator_Study.md)
- [已完成shadow结果与下一步](TS_Predictor_Rate_Shadow_Results_20260924.md)
- [统一台账TS-014](TS_Predictor_Experiment_Log.md)

上述文件的Rate旧文件名保留以保证历史链接；标题、主宏及正式轮次统一为R7。
目前结论仍为评分误差减少、条件CG率未净改善，算法增量Weak；未因此重跑完整CTC。

## 重命名验证

`build/ts-r7`已编译EncoderApp、DecoderApp、TsRateCodecTest；默认仍Current。
10项宏默认/覆盖/互斥/新旧别名测试、20项batch测试（含旧rate目录续跑）、4项shadow分析测试通过。
原R3及R7两模式各160个native TU的编解码、上下文及因果检查通过。
36项短帧smoke全部解码hash正确，且每个码流与重命名前对应测试SHA256一致（包含两种新评分模式）。
记录：`runs/ts_r7_naming_smoke/{validation,rename_validation}.json`。本次没有再次测试宏OFF编码或运行正式CTC。
