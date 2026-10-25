# Johnny QP32 POC16 单个 TS 候选的 predictor 明细

本地17帧EQ前缀中捕获Y(856,384)8×32 TS搜索候选；该候选最终未保留。
固定同一份q、同一个TSRC入口概率状态，Current/EQ/SP各自更新私有CABAC状态。
唯一pred/remap差异在scan31：EQ p0，SP p2，q1分别映射为1/2。
SP−EQ精确为90521/32768=2.762481689453 bit。

- [逐项可读表](trace_tables.md)：全部14个非零系数、12个有评分位置、5个差异syntax事件。
- [coefficient_process.csv](coefficient_process.csv)：全部256个系数及三分支H/p/remap、pass和码率。
- [candidate_process.csv](candidate_process.csv)：每个候选、每个非零邻居的幅值、权重、单项KeepHit分数和总分。
- [nonzero_process.csv](nonzero_process.csv)：仅14个非零系数，便于快速查询。
- [zero_predictor_changes.csv](zero_predictor_changes.csv)：零系数pred差异；本次无数据行。
- [paired_bins.csv](paired_bins.csv)：全部EQ/SP语法事件配对，保留概率状态、0/1 fractional cost和budget。
- [changed_bins.csv](changed_bins.csv)：上述配对中的5项差异。
- [summary.json](summary.json)：rate分解、完整性审计及原始观察CSV的SHA256。
- [run_validation.json](run_validation.json)：运行命令、源码/二进制/输入指纹、byte-exact及17帧解码MD5验证。
- [native_validation.json](native_validation.json)：36个合成TU的native estimator一致性与无状态污染验证。

分数168单位是KeepHit代理，不是bit；rate_frac每32768单位为一个估计bit。
Current是同q反事实分支，不是独立anchor编码结果；本数据不新增正式RD点，不计算BD-rate。
原始运行记录留在`runs/r13_pred_detail_20261025/`，不上传码流、输入视频或构建产物。
生成命令与解释见[定点报告](../../TS_Predictor_R13_Pred_Rate_Trace_20261025.md)。

合成TU检查可用同一次构建的静态库复现（不运行视频编码）：

```bash
g++ -std=gnu++17 -O1 -flto=2 -DNDEBUG -DTARGET_SIMD_X86 \
  -DENABLE_TRACING=0 -DENABLE_CABAC_DUMP=0 \
  -I source/Lib -I source/Lib/CommonLib -I source/Lib/CommonLib/x86 \
  -I thirdparty -I thirdparty/sadl scripts/ts_r13_pred_detail_native_test.cpp \
  build/ts-r14/lib/libEncoderLib.a build/ts-r14/lib/libCommonLib.a \
  -o /tmp/ts_r13_pred_detail_native_test
TS_FIXED_PREDICTOR=r13_keep_hit_uniform TS_R13_PRED_DETAIL=/tmp/r13_detail_native \
  /tmp/ts_r13_pred_detail_native_test
python3 -m unittest discover -s scripts -p test_ts_r13_pred_detail_analysis.py
```

另外分别用`TS_FIXED_PREDICTOR=current`、`r13_keep_hit_spatial`执行同一fixture，覆盖另外两条native分支。
