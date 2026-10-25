# R13双源解码审计验收（2026-10-25）

这是实现验收与码流收件记录，不是正式RD/BD结果或评分优劣分析。
原始需求：[双源解码合同](../../TS_Predictor_Dual_Stream_Decoder_Audit_Requirements.md)；
实现、构建与实际命令：[交付说明](../../TS_Predictor_Dual_Decoder_Audit_Implementation.md)。

- 源码基线：`f603715223291e26744e5dfae398661fc07fa494`＋本轮实现补丁；完整指纹见validation.json。
- 实现revision：`R13-DUAL-DECODE-AUDIT-impl1`。
- 最终程序SHA256：`13f77d9008dcf826fbcef2074fe68e08d38fca4842223ea88641f4d397d251d3`。
- 本地包：`runs/r13_dual_decode_audit_bundle/`。本目录只保存小型核验数据，没有码流/可执行/完整Ctx。
- 原收件96条（两模式各48），12序列×4QP，167073025字节，复制后每条SHA256一致，源文件保留。
- 额外17帧已验证前缀仅用于接口验收，manifest共49对/98条，不作为额外正式实验点。

## 最终程序的固定验收集

| 输入 | 来源 | 实际解码帧 | 观察POC | 原生TU逐bin验证 | 回放次数 | on/off MD5 |
|---|---|---:|---|---:|---:|---|
| Johnny_QP32_prefix17 | R13-1 | 17 | 0–16 | 3 | 4 | 一致 |
| Johnny_QP32_prefix17 | R13-2 | 17 | 0–16 | 3 | 4 | 一致 |
| Johnny_QP32 | R13-1 | 300 | 0–31 | 4 | 8 | 一致 |
| Johnny_QP32 | R13-2 | 300 | 0–31 | 3 | 4 | 一致 |
| Johnny_QP27 | R13-1 | 300 | 0–31 | 9 | 17 | 一致 |
| Johnny_QP27 | R13-2 | 300 | 0–31 | 12 | 19 | 一致 |
| FourPeople_QP32 | R13-1 | 300 | 0–31 | 2 | 4 | 一致 |
| FourPeople_QP32 | R13-2 | 300 | 0–31 | 2 | 4 | 一致 |

以上每条均逐帧SEI MD5通过、native bin/context/出口状态/pass/budget一致；无预算跳过或日志截断。
共38个采样TU；on解码1834帧，off同数，共3668帧次。此合计仅为固定最终验收集，未重复计入开发轮或额外错误输入测试。
正式文件实际各300帧；预计帧数、完整服务器编码身份未知时仍为null。前32帧TS少，本轮不据此评价方法普适性。

## 其它实际验证

- DecoderApp Release构建成功。总实验宏关闭仅完成新观察头的独立编译，不冒称完整宏关闭工程构建。
- EQ/SP各48个合成TU：真实局部Writer→Reader→回放→序列化；YUV、矩形、Rice1–8、两种BDPCM及regular耗尽。没有视频编码。
- 历史众数逐前缀对照、同映射复用、序列化写盘上限先检查通过。
- Python 8项测试通过：来源等权/交换、空分母、观察范围、错误重复帧、BDPCM-only帧、C0/C+分层等。
- 运行时7项记录：两来源无SEI on/off、极低回放预算、summary零回放、损坏快照、截断码流、错误绑定manifest。
- 新进程从真实快照恢复后，七种策略的fractional总额与捕获时逐一相等；完整q/模型/逐bin文件留本地offline目录。
- CE01最终码流定点为`not_in_final_bitstream`；完整搜索fixture为`missing_fixture`。旧真实q与部分context已保留，没有伪造字段。

## 查询文件

- [copy_inventory.csv](copy_inventory.csv)：96条原件与目标、字节数及SHA256。
- [validation.json](validation.json)：8次on/off配对验收的命令、环境、程序/源流/重建指纹、资源与状态。
- [native_fixture.json](native_fixture.json)：两模式局部语法验证摘要。
- [runtime_validation.json](runtime_validation.json)：7项运行时/失败输入验收。
- [offline_roundtrip.json](offline_roundtrip.json)：独立快照重读的7种rate对应。
- [ce01_status.json](ce01_status.json)：CE01查询和缺fixture记录。
- [example_filter.json](example_filter.json)：损失方向筛选验收，不作为代表性频率。

单层串行解码范围已测；多层/并行slice未测。快照支持≤64×64/4096系数、动态范围8–20。
完整96条码流未全跑；没有新增BD-rate，台账正式曲线和QP分析均未变更。
