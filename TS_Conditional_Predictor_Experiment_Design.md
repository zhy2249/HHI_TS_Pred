# 条件启用 directional：首轮实验设计

日期：2026-09-16。以下保留早期三组设计用于追溯。
后续用户要求同时比较无历史和历史自适应，当前已实现的五组 N1/N2/A1/A2/A3
以 `TS_Conditional_Predictor_Implementation.md` 为准；本文 G3=q32_conf2 **未实现**，
不能与当前 A3=q32_ewma 混淆。CTC 尚未运行。

## 1. 目标与边界

固定 NoPred / directional 的 LB BCE 分别 −0.041705% / −0.035706%，未达到 −0.05%。
既有 nominal QP22/27 directional、QP32/37 anchor 的组合为 −0.070258%，
只是低 QP 条件方向的线索，不是下列新规则的收益预测。
本轮检验两个独立假设：较细量化时 directional 是否更适合；方向差异清楚时是否更适合。
只在 Current 与既有 directional 之间选择，不重写 directional，不加入 gradient 或 NoPred 三选一。

三套候选和固定 directional 构成 QP gate × confidence gate 的 2×2 对照。
固定 directional 已有数据，但复用必须核对版本/配置；Current 为共同 anchor。
无条件门控、QP 门控、置信门控、联合门控可分离两个条件的作用。

## 2. Decoder-known 定义

`source/Lib/DecoderLib/CABACReader.cpp` 的 `transform_unit_last` 中，
CU delta QP / chroma offset 在 residual coding 前处理；`cu.qp` 为实际 CU luma QP，
不是 nominal QP，也不是含 bit-depth offset 的 `QpParam::Qp(true)`。
`source/Lib/CommonLib/Quant.cpp` 显示后者包含 bit-depth offset，色度映射和 offset，
并有 TS minimum QP clamp；不能直接用同一个阈值比较这些不同量。

首轮统一定义 `Q = tu.cu->qp`，Y/Cb/Cr 共用此 luma-QP 门控。
这是有意控制变量，不声称能精确表示色度量化步长。与编码端 RDOQ 使用的 QP 是否一致须加断言验证，
特别是临时 QP override、DQP、dual tree、lossless 路径；不一致时先解决同步，不能默认忽略。
不从命令行 nominal QP、GOP QPoffset model 或输入配置反推门控。

沿用已有因果邻域：L/U 为左/上，D 为左上，LL/UU 为左二/上二的量化幅值。
`EH=|L−LL|+|U−D|`，`EV=|U−UU|+|L−D|`。
Current 为 `max(L,U)`；directional 在 EH<EV 时取 L、EV<EH 时取 U、平局取 max。
邻域不足 x<2 或 y<2 时保持 Current；计算使用宽整数。

## 3. 三套首轮规则

### G1：q32（仅 QP 门控）

当 `Q <= 32` 时使用原 directional，否则 Current。
门控在 component TU 进入时确定，不读取当前 TU 系数决定 QP 门控。
32 是预先选定的首轮实际 CU QP 截点，不是最优阈值，也不等价 nominal QP27。
已有例子 nominal QP27 的部分 B slice 可到 33/35，因此这是一套更保守、不同的实际工具。

### G2：conf2（仅方向置信度门控）

令 `emin=min(EH,EV)`、`emax=max(EH,EV)`。
仅当 `emax > 0 && emax >= 2*emin` 时使用原 directional，否则 Current。
其中 `emax>0` 排除全平局，2:1 为预先冻结的整数量级差条件。
这只意味着两个方向的一致性分数存在差距，不是经校准的预测正确概率。
emin=0、emax>0 时允许使用 directional；低幅值的偶然方向也可能通过，属于需要证伪的风险。
不额外叠加绝对幅值下限、非零密度阈值或经验特殊情况。

### G3：q32_conf2（联合门控）

仅当 `Q <= 32 && emax > 0 && emax >= 2*emin` 时使用 directional，否则 Current。
判断顺序先 QP、后邻域置信度；可避免 QP gate 关闭时读取额外邻居。
G3 是较保守的主候选，但不预设必胜：它可能过滤错误，也可能丢失有效切换。

所有规则在边界、BDPCM 原有 identity 路径、TSRC disabled 以及 native bypass 条件下保留原行为。
不限制 TU 尺寸，不人为只启用色度，不按序列名、分辨率或“RA/LB 配置名称”开关。
RA 和 LB 不是可直接作为规范条件使用的配置标签；本轮用同一规则测试两者。

## 4. 因果性与原始 CG 课题的区别

