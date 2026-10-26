# R15：真实量化与 TSRC 接入

用户在审计实现之后要求“完成代码修改”。本次在 `5b6d5fc` 基础上将相同的 18 项静态多目标映射接入 **QuantRDOQ、真实 CABACWriter 和 CABACReader**。算法 revision 为 `R15-CODEC-v1`，映射仍为 `TS-MG-STATIC-FAST-v1`，连续编号仍为 `compact-18-v1`。

实现已具备生成和解码新实验码流的路径。当前验证使用合成 TU 和局部编解码库；没有启动 EncoderApp，没有新视频编码或正式 BD-rate。原双来源固定 q 审计继续保留，其结果与今后的闭环编码结果分别保存。局部验收见 [验证记录](TS_Predictor_R15_Codec_Validation.md)，运行命令见 [脚本说明](../../scripts/README_ts_r15_codec.md)。

## 算法与适用范围

18 项编号、候选、tie、G/N/P/D/X 搜索及 11111/22111 权重均沿用 [原实现说明](TS_Predictor_R15_Implementation.md)。不新增 predictor、阈值或 guard。源码选用已验证的 PREFIX 引擎；没有把 FAST 微基准或离线 rate 当作编码性能。

输入为已经恢复的 `H=(L,U,D,LL,UU)` 幅值，以及该 TU 的 Rice 和动态范围。`n` 是非零位置数，重复幅值计入。Identity 对所有 n 返回空列表，其余方法在 n<3 时返回 Current；候选为 `{1} ∪ positive(H)`。

动作 `P=(p1,...,pk)` 用完整结构传递：0→0；命中 pj→j；其它正幅值 a→`a+k−count(pj<a)`。解码使用同一函数族的逆置换，不用针对当前 a 拟合出的虚拟单 predictor。只删除最终无作用后缀，不改变搜索中的中间状态。

适用范围是 **TS 且 TSRC 启用、非 BDPCM，Y/U/V**。TU 尺寸完全由现有码流/配置决定，没有增加尺寸白名单。普通变换、TSRC 禁用和 BDPCM 保留 Current 路径。纯 bypass 系数不 remap；这是 TSRC 原有规则。

选择器无可变历史状态。既不传 mode bit，也不传目标列表；编码器和解码器须采用相同实验设置和版本。R15 码流不能交给旧单 predictor 解码器，也不能用 R15 模式解码现有 R13 来源流。

## 三条真实调用路径

| 文件 | 接入与约束 |
|---|---|
| `CommonLib/ContextModelling.h/.cpp` | 构造时固定目标范围；`prepareTsR15()` 读取物理因果邻域并返回完整 Action；目标路径误用单 predictor API 明确报错 |
| `CommonLib/QuantRDOQ.cpp/.h` | 在写入当前临时 level 前固定一次 Action；同一组候选共用该 Action；regular 路径按完整 map 调用原 `xGetICRateTS()` |
| `EncoderLib/CABACWriter.cpp` | 每个 CG 调用内懒计算映射缓存；真实编码与 fractional estimator 共用逻辑；三个 pass 不重新搜索；缓存不跨 CG/量化试验 |
| `DecoderLib/CABACReader.cpp` | 第三遍恢复当前 remainder 后，使用已经反映射的早先邻居重新选择 Action，再逆映射当前正幅值；不读取未来部分 level |
| `CommonLib/TsMultiMapping.h` | 原共享选择、完整 map/unmap 和 checked public-mode lookup |
| `CommonLib/TsR15CodecStats.h` | 可关闭、固定规模、线程安全的只读计数 |

RDOQ 的零候选、原有 distortion、lambda、significance/sign context 以及 CG 全零 RD 竞争没有改变。后续 CG 从最终 dstCoeff 读取邻域；CG 清零后没有 R15 历史状态或旧缓存需要回滚。Reader 只读取已经恢复的幅值，符号最终写回的时机不影响幅值选择。

