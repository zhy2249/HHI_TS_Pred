# R3本地实现验证（2026-09-19）

版本：R3-20260919-v1。四组算法已实现、构建并通过下述测试。**没有正式CTC或R3收益结论。**
算法与启用方式分别见 `TS_Predictor_R3_Experiment_Design.md`、`TS_Predictor_R3_Implementation.md`。

## 1. 代码范围与状态

- TypeDef.h：新增 `JVET_BJUT_TS_R3_MODE=0..4`，与旧fixed/revision1/R2默认模式互斥。
  master关闭却选择实验、非法模式值均编译失败；交付master=1、模式全0，即Current。
- TsFixedPrediction.h：RG/RGY复用R2-R winner，仅加入固定候选G−B>0保护；
  NG/NGY保留R2-N score，仅增加紧邻上一CG的G−B>0条件。
- ContextModelling：仅最终CG更新，TU-local；空CG清除近期证据；Y-only色度不改变预测、不更新状态。
  RDOQ最终CG清零决策之后的钩子、Writer/Reader共同预测入口继续复用，没有更改正式语法结构。
- 新增TsR3Stats.h及TsR3StateTest，基础分析工具通过 `--revision r3` 识别新模式。
- batch只扩展模式列表，不改共享池、恢复、无重建和每组完成即写Excel逻辑。

所有实验比特流仍需要选择同一实验的解码器；模式未传入bitstream。
运行时覆盖优先于宏默认，不能只检查源码宏而忽略实际启动banner与可执行文件路径。

## 2. 构建与二进制身份

独立Release构建，`NX2_TOPLEVEL_OUTPUT_DIRS=OFF`、`NX2_ENABLE_LINK_TIME_OPT=OFF`，未用CMake选择实验宏。
先完成ON构建，再临时改头文件master=0构建OFF，最后恢复源码master=1。
OFF可执行文件是已编译的OFF版本；恢复头文件后不要把OFF目录重新编译成ON而继续称为OFF。

| 可执行文件 | SHA256 |
|---|---|
| build/ts-r3/bin/EncoderApp | 52b87556799c0c4105bc9191cec0be578e66f70b3ac7aa92f8e676d1f845d9ee |
| build/ts-r3/bin/DecoderApp | b5be5e5e13cdb34f1750bb56978ffc4fd6274e8d8df00f7c79748392fef467ca |
| build/ts-r3-off/bin/EncoderApp | d9a593a2b3abe043968e97fbfdcf12bd5552cdd9f6e8d71aeb8e0d98efa98e84 |
| build/ts-r3-off/bin/DecoderApp | e2af1a91d79ca6e005568f0d167c0c9876d04fe86ba7f488d0f4900d7b0745c2 |
| 保留build/ts-r2/bin/EncoderApp | 1d2d81013ca0ee47217d48ee81cae8b7ed0dbcaabfc1582f56a89988a9a0c953 |
| 保留build/ts-r2/bin/DecoderApp | 3428422c50027fe44e4abe2f36ae171981c750f2e2f6cd9fe33ef53dc21de898 |
| 保留build/ts-anchor/bin/EncoderApp | 4203250460849a87e5643b49b1c96354e4eb92d263b404c82f0074d3ae046257 |

旧build目录程序未重编，以上旧SHA与开始实施时一致。
**构建副作用**：初次配置沿用了项目默认顶层输出，曾更新 `bin/release`、`lib/release` 及顶层Static程序。
随后已改用隔离目录重新构建并测试。不要把顶层默认程序当成保留的旧实验程序续跑；
本验证和后续命令明确使用 `build/ts-r3/bin/`，没有恢复或删除不明版本的顶层构建产物。

## 3. 独立公式、扫描与CG状态测试

`TsFixedPredictorTest`：通过。包含三个局部保护例子、支持不足fallback、32768个五样本模板的固定候选删一贡献检查，
以及64种原生扫描形状、1,267,924次因果邻居检查。扫描原语的覆盖不能替代实际配置允许尺寸的审计。

`TsR3StateTest` 每模式600个人工TU，Y/U/V、intra/inter、矩形、小尺寸、不同幅值、BDPCM、全零CG等：

| 模式 | CG检查 | 当前/未来q污染后的预测检查 | 色度scope隔离检查 | 选NoPred CG | 在CG1选NoPred | 空CG后清除正state的旧证据 |
|---|---:|---:|---:|---:|---:|---:|
| RG | 6587 | 104192 | 0 | — | — | — |
| RGY | 6587 | 104192 | 66932 | — | — | — |
| NG | 6587 | 104192 | 0 | 279 | 135 | 93 |
| NGY | 6587 | 104192 | 66932 | 98 | 43 | 31 |

用独立实现的remapping、log cost、三遍预算及G/B/S/H公式核对结果；
并调用原生CABACWriter核对预算，改变当前及未来系数不能改变当前预测或已完成CG的历史。
测试中CG0始终Current；NG/NGY不等到两个历史CG才启用；空CG即使留下小正S也必须把H清零。
这些是状态与因果正确性检查，不是对人工系数进行RD评价。

旧 `TsR2RateTest` 在新ON程序中回归：

