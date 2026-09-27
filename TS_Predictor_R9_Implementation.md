# R9 实施说明与运行入口

日期：2026-09-27；算法版本 `R9-20260927-v1`。原始规格为 `R9_Experiment_Plan.md`。
本轮是 **R9-1～R9-13 的一轮实验**，不是只实现编号 9。Current 仍是唯一正式 anchor。
没有运行正式 CTC，没有新增 BD-rate 结论。

## 1. 规格审核

已核对当前真实 R8 代码，而不是沿用计划中“仅提供截至 R7 源码”的历史状态说明。
`TsR8Prediction.h` 中 R8-10/12 确实实现 P0 上的 `T=S+B`，区别仅为 S0/Smax。
`RateTable` 的 CF10 是 **CG 入口冻结、按直接 L/U 非零数分类**的 magnitude fractional 模型，
不含固定非零样本会抵消的 significance/sign，仍假设 regular cutoff=10。
它不是目标系数的完整 CABAC rate，更不是闭环 `D+lambda R`。

根据已有 R8 报告，R8-12 的 C/E 表现不同，扩候选也在某些匹配对照中有效。
因此保留原计划的候选覆盖、稀疏恢复、惩罚强度、映射、专家和量化六类机制，
不按序列、类别、QP、分辨率硬开关，不根据本轮短测收益修改公式。
用户提供的历史报告及工作簿未在本轮重新计算、修改或作为新编码结果。

## 2. 13 个冻结配置

| R9_MODE | 工程标识 | 运行名 | 主要变化 | 阶段 |
|---:|---|---|---|---|
| 1 | P10 | r9_p10 | R8-10：P0→P1，保留 S0 | I |
| 2 | P12 | r9_p12 | R8-12：P0→P1，保留 Smax | I |
| 3 | 01 | r9_axis_sparse | 同轴重复且 CF(pC)>CF(1) 才恢复稀疏 pC | I |
| 4 | 02F | r9_half_penalty | dense 目标 2S+B | I |
| 5 | 02A | r9_feature_penalty | dense 目标 nS+n2B，n2=#幅值≥2 | I |
| 6 | 03 | r9_unit_risk | T 加单位幅值上推的非负惩罚 | I |
| 7 | 04 | r9_protect_one | P1、固定 k=1 的可逆保护1映射 | III |
| 8 | 05 | r9_joint_mapping | 联合选(k,p)，P12优先，严格改善才换映射 | III |
| 9 | 06I | r9_expert_integer | 同CG因果目标验证 A/B/C，整数验证损失 | II |
| 10 | 06F | r9_expert_fractional | 同上，目标j自身分类的冻结 fractional 损失 | II |
| 11 | 07D | r9_quant_down | R8-12 predictor，完整 q0 与独立 D 编辑比较 | IV |
| 12 | 07DU | r9_quant_down_up | 相同 q0/D，再增加独立 U 编辑 | IV |
| 13 | 08 | r9_axis_feature | 模式3 sparse＋模式5 dense，P0 | I |

`P1={0,a_i,a_i+1}` 含 Current；幅值受动态范围限制、候选去重、位置重复证据保留。
零/缺失不计入 n。p≤k+1 规范化成 identity。旧模式及旧 tie 规则不修改。
R9-8 的同分优先 P12 动作，其余 k=0 再小 p；k=1 不另加 Current 优待。

## 3. 源码组织和同步

- `TypeDef.h`：R9 默认编号、范围和与此前所有轮次的互斥检查。
- `TsFixedPrediction.h`：稳定运行名、内部 policy 58～70、启动 banner、`MagnitudeAction(p,k)` 与正逆映射。
- `TsR9Prediction.h`：纯函数评分；所有候选共用不可变成本输入，不写 CABAC。
- `ContextModelling.cpp/.h`：原生 scan 逆索引、真实几何可得性和每次访问的因果断言；专家验证和最终统计。
- `QuantRDOQ.cpp/.h`：p/k 一致的评分、up 命中条件和编码端零一提案/注入。
- `CABACWriter/Reader`、`TsRateReplay.h`：所有 regular pass 使用同一(p,k)动作；pure bypass/BDPCM不映射。
- `TsR9Quant.h`、`TsR8Search.h`：沿用现有 owner checkpoint/evaluator，新增独立 q0/qD/qU 比较。
- `Unit.h/.cpp`：不复制的短生命周期试编码请求；可复制的最终编辑诊断标记，不进入码流。

Reader 只在第三遍按原生扫描逐点反映射，历史邻居已恢复，当前/未来临时 mapped levels 不可读。
R9-7/8 的 up 条件为命中真实非 identity predictor；没有开启 R8-23 的额外扫描策略。
R9 不保留跨 TU 状态，不用原像素/残差来选公共 predictor。
RDOQ 使用自己的输入 estimator 状态及最终 CG replay；Writer/Reader 使用各自真实 CG 入口，
两种入口并不保证相同，保留此前已明确的 RDOQ/最终 Writer 失配边界。

### 专家验证

