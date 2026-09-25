# R8 首批八组：实现与运行

算法规格：`R8-DESIGN-20260925-v2`。八组已接入 C++；其余16个编号仍只保留设计。
正式基线 **Current**，不把 NoPred、R3 或 R7 当正式 anchor。不改变本轮冻结公式来追求正收益。

## 1. 如何选择

直接修改 `source/Lib/CommonLib/TypeDef.h`，然后重新编译 Encoder 和 Decoder：

```cpp
#define JVET_BJUT_TS_FIXED_PREDICTOR 1
#define JVET_BJUT_TS_R8_MODE         1 // 按下表选择；0=本轮不启用
```

固定 NoPred/gradient/directional、CONDITIONAL_MODE、R2..R7_MODE 都设0；R7_SHADOW建议0。
源码交付默认 `R8_MODE=0`，因此不加覆盖参数仍是Current；并没有替用户默认启用某个新算法。
宏选择算法，不用CMake选算法。宏互斥和master-OFF检查均在编译时执行；未实现编号报错。

| R8_MODE | ID | `--fixed-predictors` / `TS_FIXED_PREDICTOR` | 改动 / 主父法 |
| --- | --- | --- | --- |
| 1 | A01 | r8_raw_sparse_max | R7-1 + Smax |
| 4 | A04 | r8_guard_sparse_max | A01 + 原H>0 guard |
| 8 | A08 | r8_reject_nopred | R7-2的真正guard拒绝出口→identity |
| 13 | B01 | r8_mixed_raw | A01，CIq+CF评分 |
| 15 | B03 | r8_complete_raw | R7-1，补齐a+1候选，S0 |
| 16 | B04 | r8_complete_sparse_max | B03 + Smax；A01补齐候选 |
| 17 | B05 | r8_minimax | A01，固定P0的完整/逐位置删一minimax regret |
| 19 | B07 | r8_smoothed_dense | B04，1:2:1平滑，原始n不变 |

详细公式：[冻结设计](TS_Predictor_R8_First8_Design.md)。直接运行程序时环境变量覆盖宏；
batch省略`--fixed-predictors`会探测编译默认并同步两端，显式提供时覆盖宏。不要仅凭宏文件判断服务器旧二进制。
日志必须同时看到`EXPERIMENT: TS_FIXED_PREDICTOR=...`和`TS R8 revision=...; mode=...`。
运行时内部policy34..41仅用于分发，**不能填入R8_MODE**。

## 2. 代码边界

- `TsR8Prediction.h`：纯五点幅值函数，固定数组，最多21候选×5位置；所有成本、G/H和regret为int64。
- `ContextModelling.h`：因果读取及统一分发；候选共用CG入口、group flag之前冻结的CABAC fractional表。
- `QuantRDOQ.cpp`：沿用R7私有context回放，仅在CG最终清零决策后推进；未改round/min/up规则、lambda或`xGetICRateTS`。
- `CABACWriter.cpp` / `CABACReader.cpp`：通过同一个`needsTsRateContext`冻结快照，再使用同一R8函数。
- `ContextModelling.cpp` / `TsR8Stats.h`：最终Writer聚合及可选两端CG跟踪，不作为算法状态。
- `batch_test.py` / `ts_predictor_naming.py`：只增加模式注册、编号目录和R8观察开关的resume指纹，沿用原调度及写表逻辑。

幅值上限取实际transform动态范围的`1<<range`：包括合法负系数最小值的绝对值（如−32768）。
TS-RDOQ原有量化候选仍按源码`(1<<range)-1`截断，未拓宽其量化搜索。
平滑和新predictor都裁剪在幅值域，不使用像素位深作上限；边界测试包含−32768/32767。

CF仍是**CG入口冻结、完整regular/cutoff10的局部模型**，不是每个目标实际更新后的概率或完整RD。
不读取目标q来选择cutoff或candidate。pure bypass不应用remap，BDPCM完全沿用原生编码。
改predictor可能通过既有RDOQ反馈改变q/TS选择；没有同入口成对RD探针，`q_changed=not_measured`。
码流不增加syntax，但实验Encoder/Decoder必须使用相同模式；不能交给未修改Current解码器。

## 3. 编译与本地验证

在工程根目录：

```bash
cmake -S . -B build/ts-r8 -DCMAKE_BUILD_TYPE=Release \
  -DNX2_TOPLEVEL_OUTPUT_DIRS=OFF -DNX2_ENABLE_LINK_TIME_OPT=OFF
cmake --build build/ts-r8 --target EncoderApp DecoderApp TsRateCodecTest -j 8
python3 -m unittest discover -s scripts -p 'test_ts_*.py'
python3 scripts/ts_r8_smoke.py --jobs 8
```

