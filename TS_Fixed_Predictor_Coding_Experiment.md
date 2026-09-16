# 固定 TS predictor：真实闭环编码实验（v1）

## 1. 本轮问题与边界

本轮验证 NoPred、有界梯度、方向一致性三个固定工具相对 Current 的真实 RD 表现。
每个条件独立从原始视频编码，不复用 anchor 的量化系数、TS 选择、划分、预测或参考重建。
因此，原本输掉 TS 竞争的块可以在新 predictor 下重新入选，避免只在 anchor 已选 TS
样本上评价新 predictor 的局限。

这不是 CG adaptive selection，也不是固定 q 的 counterfactual Oracle。所有普通编码搜索和
快速启发式保持原配置，允许 predictor 引起的后续决策自然变化。本轮不为获得正结果调整阈值、
增删序列或给某一个 predictor 单独放宽搜索。固定 predictor 全部失败仍不能严格否定所有 adaptive
策略，但会降低继续研究的优先级。

不重新运行完整 anchor。使用用户已有 `scripts/JVET-hhi.xlsm` 的 Reference 数据。
该工作簿没有提供可自动证明其编码软件/配置/帧数来源的完整 provenance，因此历史 anchor 的
可比性仍需用户确认；不能仅因路径名匹配就视为验证通过。

## 2. 冻结候选

L=|q(x-1,y)|，U=|q(x,y-1)|，D=|q(x-1,y-1)|，
LL=|q(x-2,y)|，UU=|q(x,y-2)|，均限于当前 TU。

| 参数值 | Predictor | 边界规则 |
| --- | --- | --- |
| current | max(L,U)，原版 | 缺失 L/U 为 0 |
| nopred | p=0，identity remapping | 全位置适用 |
| gradient | clip(L+U-D,min(L,U),max(L,U)) | x=0 或 y=0 时 Current |
| directional | EH=|L-LL|+|U-D|；EV=|U-UU|+|L-D|；EH<EV 取 L，EV<EH 取 U，否则 Current | x<2 或 y<2 时 Current |

新 gradient/directional 不是旧统计实验的 M2 Left/M3 Above，文件与任务以名称标识。
没有训练参数或待调阈值。新公式只是待检验假设，不预设预测准确度或 RD 收益优于 Current。

保持原 remapping：a=0 -> 0；a=p>0 -> 1；0<a<p -> a+1；a>p -> a。
p=0 时仍保留 significance/sign/greater-than/parity/remainder 等语法，不能删除整个 TSRC。
BDPCM 及原本 cutoff=0 的 bypass-only 路径保持 identity。所有合法 TU 尺寸和 component
均走同一逻辑，不硬编码 8×8。

## 3. 真实编解码实现

编译宏 `JVET_BJUT_TS_FIXED_PREDICTOR` 默认在 `source/Lib/CommonLib/TypeDef.h` 定义为 0。
CMake 选项支持 `AUTO`（新构建默认，使用 TypeDef.h）、`ON`（强制 1）、`OFF`（强制 0）。
已有构建目录缓存的 ON/OFF 会保留；要改由头文件控制，先执行
`cmake -S . -B <构建目录> -DJVET_BJUT_TS_FIXED_PREDICTOR=AUTO`，然后修改头文件并重新编译。
不要在正在编码或准备续跑的实验中随意重编原二进制，否则成功 marker 的二进制指纹会变化。
该实验与旧的
`JVET_BJUT_TS_PRED_ANALYSIS` 构建互斥，防止旧 Oracle 的模式解释混入真实实验。

实验 ON 时，`TypeDef.h` 中三个模式宏控制默认选择：

```cpp
#define JVET_BJUT_TS_FIXED_NOPRED       0
#define JVET_BJUT_TS_FIXED_GRADIENT     0
#define JVET_BJUT_TS_FIXED_DIRECTIONAL  0
```

最多一个设为 1；全为 0 时 Current。多开或使用非 0/1 值会在编译时报错。
这些子宏只选择默认模式，总开关 `JVET_BJUT_TS_FIXED_PREDICTOR` 仍需开启。
环境变量 `TS_FIXED_PREDICTOR` 可在单独进程中覆盖宏默认，拼写错误立即退出。
Encoder/Decoder 开始时均输出包含实际模式及 `experimental-v1` 的 banner，另打印宏默认和选择来源。

