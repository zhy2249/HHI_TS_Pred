# R13-1 / R13-2 码流收件

原始服务器文件分别位于 `13_1/`、`13_2/`，各48条。2026-10-25已复制整理为
`runs/r13_dual_decode_audit_bundle/streams/<Sequence>_QP<qp>/R13_1.bin` 和 `R13_2.bin`。
原96条全部保留，167073025字节逐条SHA256一致。程序与manifest在同一本地包；没有上传码流到Git。

编码器commit/二进制、原图及配置指纹缺失字段保留未知，不能由目录名自动确认。
运行说明见 [双源解码评分审计](../../../docs/experiments/TS_Predictor_Dual_Decoder_Audit_Implementation.md)，
复制清单与验收见 [核验记录](../../../docs/experiments/results/r13_dual_decoder_audit_20261025/README.md)。

2026-10-25统计修复：当前使用 `runs/r13_dual_decode_audit_impl2_release/`（schema 2），旧impl1包作为历史验证保留。原96条文件未改动；实际二进制/码流仍为本地归档交付，未上传Git。

2026-10-25后续更新：用户例外授权后，96条正式码流及配套程序已复制上传至 [`deliveries/r13_decode_audit_impl2/`](../../../deliveries/r13_decode_audit_impl2/README.md)。原件不变；已从远端重新克隆并核验实际文件与双来源前缀解码，详见该交付目录和审计验证记录。
