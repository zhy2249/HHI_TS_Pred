# 61组规则的原生回放验证（2026-10-26）

本轮从 `b082d9300f589d2f26a2f67ff915c3b06e53549e` 接入 `TS-RULE-LAB-v1`。
规则清单和公式维持 `TS-RULE-SUITE-v1`，没有根据测试结果调参数。
只解码既有码流、运行局部语法fixture和私有CABAC回放，没有运行EncoderApp或重新编码视频。
正式码率、PSNR、BD-rate及对应台账不改写。

## 覆盖与完整性

第一遍已完整读取96条正式码流至EOF：12序列 × 4QP × R13-1/R13-2。
每来源13,000帧，总计26,000帧；实际每流150/250/300帧，未人为统一截帧。
共754,151个最终目标TS TU、125,949,812个系数位置、3,856,051个非零。
本人口BDPCM和unsupported均为0，754,151个原生回放全部验证。
第一遍每条流均通过逐帧编码端SEI MD5及同程序观察开关MD5核对。

本轮默认不生成全量单位置oracle标签，`all_point_labels=false`。
不得由整TU的61策略rate推算逐系数准确率，或声称已经完成全部候选训练标签。
两个来源各自使用自己的最终q、划分与原生入口，不强行配对TU。

第二遍也已96/96完整完成。每TU前10固定对照全部一致，四份逐帧重建hash表一致。
[结果解释](../../TS_Predictor_Rule_Lab_Results_20261026.md)给出全部规则族、来源/QP变化和后续优先级。
[协议报告](report/)保留全部9份文件，[补充汇总](analysis/)保留6份文件；
`evaluation_validation.json`逐流记录跨阶段核验。

## 原生接入及修复

- `tsaudit/Corpus.h`复用现有Replay，捕获一个目标TU，核对真实bin/context/pass/预算后再私有回放。
  外部schedule绑定几何、q摘要、入口context摘要及方法身份，最多64条；本轮61条。
- `Manager.h`和`decmain.cpp`提供独立 `TS_CORPUS=1`通道及版本探测，与旧抽样审计互斥。
  旧廉价联合计数改用 `q[geom.blockPos(scan)]`，使幅值和邻域属于同一扫描位置；
  不改变真实预测、反映射、RDOQ或编码语法。
- 上游模板首次编译触发`-Werror=misleading-indentation`，仅补明确花括号/换行，源码与模板一致。
- schedule增加逐流并发及严格SHA续跑；`n<3`只按因果邻域跳过冗余规则计算，仍输出完整预测序列。
  原61规则与优化生成器在全部68个原生非BDPCM fixture上逐位置一致。

## 已执行的小型验收

- 32项规则/协议/汇总测试，14项旧审计Python测试通过。
- 资源包装器3项测试通过：子命令失败状态、地址空间限制造成受控MemoryError、并发启动拒绝。
- 存储工具4项测试通过：无损往返、坏SHA保留原文件、归档限额保护、跳过正在回放的文件。
- 活动统计2项测试通过：CE01已记录的7个评分位置/1个EQ-SP映射分歧，以及全零无更新。
- R13-1/R13-2各48个局部Writer→Reader语法fixture；覆盖Rice、预算耗尽、矩形、BDPCM、历史扩展。
  它们是语法单元测试，不是视频编码。
- 其中68个非BDPCM TU、14,784个位置的10个固定predictor，Python/C++完全一致。
- 两来源Johnny32既有17帧前缀各10个TU：61方法完整回放，前10个策略rate逐TU与C++控制一致；
  每侧7个可评分单点标签用于小型接口验收。
- 错q、错context、错几何、缺行、多行、负预测幅值六类输入均拒绝。
- 旧impl2的13项运行时检查通过，含summary/standard、低预算缺失、独立进程快照、无SEI和坏输入。
  本轮未运行旧schema1快照兼容额外检查；小前缀未观察到B Slice intra TU，不能扩称覆盖。
- 关闭实验总宏的观察器头文件编译通过；没有重新构建完整宏关闭程序。

## 内存、中断与续跑

用户报告前次内存中断；没有内核OOM记录可据以确定具体原因。
之后各阶段顺序执行；采集续跑单工作进程，进程树RSS采样峰值677.2MiB。
剩余阶段最多两个工作进程，每进程地址空间上限3GiB，进程树RSS每秒监测阈值2GiB。
采样阈值不是瞬时内核总内存硬上限；文件缓存单独对任务派生文件提供释放提示。

