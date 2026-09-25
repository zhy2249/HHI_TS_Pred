# R7 shadow：实际编码仍是原R3-1

TypeDef.h：master=1、R3_MODE=1、R7_MODE=0、R7_SHADOW=1；运行时`TS_RATE_SHADOW=1`。
保留旧统计环境变量/schema，不改变原R3码流；RDOQ搜索探针与最终Writer统计分开。
现有六项短测保留在`runs/ts_rate_shadow_audit/`，不复制成另一份数据，不作为BD-rate结果。
