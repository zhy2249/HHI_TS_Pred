# R14 设计阶段检查记录

日期：2026-10-23；规格：`R14-NF-168-v1`。

本轮为用户准备下一组实验：2档权重网格×3种缓冲×3种初态，共18组动态方法，另补3组静态比例对照。详见[实验设计](../TS_Predictor_R14_Experiment_Design.md)。未实现编解码器、未启动编码或修改历史数据。

## 已执行的检查

在独立Python进程运行同目录`ts_r14_design_reference.py`，标准库实现，无视频、编码器或外部依赖。输出：

```json
{
  "revision": "R14-NF-168-v1",
  "status": "pass",
  "checks": {
    "rational_table_entries": 512,
    "neighborhoods": 3125,
    "eligible_grid_winner_checks": 23552,
    "state_transition_checks": 288,
    "synthetic_feedback_events": 12000,
    "scaled_grid_steps": 9000,
    "explicit_boundary_cases": 4
  },
  "scope": "Pure mathematical/state reference only; no codec integration or video encoding",
  "seed": 20261023
}
```

- D/U两种表对c=1..256作精确有理数积分对照，含大成本尾部。
- 五邻域0..4全枚举共3125种；n>=3共有2944种，分别核对G2/G4的3+5档赢家，共23552次。
- 288个转移检查包括无资格冻结、有效中性清缓冲、确认切换、目标变化和方向变化。
- 12000个确定种子的合成反馈事件检查目标选择、边界和抽象CG状态回滚。
- 9000步检查G2与等比例放大网格K=4、r={0,2,4}的完整状态等价，不将它与五档G4混淆。
- 4个显式案例覆盖R13两端点、第三候选反例、缓冲时钟、同方向不同目标的两种确认规则。

复现：

```bash
python3 docs/experiments/reference/ts_r14_design_reference.py
```

该命令只打印自测结果，不运行或调用任何编解码器。

## 未验证范围

测试成本回调只定义0..9的已知syntaxCost值，未实现完整Rice coder。Python使用任意精度整数；生产C++仍须按设计验证64位范围、合法幅值和工具路径。

没有原生TS扫描、真实QuantRDOQ、Writer三遍缓存、Reader反映射、CG清零、帧间参考链或视频闭环验证。抽象回滚测试只验证状态规则，不证明实际钩子位置正确。

远端设计基线`6abe8fd11bd2f4c62f6ce9fb29545b809d023993`中，R13生产头文件读取返回404；已有实现文档不能代替当前工作树。Codex接入前应检查本地未提交实现，禁止覆盖或假定不存在。代码身份与文档SHA必须分开记录。

本次纯函数检查只说明实验规则内部自洽，不构成收益、复杂度或编解码同步验收。