恢复时发现重复启动的schedule控制器，已停止；96份文件重新核对发现3份SHA不匹配，
隔离BQTerrace22/R13-2与RitualDance22两来源的输出并从未改动的第一遍数据重新生成。
受影响文件不进入有效结果，未完成回放重试；原始码流未改动。
包装器新增任务目录独占锁，防止同一目录的重复启动/跨阶段重叠。
中断的receipt保留并明确标注，不能把它们当作成功运行或规则效果。
成功schedule原峰值receipt曾被重复运行覆盖，该次峰值不作报告；其余成功阶段另有完整receipt。

## 预先指定异常点的活动检查

额外只读Johnny27/32/37、KristenAndSara32和FourPeople32这五个既有诊断点，
每点两来源完整EOF数据；没有增加解码。`activity_diagnostic_population.csv`记录非零、n≥3/n=3及EQ/SP映射分歧，
`activity_diagnostic_activity.csv`记录61规则的潜在remapping变化、内部state/实际权重步数及保护计数。
变化数量尚未施加真实regular-bin预算，因此不是实际编码活动数或逐位置准确率；完整TU rate仍由原生回放确定。
这些定点机制检查不混入全数据平均，不能推广为所有内容的状态更新频率。

## 文件体积控制

61列明文schedule原为14.4GiB，中断副本约10.3GiB。按用户补充要求，
中断副本无损归档约228MiB，已完成回放的schedule逐条gzip归档，
验证压缩往返SHA及完整evaluation身份后才移除明文，未完成任务不处理。
最终96份有效预测文本从14.36GiB归档为305.8MiB，归档文件SHA及原明文SHA再次核验。
归档默认单文件上限256MiB、固定1MiB读写缓冲，不涉及原始.bin。
第二遍RSS采样峰值1328.37MiB，报告生成86.15MiB；全部资源receipt保留在`resource_receipts.json`。
压缩不改变schedule原SHA、生成器或统计身份；存储清单另外保存压缩文件SHA。
完整结果可以直接由evaluation gzip重新汇总，无需恢复schedule。
若需要重新解码，现有原生接口仍要求先按需恢复明文；不能直接对已归档全目录运行原collect续跑。

## 复现

在仓库根目录执行；新环境先构建本接口，不能直接使用旧impl2交付包中的DecoderApp：

```bash
cmake -S . -B build/ts-rule-lab -DCMAKE_BUILD_TYPE=Release \
  -DNX2_OPT_TARGET_ARCH= -DNX2_ENABLE_TRACING=OFF -DNX2_TOPLEVEL_OUTPUT_DIRS=OFF
cmake --build build/ts-rule-lab --target DecoderApp -j 2
build/ts-rule-lab/bin/DecoderApp --ts-corpus-version
python3 -m unittest discover -s scripts/ts_rule_lab -p 'test_*.py' -v
python3 scripts/ts_rule_lab/validate_native.py \
  --decoder build/ts-rule-lab/bin/DecoderApp \
  --manifest deliveries/r13_decode_audit_impl2/manifest.json \
  --output runs/ts_rule_lab_check
```

实际构建使用GCC11.4/Release，未设置`march=native`；构建命令、程序与源码SHA见`build_validation.json`。
全量计划及两遍运行见[脚本README](../../../../scripts/ts_rule_lab/README.md)，
内存受限时用其中`bounded_run.py`包装每个阶段；需要续跑时使用原身份和`--resume`，不覆盖成功receipt。

本地大输出位于`runs/ts_rule_lab_20261026/`：corpus、schedules、evaluation及隔离记录。
Git只保存小型表、验收与代码；不重复上传原始码流、重建、派生逐TU数据或新二进制。
已有96条输入仍从`deliveries/r13_decode_audit_impl2/`取得。
交付CSV统一为LF换行，run_receipts中的开发目录改为仓库相对路径；数值及输入/程序SHA不变。
本目录`.gitattributes`固定文本换行，`artifact_manifest.json`校验交付版本的实际字节；
原始和便携run_receipts的SHA分别保存在`evaluation_validation.json`。

## 解释范围

每个TU固定当前来源的最终q和原生入口context，完整回放TU内概率与regular-bin传播。
它保留TU内传播，未把不同TU改动后的CABAC出口串成新片；也未重新优化q或TS启用决策。
这些是条件TSRC fractional-bit比较，不是实际改码字节差、视频BD-rate或最终算法收益。

主统计：每来源节省bit/自身非零数 → 两来源各1/2 → 内容内QP等权 → 内容等权。
YUV按实际TSRC bit相加，不套用6:1:1 BD-rate权重。零分母保持缺失并报告支持数。
全数据排名用于描述；留一内容选择把该内容全部QP与两来源一起排除。
数据曾用于方法开发，留一内容检验也不等于全新盲测或总体泛化置信区间。
