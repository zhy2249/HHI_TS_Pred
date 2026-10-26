# TS规则本地实验室

规则规格 `TS-RULE-SUITE-v1`；采集/回放接口 `TS-RULE-LAB-v1`。
本目录把此前仅在会话附件中的规则和依赖正式放入Git。Python 3.10+标准库，无numpy依赖。

**当前状态：28项纯规则/合成流程测试通过；本目录C++全量接入仍需用户本地编译及原生码流验收。未执行96条新审计、未测得全数据最佳规则。** 现有impl2二进制不是本接口；不能直接用旧程序运行新命令。

完整规则/口径见 [实验设计](../../docs/experiments/TS_Predictor_Rule_Lab_Design.md)。不要把CE01测试结果当成全量收益。

## 1. 文件

- `rule_suite.py`：61组固定规则、邻域保护、逐级状态、混合保护、三方式历史信用。
- `ts_learning.py`：原评分、因果邻域与历史、固定10对照；不使用当前a选择当前p。
- `native/Corpus.h`：全TU收集、固定系数CABAC回放、最多64条外部预测序列的私有评估。
- `integrate.py`：默认dry-run；仅显式`--apply`才修改两处接口并复制Corpus.h。目标脏文件/已有Corpus.h/anchor不符即拒绝。
- `ts_corpus.py`：全manifest计划、EOF解码、输入指纹、并发/续跑、压缩输出。绝不启动编码器。
- `benchmark_rules.py`：生成61条预测序列、完整TU收益与损失、双来源等权统计、留一内容选择。
- `test_*.py`及`ce01_tu.json`：因果性/状态/统计/协议测试；CE01是已经记录的落选搜索块，不是训练视频或完整CABAC快照。

## 2. 先检查与接入，不覆盖本地工作

所有命令在仓库根目录执行。保持当前实验分支，先同步Git并检查工作区。

```bash
python3 -m unittest discover -s scripts/ts_rule_lab -p 'test_*.py' -v
python3 scripts/ts_rule_lab/integrate.py --repo .
# 确认dry-run仅涉及本任务目标文件，且没有用户待保留改动后：
python3 scripts/ts_rule_lab/integrate.py --repo . --apply
cmake -S . -B build/ts-rule-lab -DCMAKE_BUILD_TYPE=Release \
  -DNX2_OPT_TARGET_ARCH= -DNX2_ENABLE_TRACING=OFF
cmake --build build/ts-rule-lab --target DecoderApp -j 6
build/ts-rule-lab/bin/DecoderApp --ts-corpus-version
```

最后一行必须输出`TS-RULE-LAB-v1`。输出其它revision或编译失败时先排查，不得启动批量。
已有同名全量接口/本地源码修改时，Codex应手工对齐集成点，保留用户修改；不要强制执行脚本或退回旧源码。

接入还会修复旧Manager中scan/raster联合计数：读取`q[geom.blockPos(scan)]`后配合同一scan的邻域，不再用`q[scan]`。
没有改R13预测、RDOQ、映射或默认码流行为；新增通道只在`TS_CORPUS=1`下启用，不能与旧`TS_SCORE_AUDIT`混开。

## 3. 必须先做本地原生验收

先用既有Johnny_QP32_prefix17的两个来源，各自绑定正确native policy，执行同一个新程序的on/off重建MD5比较。每个TU会强制验证native bins/context/pass/budget，失败即退出。
同时执行原仓库的审计测试。重点额外核对：

1. 全量开/关重建逐帧一致；schema/动作顺序一致；实际读取EOF。
2. Python生成前10个固定动作与C++10对照逐TU完全一致；最终report会检查这一项。
3. 同一q/入口的外部原生预测序列回放等于原生rate；错q/context/几何、少行/多行必须拒绝。
4. 负值、幅值1、Rice边界、历史大于局部max、预算耗尽和矩形TU覆盖。
5. 运行中不要修改规则或二进制；修改后必须另起输出目录，续跑不能混合身份。

无原生编译/这些检查的执行记录时，只能说“参考代码测试通过”，不能宣称视频验收通过。

## 4. 全序列导出：不是原抽样审计

```bash
python3 scripts/ts_rule_lab/ts_corpus.py plan \
  --manifest deliveries/r13_decode_audit_impl2/manifest.json \
  --expect-sequences 12 --output runs/ts_rule_lab/plan.json

python3 scripts/ts_rule_lab/ts_corpus.py collect \
  --plan runs/ts_rule_lab/plan.json \
  --decoder build/ts-rule-lab/bin/DecoderApp \
  --jobs 4 --verify-off --resume \
  --output runs/ts_rule_lab/corpus
```

