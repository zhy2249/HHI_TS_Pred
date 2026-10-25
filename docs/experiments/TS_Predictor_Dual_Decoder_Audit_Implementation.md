# R13 双码流只读评分审计：实现与本地交付

日期：2026-10-25。需求：`R13-DUAL-DECODE-AUDIT-v1`；实现：`R13-DUAL-DECODE-AUDIT-impl1`。
已快进同步至`f603715`，按[双源需求](TS_Predictor_Dual_Stream_Decoder_Audit_Requirements.md)实现。
不改R13-1/2的候选、评分、RDOQ、反映射或正式实验编号；本轮没有运行EncoderApp或视频编码。

## 1. 当前交付

- `scripts/ts_decode_score_audit.py`：prepare、inspect、decode-pair、detail、replay、compare、select-examples。
- `source/Lib/DecoderLib/tsaudit/`：原生bin观察、显式快照、公共TSRC回放、采样/预算与离线导出。
- 已编译Linux x86_64程序：`runs/r13_dual_decode_audit_bundle/bin/DecoderAppAudit`。
- 可移动本地包：`runs/r13_dual_decode_audit_bundle/`，包含程序、包装脚本、manifest、build_info、码流和CE01已有部分输入。
- 验收记录：[明细索引](results/r13_dual_decoder_audit_20261025/README.md)。本说明的“通过”只指下列已执行范围。

该包目前要求SSE4.1，按机器能力分派SSE4.2/AVX/AVX2，**没有使用`-march=native`**；
编译器、动态库和二进制SHA256记录在build_info.json。需要Python3.10+标准库，无Python第三方包、GPU或原始YUV。
不宣称已在SSE2-only机器、其它OS/glibc组合上验收；可按第8节重新构建。

## 2. 13_bin整理及身份边界

原收件目录：`experiments/ts_predictor_r13/13_bin/13_1/`、`13_2/`，各48条。
已**复制**到：

```text
runs/r13_dual_decode_audit_bundle/
  manifest.json
  build_info.json
  README_run.md
  copy_inventory.csv
  bin/DecoderAppAudit
  scripts/ts_decode_score_audit.py
  streams/<Sequence>_QP<22|27|32|37>/R13_1.bin
  streams/<Sequence>_QP<22|27|32|37>/R13_2.bin
  validation_streams/Johnny_QP32_prefix17/{R13_1.bin,R13_2.bin}
  fixtures/CE01/{detail_input_q.csv,detail_entry_context.csv}
```

原96条不删除、不覆盖，共167073025字节；每条复制后SHA256复核一致。
另收录之前已验证的17帧EQ/SP前缀作为最小配对输入。因此本地manifest包含49对/98条，
其中48对是本次用户提供的完整文件收件，不把额外前缀计成新CTC结果。
[复制清单](results/r13_dual_decoder_audit_20261025/copy_inventory.csv)逐条记录源、目标、大小与SHA256。

目录`13_1/13_2`用于**显式绑定**原生EQ/SP；它不是自动识别编码器revision。
上传文件的encoder commit、编码器hash、输入/配置hash、预期帧数等缺失信息保持null。
历史LB半帧约定仅记为hint，不假装已经验证上传文件的完整编码配置。
已测文件在decode_validation中记录实际帧数、SEI与on/off校验；这不能补造未知的编码身份。
源码/文档/小型派生表提交Git；码流、二进制、快照及大日志继续留在忽略的本地目录。

## 3. 原生核验与快照

`CABACReader::residual_codingTS`在首个CG flag之前保存被暂留采样TU的概率状态，
正常完成三遍语法、反映射和符号恢复后才读取q。`BinDecoder`在context更新前累计原生fractional cost：

- context bin记录真实ctx id、0/1值与`estFracBits(value)`；
- EP按真实位序展开计数；`decodeRemAbsEP`不再单独计数，避免与内部EP重复；
- 每CG记录原生pass1/pass2末位置与remaining regular budget。

