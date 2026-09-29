# R10 工程验收（2026-09-28）

算法版本`R10-20260928-v1`；同步基点`0b08de8`。
本记录只证明实现正确性与活动，不是CTC或BD-rate结论。
说明及运行命令见[R10实施](TS_Predictor_R10_Implementation.md)。

## 1. 构建和规则

Release EncoderApp、DecoderApp、TsRateCodecTest构建通过；算法选择仅由TypeDef.h/显式运行覆盖决定。
另复制源码，仅把TypeDef.h总宏改为0，构建独立master-OFF EncoderApp。
保留所有历史`build/ts-r9`等实验二进制，新的正式入口为`build/ts-r10/bin/`。

完整`test_ts_*.py`共120项通过（435.726秒）。包括旧实验、数据台账、batch写表/续跑、
全部新宏默认及运行覆盖、R10与fixed/conditional/R2～R9的互斥、非法值、master关闭检查。
独立Python损失矩阵参考：1,600×7=11,200项任意非单调成本、CI平局、空集、完整动作同一、
2:1权重、最大正贡献删除、CF字典序检查。最终统计短路细化后4项R10设计测试通过，
其中新增能力探测不受`TS_R10_CACHE=1`环境影响的检查；实际任务仍按请求开启缓存。

## 2. 原生CABAC与因果性

R9-9及R10-1..7分别在缓存关闭/开启两种情况下运行原生测试。
每次包含262,144项中性context长度检查、40,000项旧score等价检查，160个原生TU、
1,491个CG、23,436个未来系数污染位置。
尺寸2～32方形/矩形、YUV、Rice1～8、低regular预算、BDPCM、全零CG和幅值边界均覆盖。

每CG比较私有回放与原生CABAC estimator的fractional bits、regular预算和出口概率状态，
入口真实状态不受修改，Writer→Reader量化系数完全一致。
R10另有独立参考：直接调用旧公开R9/R8/R2/R3专家接口、独立几何/scan构造V、
按历史目标自己的直接非零类别取CF，再手写选择公式，与新实现动作和loss逐点比较。
缓存测试包含历史q编辑、前缀清零、恢复原q；最终版另检查复制分支切换/恢复概率快照。
公共mode0验证动作逐点等于R9-9，非“近似等价”。

## 3. 第一轮完整回归

证据：`runs/ts_r10_smoke/validation.json`。人工64×64两帧，固定种子；
AI22、AI0（最大TS允许到32）、LB22、RA37、禁TS、BDPCM配置。
308任务=300编解码检查+8次单任务计时（其中2次warmup）。

- 71个旧运行模式在AI22相对历史R9二进制逐字节一致，Current/R9-9还覆盖六个case。
- 七组R10禁TS时等于Current。
- 七组R10及R9-9在六个case均通过统计关闭、缓存开关的bit-exact比较。
- 4,553条最终CG q/action/预算trace两端完全一致。
- 七组R10均至少在一个case相对R9-9有码流活动；没有解码hash错误。

| 模式 | 相对R9-9出现码流差异的合成case |
|---|---|
| 1 | AI0、LB22、RA37、BDPCM配置 |
| 2 | AI0 |
| 3 | AI22、AI0 |
| 4 | AI0 |
| 5 | AI22、AI0、LB22、RA37 |
| 6 | AI0 |
| 7 | AI22、AI0、LB22、RA37、BDPCM配置 |

BDPCM配置仍含普通TS块；差异不表示修改BDPCM语法。2/4/6只在AI0活动，
因此必须先用固定真实内容QP22/37短测验证，不能以合成极低QP活动替代CTC证据。

## 4. 最终源码复验

第一轮后只细化“当前动作全部相同则不计guard拒绝”的观察短路，预测动作不变；
同时补充快照切换测试。最终二进制重新构建，复验记录
`runs/ts_r10_smoke_final/validation.json`：

- 16次原生测试全部通过，包含新增的复制分支快照切换/恢复。
- 170任务（162编解码检查+8次串行计时）全部通过。
- 6个case中，新Current、新master-OFF、历史master-OFF码流完全一致。
- 统计关闭、缓存开关、禁TS、4,553条Writer/Reader trace再次通过。
- 与第一轮共有的150份码流逐字节一致；旧模式回归证据沿用第一轮，不把本次跳过旧组记作重新运行。
- 最终观察提取19,398分层，日志4,268,738字节。

