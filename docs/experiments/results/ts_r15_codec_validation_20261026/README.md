# R15 闭环代码的局部验收数据

这些是合成 TU 与既有 R13 前缀的正确性数据，不是正式 R15 编码结果，没有 BD-rate。

- `native_validation.json`：18模式、Current/NoPred、各模式stats开关、旧六模式、master关闭的完整记录 SHA256/字节数。完整记录包含q、算术编码字节、预算、fractional bits和所有context字段；通过FIFO哈希，没有保存几百MiB原始记录。
- `activity.csv`：18模式的合成输入活动计数；RDOQ是试验人口（含重复调用和被放弃TU），Writer仅含最终regular非零位置。不能据此估计视频收益或TS使用率。
- `legacy_decode_validation.json`：R13-1/2既有Johnny QP32前缀各17帧的MD5，与修改前及编码端SEI一致。未写重建视频。
- `python_tests.log` / `mapping_tests.log`：33项宏/调度等检查和12项映射/审计检查。日志里的full96为测试生成的假计划，不是运行了96条码流。
- `native_tests.log` / `native_resources.log`：顺序运行与资源记录。GNU time最大RSS为单进程/子进程口径，不是瞬时全进程树总和。
- `manifest.json`：源码和本地可执行文件SHA，源码基点与版本。二进制仅在本地构建目录，不声称随本提交远程交付。

R15-1仅在共同目标范围与旧NoPred比较；全部R15非目标范围与Current比较。旧构建以实测可执行文件SHA绑定，不能由目录名推断其源码commit。更广泛视频/CTC测试尚未执行。
