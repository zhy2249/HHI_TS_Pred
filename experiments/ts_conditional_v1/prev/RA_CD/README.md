# A1 / prev / RA_CD

状态：待外部服务器编码，当前无结果。

把此模式此配置的表格保存为本目录的 `JVET-hhi.xlsm`。
应含 C/D、QP22/27/32/37 共 32 个有效 Test 点；Reference 保持原 anchor。
RA 帧数采用与 anchor 一致的原配置，并在元数据明确记录。
不要把其它 predictor 或配置的结果覆盖到这里。

同时提供 `run_metadata.json`（按上级总目录的模板填写）、编码/解码日志（可放 `logs/`）。
缺日志时只能做工作簿数值审计，不能确认配置/帧数/模式/hash。
不需要上传 YUV 重建视频。规则身份：`TS_FIXED_PREDICTOR=prev`，conditional revision=1。
