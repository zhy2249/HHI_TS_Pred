# A3 / q32_ewma / LB_BCE

状态：待外部服务器编码，当前无结果。

把此模式此配置的表格保存为本目录的 `JVET-hhi.xlsm`。
应含 B/C/E、QP22/27/32/37 共 48 个有效 Test 点；Reference 保持原 anchor。
LB 使用项目确认的 CTC 半帧。
不要把其它 predictor 或配置的结果覆盖到这里。

同时提供 `run_metadata.json`（按上级总目录的模板填写）、编码/解码日志（可放 `logs/`）。
缺日志时只能做工作簿数值审计，不能确认配置/帧数/模式/hash。
不需要上传 YUV 重建视频。规则身份：`TS_FIXED_PREDICTOR=q32_ewma`，conditional revision=1。
