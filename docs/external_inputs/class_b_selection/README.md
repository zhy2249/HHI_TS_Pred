# Class B序列选择：派生数据

报告：[ClassB_Test_Selection_Analysis.md](../ClassB_Test_Selection_Analysis.md)。

本目录同步小体积派生结果；完整逐点输入、PCHIP脚本、留一/删方法族检查和全部相关表随本次会话的 `ClassB_Selection_and_Correlation.zip` 提供，未重复上传全部旧点或大体积文件。本目录单独不是完整复算环境，报告中的复现命令在完整包目录内执行。

- `ClassB_Observed_Profiles.csv`：CE为四点曲线；B各列与B_3pt为统一QP27/32/37纯实测诊断，不能作为完整B/BCE。
- `B_four_point_measured.csv`：仅完整实测四点曲线；空白为缺失，不是0。B_full只有五序列都完整才计算。
- `selected_correlations.csv`：全8、去除固定方法6、再去除R3-2共5版本的探索性相关与删一敏感性。
- `audit.json`：来源与数值检查边界。

结论：当前B目标平均≤−0.04%，少数候选先测Cactus/BQTerrace/MarketPlace，而非只测容易获益序列。相关性只能给优先级线索，不能为R12填补未测B。BQTerrace的R10-3 QP22缺点应优先补齐。

本次未修改codec、正式台账或旧实验计划，未启动视频编码，也未认证真实运行身份或速度。
