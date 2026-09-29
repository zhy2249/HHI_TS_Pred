# R9 结果收件目录

13组编号与实现见[R9_Experiment_Plan.md](../../docs/external_inputs/R9_Experiment_Plan.md)、[TS_Predictor_R9_Implementation.md](../../docs/experiments/TS_Predictor_R9_Implementation.md)。
默认先跑阶段I（1～6、13），然后II（9/10）、III（7/8）、IV（11/12）。
每个文件夹名称含公开 R9_MODE 数字；原工程标识保留在 README/metadata/manifest。
Current是正式anchor，Y/U/V先分别算BD-rate后6:1:1加权；CE七序列等权。
13组LB CE共364个实测点已于2026-09-28登记。
2026-09-29新增R9-9 LB B的16个实测点；MarketPlace、Cactus、BasketballDrive、BQTerrace
的QP22按用户授权暂用Current补点，仅写派生台账、不改原表。详见[结果明细](../../docs/experiments/results/r9.md)。
源文件为本目录`R9_<编号>_JVET-hhi.xlsm`和`<编号>.csv`；9.csv仅覆盖CE，R9-9新增B点来自工作簿。
不要覆盖原R8数据、不要将诊断收益填成BD-rate。