A=R8-12，B=原整数 R2-2，C=原整数 R3-1。三者在当前点的映射都等价时直接 A。
否则只在五邻域内的 **同CG、scan更早、真实存在且非零的目标 j** 上验证。
先从 j 自己更早的邻居重算专家，再读已知 a_j 评分；不会递归调用专家选择器。
CF 使用 j 的直接邻居分类，不错误复用当前点 i 的分类。平局 A→B→C；空验证集回 A。
这是冻结路径下的小样本规则验证，不是历史真实字节，也不保证下一点改善。

## 4. 07D / 07DU 的明确覆盖限制

本版接受计划允许的保守实现：**拒绝 TU-CBF 翻转；联合色度路径不执行编辑**。
正常 predictor 仍覆盖 YUV；独立 chroma 的编辑仍启用，未按历史 BD-rate 关闭 UV。
BDPCM、non-TS、noResidual、lossless/小尺寸等不进入原生 TS-RDOQ 的路径仍按原规则处理。

1. q0 必须是原生 TS-RDOQ 所有 CG 清零决策之后的完整 q。
2. 一次 O(N) 扫描独立选 D/U 位置。D 为 |q|=1→0；U 为 q=0 且源TS系数非零→其符号。
3. 提案排名用原 RDOQ 量纲的平方误差变化＋lambda乘局部固定CF10及sig/sign变化。
   这是便宜 proxy：不声称模拟了编辑后的预算、CG flag 或推断 significance。
4. 删除 TU 唯一非零值、向全零 TU 添加非零值均拒绝并计数。D 和 U 从同一 q0 生成，不串联编辑。
5. 只有基线 owner 代价有限、CBF非零、owner 没把原 q0 改掉的 trial 才进行额外完整比较。
   提案扫描发生在量化层，计入全部内部 trial；不是仅在最终提交 TU 上扫描。
6. 每条候选从相同 TU/信号/CABAC 入口恢复，直接注入固定编辑后的 q，
   由原 evaluator 重新做重建、滤波/色度权重、CBF/TS语法及残差编码。
   后继 predictor、CG significance、sign、Rice、regular预算与出口context全部重新推导。
7. 原 owner 又将编辑块整体清零时同样拒绝，不冒充覆盖父层语法翻转。
8. 严格 J 改善才更新，平局 q0→D→U。若最后试验不是赢家，重演赢家并断言 J/q 完全一致。
   最多 3 个不同完整候选，另可能有一次恢复赢家的重演，不是 O(N²) 完整重编码。

保证仅限 **同一入口、同一候选子空间下的 owner 局部最小 J 不劣于 q0**。
R9-12 的局部候选集包含 R9-11，但两次独立视频编码的输入状态会分叉，BD-rate 没有单调保证。
不将 YUV 6:1:1 评价权重写入编码器局部失真目标。

## 5. 开启与构建

在 `source/Lib/CommonLib/TypeDef.h` 直接设置：

```cpp
#define JVET_BJUT_TS_FIXED_PREDICTOR 1
#define JVET_BJUT_TS_R9_MODE        5  // 举例：R9-5 / 02A
```

其它 fixed、CONDITIONAL、R2～R8 模式均为0；建议 R7_SHADOW=0。
交付默认仍为 R9_MODE=0，即不改 Current anchor。修改宏后必须重编两端。
`TS_FIXED_PREDICTOR` 环境变量和原批量 `--fixed-predictors` 可覆盖宏默认；
不传该参数则保留原脚本按二进制默认运行的行为。两端必须同模式。

```bash
cmake -S . -B build/ts-r9 -DCMAKE_BUILD_TYPE=Release \
  -DNX2_TOPLEVEL_OUTPUT_DIRS=OFF -DNX2_ENABLE_LINK_TIME_OPT=OFF
cmake --build build/ts-r9 --target EncoderApp DecoderApp TsRateCodecTest TsR9QuantTest -j8
```

CMake 只构建，不用它选实验。日志须同时核对 `EXPERIMENT` 与
`TS R9 revision=R9-20260927-v1; mode=...; runtime=...; engineering=...`。
所有组需要配套 decoder；无额外 mode 信令不等于兼容旧 decoder。

## 6. 运行顺序和批量命令

先短测/活动审核，再按 I→II→III→IV。不要因已实现13组而立即全部铺开完整CTC。
阶段I为7组196个LB CE点；阶段II/III/IV各2组56点，合计364点。
LB 半帧直接读取已有 LBeu INI，不再次除2；不重新跑 Current 工作簿 anchor。
沿用共享跨组线程池；每组完成即写自己的工作簿；保留失败日志、resume和无重建。