两种来源分别校验自己的原生分支，逐bin核对顺序、值、ctx id、cost，再核对总rate、CG边界/预算、
所有概率模型出口字段。CBF/TS flag等TSRC范围外语法不计入该rate。首次不一致保存`invalid_snapshot.tsa`，
审计标invalid；不把错误分支的rate纳入统计，也不改用另一种native mode重试。

快照新增显式保存`m_stateUsed[2]`：原`getState()`和`setState()`不足以恢复它。
只给概率模型增加诊断getter/setter，原始update、概率表和codec决策未改。
`.tsa`是有版本的ASCII十进制字段序列，头含精确字节长度和FNV1a64负载校验；不是C++内存转储。
保存有符号q、完整scan、CG flags和context索引、Rice/range/budget、原生bins/末状态等。
每个概率模型保存state[2]、stateUsed[2]、window、weight、offset[2]以及两个冗余fractional cost；
重读后检查cost，实际重放进一步验证更新后的全部状态。TS不使用的Ctx baseLevel不冒称已序列化。
manifest/复制清单另使用SHA256；FNV仅用于快照内部损坏检测，不作为来源认证。

审计关闭时不复制Ctx、不开审计文件。`TS_AUDIT_HASH`是独立验收开关，可在审计关闭时仅计算最终重建MD5。
无需原图；无SEI时只声明on/off重建一致，输出`SEI_not_available`，不冒充编码端MD5验证。

## 4. 七个影子方法与评分标签

| 方法 | 评分 | 权重 | 候选 |
|---|---|---|---|
| CURRENT | max(L,U)，不评分 | — | Current |
| STATIC_EQ / STATIC_SP | 原syntaxCost(remap)，乘168 | 11111 / 22111 | C0 |
| KEEP_EQ / KEEP_SP | 原R13 KeepHit | 11111 / 22111 | C0 |
| KEEP_EQ_H / KEEP_SP_H | 原R13 KeepHit | 11111 / 22111 | C+ |

C0复用旧候选顺序、0/1等价、去重、严格更优和平局规则，n<3仍Current。
代码逐位置检查KEEP_EQ/SP与原`r13Predict`一致。所有观察policy都显式传给私有回放，不切换全局native模式。

C+仅追加同TU/同分量的扫描前非零幅值众数，包含1，频数平局取较小幅值；先预测后计当前q。
众数1与NoPred重复，不新增；历史是候选而非伪样本/奖励。最多7个候选，评分直接调用原单样本loss，
所以历史候选大于局部最大值时仍按实际候选计算raised cost，不沿用旧最大邻居缓存假设。

每采样TU输出全部方法的完整TSRC rate；对抽中位置保持native后继序列，单独覆盖该位置的p，
覆盖全部相关语法遍，并完整重放TU。相同映射共享结果；原生结果外最多两种额外映射回放。
按真实cost最优集合而非任意单一oracle mode统计准确性。零系数、n<3不进入单点准确率；全tie单列。
C0/C+的oracle、准确性分母分开，历史coverage与选择损失另表。单点差不相加冒充整TU差。
点记录保留直接bin差与后继传播差，后继p没变不会再计成一次误选。

## 5. 对称采样、资源与输出

- 两来源独立按自己的q/context统计，POC/分量/方法/seed/配额一致；一次decode-pair并发启动两个独立进程。
- 每origin、POC、分量至多2个TS TU，按不含q/评分结果的固定seed几何hash取最小优先级。
  暂留槽可能被后来的TU替换，帧结束后才做精确回放。BDPCM单列分母，不混入目标评分。
- 每TU至多2个合法非零评分位置作均匀样本，再从未重复分歧位置取2个富集样本；两种人口不混合。
- 记录TU与位置两级包含比例。frame_summary中的HT量明确为采样估计，native原始rate和单点cost仍保存整数fractional units。
- 每origin/POC至多96次回放、125000次回放语法遍系数访问。cheap census/邻域准备不算“回放访问”；
  三遍各自计数。预算不足标skip，主比较不冒充完整随机样本。没有把另一来源剩余预算转入本来源。