批量脚本显式提供 `--fixed-predictors` 时强制覆盖默认（仍可列多个模式，分成独立任务）；
不提供时，脚本通过编码器 `-h` 的 banner 获取**实际编译的默认值**，不是读取尚未编译的源码。
探测时清除 shell 中继承的 `TS_FIXED_PREDICTOR`，因此省略参数不会被环境残留悄悄改成另一模式。
随后将选定模式传给每个 Encoder/Decoder 子进程，保证两端一致，并按实际模式分目录输出。
这意味着批量默认模式的子进程日志可能显示 environment override，但该值来自编码器的宏默认。
直接运行二进制且不设置环境变量时则完全使用本二进制的宏默认。
总开关关闭的二进制不能由运行参数强行启用实验，脚本会拒绝显式的 fixed 实验请求。

批量脚本在启动前检查二进制能力，并检查实际日志模式，防止把旧统计版当作真实编码版。

源码路径：

- `source/Lib/CommonLib/TsFixedPrediction.h`：模式、公式和进程设置。
- `ContextModelling.h`：从真实 scan position 获取邻居及统一的正/反 remapping。
- `QuantRDOQ.cpp`：量化候选上取整补充检查和候选 level rate 都使用新 predictor；保持最终 CG RD 清零决策。
- `CABACWriter.cpp`：实际 Writer 与 estimator 的 TS 多遍 level coding 共用新 remapping。
- `CABACReader.cpp`：最后一遍按前向扫描恢复真实幅值时使用同一 predictor。

没有修改正式 bitstream signaling。实验模式在码流外指定，非 Current 码流必须使用匹配实验模式的
Decoder；不得宣称原版兼容或作为可交换的正式码流交付。正式集成时仍需定义工具开关/语法。

CG 内之前位置的系数在 Decoder 最后一遍已完成 inverse remapping；前面 CG 已完全完成。
新增 LL/UU/D 也满足前向分组对角扫描顺序，原生 scan 表测试覆盖了包含 TS 尺寸在内的更大集合。
不使用邻近 TU、原始残差、未来系数选择 predictor。

## 4. C/E、LB 配置：特别注意完整帧与半帧

复用 `--preset LBeu --class C,E`，这实际读取
`scripts/HHI测试cfg/LBeu/ConfigLB.ini` 和其中的 `encoder_lowdelay_nx2High.cfg`。
这与先前 CE 短帧统计的 `--local-preset LB` 普通配置不同。
完整实验不能不经确认直接与普通 LB 的历史 anchor 混比。

| 序列 | per-sequence 完整帧数 | 当前 HHI INI 帧数 |
| --- | ---: | ---: |
| BasketballDrill | 500 | 250 |
| BQMall | 600 | 300 |
| PartyScene | 500 | 250 |
| RaceHorsesC | 300 | 150 |
| FourPeople | 600 | 300 |
| Johnny | 600 | 300 |
| KristenAndSara | 600 | 300 |

`--full-sequence` 从各自 per-sequence cfg 读取 FramesToBeEncoded，覆盖 INI 的 framecount；
不把这些数字写死到脚本。与 `--frames` 互斥。不加该选项则保留已有脚本的 INI 帧数语义。

QP 22/27/32/37，三候选 × 七序列 × 四 QP = 84 任务，每候选 28 任务。
不运行完整 Current；仅小规模 bit-exact 检查。输入默认 `/home/zhy/videos`。

启动前必须确认 Reference 的软件版本、配置（High/普通）、输入文件、帧数、位深、
帧率/TemporalSubsampleRatio、QP 和工具开关与本轮一致。
如果旧 anchor 是半帧，不能直接将它与完整帧新结果算 BD-rate：选择匹配的半帧实验，
或提供匹配的完整帧 anchor；不能把不匹配的数据包装为有效对照。

## 5. 构建与测试

在工程根目录执行。只创建独立构建，不覆盖原来的 bin/EncoderAppStatic。

```bash
cmake -S . -B build/ts-fixed \
  -DCMAKE_BUILD_TYPE=Release \
  -DNX2_ENABLE_LINK_TIME_OPT=OFF \
  -DNX2_TOPLEVEL_OUTPUT_DIRS=OFF \
  -DJVET_BJUT_TS_FIXED_PREDICTOR=ON \
  -DJVET_BJUT_TS_PRED_ANALYSIS=OFF
cmake --build build/ts-fixed --target EncoderApp DecoderApp TsFixedPredictorTest -j 4
build/ts-fixed/bin/TsFixedPredictorTest
python3 scripts/test_ts_fixed_batch.py
python3 scripts/test_ts_fixed_defaults.py
```

