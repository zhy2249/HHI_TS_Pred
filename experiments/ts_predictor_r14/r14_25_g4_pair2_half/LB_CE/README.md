# R14-25 LB CE 结果收件

- revision：`R14-NF-168-v3`；runtime：`r14_g4_pair2_half`。
- 公开号 25，内部 policy 124；K=4，update=PAIR2，r0=2，s0=4。
- 阶段 B（阶段 A 复核后才运行）；Current 为正式 anchor。
- LBeu 原 INI 半帧，QP 22/27/32/37，CE 七序列，共 28 点；无重建输出，保留 decode hash。
- 当前尚无本轮编码结果。回传该模式的工作簿、summary.csv、逐点 identity/done 及必要日志；
  不混合其他模式，不自动补缺 QP。
- 复制并填写 [metadata 模板](../run_metadata.template.json)，保留空字段为未知，不把配置值当作验证结果。
- 规划、身份和续跑说明见 [R14 总说明](../../README.md)。
