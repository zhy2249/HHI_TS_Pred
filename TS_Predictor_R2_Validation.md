# R2 本地正确性验证

日期：2026-09-18。仅验证实现和隔离，**未运行正式CTC，不提供新BD-rate结论**。
Current是唯一正式anchor；未修改 `scripts/JVET-hhi.xlsm`。

## 构建与控制

GCC 11.4、Release、LTO关闭，独立构建 `build/ts-r2` 与 `build/ts-r2-off`。
ON/OFF均通过编辑TypeDef.h验证；交付源码已恢复master=1、所有默认模式宏=0（Current）。
旧 `build/ts-anchor`、`build/ts-fixed`、`build/ts-conditional` 二进制未重编。

- 6项宏测试：13种有效默认、13×13显式覆盖、非法值/新旧互斥、master OFF拒绝实验、批量探测忽略环境残留。
- 9项调度测试：新四组模式、共享池、无重建、续跑、组完成即写表、失败重试刷新和Reference保护。
- 3项分析测试：先分量BD-rate再6:1:1、缺点不补、不接受非Current Reference。
- 空R2结果目录分析明确返回112个缺失点，不伪造零收益/完整组结论。

## 独立评分与因果检查

`TsFixedPredictorTest`：remap往返/p=0或1 identity、局部公式/平局/支持度、EWMA，
64种native grouped scan尺寸、1,267,924次因果邻居检查；未写死8×8。

`TsR2RateTest`：CommonLib新回放对照保留的原生 `CABACWriter::residual_coding_subblockTS`
和 `BitEstimator_Std`，并非两个调用同一回放函数的自证。

- Current、NoPred各6,014个CG：fractional累计成本零差异、预算一致、检查的最终概率/更新参数一致。
- 覆盖Y/U/V、矩形、空CG、last-CG inference、不同regular预算、Rice 1..8、BDPCM、context-switch分支。
- 15/20-bit动态范围共12,672个Rice长度样例，与codec estimator零差异，包含limited escape。
- R2-N/F各5,718个CG状态检查：进入TU为0，克隆状态后任意污染未来q不改变当前更新，空CG按定义衰减。

这证明给定相同起点的回放一致，不代表虚拟I先验等于真实slice上下文，也不证明RD收益。

## 端到端smoke

11场景×10构建/模式＝110次两帧64×64编码，全部解码hash通过：
QP22/32/33、TS off、QP0大TS、lossless、TSRC off、DQP、BDPCM、LB、RA。
10种为旧anchor、新OFF、Current、旧三种固定模式、R2四组。

- Current及新OFF在11个场景均与保留anchor码流bit-exact。
- TS off/TSRC off场景各模式码流一致。
- 最终Writer与Reader逐CG的状态、选择、gain、预算、q hash、虚拟分支成本trace全部一致。
- R2-N/F每TU的CG0均Current，四个新模式均真实改变过remapping，测试不是空运行。
- 另加4次QP0编码关闭trace及全部R2统计，码流不变。
- 另加3次旧固定QP0回归，与保留revision1二进制的NoPred/gradient/directional逐码流一致。

| 模式 | 非BDPCM trace CG | 选择NoPred的CG | 实际映射改变位置 |
|---|---:|---:|---:|
| r2_modal | 1477 | 不适用（逐系数） | 161 |
| r2_risk | 1464 | 不适用（逐系数） | 714 |
| r2_cn_log | 1483 | 603 | 1055 |
| r2_cn_frac | 1456 | 302 | 648 |

这里只是覆盖计数，不是模式优劣或真实内容上的TS使用率。
初次99项通过后加入真实入口上下文观察，最终110项及4项关闭统计复核均基于交付版本重跑。

在线聚合导出645行，R2-F的1456个非BDPCM CG都有虚拟/真实入口两套成本。
该smoke集合虚拟Current/NoPred成本约99978.78/102200.22 bit，真实入口对应约95294.93/97119.90 bit。
两套成本不同，符合先验/历史定义；这些固定q、混合测试条件的总和**不是BD-rate或Oracle收益**。

## 边界与尚未完成的实证

- 编码smoke主要8-bit输入/10-bit内部，lossless为8-bit；20-bit动态范围只在独立语法测试覆盖。
- DQP/BDPCM开关启用不代表所有内部子分支穷举；未宣称所有工具组合通过。
- 已检查最终CG/全零历史及源码更新位置；没有把每次RDOQ试算与最终选中TU逐候选完整追踪。
  Writer/Reader同步和独立回放不等于证明RDOQ的原生近似rate预算变成精确三遍模型。
- 统计仅包含最终进入TSRC residual coding的TU；不包含CBF=0或TSRC关闭的TU。
- 未测正式BCE/RA收益及decoder性能；R2-F额外回放成本必须在同机正式结果中评估。
- RAeu dry-run确认为64/32帧单段；不能直接与帧数/分段来源未确认的外部RA anchor作正式比较。

机器可读结果：`runs/ts_r2_smoke/validation.json`、`summary.csv`、`activity.csv`和逐任务日志。
LB CE dry-run确认112项半帧任务；RA CD仅确认128项任务结构，均未正式运行。

## 交付二进制SHA-256

```text
ON EncoderApp  1d2d81013ca0ee47217d48ee81cae8b7ed0dbcaabfc1582f56a89988a9a0c953
ON DecoderApp  3428422c50027fe44e4abe2f36ae171981c750f2e2f6cd9fe33ef53dc21de898
OFF EncoderApp b73d8ac13a649d2f7ef871879ba97e4db0b41d2d78c62a5ea4db9e57f2bd7cf9
OFF DecoderApp 87585dec6baabcfd93eddb143c4ede5d8dc61ea7c6b7fa93221ac0a4c7ae49a3
```

本地hash仅标识本地构建，不代替其他服务器的构建和配置审计。
