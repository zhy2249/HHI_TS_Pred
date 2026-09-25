# R2-M / r2_modal / RA_CD

状态：算法已实现，目录等待正式CTC结果；短帧验证不代表本组完成。

方案以仓库根目录 `TS_Predictor_R2_Experiment_Protocol.md` 为准。
本组预期32个Test点，QP22/27/32/37。帧数与现有RA anchor保持一致，不能自动套用LB半帧。
未来将表格放为 `JVET-hhi.xlsm`，Reference不变，不用anchor填补正式缺失点。
同时提供 `run_metadata.json`（参考总目录模板）、`logs/`，可选在线聚合统计。
不得把旧revision1或其它模式表格放到此目录。须使用R2二进制及匹配模式；唯一anchor为Current。