这里CMake参数仅为构建路径/优化配置，没有实验宏。独立输出不覆盖旧R3/R7程序。
`ts_r8_smoke.py`默认需要保留的`build/ts-r7/bin/EncoderApp`作旧模式回归；其它服务器用`--legacy`指定旧R7程序。
该smoke是2帧64×64人工输入，不能替代下面预注册的真实内容运动短测。

实际验证结果见 [验收记录](TS_Predictor_R8_Validation.md)。原始validation JSON、日志、码流留在`runs/`，不上传Git。

## 4. 推荐先运行真实内容短测

```bash
bash scripts/run_ts_r8_preflight.sh --input-dir /你的/YUV目录 --jobs 10 --dry-run
bash scripts/run_ts_r8_preflight.sh --input-dir /你的/YUV目录 --jobs 10
python3 scripts/ts_r8_activity.py runs/ts_r8_preflight \
  --out runs/ts_r8_preflight/activity
```

固定PartyScene/BQMall/KristenAndSara/Johnny，QP22/37，17帧；八个新方法加Current/R3/R7-1/R7-2，96项。
短测不写正式CTC工作簿、不按短帧BD排名；检查解码、模式身份和新增候选的真实活动。
本轮只完成该清单dry-run，**没有把人工smoke冒充96项真实内容已完成**。

## 5. 之后正式LB CE

```bash
bash scripts/run_ts_r8_lb_ce.sh --input-dir /你的/YUV目录 --jobs 10 --dry-run
bash scripts/run_ts_r8_lb_ce.sh --input-dir /你的/YUV目录 --jobs 10
```

七序列×四QP×八模式=224项；默认输出`runs/ts_r8_LB_CE_half/r8_<MODE>_<name>/`。
半帧直接读取LBeu INI，不再次除2；C为250/300/250/150帧，E为300/300/300帧。
**不重跑完整Current anchor，不输出重建YUV**。所有组共用一个任务池，有空位即可进入下一组。
每组完成立即由原batch逻辑复制模板、写该组XLSM，不等八组全部结束。中止后重跑同一命令续跑。
默认使用`scripts/JVET-hhi.xlsm`；服务器路径不同可追加`--xlsm-template /路径/JVET-hhi.xlsm`。

只选部分组可在命令尾覆盖，例如先A01/A04/A08：

```bash
bash scripts/run_ts_r8_lb_ce.sh --input-dir /你的/YUV目录 --jobs 10 \
  --fixed-predictors r8_raw_sparse_max,r8_guard_sparse_max,r8_reject_nopred
```

宏默认运行可直接使用原batch，不带`--fixed-predictors`；两份包装脚本为固定的多实验清单，故主动提供覆盖。
不修改同一输出目录中既有配置/程序身份来混用旧结果；改变二进制/配置会触发原指纹检查。

## 6. 统计口径与收件

`TS_R8_STATS=1`为默认；`0`可关闭观察以测复杂度。`TS_R8_TRACE=1`仅调试时用，正式脚本关闭以免大量日志。
不得把stats开与关的总编码时间直接归因为算法复杂度；公平测速须各组统一观察设置。

`TS_R8_STATS_HEADER`和`TS_R8_STATS`位于每个encode.log末尾，在线聚合，不逐系数落盘。
键为公开MODE、分量、W/H、CU-QP、intra、BDPCM、CG总数/位置、support n、实际cutoff。

- `support=cutoff=-1`是独立TU/CG census；其它行不重复计TU/CG。
- cutoff0是pure bypass，决策/映射变化计数为0；cutoff2/10才为active。BDPCM仅census，空CG不伪造predictor活动。
- 按active位置计Current-equivalent/identity/其它、相对Current/主父法/R3的predictor及真实remap变化。
- dense区记录raw赢家类别、H>0、identity/nonzero guard拒绝、tie、新增P0之外候选获胜、最终选择与raw差异。
- G/H、selected score、B05 regret是**历史局部目标的诊断值**；不是目标系数真实码率收益。B01总尺度为双份、B07为四倍样本权重，不能跨组直接比较分数绝对值。
- n<3的评分列未评估；读取时按support筛选，不能将存储占位0当成真实0成本。regret仅MODE17有效。

`ts_r8_activity.py`从通过的summary任务提取`by_stratum.csv`、`by_job.csv`、`log_status.csv`和`audit.json`。
没有统计段时标记`no_TS_or_stats_disabled`，不伪造“零活动”。最终TS统计依然有工具选择偏差，仅作机制解释。
跨服务器拷贝日志时应同步修正summary里的日志路径；不通过模糊同名匹配混用不同运行日志。

正式结果放入`experiments/ts_predictor_r8/r8_<MODE>_<name>/LB_CE/`，带工作簿、summary、真实元数据与活动CSV。
按Y/U/V各自BD后`(6Y+U+V)/8`；CE七序列等权，不用(C+E)/2；最后按主父法分解增量。
八组尚无正式CTC收益证据，不能因人工短测存在活动便宣称Promising。