- Current、NoPred各6014个CG，fractional cost、context、budget与原生Writer一致，各12672项Rice长度检查。
- R2-N、R2-F各5718个状态/clone/未来污染检查，各12672项Rice长度检查。

这验证旧CABAC回放未被破坏，**不把R3的syntax/log代理成本称为真实CABAC bits**。

## 4. 端到端短帧编码

命令见实现文档；输出 `runs/ts_r3_smoke/`。

- 13个case ×（17个运行模式 + 保留anchor + 新OFF）= **247项**，每项2帧64×64合成输入。
- 覆盖QP22/27/32/33/37、QP0扩展TS尺寸、TS关闭、lossless、TSRC关闭、DQP、BDPCM、LB、RA。
- 全部编码成功并通过解码picture hash；Writer/Reader逐CG S、选择、G、H、B、预算及最终q哈希一致。
- 每个case的Current、新OFF对保留anchor **bit-exact**，共两组各13项对照。
- TS关闭、TSRC关闭时所有模式与Current一致。
- 额外4项活跃QP0实验关闭trace和统计，码流与观察开启时一致。
- 额外13项旧模式QP0与保留R2编码器bit-exact，涵盖Current、固定三组、revision1五组、R2四组。
- 不输出重建YUV；目录中唯一YUV为生成的测试输入。

主要证据：`validation.json`、`summary.csv`、各任务encode/decode日志、`.done.json`及比特流。
247不包含额外4+13项的重复编码；重复编码在临时目录比较后自动清理。
测试不是对所有输入bit-exact的数学证明，也没有证明远端编译及配置正确。

### 实际作用与保护覆盖

从四组13个case的最终Writer合计1790行聚合数据提取；不是同一批CG的配对比较。

| 模式 | mapped改变位置 | 局部提出/接受/拒绝 | 选NoPred CG | 正S被近期保护阻止CG |
|---|---:|---|---:|---:|
| RG | 77 | 1551 / 153 / 1398 | — | — |
| RGY | 60 | 1227 / 117 / 1110 | — | — |
| NG | 776 | — | 224 | 375 |
| NGY | 663 | — | 193 | 324 |

RG接受和NG选择并不必然改变当前最终q的映射；零值及p=0/1等价等情况使两个计数不同。
合成输入常用QP的很多实验码流仍与Current相同，非零覆盖主要由QP0/lossless等case提供；
这不代表真实内容一定缺乏活动，也不能证明常用QP已有足够实验作用。
无需为让smoke“更活跃”而改变已冻结条件。

## 5. 宏、批量与分析测试

| 测试 | 结果 |
|---|---|
| test_ts_fixed_defaults.py | 6项通过；17种ON默认+OFF、289种显式覆盖、非法值/新旧冲突/OFF误配置 |
| test_ts_fixed_batch.py | 10项通过；R3共享池、分组写入、恢复/失败与重试路径 |
| test_ts_r2_analysis.py | 6项通过；R2兼容、R3识别、分量BD后6:1:1、缺点/Reference检查 |
| Encoder/Decoder四模式启动探测 | 8项有效banner匹配 |
| LB CE计划dry-run | 112项；C4+E3、四QP、半帧、无重建、hash、Excel |
| ts_r2_activity.py --revision r3 | 成功提取1790行，无列数不一致 |
| Python编译及git diff --check | 通过 |

调度测试会有意打印模拟FAIL/RETRY，最终unittest为OK；不代表真实编码失败。
dry-run只核对计划，不证明输入存在、任务已编码或远端配置已核实。
BD分析依旧Current主比较、各分量独立积分后6:1:1；完整性不足不自动填补anchor。

## 6. 限制与尚未完成事项

1. 未运行正式CTC；未生成新正式XLSM，未修改anchor Reference。没有R3 BD-rate、复杂度或Promising结论。
2. 设计Phase 0的四条真实序列/四QP预检尚未做：默认 `/home/zhy/videos` 下对应四文件不存在。
   用户服务器正式长跑前应先做真实内容短帧检查，核对有效模式、TS活动和解码hash；不能把当前合成测试当成该步骤完成。
3. 当前聚合已有支持数、G/B/H符号/分桶、提出/接受/拒绝、实际映射与CG状态；
   尚未单列局部winner的Current/identity/other三分类，也未加入可选真实context诊断。
   NG的gain_positive_sum/negative_abs_sum是正/负**CG净代理优势**的累计，不是逐系数正/负贡献总量。
4. 基础RD工具已支持R3；协议中三方共同质量区间的父方法消融需有完整结果后进行跨轮分析，不是当前已生成的结果。
5. 日志只观察各实验最终选择TS的样本，仍有条件性。闭环编码允许RDOQ及TS选择改变，减少固定anchor-q研究的限制；
   不能据最终TS内部统计声称彻底分离或消除了选择偏差。
6. 没有跨TU历史、QP启用阈值、训练后调参或在看到smoke结果后更换规则。全分量/Y-only的作用归因仍按冻结设计解释。

后续顺序：服务器真实短帧预检 → 完整LB CE112项 → 按预先规则决定RA/B；不提前选择赢家。
