# R8 实验收件：七组完整LB CE已收到，R8-19待完成

2026-09-26：MODE 1/4/8/13/15/16/17各28/28点，共196点，无补点。
源文件当前直接存于本根目录 `r8_<MODE>_JVET-hhi.xlsm` 与 `<MODE>.csv`，未擅自移动。
数值审计通过，服务器实际模式/配置/帧数/解码与活动日志尚缺；不要把表内pass等同远端身份验证。
分析见 [首七组结果](../../TS_Predictor_R8_First7_Results_20260926.md)，R8-19未混入均值。

设计与分组见 [R8 实验设计](../../TS_Predictor_R8_Experiment_Design.md)。
机器可读规格见 [manifest](../../scripts/ts_r8_experiment_manifest.json)；它不是当前 batch 接受的运行 manifest。

目录命名为 `r8_<公开MODE数字>_<方法名>`：1..12 对应 A01..A12，13..20 对应 B01..B08，21..24 对应 C01..C04。
各目录 README 给出宏、runtime、父对照；**仅首批MODE 1/4/8/13/15/16/17/19可运行**，其余请求将报错。

每组实际完成后，在对应配置子目录存放：

```text
r8_<MODE>_<name>/
  smoke/                # 工程验证，不能混作 CTC
  LB_CE/                # 七序列、四 QP、HHI INI 半帧
  LB_B/                 # 五序列、四 QP，后续按计划扩展
  RA_CD/                # 如另行确定配置身份后扩展
```

配置目录内接收实际 `JVET-hhi.xlsm`、CSV、`run_metadata.json`、身份/活动/hash/失败日志。
需要时复制本根目录空白 `run_metadata.template.json` 并据真实运行填写；模板不是运行记录。
不预生成空白 XLSM、不补写成功 marker、不移动任何旧 R3/R6/R7 结果。

首轮八组（替代旧10组安排）：MODE **1、4、8、13、15、16、17、19**。
选择理由、精确规则和直接对照见 [首轮设计](../../TS_Predictor_R8_First8_Design.md)。
第二批保留：MODE 2、3、5、6、7、9、10、11、12、14、18、20；第三批21、22；第四批23、24。
首轮完整LB CE为224个新增编码点；工程短测含四个旧对照为96点，不重跑完整Current anchor。

正式 Current anchor；R3-1 是增量对照。Y/U/V 分别 BD 后 6:1:1，CE 七序列等权、BCE 十二序列等权。
共享任务池、逐组完成即写表、无重建、resume均沿用现有batch。
运行命令见 [实现说明](../../TS_Predictor_R8_Implementation.md)，本地验收见 [验证](../../TS_Predictor_R8_Validation.md)。

本轮文档按约定上传 Git，实际结果源表、码流和大体积日志保留本地。