原候选生成限制继续保留：round 和原 min 候选先加入；只有 `up` 不同于二者，且 **`map(up,P)==1`** 时才增加上取整候选。映射到 2～K 不自动增加试探。实际源码在该处没有单独 epsilon 判定，本次没有凭文档增设 epsilon。原保护映射和 R8 扩展搜索分支保持原逻辑，R15 不启用 R8 搜索。

`P` 在当前量化值产生前固定，并不意味着整个 TU 的 P 在量化开始前固定：第 i 个位置使用当时已经确定的前序量化值。改变 P 后仍可能改变量化候选、q 和 TU 选择。因此未来必须测真实 bit/PSNR、hash 和 BD-rate；不能沿用固定 q 的收益数字作为闭环结果。

## 宏与运行时选择

`source/Lib/CommonLib/TypeDef.h` 提交默认值：

```cpp
#define JVET_BJUT_TS_FIXED_PREDICTOR 1
#define JVET_BJUT_TS_R15_MODE       0  // 1..18 选择对应闭环子实验
#define JVET_BJUT_TS_R15_STATS      0  // 固定长度计数，计时默认关闭
#define JVET_BJUT_TS_R15_ANALYSIS   0  // 旧 R13 来源的离线审计，不选择编码实验
```

直接将 `R15_MODE` 改为目标编号并重新构建即可；其它实验默认宏须为 0。无运行参数时使用宏值。`TS_FIXED_PREDICTOR=r15_...` 或批量脚本 `--fixed-predictors` 显式覆盖宏默认；编码和解码进程必须一致。新模式为内部 policy 115～132，不与旧编号重叠。编译检查覆盖 master、R2～R14、旧固定/条件模式、R7 别名和 R10 cache 的冲突。

启动行明确输出 `R15-CODEC-v1`、映射协议、公共编号、runtime、PREFIX、integer-syntax、目标范围、map-up-to-1、state=none 和 mode-bits=0。批量任务及断点记录核验这些信息和程序/config SHA；旧版本不被当作已完成 R15 编码。

## 统计口径与资源

`JVET_BJUT_TS_R15_STATS=0`，运行时 `TS_R15_STATS=0/1` 可覆盖。默认不做计数。开启后进程结束最多输出两条人口汇总和 k=0～6 共七条深度汇总，没有逐系数、逐帧、逐 bin 输出。

- `TS_R15_QUANT_STATS`：RDOQ **试验**位置数、上取整具备加入条件的数量、实际加入次数、相对 Current 的 gate 改变数、候选列表长度之和。这些位置可能来自被放弃的 TU/CG；不是最终 TS 人口。`listed-levels` 是候选列表数，不能当作实际完成 rate 评估的次数，原函数可能提前返回。
- `TS_R15_WRITER_STATS`：最终真实 Writer 的 regular 非零位置和实际映射改变数；同一位置跨 pass 不重复计数。排除 BitEstimator、纯 bypass、BDPCM 和零值。它不是所有最终 TS 系数的分母。
- `TS_R15_TARGETS`：分别给出上述两个人口的规范化列表长度直方图，禁止混合两种分母。

本地测试以单子进程逐模式执行。完整 q/语法/上下文记录经 FIFO 流式 SHA256，不在磁盘保存几百 MiB 的原始记录；只保存小日志和哈希。

## 回归边界与后续使用

R15-2 和 R15-6 应全路径等价。R15-1 和旧 NoPred 在共同目标范围内应等价；但**不能要求所有工具范围的两份编码都等价**：旧 NoPred 在 TSRC 禁用时也会影响现有 TS-RDOQ，而 R15 明确保留该非目标路径为 Current。局部测试分别核验共同范围的等价性、所有 R15 非目标路径与 Current 的一致性，不修改旧 NoPred 来迎合比较。

已有 R13/R14 码流、正式码率/PSNR/BD-rate 表不变。离线控制 MG00/02/03 不创建新子实验，正式 anchor 继续是 Current。今后小范围闭环通过后再选少量方案进入 CE/B；当前没有工程收益或复杂度百分比结论。阶段性建议先核验 R15-2/3/17，R15-6 作为等价回归不重复跑完整 CTC，X 组用于比较搜索上限，不能称为 CABAC oracle。