```bash
# 先做固定内容窗口的活动预检，不写与完整anchor不匹配的工作簿（56个点）
bash scripts/run_ts_r9_lb_ce.sh --input-dir /home/zhy/videos --jobs 10 \
  --sequences PartyScene,BQMall,Johnny,KristenAndSara --qps 22,37 --frames 8 \
  --no-xlsm-report --out-dir runs/ts_r9_stage1_preflight --dry-run
# 去掉 --dry-run 才启动。此短测只审核活动/hash/开销，不计算对完整anchor的BD-rate。

# 阶段I：先检查任务，不启动编码
bash scripts/run_ts_r9_lb_ce.sh --input-dir /home/zhy/videos --jobs 10 --dry-run
# 确认后去掉 --dry-run。

# 阶段II（按需要运行）
bash scripts/run_ts_r9_lb_ce.sh --fixed-predictors r9_expert_integer,r9_expert_fractional \
  --out-dir runs/ts_r9_stage2_LB_CE_half --dry-run
# 阶段III
bash scripts/run_ts_r9_lb_ce.sh --fixed-predictors r9_protect_one,r9_joint_mapping \
  --out-dir runs/ts_r9_stage3_LB_CE_half --dry-run
# 阶段IV：优先短测确认最终编辑存活和开销
bash scripts/run_ts_r9_lb_ce.sh --fixed-predictors r9_quant_down,r9_quant_down_up \
  --out-dir runs/ts_r9_stage4_LB_CE_half --dry-run
```

服务器结果放 `experiments/ts_predictor_r9/r9_<数字>_<名称>/{smoke,LB_CE,LB_B,RA_CD}/`。
每组提供 `run_metadata.template.json`；记录源提交、两端sha256、帧范围、配置和真实状态。
与旧实验不能复用不同二进制指纹的续跑目录。不要填造缺失点或将短帧视为全 CTC。

## 7. 日志与分析

默认 `TS_R9_STATS=1` 在线聚合；`TS_R9_STATS=0` 关闭观察；`TS_R9_TRACE=1` 仅短测调试。

- `TS_R9_STATS`：最终 TS Writer 的 TU/CG census 和系数分层。按 component、W/H、CU-QP、
  intra、CG序号/数量、n/n1、直接邻居数、实际 cutoff、目标幅值桶聚合。
  n2=n−n1；另按实际 pC、pC 非零重复次数、验证集大小、不同专家数、所选专家分层。
  记录同轴命中/cost通过、动作变化、实际映射变化、k1非identity、专家A/B/C、
  验证loss与各专家相对样本内最佳的regret、邻域score差与同一最终目标的局部cost差。
  选中专家的样本内regret按定义应为0，这是实现检查，不是未来目标性能。
  三专家当前动作相同而跳过验证时，validation_size=0，不冒充已经观察过全部潜在验证点。
  动作/目标比较参考为R8-12；score差按各模式目标的原始Q15整数尺度记录，
  例如2S+B和nS+n2B未除回权重，不能直接跨模式比较差值大小。
- `TS_R9_SEARCH`：量化内部 trial、D/U位置数、CBF拒绝、完整测试/接受数、局部J收益。
  `owner>=0` 是搜索人口；`owner=-1` 为真实 Writer 提交的最终D/U编辑计数，两者禁止相加作分母。
- `TS_R9_TRACE`：每CG最终q和动作摘要，用于两端比对，不默认保存逐系数大文本。
- `TS_R9_EDIT`：仅TRACE开启时逐个记录最终提交编辑的POC、分量、TU坐标、D/U类别与raster位置。

```bash
python3 scripts/ts_r9_activity.py runs/ts_r9_stage1_LB_CE_half \
  --out runs/ts_r9_stage1_LB_CE_half/activity
```

输出 `final_by_stratum.csv`、`final_by_job.csv`、`search_by_stratum.csv`、`log_status.csv`、`audit.json`。
只处理 pass 任务，按编码日志绝对路径去重；文件迁移后应修正 manifest 路径，不猜测对应日志。
没有统计段不能自动解释为零活动。

仍需明确的未测量项：跨 R2/R3/R8-12 三种最终 q 分布的匹配 shadow 数据集、
各候选完整反事实 CG rate 表、所有试编码与最终TU逐一关联、分支DeltaD/DeltaR分解、
验证loss逐事件完整分布与模型因果效果。这些不是本版已有字段，不能以0代替。
最终Writer统计仍有TS选择偏差；邻域改善、固定q目标cost改善、闭环RD改善分开解释。

结果评价保持各分量先算BD-rate，再 `(6BD_Y+BD_U+BD_V)/8`；CE为7序列等权，
不是 C/E 简单各占一半。匹配基础要重新积分，不相减两个对Current百分比。
缺失点与anchor暂代点显式标记，不能作为纯实测收益证据。

## 8. 验收入口

```bash
python3 -m unittest discover -s scripts -p 'test_ts_*.py'
python3 scripts/ts_r9_smoke.py --quant-test build/ts-r9/bin/TsR9QuantTest \
  --out runs/ts_r9_smoke --jobs 8
```

Smoke 使用人工2帧64×64输入，含AI22/0、LB22、RA37、禁TS、BDPCM；
原生测试覆盖2～32的方形/矩形TU、YUV、Rice1～8、低预算、幅值上限和未来系数污染。
旧程序默认为 `build/ts-r8-all/bin/EncoderApp`；可用 `--legacy` 指定服务器上的旧版本。
`--off` 指定新构建的master关闭程序，`--anchor-off`指定历史关闭程序；缺失对照不能冒称验证。
实际验收结果见 `TS_Predictor_R9_Validation.md`，不将原计划参考脚本的通过次数当作本版验证。