可重做合成短帧验证（原版路径换成本地真实原版；临时目录不保证长期存在）：

```bash
python3 scripts/ts_fixed_smoke.py \
  --anchor /tmp/ts-pred-original/bin/release/EncoderApp \
  --off build/ts-anchor/bin/EncoderApp \
  --encoder build/ts-fixed/bin/EncoderApp \
  --decoder build/ts-fixed/bin/DecoderApp \
  --jobs 2
```

smoke 仅生成一个小型 synthetic_input.yuv 作为输入，不输出重建视频。
合成数据不能用于判断压缩收益，不计入 CTC 数据集。

## 6. 正式批量命令

以下命令按用户要求规划完整帧数；仅当 anchor 同样是完整帧数和相同 HHI 配置时用于正式对比。
先 dry-run，核对列出的 84 个任务；再去掉最后的 `--dry-run` 执行。

```bash
python3 -u scripts/batch_test.py \
  --preset LBeu --class C,E --full-sequence \
  --qps 22,27,32,37 \
  --fixed-predictors nopred,gradient,directional \
  --encoder build/ts-fixed/bin/EncoderApp \
  --decoder build/ts-fixed/bin/DecoderApp \
  --decode-md5 --no-recon --jobs 10 \
  --input-dir /home/zhy/videos \
  --xlsm-template scripts/JVET-hhi.xlsm \
  --out-dir runs/ts_fixed_LB_CE \
  --dry-run
```

若 anchor 确认使用 INI 半帧配置，去掉 `--full-sequence`，并建议把输出目录改为
`runs/ts_fixed_LB_CE_half`，避免把两套实验混在一个目录。
若只有普通 LB anchor，应重新明确对应配置，再使用 `--local-preset LB --sequences ...`；
不能在保持 High 结果的同时仅更改报表标签来匹配。

## 7. 无组间等待的调度与存储

不创建“三次 batch_test.py 依次运行”的 shell 循环。
`--fixed-predictors` 把所有任务展开到现有同一个 ThreadPoolExecutor，`--jobs 10` 为
全实验最大并发任务数（一个任务包括编码及可选 hash 解码，解码也占该槽位）。
提交顺序为 nopred 的全部任务、gradient 的全部任务、directional 的全部任务，**没有组间 barrier**。
当 nopred 已全部分派、其中仍有 9 个运行时，只要空出 1 个槽位，就立即开始 gradient，
无需等余下 9 个完成。支持把多个 `--run` 配置同样加入该队列。

任务环境独立传给子进程，不修改全局 os.environ，不同组同时运行不会串 mode。
不要同时启动多个脚本写同一输出目录。并发数是资源上限，不是每组分别 10 个。
正常任务可持续补位；剩余任务总数不足 10 时，末尾尾部空闲属于正常现象。
编码时间受并发、CPU/内存带宽竞争影响；本轮时间是运行信息，不用于精确复杂度结论。

`--fixed-predictors` 自动启用 no-recon。编码和解码的最后一个输出参数均为 `-o ''`，
覆盖 cfg 的 ReconFile，真正关闭重建文件 I/O；不是先生成 YUV 再删除，也不是向 /dev/null
持续写重建数据。Decoder 仍然在内存重建并核对 picture hash。保留实验码流用于复查。

不输出逐 coefficient/CG 文本或旧 counterfactual CSV，因此数据主要为码流、文本日志和报表。

输出结构：

```text
runs/ts_fixed_LB_CE/
  experiment_plan.json
  summary.csv
  failures.csv
  nopred/
    summary.csv
    JVET-hhi.xlsm
    LBeu_BasketballDrill/
      LBeu_BasketballDrill_QP22.bin
      LBeu_BasketballDrill_QP22.encode.log
      LBeu_BasketballDrill_QP22.decode.log
      LBeu_BasketballDrill_QP22.done.json
      ...
  gradient/...
  directional/...
```

每个模式单独复制模板、填 Test 数据，避免多个 predictor 覆盖同一组 Test 单元格；
原始 `scripts/JVET-hhi.xlsm` 不修改。不伪造脚本没有计算的 BD-rate：工作簿公式/宏是否重算
取决于表格应用，检查 Test 数据及 Reference 后按项目原流程重算。

