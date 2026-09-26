# R8 首批八组工程验收

2026-09-26：本页保留首八组历史验收。剩余16组的新代码、验证与搜索活动边界见 [全量接入记录](TS_Predictor_R8_All24_Implementation.md)，不要用本页旧数量代表最新覆盖。

日期：2026-09-25；规格`R8-DESIGN-20260925-v2`。
结论：**八组已实现并通过本地正确性/回归验证，可以进入预注册真实内容短测。尚无R8正式CTC或BD-rate结论。**

## 1. 实际执行的检查

| 检查 | 结果 / 覆盖 |
| --- | --- |
| 独立编译 | `build/ts-r8/bin/{EncoderApp,DecoderApp,TsRateCodecTest}`，Release，未覆盖旧程序 |
| Python全套 | 89项通过；包括模式注册、互斥、默认/覆盖、原batch调度/写表、公式和统计解析 |
| C++ vs 独立Python公式 | 24,672次逐项对照，含全部候选/score/raw winner/G/H/regret；n=0..5、重复/平局、裁剪、32768幅值和大于int32的cost |
| 原生CABAC测试 | 八组各160个TU、1,491个CG；Y/U/V、矩形2..32维度、Rice1..8、低budget、零CG、BDPCM和正负大幅值 |
| 因果性 | 每组23,436个位置，将目标及未来系数污染后predictor不变 |
| 完整CG复演 | native BitEstimator与复制context replay的fractional bits、budget、完整context逐项相同；不污染真实context |
| 闭环人工smoke | **176个encode/decode任务**，全部decoded-picture hash通过；2帧64×64，AI QP22/0、LB22、RA37、禁TS、启BDPCM |
| Writer/Reader同步 | **5,326个CG trace一致**，包含最终系数/预测值摘要、pass1/2终点和regular budget |
| 旧模式回归 | 保留R7程序支持的34种旧模式均与新程序bit-exact；Current/R3/R7两种在六个case上检查，其余在AI22上检查 |
| master关闭 | 在隔离源码副本中直接设TypeDef master=0编译；六个case均与保留的旧OFF程序以及Current逐码流SHA256一致 |
| 无TS | 八组与Current bit-exact |
| 观察关闭 | 八组分别关闭stats/trace，AI22码流与观察开启相同 |
| 成本预计算 | 优化前后156个原smoke码流SHA256一致，冻结公式不变 |
| dry-run | 真实短测96项；LB CE半帧224项；均无重建输出、同一跨组任务池 |

测试中的随机TU不声称每个尺寸都能被当前CTC自然选中；源码没有新增尺寸限制。
测试中`BDPCM=1`的完整序列仍可包含非BDPCM块，因此该case的新码流变化不能归因于BDPCM算法改变。
原生子块测试单独覆盖BDPCM不应用新remap的路径。

实际脚本：`scripts/ts_r8_smoke.py`、`scripts/ts_rate_codec_test.cpp`、`scripts/test_ts_r8_codec_formula.py`。
完整证据：`runs/ts_r8_smoke_final/validation.json`、`summary.csv`、`quiet_summary.csv`和对应编码/解码日志。
不将这些人工数据填入正式JVET工作簿，不上传原始测试码流/大日志。

## 2. 活动不是只改了名称

下表来自人工smoke中最终Writer的48个R8任务（含8个禁TS任务）；40个任务有统计。
`remap vs parent`是在**本方法最终q**上反事实应用同一冻结快照下的父法，仅证明机制有活动。
各行q和最终TS块可能不同，不能把计数跨行相减解释成码率优劣。

| MODE | active位置 | 相对主父法实际remap改变 | 最终选中P0之外候选 |
| --- | ---: | ---: | ---: |
| 1 | 4,467 | 794 | 0 |
| 4 | 4,363 | 253 | 0 |
| 8 | 4,783 | 293 | 0 |
| 13 | 4,472 | 387 | 0 |
| 15 | 4,776 | 234 | 595 |
| 16 | 4,361 | 232 | 556 |
| 17 | 4,484 | 82 | 0 |
| 19 | 4,154 | 313 | 562 |

B05相对raw改判146个dense位置；B07相对B04有313个实际remap变化。
新增候选获胜不保证该目标remap变化，两个指标不混用。
所有八组至少一个case相对主父法的完整码流发生变化；完整候选组的人工活动主要出现在QP0压力case，
**不能据此保证QP22–37真实CTC具有足够活动**，这正是后续96项预检需要检查的问题。

提取命令：

```bash
python3 scripts/ts_r8_activity.py runs/ts_r8_smoke_final \
  --out runs/ts_r8_smoke_final/activity
```

输出6,499个聚合分层行，按component/W/H/CU-QP/intra/BDPCM/CG数量与位置/n/实际cutoff分组。
TU/CG census独立，避免按support或cutoff重复累加TU；没有统计段不自动当作零活动。
`q_changed`未测，运行时间也未做公平复杂度比较；默认stats的父法重评分开销不能计为算法复杂度。

## 3. 二进制身份

本次验收JSON记录：

| 程序 | SHA256 |
| --- | --- |
| R8 Encoder | `4d9d80512fc6517f9e9464e9bfd3e4dbafe850b6f7e5b57cf5079184ddc51862` |
| R8 Decoder | `455a078a9941835927a272a6bba8eec38810cf3481c58b90848e9d882da5963c` |
| 保留R7 Encoder | `8347971ba0120a8716578830d967376a0f767c29c4d100045782fa829703ee25` |
| 新master-OFF Encoder | `af931f5041da18613506c42f7792b305e5228bd984b7cbc6228f737fcad6e4b9` |
| 保留旧OFF Encoder | `1dd4b2e8a925d4f58956ed0669a65d29f8221d21fcabf4c31eca2a5d829a5f70` |

这是本地构建身份，不要求另一服务器的二进制字节相同。服务器仍须保留自己的源码commit、宏、模式启动行、构建hash和实际配置。
OFF构建仅改隔离副本的master宏；主工作树保持master=1、所有实验MODE=0。

## 4. 尚未完成，不能由smoke替代

- PartyScene/BQMall/KristenAndSara/Johnny，QP22/37、17帧、四个对照加八个新方法的96项真实内容预检：仅dry-run。
- 八组LB CE半帧224点：未启动；没有任何新R8正式BD-rate。
- 与Current及直接父法的闭环收益、序列稳定性、复杂度：待真实数据。
- 完整BCE目标仍按各分量BD后6:1:1、十二序列等权衡量，不能将CE或人工输入视为BCE达标。

下一步运行 [实现说明](TS_Predictor_R8_Implementation.md) 中的preflight；如身份/解码不一致则停止，
若某组真实内容无新增映射活动，先解释其等价区域，不临时调参制造差异。
