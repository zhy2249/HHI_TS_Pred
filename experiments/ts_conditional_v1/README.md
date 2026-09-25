# Conditional TS predictor revision 1 — external result inbox

| 实验 | 模式名 | LB 结果目录 | RA 结果目录 |
|---|---|---|---|
| N1 | q32 | q32/LB_BCE | q32/RA_CD |
| N2 | conf2 | conf2/LB_BCE | conf2/RA_CD |
| A1 | prev | prev/LB_BCE | prev/RA_CD |
| A2 | ewma | ewma/LB_BCE | ewma/RA_CD |
| A3 | q32_ewma | q32_ewma/LB_BCE | q32_ewma/RA_CD |

每个目录放 `JVET-hhi.xlsm` + `run_metadata.json`，尽量附 `logs/`。
尚未编码时只有 README，不放空白表格，避免被误认为已完成实验。
LB 每组 BCE 12 序列 × 4 QP =48 点，CTC 半帧；RA CD 8 序列 × 4 QP =32 点。
半帧不自动推广到 RA；RA 必须与 anchor 实际帧数及配置一致。
保持原 Reference；Test 中标签为 `<sequence>.Q<qp>.ecm.lb` 或 `.ecm.ra`。
后续读取脚本可根据目录名区分模式，无需从表格文件名猜测。

完整规则及直接编解码方法见仓库根目录 `TS_Conditional_Predictor_Implementation.md`。
这里仅约定结果结构，不提供批量运行脚本，不包含任何已测 BD-rate。
