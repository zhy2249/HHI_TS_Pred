# R12 实现验收记录

日期：2026-10-01；规格 R12-POS-01；实现起点 `94a3540`。
**代码及局部验证通过，尚未运行真实视频序列，不存在 R12 BD-rate 或速度结论。**
本次测试没有启动序列级 EncoderApp/DecoderApp；应用程序仅用于编译和 `-h` 身份探测。

## 编译与规则

- Release 构建 EncoderApp、DecoderApp、TsRateCodecTest、TsR12QuantTest 通过。
- 独立 master-OFF 构建 EncoderApp/DecoderApp 通过；没有据此声称原版/修改版整帧码流 bit-exact。
- `python3 -m unittest discover -s scripts -p 'test_*.py'`：140项通过，包括旧轮/批量调度/台账测试。
  测试中的 FAIL/RETRY、故意写表失败是受控模拟失败案例，不是运行了真实编码。
- 宏测试包含12个默认值、所有运行名覆盖、master-off拒绝实验、旧轮及缓存互斥、非法范围。
- 新统计选项的非法值、重复/超量shadow、不支持轨迹均拒绝；默认身份探测隔离观察参数。
- shell语法与 `git diff --check` 通过。

纯 C++ 公式与上传的独立 Python 参考逐条比对：

| 检查 | 范围 | 结果 |
|---|---|---|
| 外层选择 | 4,000种随机损失矩阵×13模式含诊断0，共52,000案例；含Q边界及64位总量 | 一致 |
| 小幅值加权 | 6⁵=7,776邻域×7/8/11/12，共31,104比较 | 一致 |
| 权重变体 | 2,000邻域×raw/full×uniform/W/2W，共12,000比较 | 一致 |
| 横纵对称及guard次序 | 2,000邻域×7/8/11×原始/转置，共12,000比较 | 一致 |

上述随机损失矩阵是代数测试，不声称均可由真实内容产生；改变权重只在测试中，正式算法固定W22111。

## 原生语法与因果验证

独立 `ts_r12_native_reference.h` 从原生scan枚举几何，调用既有A/B/旧C API，
另写加权C与外层比较；不复用生产 `r12Integer/r12Experts/r12Select/r9SupportTS` 作为预期结果。
模式0的公共动作逐位置等于原始R10-3；exact-CI-tie保护及mode10唯一赢家保护均检查。

每个R12模式和R10-3对照，每次运行：

- 160个合成TU，包含方形/矩形、Y/U/V、intra/inter标记、BDPCM、Rice1～8、极端幅值、
  清零CG以及正常/极少/零regular预算。尺寸2～32用于边界测试，不等于实际CTC observed sizes。
- 1,491个CG：native Writer、fractional estimator、独立完整CG replay的预算、所有context状态和fractional bits一致；
  native Reader逐系数恢复原始q。
- 23,436个query：扰动当前和所有未来系数，动作不变；R12额外检查历史集合和CI/CF行不变。
- 每个R12模式29,544次独立参考核对，包含已知prefix编辑、清零、恢复和概率快照分支/回滚。
  R12-3覆盖395次“ABC动作相同而D不同”的参考调用，没有错误短路。

13组分别运行统计关闭、开启统计＋trace，两次合成码流摘要一致、测试结果一致；
累计19,383对Writer/Reader CG摘要完全一致。每个进程限定3条detail，实际恰好3条；
13,669条在线聚合记录通过列数、人口、CI分区、槽位和guard嵌套校验。
R10-3还执行1/7/9三模式shadow，码流摘要不变。全部原生日志约7MB，未上传。

十二个新模式的合成码流摘要均不同于R10-3，参考检查均有动作差异；
这证明测试激活了修改，不证明真实序列有足够活动或会获得收益。
另运行R3-1、R9-9、R11-2的同类局部回归，各160TU/1,491CG通过；
没有将这项回归冒称旧二进制的完整码流比较。

## 原生量化验证

`TsR12QuantTest` 直接调用TS-RDOQ，不调用整帧/序列编码器。
13模式各180个合成残差案例，共2,340案例；覆盖YUV、方形/矩形、intra/inter、QP和lambda变化。
使用测试自建SPS/PPS、picture header与identity色度QP表，不宣称CTC参数。

每个案例验证原始输入及真实CABAC状态不被修改；量化一次后污染输出、试探全零残差分支、
再恢复原残差，最终q和absSum必须一致。各组14次零输入早退、14次非零输入量化全零通过。
各R12组q摘要均不同于R10-3。这是实际量化路径活动，不是BD-rate。
任意同CG事后编辑/清零的因果重新计算由上述语法参考测试另行覆盖；
未声称已统计真实内容每一次CG全零RD事件。

## 批量准备

首批wrapper dry-run（统计关，以及R10-3可用的1/7/9观察参数探测）均规划168任务，
模式1/2/4/7/8/9；Class C/E、QP22/27/32/37、LBeu原INI半帧，例如BasketballDrill250帧、Johnny300帧。
所有任务no-recon、decode-hash准备开启。没有实际运行这些任务。
现有共享任务池、逐组写表、失败重试和指纹resume逻辑沿用并通过脚本单元测试。
未因有新目录就虚构服务器结果或成功marker。

## 复现与未测项

```bash
cmake -S . -B build/ts-r12 -DCMAKE_BUILD_TYPE=Release \
  -DNX2_TOPLEVEL_OUTPUT_DIRS=OFF -DNX2_ENABLE_LINK_TIME_OPT=OFF
cmake --build build/ts-r12 --target EncoderApp DecoderApp TsRateCodecTest TsR12QuantTest -j4
python3 -m unittest discover -s scripts -p 'test_*.py'
python3 scripts/test_ts_r12_native.py --jobs 2
bash scripts/run_ts_r12_lb_ce.sh --dry-run --allow-missing-input
```

综合局部结果写 `runs/ts_r12_native/validation.json`；测试日志和构建产物留在本地。
单元测试中的g++宏覆盖及独立OFF构建仅用于自动校验；正常选择实验仍直接改TypeDef.h或显式运行参数。

尚未执行：序列级短帧encode/decode/hash、Current或OFF对旧anchor的整帧bit-exact、真实CE/B、
同机配对时间/峰值内存、真实最终TS人口活动。没有以上证据时，不宣称通过正式编码验收或获得收益。
下一步由服务器先做少量内容预检，确认身份/hash/实际remap，再按首批六组CE及人工B门槛推进。