G1 的 TU 门控不使用系数；G2/G3 的系数位置门控只读当前 coefficient 之前已重建的因果邻居。
它们可能读取当前 CG 内已经解码的邻居，因此是**局部 predictor refinement**，
不是“仅利用历史 CG 选择当前整 CG mode”的原始实验。
不能用它们证明 CG persistence 或计算历史 selector 的 Oracle capture ratio。

Encoder/Decoder 必须在相同 coefficient 扫描位置读到相同最终量化邻居；
不能对尚未完成 remapping inverse 的临时符号取幅值。
RDOQ 的候选系数随搜索改变允许导致候选代价变化，但 writer/reader 必须一致；
之前 CG 如最终被 RD 清零，后续读取应看到零，不缓存清零前的置信度。
本轮不引入跨 TU 状态或对当前待编码系数 |q| 的判断。

## 5. 实现约束与验证计划

未来实现应在现有统一 predictor helper 中增加规则身份；CU QP 门控通过编码上下文传入，
不要让公共数学 helper 读取全局 encoder 配置。三条路径必须同时接入：
TS-RDOQ（包括候选 remapping/rate）、CABACWriter、CABACReader inverse remapping。
现有固定 predictor 宏和 CLI 覆盖语义保留；新名字需先实现，现有 batch 不接受这三个名字。
规则身份仍为实验版本双方约定，不新增逐 TU mode 信令；普通标准 decoder 不能直接解码启用的实验流。

验证：

- 宏 OFF 与 Current anchor bit-exact；门控恒关等于 Current、恒开等于既有 directional。
- Q=31/32/33、方向平局、2:1 边界、emin=0、零系数、邻域不足、矩形/小 TU 单元测试。
- 确认扫描邻居先完成解码；encoder/decoder trace 比较 gate、p、remapping 前后幅值。
- DQP、不同 bit depth、色度映射、BDPCM、lossless、TSRC off、非 TS 路径及 CG 清零 smoke。
- 明确 RDOQ 实际 QP 与门控用 CU QP 的关系，禁止未验证的临时 QP override 同步假设。

## 6. 实验与统计

实现后每个模式跑 LB BCE 半帧 QP22/27/32/37，另跑 RA CD 作回归检查。
每模式 48+32=80 任务，三个模式共 240 个任务；统一任务池、无重建 YUV，复用 batch 与 Excel 输出。
用户本地执行长跑；可先 smoke，再提交完整三组，不按短帧收益决定是否保留某序列。
anchor 复用须先核对外部编码版本、实际配置、输入和帧数；无法对齐时先修正实验条件。

主指标不变：分量 PCHIP BD-rate 后 6:1:1，LB BCE 12 序列等权。
输出 B/C/E/BCE、RA C/D/CD，Y/U/V，均值/中位数/分位数/leave-one-out 和序列 bootstrap。
做 G1 对固定 directional、G2 对固定 directional、G3 对 G1/G2 的配对比较，区分“有效筛选”与“更少启用导致回到 anchor”。

最终编码 TS TU 的在线聚合计数（非 coefficient 文本）：实际 Q、component、W×H、
可用邻域数、QP通过数、置信通过数、最终 predictor 真正不同于 Current 的次数。
进一步分开 `p_current != p_selected` 与 remapping 实际变化；只 gate=true 但 predictor 相同不能算有效切换。
这些统计仅解释选择后的 TS 样本，不作为全编码收益的无偏替代。
可按 nominal QP 标记实验任务、按实际 Q 汇总启用率，但 nominal QP 不参与 decoder 算法。

## 7. 预先冻结的取舍标准

- LB BCE <=−0.05% 才达到用户目标，<=−0.08% 为不错，<=−0.10% 为可观。
- RA CD 正值须明确报告为回归；本轮以 RA CD 均值不退化（<=0）作为通用规则的首轮保守筛选，
  不因退化小就事后宣布可接受，也不掩盖单序列大幅退化。
- 若 G3 不优于 G1，则置信门控没有增量证据；若 G2 不优于固定 directional，也不能宣称 confidence 有效。
- 若仅在少数内容改善、去掉 Cactus/PartyScene 后结论显著削弱，降低优先级。
- 不在本轮追加 q30/q34/q36、1.5:1/3:1、分量专用阈值寻找最好点。
  如果后续确需阈值实验，另立探索轮并预留独立验证集合。
- 所有 BCE 已用于提出门控方向，后续同集合结果仍有研究选择偏差；最终需独立内容或独立条件确认。

G3 为首要候选，G1/G2 为必要拆分对照。NoPred 保持已有固定对照；历史 CG selector 留待单独阶段，
不在这轮混入从而扩大候选和调参自由度。
