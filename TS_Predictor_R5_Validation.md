# R5 本地验证与活动证伪（2026-09-21）

版本 R5-20260921-v1。两组已实现，**没有正式 BD-rate 收益结论**。
重要结论：正确性通过，但合成及本次真实短测均未显示相对 R3-1 的新增映射/码流变化；不建议直接扩大完整 CTC。

## 1. 构建和身份

TypeDef.h 控制宏，不通过 CMake 选择算法。独立 Release `build/ts-r5`，顶层输出关闭、LTO关闭。
临时把 master 改0构建 `build/ts-r5-off`，完成后恢复 master=1，R5/所有旧模式=0，即交付默认仍Current。
旧 R3、R4、anchor 二进制未覆盖，服务器结果表和 Reference 未改。

| 程序 | SHA256 |
|---|---|
| R5 Encoder | 647cd138cb09c2396b870c9f0a6eb513fa674a83cd526a2202fbb03c8b6eecea |
| R5 Decoder | ee52226965c4491927505c83e961d6a9be8d242cf8ab908a7e817b498693bc34 |
| R5 OFF Encoder | 1521047f3a97aee127fe66657ea280ab715ced4eb79bf6827fe0942426bad624 |
| R5 OFF Decoder | b3015e388bc8c6086df253ca9707cc7f7762846458629b0d0e79fec88d17e974 |
| 保留 R4 Encoder | 6879d505657d05cab4fefc5ee4a6f083872fa5b71a0ae460411ed6791b8ed46d |
| 保留 R3 Encoder | 52b87556799c0c4105bc9191cec0be578e66f70b3ac7aa92f8e676d1f845d9ee |
| 保留 anchor Encoder | 4203250460849a87e5643b49b1c96354e4eb92d263b404c82f0074d3ae046257 |

恢复master后不得重编OFF目录再继续称它是OFF。模式没有码流信令，编解码器须一致。

## 2. 独立规则与因果性测试

`scripts/ts_r5_design_check.cpp`：

- 五幅值0..15、Rice1/2/4，共 **3,145,728** 组合；R5-1逐项与独立候选去重/评分实现一致。
- 3000个8×8 signed人工网格，幅值集合包含0/1、多个语法边界、255和32767，Rice1..4。
  共192000个目标、两模式 **384000** 次预测；R5-1/2与独立规则一致。
- 当前及未来污染不改变预测，符号翻转不改变预测，历史R3 primitive不读取历史目标自身。
- 评分仍复用真实remap/代理C函数；这证明规则一致性，不是独立验证CABAC损失模型。

**不能省略的负面发现：**

- R5-1小模板中回退补查2520次，但“重排已接受的R3”计数0；宽幅值网格重排也为0。
- 同时逐项比较R4-3，小模板及宽幅值网格中的预测差异均为0；这是有限测试覆盖内的相同，不是全域等价证明。
- R5-2宽幅值网格只否决3次（identity1、其他幅值2）；不能把这理解成真实视频概率。
- 初版测试要求出现accepted-parent重排，该覆盖断言失败；检查后确认是预期机制未观察到，不是公式实现不一致。
  未改公式强行产生变化，最终测试显式打印零覆盖，保留低优先级结论。
- 有限枚举不能证明 R5-1 与 R4-3 在所有合法输入上等价，不能把“尚未发现差异”写成数学定理。

完整测试stdout和源/测试/程序SHA见 `runs/ts_r5_smoke/native_validation.json`。

## 3. 原生 CABAC 往返

`TsR5CodecTest` 两组各 **240个人工TU**，宽高2/4/8/16/32的方形和矩形，YUV、intra/inter、BDPCM、Rice1..4、稀疏/大幅值/全零CG。
人工几何覆盖不等于正式配置中观察到这些尺寸。

