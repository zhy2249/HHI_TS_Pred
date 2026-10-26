# R15 小型验收派生数据

这是实现验收，不是完整96条码流的实验结论，也不是BD-rate。两来源均为已有Johnny QP32的17帧前缀；各10个TS TU、2112个系数、41个非零。方法全集为18个新子实验+3个既有对照。

- `fast_equivalence.json`：18,000邻域，378,000组三引擎比较，13,048,128次映射检查；包含全幅值域的大幅值六目标边界。
- `native_validation.json`：528次局部算术语法往返、独立Python比较、源文件SHA；没有启动EncoderApp。
- `snapshot_validation.json`：4个TU新进程复现全部21 rate/动作，6类动作损坏拒绝；快照本身留在runs，不默认上传。
- `macro_off_validation.json`：宏OFF与审计ON/OFF三种状态的来源内重建一致；宏关闭时强制请求被拒绝。
- `prefix_*.csv`：仅上述小前缀的人口、完整费用和活动计数；不要据此对方法做全局收益排序。
- `complexity*.csv` / `benchmark_manifest.json`：同一4096行固定合成H，固定CPU亲和性，1次预热+5次轮换。选择器/map/unmap分开；非生产编解码复杂度。
- `run_receipts.json` / `resources.json` / `validation_status.json`：范围、输入/程序/源码身份、资源与当前放行阶段。路径已转为仓库相对形式。

SOURCE的I/P/B Slice字段与CU的is_intra_cu独立；分量0/1/2为Y/Cb/Cr。fractional rate单位1/32768 bit。各源先归一化后等权；本短测无完整四QP和12内容，不能产生正式balanced总体结果。

复现入口见[脚本README](../../../../scripts/ts_multi_mapping/README.md)和[R15验证记录](../../TS_Predictor_R15_Validation.md)。未提交视频、重建、构建程序或原始全量数据；保留已有R13交付目录。
