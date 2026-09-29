# R10 / R9-B复算与R11数学参考

对应输入提交：`e1413fd0bf361cdea7d06fbc1b3a78c7036de5de`。本目录仅含外部分析脚本，不修改正式编码器或结果台账。

在仓库根目录运行：

```bash
python3 docs/external_inputs/r11_analysis/recompute_from_ledger.py --repo . --out /tmp/r11-results
python3 docs/external_inputs/r11_analysis/r11_reference.py
```

复算依赖NumPy/SciPy，读取既有 `docs/experiments/results/rd_points.csv`。默认核对固定CSV的Git blob指纹；若后续补点改变了台账，应先检查变化，确需重算新数据时显式加 `--allow-updated-ledger`。输出均为百分比，0.1表示0.1%。不新增补点，不外推。

`R10_key_summary.csv`同时包含Current/R9-9/R3配对及R10-6排除PartyScene/RaceHorsesC的完整五序列结果。`R9_B_key_analysis.csv`分开记录四点含现有暂代和QP27/32/37三点纯实测诊断；三点不是完整四点CTC。

`r11_reference.py`只验证数学选择、有限几何邻域、无证据回退与未来污染不变性，不是C++补丁；其CG扫描仅为合成测试。`validation.json`记录本轮实际运行的复核范围，不能用来宣称R11已获编码收益、速度或原生编解码同步验证。

完整离线包另附逐点输入、质量分段、插值/删一敏感性及完整复算脚本；Git主目录保留分析报告、R11规格和关键派生表，原始工作簿/大日志未上传。
