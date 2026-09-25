# R4本地正确性验证（2026-09-20）

版本R4-20260920-v2；六组公式不变。实现见 `TS_Predictor_R4_Implementation.md`。
本文件是实现验证，不是正式CTC、BD-rate、复杂度或Promising结论。

## 1. 构建与身份

宏仅由TypeDef.h选择；未用CMake定义实验模式。独立Release目录、顶层输出OFF、LTO OFF。
完成ON构建后，临时把master改0构建独立OFF程序，随后恢复master=1，所有模式=0（Current）。
旧R3/anchor程序SHA与开始实施时一致；未更新顶层bin/lib，未替换任何服务器结果表。

| 程序 | SHA256 |
|---|---|
| build/ts-r4/bin/EncoderApp | 6879d505657d05cab4fefc5ee4a6f083872fa5b71a0ae460411ed6791b8ed46d |
| build/ts-r4/bin/DecoderApp | 84cb761dc22263a6eea7790d775cc8d64796d3481aa325281793626b39b3457a |
| build/ts-r4-off/bin/EncoderApp | ef502ac5db1962d6f1ad5c5aa2d5ba78c817cb3b0c430a90f9d53754a14181cf |
| build/ts-r4-off/bin/DecoderApp | 5fe2421f4d6231ee1b2aa8e80e700bf3b2f724c8f5f5e0d9290fb8afed012d5d |
| 保留build/ts-r3/bin/EncoderApp | 52b87556799c0c4105bc9191cec0be578e66f70b3ac7aa92f8e676d1f845d9ee |
| 保留build/ts-r3/bin/DecoderApp | b5be5e5e13cdb34f1750bb56978ffc4fd6274e8d8df00f7c79748392fef467ca |
| 保留build/ts-anchor/bin/EncoderApp | 4203250460849a87e5643b49b1c96354e4eb92d263b404c82f0074d3ae046257 |

OFF目录在恢复头文件后不能直接重编，否则会变成ON。新实验模式没有传输信令，编解码器必须选择一致。

## 2. 冻结原型对生产实现

- `ts_r4_design_check.cpp`：3,145,728个五位置模板/Rice组合，生产R4-1/2/3与独立冻结原型逐项一致。
  I/M不重搜候选，固定输入上的分支互斥与并集正确；C不重排R3已接受选择，2520个人工组合有rescue。
- `ts_r4_extension_design_check.cpp`：32000个signed网格目标，生产R4-4/5/6与独立冻结原型一致。
  方向平局/边界、guard、当前和未来污染、primitive不读自身目标、signed范围检查通过。
- 这些原型沿用真实remapping/成本函数，属于公式与实现一致性检查，不是独立CABAC损失模型验证或视频收益估计。

## 3. 原生CABAC往返和实际扫描

`TsR4CodecTest`每组240个人工TU，宽高各2/4/8/16/32，覆盖矩形、YUV、intra/inter元数据、
BDPCM、零CG、小/大/稀疏幅值、Rice1..4。每组2254个CG、35476个目标：

- 直接调用原生CABACWriter/BinEncoder和CABACReader/BinDecoder，逐CG解码q与输入完全一致，regular budget一致。
- 所有读取位置必须满足原生grouped scan index<当前index；当前及全部未来系数污染不改变预测。
- 以Reader当前CG去符号缓冲区＋signPattern构造视图，与完整signed网格预测一致。
- `TS_COND_TRACE=1`重跑时，final-CG诊断预算也通过与实际Writer/Reader的断言。
- R4-3专门注入模板[2,1,10,1,1]、目标a=2、Rice1，断言R3=2、rescue=0、H=2，并完成真实CABAC往返。
- 旧`TsFixedPredictorTest`通过：64种扫描形状、1,267,924次邻域因果检查。
  人工几何覆盖不等于所有尺寸在CTC里都出现或都被配置允许。

旧R3四模式的600-TU状态测试均通过；Current/NoPred各6014个CG回放与原生fractional cost/context/budget完全一致，
R2-N/F各5718个状态检查通过，每模式12672个Rice长度检查通过。没有把R4代理分数称为fractional bits。

## 4. 合成端到端短帧

`runs/ts_r4_smoke/validation.json`、`summary.csv`及encode/decode日志记录：

- 13个case ×（23个ON模式＋旧anchor＋新OFF）= **325项**，每项2帧64×64合成输入。
- 覆盖QP0/22/27/32/33/37、TS关闭、lossless、TSRC关闭、DQP、BDPCM、LB、RA。
- 全部解码picture hash通过；逐CG实际系数hash、预测变化计数和regular预算trace一致。
- Current和新OFF分别在全部13个case与保留anchor bit-exact；TS/TSRC关闭时全部模式一致。
- 额外6项R4 QP0关闭trace/统计编码，与观察开启码流一致。
- 额外17项旧模式QP0，与保留R3 Encoder逐项bit-exact（含四个R3模式）。
- OFF Decoder另解码QP22 OFF码流，两帧hash通过。
- 唯一生成YUV为测试输入，没有重建文件。合成目录约19MB，含所有模式的debug trace，不代表正式聚合日志规模。

325不包含额外重复编码；第一次无OFF的312项已成功，第二次复用这些结果，只追加13个OFF任务并重做验证。
不能把两次运行相加称为637个独立case。

### 实际最终Writer活动

六组共2612行聚合记录，来自各自闭环结果，不是同一批系数的配对实验：

