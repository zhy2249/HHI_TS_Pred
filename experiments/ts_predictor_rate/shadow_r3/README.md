原R3-1的观察实验；TS_RATE_SHADOW=1，实际mode=r3_risk_guard。
可选TS_RATE_RDOQ_SHADOW=1为搜索诊断，不能与最终Writer样本合并。
日志、summary和analysis放在此目录供后续读取；不是BD-rate结果。

2026-09-24本地6项已完成，原始数据保留于`runs/ts_rate_shadow_audit/`，没有复制成另一份正式CTC数据。
结果：winner分歧29.32%；成本差MAE 0.8734→0.5225 bit；new guard条件CG率增加0.033802%。
旧R3对照位于`runs/ts_rate_shadow_parent/`，六个码流SHA256一致。
