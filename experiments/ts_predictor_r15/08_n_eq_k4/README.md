# R15-8: N_EQ_K4

原设计 MG10。规则 `N`，K=4，权重 11111。

本目录用于后续结果收件；当前没有正式 BD-rate。R15 首阶段为已有双来源码流的固定 q 审计，同一次解码输出全部方法。统一运行说明见 `scripts/ts_multi_mapping/README.md`，完整设计见 `docs/experiments/TS_Predictor_R15_Implementation.md`。不要以空目录/短测代表完整结果。

闭环代码现已接入：`JVET_BJUT_TS_R15_MODE=8`，运行覆盖名 `r15_n_eq_k4`；适用于启用 TSRC 的非 BDPCM TS。运行与验收见 [编码说明](../../../scripts/README_ts_r15_codec.md)。