- 暂留快照缓存按已支持TU上限约束并核对64MiB；磁盘快照≤64MiB/stream，缺额有计数。
- 原生聚合JSONL≤8MiB；全部core输出检查≤32MiB/stream。on/off纯日志合计上限8MiB。
  core截断写入validation，主比较不再标完整；详例每来源随机128条＋每分量正/负各32条，最多320条。
- 完整解码与观察范围分开：`--first-poc/--last-poc`只限制观察，仍解码完整文件/必要参考，不字节seek到中段。

输出`run.json`、`decode_validation.json`、`frame_summary.csv`、`strata.csv`、`tu_policy_matrix.csv`、
`history_summary.csv`、`examples.jsonl`。配对额外输出`pair_comparison.json/csv`、`score_comparison.csv`、`pair_uncertainty.json`。
分层包括幅值、n、I/inter、面积、归一分差、近远冲突、边界缺邻、native regular/bypass；
全量cheap分母与采样位置统计明确分开。未计算SSE/PSNR，不用0填未知失真。

主矩阵只作行内SP−EQ。比较使用共同**观察**帧集，另列共同解码帧集；不同最终划分不按第n行配对，
几何交集与单边样本分别保留。balanced先算每来源指标，再各占1/2；空分母或缺来源为null。
Y/U/V分开，不将选择损失当BD-rate或强行6:1:1。detail是定点诊断，不产生代表性总体归一比较。

整TU增量的不确定性采用两来源配对的循环POC块bootstrap，块长8、2000次、seed20261025；
至少两侧各有2个非零支持帧才给区间，报告有效抽样次数。区间条件于已抽样的TU和有限内容，
不涵盖完整两级抽样/跨内容总体方差；不能借此宣称数百万系数独立或模型普适显著。

## 6. CE01的实际状态

- 原256个q、14非零/absSum15及已有context公开字段已放进包的`fixtures/CE01/`。
- 旧CSV没有`stateUsed`，也没有完整的原生bin/出口快照。**本轮未伪造入口概率，完整fixture仍为`missing_fixture`。**
- 对已有17帧SP码流的POC16/Y/(856,384,8,32)查询返回`not_in_final_bitstream`，符合该TS候选落选的事实。
- 原[CE01已验证的90521差额](counterexamples/CE01_Johnny32_POC16_8x32.md)不被此次缺快照状态推翻；
  但不能把之前进程内成功回放写成新程序已从旧CSV精确恢复该fixture。
- 若未来获准再次捕获该搜索trial，应使用本轮完整快照字段；本轮没有为此启动编码。

## 7. 运行命令

均从仓库根目录执行；已有输出目录受保护，重跑换新目录。

```bash
python3 scripts/ts_decode_score_audit.py inspect \
  --manifest runs/r13_dual_decode_audit_bundle/manifest.json

python3 scripts/ts_decode_score_audit.py decode-pair \
  --manifest runs/r13_dual_decode_audit_bundle/manifest.json \
  --pair Johnny_QP32 --profile standard --first-poc 0 --last-poc 31 \
  --verify-off --output runs/johnny32_decoder_audit_new

# 去掉POC范围参数即可观察完整文件；仍只解码，不重编码。
# 最小配对输入可将 --pair 换为 Johnny_QP32_prefix17。

python3 scripts/ts_decode_score_audit.py replay \
  --snapshot runs/r13_dual_decode_audit_bundle/validation/prefix17/R13-1/snapshots/0_0_824_112_8_16.tsa \
  --decoder runs/r13_dual_decode_audit_bundle/bin/DecoderAppAudit \
  --policies KEEP_EQ,KEEP_SP --output runs/ts_snapshot_replay_new

python3 scripts/ts_decode_score_audit.py detail \
  --manifest runs/r13_dual_decode_audit_bundle/manifest.json \
  --pair Johnny_QP32_prefix17 --origin R13-2 --poc 16 --component Y \
  --tu 856,384,8,32 --output runs/ce01_final_query_new

# 从已保留样本筛选正损失案例；不会重新解码或改变主统计。
python3 scripts/ts_decode_score_audit.py select-examples \
  --input runs/r13_dual_decode_audit_bundle/validation/j32/R13-1 \
  --component Y --loss-sign positive --max-examples 32 \
  --output runs/ts_positive_examples_new
# 可另加 --size 8x16、--first-poc/--last-poc；负损失用 negative。
```

