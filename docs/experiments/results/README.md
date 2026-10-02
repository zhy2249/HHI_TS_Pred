# 实验结果明细

更新时间：2026-10-02。仅数据登记，不含实验分析。

[返回总结果台账](../TS_Predictor_Results_Ledger.md)

每个实验按配置、序列列出 QP22/27/32/37 的总码率（kbps）、Y/U/V PSNR（dB），
并并列 Current 参考点；每条序列单独列出 Y/U/V BD-rate 及 6:1:1 加权 BD-rate（%）。
BD-rate 属于四点曲线，不是单个 QP 的指标。负数为节省；不先加权 PSNR。

CSV 的空字段和 Markdown 的“—”均为缺失/不可计算，不是零。补点逐点标记且保留原工作簿定位。
各组的 incomplete 曲线不计算 BD-rate；组级可用子集均值明确标记，不冒充完整 CE/BCE。
若参考点状态不是 pass，保留其原始数值和状态，但对应序列不计算 BD-rate。
这里只核验表内数值、Current Reference 和可用配套 CSV；不认证服务器宏、帧范围或解码 hash。

## 查询文件

- [逐 QP 数据 CSV](rd_points.csv)：含实验、配置、序列、QP、两组 RD 值、来源单元格和补点状态。
- [逐序列 BD-rate CSV](sequence_bdrate.csv)：含分量、加权 BD、实测/补点/缺失数量及积分区间。
- [类别汇总 CSV](group_summary.csv)：按序列等权，含有效序列数及完整/子集标记。
- [来源与核验记录](sources.json)：源文件 SHA256、配套 CSV 核对及 VBA 数值交叉检查。

## 按实验轮次

| 轮次 | 方法数 | 实测点 | anchor 补点 | 缺失点 |
| --- | --- | --- | --- | --- |
| [FIXED](fixed.md) | 3 | 220 | 0 | 0 |
| [CONDITIONAL](conditional.md) | 5 | 130 | 9 | 1 |
| [R2](r2.md) | 4 | 112 | 0 | 0 |
| [R3](r3.md) | 4 | 232 | 3 | 1 |
| [R4](r4.md) | 6 | 168 | 0 | 0 |
| [R5](r5.md) | 2 | 56 | 0 | 0 |
| [R6](r6.md) | 7 | 216 | 0 | 0 |
| [R7](r7.md) | 2 | 56 | 0 | 0 |
| [R8](r8.md) | 24 | 670 | 2 | 0 |
| [R9](r9.md) | 13 | 380 | 4 | 0 |
| [R10](r10.md) | 6 | 185 | 2 | 1 |
| [R11](r11.md) | 8 | 240 | 0 | 4 |
| [R12](r12.md) | 12 | 336 | 0 | 0 |

## 维护与复现

在仓库根目录运行（只读源表，生成本目录派生文件）：

```bash
python3 scripts/ts_results_ledger.py
python3 scripts/ts_results_ledger.py --date 2026-10-02 --check
```

新增实验在脚本 catalog 中登记身份和源表路径；历史补点白名单不自动扩展。
实际数值出现后优先使用实际值。`--check` 只比对当前输入生成的内容与已登记文件，不写文件。
旧汇总的补点替换等变更保留在总结果台账中；源工作簿、CSV 和外部原稿不改写。