六组各自观察到相同的13种TSRC尺寸：2×8、4×4、4×8、4×16、8×2、8×4、8×8、8×16、
16×2、16×4、16×8、16×16、32×4。这是本次合成的observed集合，不是写死的支持尺寸列表。

| 组 | 相对Current实际映射改变 | 本组q上相对R3映射改变 | 额外机制观察 |
|---|---:|---:|---|
| R4-1 | 27 | 51 | 屏蔽114个原R3非identity分支 |
| R4-2 | 53 | 27 | 屏蔽45个原R3 identity分支 |
| R4-3 | 77 | **0** | 补查1398次、接受1次，但未改变目标映射 |
| R4-4 | 94 | 62 | 完整方向模板且支持足够的搜索2067次、接受168次 |
| R4-5 | 648 | 591 | 选NoPred1099次、directional25次，选Current为0 |
| R4-6 | 101 | 31 | 采用plane138次；候选在模板外且非identity551次，未必被采用 |

R4-3的人工native反例证明实现并非等价重写；**合成编码并未证明其新增分支有有效真实覆盖**。
不能把它相对Current的77次改变当作新增rescue收益，后者可能全部来自继承R3。
CB的Current专家在本批合成短帧没有选中，不等于该分支不存在（独立网格原型有覆盖）。
SP的551是候选计数，不是551次有效采用；选择/预测改变/remapping改变必须区分。
本批很多常用QP码流仍可能与Current一致；不为让smoke活跃而改公式、阈值或选择序列。

## 5. 宏、调度和基础分析

| 测试 | 结果 |
|---|---|
| test_ts_fixed_defaults.py | 6项通过；23种ON默认＋OFF，529种显式覆盖，非法值/新旧冲突/master误配置 |
| test_ts_fixed_batch.py | 11项通过；新增六模式，共享池、无重建、逐组写表及失败重试保持原行为 |
| test_ts_r2_analysis.py | 9项通过；R2/R3兼容、R4分量BD后6:1:1、缺点拒绝、Current Reference保护 |
| ts_r2_activity.py --revision r4 | 2612行，列数校验通过 |
| LB CE六组dry-run | 168任务，C4+E3、四QP、半帧、无重建、hash、Excel；未执行 |
| Python编译 / git diff --check | 通过 |

调度测试故意模拟FAIL/RETRY，unittest最终OK；它们不是实际编码失败。
dry-run不能证明真实输入存在、算法生效或远端配置身份。

## 6. 真实内容预检及尚未完成事项

另外完成一个严格限量的真实预检：BasketballDrill、LBeu、名义QP22、2帧，Current/R3-1/六组R4共8项，
**8/8成功，实际帧数均2，解码hash全部通过**。输出 `runs/ts_r4_real_preflight/`，关闭XLSM写入与重建输出。
目录没有新XLSM或YUV；`summary.csv`和335行`activity.csv`记录实际结果。
这不替代冻结设计的四条真实序列×四QP预检，也不能计算BD-rate。
读取输入确认：该文件前两帧SHA256均为`8da85fdf95d61d68ae4f5eb1d0c982d8eae3f372c692203df096220b9cde64b9`，
第三帧不同。因此这次真实预检以纹理/实现覆盖为主，不把第二帧的少量inter码率当作运动覆盖证据。

| 组 | 相对Current映射改变 | 本组q上相对R3映射改变 | 覆盖说明 |
|---|---:|---:|---|
| R4-1 | 12 | 0 | 本例码流等于R3，不能据此推广两者等价 |
| R4-2 | 0 | 9 | 本例码流等于Current；幅值分支的真实活动覆盖不足 |
| R4-3 | 12 | 0 | 补查159次、接受0；本例码流等于R3 |
| R4-4 | 8 | 5 | 方向搜索333次，接受14次 |
| R4-5 | 18 | 6 | 回看553次，接受61次，均选NoPred |
| R4-6 | 11 | 1 | 回看544次，采用plane4次 |

R4-4/5/6的比特流与Current/R3均不同。以上只确认作用与限制，不计算单点BD-rate、不以短测挑赢家。
R4-2/3出现相同码流有其机制计数支持，不应仅据码率相同认定宏失效；仍须查看有效banner。

1. 没有正式R4 CTC/BD-rate或Decoder复杂度结论，没有改anchor Reference。
2. 单序列单QP预检不能证明各组在CE四QP都有足够活动；R4-3尤其需验证新增rescue的有效覆盖再决定长跑。
3. 精细机制日志是最终TS条件样本，不能把它作为无偏选择优势或CG persistence/η证据。
4. 新R4模式只能由匹配版本Decoder解码。远端必须核对有效banner/源码/二进制SHA/帧数/hash，不能只看宏截图。
5. 代理成本与真实CABAC、闭环RDOQ的差异仍需真实RD检验；本轮没有按测试输出反复修改冻结预测公式。

## 7. 目录编号更新

收件目录改为 `r4_1_identity_only` .. `r4_6_signed_plane`，数字与R4_MODE对应；运行mode不变。
`ts_predictor_naming.py`用于新batch目录、逐组summary/XLSM和分析读取；已有旧目录兼容，双目录冲突拒绝。
命名更新后：调度测试14项、分析测试11项通过，包含实际XLSM编号路径/Reference保护、旧目录续跑、
新编号LB_CE与flat表格读取；没有更改编解码器或重新编码，前述二进制身份与测试结果仍适用。
