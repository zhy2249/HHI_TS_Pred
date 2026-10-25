# R13 双码流审计 impl2：统计、原生回放与交付验收

2026-10-25；审查基线 `1270ad3c2b24f9a7e78a19167cb6a55a3194e2e0`。
本目录是观察器验收，不是新编码实验结果。没有运行 EncoderApp、视频编码或更改正式 RD/BD-rate。
[实现与修改前后对比](../../TS_Predictor_Dual_Decoder_Audit_Implementation.md) ·
[schema 与估计口径](../../TS_Predictor_Dual_Decoder_Audit_Schema.md)。

## 静态与异常条件

- Python 单元测试 **14 项**：两来源等权/互换不变、缺方法/缺观察帧阻止完整比较、
  B Slice 与 Intra CU 独立、正损失及分位加权、富集排除、C0/C+、空分母、预算截断和 bootstrap 限制。
- C++ **1440 种**预算分配组合：任意分量执行顺序不改变分量/TU 配额，总量不突破上限。
- 原生合成 TU：EQ/SP 各 **48 个**，实际局部 Writer→Reader→回放，包含 Rice1–8、三遍/预算耗尽、
  BDPCM、矩形/YUV、历史候选、真实 Slice/CU 身份和快照往返。这不是帧编码。
- 总宏关闭只验证观察头编译，未重建整个宏关闭工程。

[static_validation.json](static_validation.json) 保存数量和局部测试源/程序指纹。

## 双来源前缀

17 帧已有前缀，最终 Release 程序；14 条运行时验收记录见
[runtime_validation.json](runtime_validation.json)。

- standard/summary 的全部、目标、eligible、scoring、系数/非零、Slice×CU、幅值与支持数分母一致。
- 将每 POC 回放数降到 6，两来源均为原生完成、`policy_complete=[false,true,true,true,true,true,true]`。
  未完成的 CURRENT rate 为 null，`audit_complete=false`，双来源主 balanced 比较留空，已验证缓存结果仍保留。
  不是只验证“进程退出成功”。
- 快照预算 0、访问预算 0、raw 输出 400 字节分别触发独立的缺失/截断状态，均保持 on/off 重建一致。
- 六个快照由新进程加载，七方法 rate 与捕获值逐一相等；旧 schema 1 的 Slice 为 unknown，不猜测为 I/B。
- 无 SEI 派生前缀保留 on/off MD5 一致，但明确 `SEI_not_available`，不冒称编码端校验通过。
- 损坏快照、截断码流、错误来源模式和 LFS 指针被拒绝；匹配指纹 resume 不重复解码。

这个前缀没有 B Slice Intra TU；该项使用下面的真实完整流补验。

## 正式码流的覆盖范围

先对三对流观察前 32 帧，再用最终程序观察完整 300 帧；POC 范围只限制观察，解码仍完整读取参考链。
下表只计最终 300 帧验收，不重复累加前 32 帧开发结果。

| 码流 | R13-1 帧 / native TU | R13-2 帧 / native TU |
|---|---:|---:|
| Johnny QP27 | 300 / 41 | 300 / 40 |
| Johnny QP32 | 300 / 9 | 300 / 9 |
| FourPeople QP32 | 300 / 10 | 300 / 5 |
| 合计 | 900 / 60 | 900 / 54 |

共 **1800 on 帧＋1800 off 帧**，每帧 SEI MD5 及 on/off 重建一致。
**114 个**原生采样 TU 的 bins 值/context id/顺序、fractional bits、出口概率状态、pass 和 regular budget 精确一致；
所有七方法、单点、快照、输出均完整，没有预算跳过。
服务器原始预计帧数/编码配置身份未知的字段仍为 null，不由本次解码 300 帧反推认证。

实际 B Slice 内 Intra CU 共 3 个，均 `slice_type=B,is_intra_cu=1,is_inter_cu=0`：
Johnny QP27 两来源 POC168 Y `(608,316,16,4)`；Johnny QP32 EQ 来源 POC26 Y `(864,704,32,16)`。
三个快照再由独立进程回放，身份及七 rate 与捕获时一致。

- [validation.json](validation.json)：六文件输入/程序 SHA256、完整状态、命令、构建来源。
- [coverage.csv](coverage.csv)：六文件逐分量 census/覆盖/跳过数。
- [B_slice_intra_CU.csv](B_slice_intra_CU.csv)、[B_slice_offline.json](B_slice_offline.json)：实际 B/Intra 证据。
- [policy_comparison.csv](policy_comparison.csv)、[score_comparison.csv](score_comparison.csv)：完整方法/来源表的验收副本。
  空分母留空，不将空色度样本解释为高准确率；只解释为本次条件统计覆盖。
- [all96_dry_run.json](all96_dry_run.json)：48 对/96 正式解码任务，仅 dry-run，未全量解码。

## 交付与复现

最终 Linux x86_64 程序 SHA256：
`54e66385447d7ecd513c0e676b3f47a1571d9eecd9678b116d1eb6d1d81f182b`。
Release / GCC11.4 / glibc2.35 / SSE4.1，Python3.10+ 标准库，无 GPU/原始 YUV 依赖。
源码基线＋补丁指纹保存在 validation.json；最终归档另记录对应实现提交，不覆盖历史验证指纹。

本地整理包 `runs/r13_dual_decode_audit_impl2_release/`；正式归档 `runs/delivery/r13_decode_audit_impl2.tar.gz`。
候选归档已在 `/tmp` 新目录解包，逐文件 SHA256 和两个来源真实运行通过；正式归档的校验摘要在本目录另存。
**源码/小型文档经 Git 同步；实际程序与 96 条正式流＋2 条前缀仅本地归档，未远程发布，未验证 GitHub 下载。**
不取消 .gitignore、不提交这些原始文件。异目录运行与另一机器/发行版运行是两种验证；后者尚未完成。

仓库根目录可复现：

```bash
python3 -m unittest discover -s scripts -p test_ts_decode_score_audit.py
g++ -std=c++17 -O2 -I source/Lib scripts/ts_audit_budget_test.cpp -o /tmp/ts_audit_budget_test
/tmp/ts_audit_budget_test
python3 scripts/test_ts_decode_score_audit_runtime.py --manifest runs/r13_dual_decode_audit_impl2_release/manifest.json --output runs/r13_runtime_recheck
python3 scripts/package_ts_decode_audit.py verify --archive runs/delivery/r13_decode_audit_impl2.tar.gz --output runs/r13_archive_recheck --smoke-pair Johnny_QP32_prefix17
```

后续 96 条的共享任务池/续跑命令见实现文档。打包脚本提供本地归档，另一个环境仍需取得该实际归档后才能运行。

## 尚未验证及解释边界

- 多层/并行 slice、L 工具组合、全部位深和其它 OS/CPU；实际正式样本以 Y 为主，真实 U/V 大样本覆盖不足。
- 快照支持≤64×64/4096系数、动态范围8–20；协议外 TU 计数另列。
- CE01 缺完整搜索 fixture，最终码流不能恢复 Encoder search；未为补齐它重新编码。
- POC-block bootstrap 条件于已抽 TU/位置，**不包含完整两级抽样方差及跨序列不确定性**。
- 固定最终 q、各自来源 context 上的条件评分，不代表 predictor 的闭环 RD 或 BD-rate，也不代表全部96文件的模型结论。
