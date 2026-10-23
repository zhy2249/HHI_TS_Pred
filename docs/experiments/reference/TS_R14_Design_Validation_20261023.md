# R14 设计阶段检查记录

日期：2026-10-23；当前规格：`R14-NF-168-v2`；学习转移：`transition=single-step`。

## v2：逐级增减修订与已执行检查

用户要求权重不跨档跳变。当前版本保留21组实验的编号、参数组合、前向损失、全网格反馈目标与打平顺序，仅将所有动态组的学习提交限制为朝本次目标移动一个相邻档位。生产网格为0..K，所以每次提交仅能−1、0、+1。

NONE立即走一档；TARGET2在同目标两次确认后走一档；DIR2在同方向两次确认后走一档。每次实际移动都清空缓冲，下一档需要新证据。无资格事件冻结状态；有资格但当前已最优则清缓冲。TU初始化及CG/试编码回滚按正确快照恢复，不对这些恢复动作施加学习步长限制。

已在独立Python进程重新运行修订后的`ts_r14_design_reference.py`，并通过`py_compile`检查。实际输出如下：

```json
{
  "revision": "R14-NF-168-v2",
  "status": "pass",
  "checks": {
    "rational_table_entries": 512,
    "neighborhoods": 3125,
    "eligible_grid_winner_checks": 23552,
    "state_transition_checks": 288,
    "synthetic_feedback_events": 12000,
    "scaled_grid_steps": 9000,
    "explicit_boundary_cases": 10,
    "exhaustive_unit_step_checks": 354
  },
  "scope": "Pure mathematical/state reference only; no codec integration or video encoding",
  "transition": "one-adjacent-grid-level; production max abs(delta_r)=1",
  "seed": 20261023
}
```

新增检查包括：

- 对G2/G4各缓冲模式的合法状态、待确认值、反馈目标及无资格事件枚举354项，核对独立参考，并断言每次学习`abs(delta_r)<=1`。
- 无缓冲双向完整路径：0→1→2→3→4，及4→3→2→1→0。
- 两种确认模式从0朝固定目标4的有效反馈轨迹：0,1,1,2,2,3,3,4；反向同理。
- 每次确认只走一档并清空缓冲；下一档、反向移动都需要新的确认，不保留“已确认”标志连续推进。
- 当前2、依次目标3和4：TARGET2保持2等待4；DIR2第二次只到3，不到4。
- 无资格事件保留待确认信息；有资格中性事件清除信息，下一次不能冒充第二次确认。
- 全网格目标选择未改为相邻最优搜索。增加抽象候选反馈案例，明确目标更优不保证中间档位代价单调，测试不把单步参数限制误称为局部RD非劣。
- 9000步等比例表示测试中，K=4、合法档位{0,2,4}的一档指相邻合法值；这是G2的放大表示测试，不是生产五档G4。生产G4始终只能逐整数移动。

G2每步比例变化1/2，G4每步1/4；在持续相同目标的理想反馈流中，G4端到端移动需要更多有效事件。后续结果须同时解释档位分辨率和响应速度，不能将差异全部归因于分辨率。

复现当前v2：

```bash
python3 docs/experiments/reference/ts_r14_design_reference.py
python3 -m py_compile docs/experiments/reference/ts_r14_design_reference.py
```

以上命令不运行或调用编解码器。测试仍只覆盖数学评分与抽象状态规则，不证明真实量化钩子、Writer/Reader同步、码流或视频收益正确。生产编解码器未修改，视频实验未启动。

## v1 历史记录：直达目标规则，已被v2取代

以下保留上一版本的检查结果，不表示当前脚本仍执行v1规则。复现v1需读取历史文档提交`7085b667a8b2f449c28ece6014656fc7288e5b9d`，不得将其结果混入v2实验或复用其运行身份。

原规格：`R14-NF-168-v1`。实验组合为2套权重网格×3种缓冲×3种初态，共18组动态方法，另补3组静态比例对照。v1确认后直达目标，无逐级限制。

在独立Python进程运行当时的`ts_r14_design_reference.py`，实际输出：

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

历史检查内容：D/U两种表对c=1..256作精确有理数积分对照；五邻域0..4共3125种，n>=3的2944种分别核对G2/G4的3+5档赢家共23552次；288项原状态转移；12000次合成反馈；9000步放大网格等价；4个显式边界案例。它们仅是v1内部一致性证据。

## 两版共同的未验证范围

测试成本回调只定义0..9的已知syntaxCost值，未实现完整Rice coder。Python使用任意精度整数；生产C++仍须按设计验证64位范围、合法幅值和工具路径。

没有原生TS扫描、真实QuantRDOQ、Writer三遍缓存、Reader反映射、CG清零、帧间参考链或视频闭环验证。抽象回滚测试只验证状态规则，不证明实际钩子位置正确。

远端设计基线`6abe8fd11bd2f4c62f6ce9fb29545b809d023993`中，R13生产头文件读取返回404；已有实现文档不能代替当前工作树。Codex接入前应检查本地未提交实现，禁止覆盖或假定不存在。代码身份与文档SHA必须分开记录。

本次纯函数检查只说明实验规则内部自洽，不构成收益、复杂度或编解码同步验收。当前完整定义见[实验设计](../TS_Predictor_R14_Experiment_Design.md)。