## 8. 续跑、失败与模式防误用

重复同一命令自动续跑。成功条件包括编码正常、实际帧数匹配、实验 banner 匹配、码流非空；
启用 decode-md5 时还要求正常解码且全部预期帧 hash OK。
marker fingerprint 覆盖模式、二进制文件身份（路径/大小/mtime）、输入身份、配置内容、QP、
帧数、附加参数及 decoder 信息。配置改变、marker 缺失或码流截断不再被视为成功。
成功 marker 在编码和解码通过后才写出；日志缺失也会触发重跑。
未生成 marker 的半成品保留以便诊断，下次同一任务会重跑。

默认不重跑成功任务。`--overwrite` 明确重跑指定输出目录内计划中的任务；不要对生产实验
随意使用。失败可查看 failures.csv 和对应日志，再重新运行同一命令。
原有 `--retry-failed` 是所有正常任务结束后的重试流程，不影响三组正常任务之间的连续补位。

手工解码必须指定正确模式，例如：

```bash
TS_FIXED_PREDICTOR=gradient build/ts-fixed/bin/DecoderApp \
  -b runs/ts_fixed_LB_CE/gradient/LBeu_BasketballDrill/LBeu_BasketballDrill_QP22.bin \
  -o '' -dph 1
```

## 9. 分析与事前决策原则

主指标是相对于匹配 anchor 的 sequence-level BD-rate，分别报告 Y/U/V 和项目统一的综合指标；
同时检查四个 QP 的实际 rate/PSNR 点，防止区间不足、交叉或质量不匹配造成误读。
报告 C、E 分组和七序列等权平均、中位数、最差退化；不能让码流大的单序列掩盖退化。
样本有限时可按整个 sequence bootstrap，不能把大量系数当作独立证据。
实际 bitstream_bytes、编码/解码时间也保留在 CSV，但并发 wall time 不作为精确性能结论。

本轮先不在线输出 TS 细分 census；不会伪称已有新模式的 TS 使用率/尺寸统计。
如果 RD 信号需要解释，可另加最终 Writer 的模式感知 census，或独立复跑选定片段；
不可直接拿旧 CE counterfactual 数据当作本轮新系数分布。

事前规则：

- 任一解码失败或 Current 不 bit-exact：实现未通过，禁止解释该模式 RD 收益。
- 所有候选总体退化且多数序列退化：固定替换 Negative，不为了正结果继续调公式。
- 收益很小、仅一两条序列或 QP 方向反转：Weak，不等同于工程可用。
- 稳定改善、多序列一致且没有不可接受的最差退化：进入独立内容/配置确认；不是立即宣布标准工具有效。
- 不因某个 fixed 有效就推断 CG adaptive 有效；后者仍需验证历史预测与 capture ratio。

任何 Promising 判断都应同时给出收益的绝对量级和分布，不只引用统计显著性。
本轮不根据尚未产生的 CTC 数据预设正结果，也不自动启动长时间实验。

## 10. 已完成验证（2026-09-11）

- Release 实验版和宏 OFF 版 EncoderApp/DecoderApp 编译通过。
- 7 个短帧 case：AI、LB、HHI LB-High、BDPCM、lossless、TSRC-off、TS-off。
- 每 case 运行 untouched 原版、宏 OFF、current、nopred、gradient、directional，共 42 个任务。
- 全部解码 hash 通过；current 和宏 OFF 在各 case 与原版 bit-exact。
- TSRC-off/TS-off 下三种 alternative 与 Current 全部 bit-exact。
- 每个 alternative 至少在一个活动 TS case 中产生不同码流，排除模式完全未生效的空验证。
- 所有 smoke 输出目录只有 synthetic_input.yuv 输入文件，没有重建视频。
- 原生 scan 表 64 个完整形状、1,267,924 个邻居先后检查通过（覆盖 TS 尺寸的更大集合，
  不代表 64 个形状都在当前配置允许 TS）。
- 三个 Python 单元测试：任务/环境隔离、真实 main 的跨组连续补位、无重建与成功/截断续跑。
- 三模式真实 batch smoke 编解码通过，分别生成三份 XLSM，未修改模板。

机器可读验证：`runs/ts_fixed_smoke/validation.json`；
批量验证：`runs/ts_fixed_batch_smoke/summary.csv`。这些是实现检查，不是 CTC 结果。