最终Encoder SHA256：`67e710819bbf89afa8248f6e0d5bf16b015a889c6b306e77b928cb6cf15bb1a4`。
Decoder：`65143c8564cf827c29d8dace4156071d69f1d6a3cd4b0bc8f5bd52db9f78f2ac`。
总宏关闭Encoder：`d3897c5961ce3da6e1b18eb869f53aeaa012b32dcfab299a86dbd71ab903b798`。

```bash
python3 scripts/ts_r10_smoke.py --skip-legacy --off build/ts-r10-off/bin/EncoderApp \
  --out runs/ts_r10_smoke_final --jobs 8 --benchmark-repeats 3
python3 scripts/ts_r10_activity.py runs/ts_r10_smoke_final --out runs/ts_r10_smoke_final/activity
```

`--skip-legacy`仅用于已有完整回归后的针对性重验，首次验收不要带该参数。

## 5. 观察数据与性能边界

第一轮活动提取读取126个R10任务（42观察开启、84静默），19,398个观察分层，
相关编码日志4,267,226字节。所有七组均有非零target-selected regret，
说明观察不是旧“验证集内选择后regret恒为0”的同义检查。
这只是最终选中TS的人口，不能直接推断原始残差总体或BD-rate。

第一轮计时期间同主机曾有构建任务，因此不将其耗时用作干净性能结论。
最终轮在本轮构建/并发编码均结束后，关闭所有观察，对R9-9的同一AI0合成输入串行交替测量，
两次warmup不计入结果，所有码流相同：

| 配对 | cache=0秒 | cache=1秒 |
|---|---:|---:|
| 1 | 18.316 | 13.954 |
| 2（反向顺序） | 19.740 | 12.442 |
| 3 | 18.258 | 12.959 |

这是单一极低QP、两帧64×64人工片段的进程wall time；未独占主机，不是CTC速度或精确内核profiling。
缓存默认关闭，独立时序短测结果也不能外推正式CTC速度。
后续可用`--benchmark-repeats 3`串行交替开关、warmup、关闭所有观察；
应另测真实内容和内存，禁止把多任务pool的wall time直接当算法速度。

## 6. 已核对计划与尚未测量

阶段I dry-run：140点；阶段II：56点；固定四序列、QP22/37、8帧预检：56点。
LB使用HHI INI半帧，重建关闭。未开始正式编码、未新增anchor任务、未更新结果数值台账。
七组BD-rate、真实内容目标loss/闭环对应关系、跨类别/配置泛化均待测。

## 7. R10-7 服务器日志诊断（2026-09-29，未改算法）

输入：`experiments/ts_predictor_r10/BasketballDrill_22.log`，100行、5,630字节。
日志包含10次`Decoder Version`启动，均为宏默认`r10_axis_A_tiebreak / mode=7`，
cache=0；没有Encoder标题、编码配置、POC、PSNR或编码汇总，耗时均0.000秒。
它只能确认解码器的R10-7模式，不能确认服务器编码器实际启动或其宏配置。

现有HHI `scripts/HHI测试cfg/LBeu/ConfigLB.ini`第13/14行配置一次编码、十次解码，
第26/27行用`>`及`>>`将stdout写到同一日志，没有`2>&1`。
服务器是否使用相同配置尚未取得证据；若一致，这10次属于解码运行设置，不能推断为算法重试或死循环。
编码未成功启动/没有生成预期码流、解码工作目录错误、日志拿错或被覆盖均需排查。

本地非破坏性复现：DecoderApp读不存在的码流时返回1，stdout同样只有模式、
Decoder标题、内存和极短耗时；`Failed to open bitstream file ... for reading`在stderr。
这是与上传日志相容的具体故障路径，不是对服务器根因的最终确认。
额外空输入试验未复现该正常尾部，而是空NAL警告后异常退出（139），不能把两者混为一谈。

源码核对：R10-7仍为R9-3完整A专家加CI/CF字典序验证；未发现与本日志对应的独有错误。
本地重新运行R10-7原生测试通过：160 TU、1,491 CG、23,436个因果污染位置；
已有LB22合成两帧码流重新解码返回0，两帧MD5均OK。均不能替代服务器BasketballDrill完整测试。

下一步：取得服务器实际encoder/decoder命令、程序`-h`输出、目标bin的绝对路径/大小，
以及stdout和stderr合并的单任务日志和退出码。用新的诊断日志名保留原文件，不立即重跑整组。
`exact-cache=0`和统计默认关闭是合法设置，不会关闭R10-7算法。本次未修改codec或运行脚本。