默认12序列×4QP×2来源=96条；额外prefix不重复算正式数据。逐文件读到EOF，不截前32帧、不假定300帧。
所有目标TS TU都保留q/scan及10个完整固定对照rate，不使用每帧2TU或每TU4点的抽样上限。
BDPCM另记；当前原生参考范围为≤64×64/4096系数、动态范围8..20，unsupported非零即拒绝完整结论。

默认不做昂贵的全部单位置oracle，只做规则所需的全量q导出及完整固定策略回放。它不是抽样。
需要训练候选准确性数据时给第一遍collect加`--with-labels`：对所有a>0、n>=3位置计算完整候选代价标签。两种输出由`all_point_labels`区分，不能将不含标签的导出说成已完成训练数据标注。
每流默认原始结构化数据上限16GiB，实时gzip；触限报错而非自动降采样。可通过`--max-gib`显式提高。

## 5. 一次生成61条规则，再做完整TU回放

```bash
python3 scripts/ts_rule_lab/benchmark_rules.py schedules \
  --index runs/ts_rule_lab/corpus/dataset_index.json \
  --output runs/ts_rule_lab/schedules

python3 scripts/ts_rule_lab/ts_corpus.py collect \
  --plan runs/ts_rule_lab/plan.json \
  --decoder build/ts-rule-lab/bin/DecoderApp \
  --schedule-dir runs/ts_rule_lab/schedules \
  --jobs 4 --verify-off --resume \
  --output runs/ts_rule_lab/evaluation

python3 scripts/ts_rule_lab/benchmark_rules.py report \
  --index runs/ts_rule_lab/evaluation/dataset_index.json \
  --output runs/ts_rule_lab/report
```

每个码流只做一次该阶段主解码，61个策略在私有副本中回放；相同预测序列复用完整TU结果。
不是61次视频编码，也不把单位置delta相加当新策略收益。
`--verify-off`会另做无观察解码来核对重建。缺流/缺方法/坏哈希/身份不匹配不填零、不输出完整排名。
当前接口是固定已恢复q的离线评估，不是在线编码器候选联合RDO搜索。

## 6. 结果口径与回传文件

`gain_vs_X_bits = R_X - R_method`，正数表示节省。
`gain_vs_current_pct`仅为该条件TSRC人口的节省比例，不是整码流节省率或BD-rate。
全YUV总量按实际TSRC bit相加，不使用6:1:1；各分量单列。

双来源每侧先按自身非零数归一，再各占一半；QP在各内容内等权、内容再等权。任一侧无有效分母保持null，报告支持数。
全数据排名是描述性排名；另用其余内容选规则、评价留出内容。已知开发内容不等于全新盲测。

测试完成后，将以下目录复制到`docs/experiments/results/ts_rule_lab_<运行标识>/`并提交Git：

- report目录全部CSV/JSON：各方法逐流/分量、逐内容、双来源、全数据排名、留一内容选择。
- `worst_TU_cases.csv`：每方法每参考最多16个最差TU，定位后续增码分析；不是总体误判率。
- `methods.json`、`report_scope.json`、`run_receipts.json`：方法/输入/程序身份、实际帧数、native覆盖、SEI/on-off状态。
- 新写一份README：编译指令与编译结果、源码/程序SHA、通过/失败数、未支持范围、实际运行命令，以及“固定q回放，非BD-rate”。
- 单元测试与原生验收摘要；若本地为适配作了修改，提交相关源码与理由，不能只上传最终最佳数字。

原始`.bin`、`.pred`、`corpus.jsonl.gz`、二进制及大日志留在runs，不因本次设计重复上传。不要覆盖旧正式RD台账。
`run_receipts`含本地路径时可脱敏用户名，但必须保留相对文件对应关系与全部SHA/参数。

## 7. 已做与未做

本轮本地：28项Python规则/协议/合成报告测试通过，CE01当前/未来不泄漏和所有state单步约束通过。
未做：C++原项目编译、全量真实解码、61规则真实比特排名、重新编码或BD-rate。
用户在本地完成后回传上述表，即可继续区分收益来自哪些序列/幅值/机制，以及是否存在极端损失。