replay的`--policies`控制控制台展示，底层一次导出所有七方法供交叉核对；`bins.csv`是单快照限量逐bin记录，
`snapshot_fields.json`导出真实q/scan/入口概率字段，`replay.json`给各位置邻域、候选、分数和p。
解码阶段可按POC、分量、完整TU几何定位；`select-examples`支持POC范围、分量、WxH和正/负/零损失筛选，
只处理已保留的位置，最多320条，按损失绝对值排序。更一般的尺寸区间可查派生表。
不倒用评分结果控制代表性采样，也不把筛选后的频率当作主总体。

原生调试环境为`TS_SCORE_AUDIT=输出目录`、`TS_AUDIT_PROFILE=summary|standard|detail`、
`TS_AUDIT_FIRST/LAST/COMPONENT/TU`、`TS_AUDIT_HASH=文件`。默认关闭。
预算变量`TS_AUDIT_REPLAYS/VISITS/TUS`只允许降低预注册上限；包装脚本清理外部TS变量并用manifest的固定对称配置。
R13模式必须由manifest分别绑定EQ/SP；无需新增Rxx实验宏，`JVET_BJUT_TS_FIXED_PREDICTOR`总能力需开启。

## 8. 构建和验收范围

```bash
cmake -S . -B build/ts-decode-audit -DCMAKE_BUILD_TYPE=Release \
  -DNX2_OPT_TARGET_ARCH= -DNX2_ENABLE_TRACING=OFF
cmake --build build/ts-decode-audit --target DecoderApp -j 6
python3 -m unittest discover -s scripts -p test_ts_decode_score_audit.py
```

使用TypeDef.h现有总开关，未新增CMake算法开关。重新整理另一个包可用：

```bash
python3 scripts/ts_decode_score_audit.py prepare \
  --source experiments/ts_predictor_r13/13_bin \
  --decoder build/ts-decode-audit/bin/DecoderApp --output runs/r13_bundle_new
```

prepare只复制当前96条输入；本轮本地包额外收录的已验证17帧前缀/CE01部分输入已在manifest列出，
不要求另一个环境拥有这些旧runs才能整理用户码流。

已执行：

1. DecoderApp Release构建；总实验宏关闭时新观察头文件独立编译。
2. EQ/SP各48个合成TU：真实Writer→Reader→bin计数→回放→快照重读，覆盖YUV、长矩形、稀疏/密集、
   全零CG、Rice1–8、regular预算耗尽、两种BDPCM、历史众数暴力核对和同映射复用；不是视频编码。
3. 两来源17帧前缀，以及Johnny QP27/32、FourPeople QP32的两版300帧码流，观察on/off分别解码。
   正式文件仅观察前32帧，均核验全部实际解码帧MD5；独立replay在新进程核验。
4. 无SEI的派生17帧测试保留正常重建并正确标记SEI_not_available；损坏快照、错误policy manifest、
   截断码流明确失败。降低回放预算不影响解码，summary不产生快照/回放。CE01最终块查询为空。
5. Python来源等权、交换来源顺序、空分母、共同观察帧、错误帧重复及非有限JSON检查。

当前实现限定单层、单进程串行CABAC解码观察，snapshot几何≤64×64/4096系数、动态范围8–20。
未验证多层或并行slice解码，不称为全工具/全位深验收；超出快照协议范围显式报错。
完整96条码流未批量解码，未做新的BD-rate或评分全序列排名。验证小样本不能支持后续算法优劣结论。
