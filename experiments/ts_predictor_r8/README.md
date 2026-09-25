# R8 实验收件：24 组，尚未编码

设计与分组见 [R8 实验设计](../../TS_Predictor_R8_Experiment_Design.md)。
机器可读规格见 [manifest](../../scripts/ts_r8_experiment_manifest.json)；它不是当前 batch 接受的运行 manifest。

目录命名为 `r8_<公开MODE数字>_<方法名>`：1..12 对应 A01..A12，13..20 对应 B01..B08，21..24 对应 C01..C04。
各目录 README 给出预留宏、runtime、父对照；**当前 R8 宏和运行参数均未实现**。

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

第一批 1a：MODE 1、4、8、15、17、19；1b：MODE 9、10、11、13。
第二批：MODE 2、3、5、6、7、12、14、16、18、20；第三批 21、22；第四批 23、24。

正式 Current anchor；R3-1 是增量对照。Y/U/V 分别 BD 后 6:1:1，CE 七序列等权、BCE 十二序列等权。
共享任务池、逐组完成即写表、无重建、resume 的现有脚本行为应保留；目前没有新 R8 编码命令。

本轮文档按约定上传 Git，实际结果源表、码流和大体积日志保留本地。