- 直接用CABACWriter/BinEncoder和CABACReader/BinDecoder，逐CG q和regular预算一致，整TU往返正确。
- 按原生grouped scan检查每个读取位置早于目标；污染当前和全部未来位置不影响输出。
- Reader当前CG仅有幅值的视图给出相同预测，R5没有符号依赖；持久state/recentMargin始终为0。
- 人工R5-1 rescue模板 `[2,1,10,1,1]`：Current/R3=2，R5=0，H=2。
- 人工R5-2历史回看样例：R3=8、Current=9、G=8/H=3，确实否决回Current。
- 两个针对性样例提供足够TU regular预算并作断言，避免“函数产生变化但目标实际走bypass”的假覆盖。
- 原随机240TU集合未覆盖R5-2增量，补入独立网格产生的人工样例后验证对应分支；**未改算法、阈值或真实序列挑选规则**。

人工覆盖证明分支可实现，不证明其在视频里有足够作用。

## 4. 端到端合成短帧

`runs/ts_r5_smoke/validation.json`：13个case ×（25个ON模式＋原anchor＋新OFF）= **351项**，每项2帧64×64。
覆盖QP0/22/27/32/33/37、TS关闭、lossless、TSRC关闭、DQP、BDPCM、LB、RA。

- 全部解码picture hash通过；逐CG q hash/预算/变化计数trace编解码一致。
- Current与新OFF各13个case对保留anchor bit-exact；TS/TSRC关闭时各模式一致。
- 另两项R5关闭trace/统计，码流不变；另23项旧模式QP0对保留R4 Encoder bit-exact。
- 先跑338项，再复用完成任务追加13个OFF；不是338+351个独立case。
- 只生成合成输入YUV，无重建视频；868条R5聚合记录，不是正式统计样本。

| 模式 | active位置 | 相对Current映射改变 | 相对R3映射改变 | 新机制 |
|---|---:|---:|---:|---|
| R5-1 | 10318 | 77 | **0** | 搜索4211，接受154；重排0、补查1，补查未改变目标映射 |
| R5-2 | 10318 | 77 | **0** | 原R3有效选择153，回看153，否决0 |

两组全部13个case都与R3-1 bit-exact。
相对Current的77次改变来自继承的R3，不能算R5新效果。
`r5_incremental_activity_covered=false`与正确性PASS分开记录；不隐藏活动检查未满足。

## 5. 限量真实内容预检

BasketballDrill、LBeu、QP22、**3帧**，Current/R3-1/R5-1/R5-2共4项，4/4通过解码hash、实际编码帧数均3。
输出 `runs/ts_r5_real_preflight/`，没有新XLSM、输入副本或重建YUV。
相较旧R4两帧预检多包含第三帧，但单序列单QP三帧仍不是充分运动/分辨率/CTC覆盖，不能算BD-rate。

两组各9928个active位置；原R3有效选择20个：

| 模式 | attempted | accepted | 重排/补查/否决 | remap_vs_r3 |
|---|---:|---:|---|---:|
| R5-1 | 575 | 20 | 重排0、补查0 | 0 |
| R5-2 | 20 | 0 | 否决0 | 0 |

两组均相对Current有13次映射改变，但全部继承R3。
三个实验码流SHA同为 `fb27eb166d0368753ef795f6ef574cbe2fcb1062fb0a3205ca389e8b0ce8533f`；
Current为 `a7867897efcf74c7da7cf3b515373d26f9e85ba147e0e4b12841a09a3602a892`。
这次有真实码流SHA，才能声称此短测bit-exact；不要将该结论外推到全部序列/配置。

## 6. 宏、脚本与后续决定

- 默认/覆盖/互斥测试6项通过：25种ON默认＋OFF、625种显式覆盖、新旧冲突、非法值、master-OFF误请求等。
- batch测试16项通过，覆盖新模式、编号目录与既有共享池/逐组XLSM/失败重试。
- 基础BD分析15项通过，包含R5编号/flat目录、缺点拒绝、Current保护、分量BD后6:1:1。
- 所有analysis模式测试共27项通过；56项LB CE半帧dry-run完成，未正式编码。

结论：**R5-1暂不值得完整长跑；R5-2虽有人工有效分支，但真实覆盖不足，优先级低。**
本轮代码可复现、可通过宏运行，不等于已优化成功。不以放宽阈值来追求正结果。
下一轮若继续优化，应另立“评分或样本是否能区分当前候选”的新假设；保留本版结果和编号，不能悄悄换公式后沿用R5-1/2名称。
