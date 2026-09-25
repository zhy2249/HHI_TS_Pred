# R6_MODE=1: r6_dense_nopred / LB_B

待接收服务器结果；此目录没有正式RD数据。唯一anchor为Current。
放入JVET-hhi.xlsm、配套CSV、run_metadata.json、完整encode/decode日志（含stderr）。
保留输入/配置/帧数、有效模式banner、源码与二进制SHA、解码hash；禁止空白模板冒充结果。
LB为CTC半帧；RA帧数/分段须与实际anchor核对。未通过CE准入时不启动B/RA。
