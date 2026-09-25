# R2-F / r2_cn_frac / LB_CE

状态：2026-09-19收到27/28个服务器结果点，缺PartyScene QP22；按用户要求仅在分析中用Current暂代，源表不改。
分析见仓库根目录 `TS_Predictor_R2_LB_CE_Results_20260919.md`。

方案以仓库根目录 `TS_Predictor_R2_Experiment_Protocol.md` 为准。
本组预期28个Test点，QP22/27/32/37。项目CTC半帧，七序列等权。
未来将表格放为 `JVET-hhi.xlsm`，Reference不变，不用anchor填补正式缺失点。
同时提供 `run_metadata.json`（参考总目录模板）、`logs/`，可选在线聚合统计。
不得把旧revision1或其它模式表格放到此目录。须使用R2二进制及匹配模式；唯一anchor为Current。
