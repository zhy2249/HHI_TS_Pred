# R12结果分析与文件范围

固定读取提交：`a0f21db22e0ef2ed778a9e1a17aa4daa966fed45`。

本次Git同步完整分析正文、八位小数派生汇总、直接匹配比较和B更新表，不修改codec、实验规格或正式台账。报告中第9节列出的标准化输入、复算脚本、computed目录和Excel，位于同次会话提供的完整分析压缩包，不在这里重复上传二进制工作簿或原始实验数据。

- `../R12_Results_Analysis.md`：分析与下一步优先级。
- `../R12_Results_Summary.csv`：对Current的CE结果；wins/ties的总体为7条序列。
- `../R12_Matched_Comparisons.csv`：独立积分的直接比较，不是两个BD的差；equal_RD_points不代表bit-exact。
- `../R12_B_Update.csv`：完整四点与QP27/32/37区间诊断分别标记。R12尚无B结果，此表是同次推送的R10-3/R11-2 B更新。
- `audit.json`：本次核验范围，不认证服务器运行身份。

所有BD字段为百分数值，−0.1即−0.1%；负值改善。B_required是实现BCE≤−0.10%所需B均值，不是预测。

Git导出保留8位小数，完整分析包的computed文件保留计算精度。没有新增补点，没有借用其它算法B曲线，没有运行新编码或计时。
