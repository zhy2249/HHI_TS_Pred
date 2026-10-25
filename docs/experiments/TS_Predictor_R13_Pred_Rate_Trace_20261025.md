# Johnny QP32 POC16：2.762482 bit 的逐 predictor 核对

日期：2026-10-25。范围仅为已定位的一次 TS 搜索候选；EQ 指 R13-1 等权，SP 指 R13-2 空间加权。
正式基线仍为 Current。本记录不新增序列 BD-rate。

**结论：确实由 predictor 不同引起，且全 TU 只有 scan31 的 p 和 remapping 不同。**
该系数直接增加2.184661865234 bit，随后两个系数由于 CABAC 概率状态传播增加0.577819824219 bit，
合计精确复现2.762481689453 bit。不存在平局，也没有系数值或失真变化。

## 定位与取证方式

目标为 POC16、CTU36、Y `(856,384)` 的 `8×32` TS 候选，实际 CU QP33。
此前完整搜索记录中，EQ/SP 的 `currCompFracBits` 分别为 1891403/1981924，差值
`90521 / 32768 = 2.762481689453125 bit`。两边失真均为79095，absSum均为15。
该 TS 候选最终被丢弃，不能从最终码流解码出其临时系数。

因此只重新执行已有 EQ 17帧前缀，在实际 `residual_coding_coef` 调用前复制 CABAC context，
调用后获取该函数的真实 fractional-bit 增量，再以同一份 q 和同一入口 Ctx 分别重放 Current、EQ、SP。
各分支独立更新 context 与 regular-bin budget，整个 TU 内连续编码各 CG，不在 CG 边界重置概率。
原系数和真实编码状态均不修改。

定点过滤同时核对几何、POC、CU QP，以及原日志中的：

| 标识 | 值 |
|---|---:|
| 输入残差 hash | 6133638857810301496 |
| 像素预测 hash | 8384959809021157691 |
| quant 入口 context 公开字段 hash | 5773553372657782758 |
| 最终量化系数 hash | 1454644526469312942 |

Context hash 是既有日志公开字段的指纹，不宣称等于完整状态序列化；本次重放通过原生 Ctx 拷贝构造复制
TS 实际使用的 CABAC 概率状态，并显式继承 Rice 参数与 regular-bin budget。

## Predictor 的产生过程

因果幅值邻域依次为 `H=[L,U,D,LL,UU]`，其中 D 为左上，LL/UU 为左二/上二；边界不可用位置置0。
`n` 计数非零位置，重复幅值仍各自贡献支持。

- Current=`max(L,U)`。
- EQ 的物理位置权重为 `[1,1,1,1,1]`；SP 为 `[2,2,1,1,1]`。
- `n<3` 直接 Current，不进行候选评分。
- `n>=3` 候选依次为 Current 的等价值、NoPred、剩余历史幅值升序。`p<=1` 合并成 identity `p=0`，重复值去重。
  只接受严格更小的 score，平局保留前面的候选。
- 评分为 `sum(weight*loss168)`，是 KeepHit 代理分数，**不是 CABAC fractional bits**。

实际 remapping 对 `a=|q|` 为：a=0 时为0；a=p>0 时为1；0<a<p 时为a+1；其它情况为a。
`p=0/1` 都等价于 identity。只有实际 regular 路径中的非零幅值会改变相应 level syntax；
对零系数、未编码的全零 CG 计算出的 predictor 仅作观察，不能计为真正的幅值语法变化。

## 逐系数与逐 bin 结果

捕获 TU 有256个系数、14个非零、absSum15。全部256个位置中，EQ/SP只有 **scan31** 的 predictor 不同：

| 属性 | 实测值 |
|---|---|
| CG / scan / raster（均从0计数） | 1 / 31 / 59 |
| TU 内坐标 / 全图坐标 | (3,7) / (859,391) |
| 当前 q / magnitude | +1 / 1 |
| H=[L,U,D,LL,UU] | [0,2,1,0,1] |
| 非零支持 n | 3：U、D、UU |
| Current | max(0,2)=2 |
| 有序候选 | [2,0]；历史幅值1与identity等价，不新增候选 |

这个位置的逐样本 KeepHit 评分如下。零邻居不参与评分；SP只将非零的 U 加倍。

| 支持位置 | 幅值 | EQ权重 | SP权重 | p=0 的单样本 loss168 | p=2 的单样本 loss168 |
|---|---:|---:|---:|---:|---:|
| U | 2 | 1 | 2 | 504 | 168 |
| D | 1 | 1 | 1 | 168 | 488 |
| UU | 1 | 1 | 1 | 168 | 488 |

这里 `C(1)=1, C(2)=3`。p=0 直接取 `168*C(a)`；p=2 对幅值2是hit，得168；
对幅值1是near-up，得 `168*3−4*(3−1)^2=488`。

| 分支 | score(p=0) | score(p=2) | 实际选中 | 对 a=1 的实际 remap |
|---|---:|---:|---:|---:|
| Current | 不评分 | 不评分 | 2 | 2 |
| EQ | 504+168+168=**840** | 168+488+488=1144 | **0** | **1** |
| SP | 2×504+168+168=1344 | 2×168+488+488=**1312** | **2** | **2** |

因此，空间权重把一个幅值2的直接上邻居计成两份支持，翻转了原先两个幅值1对identity的优势。
SP选择p=2只有32个KeepHit整数单位的优势；**这是严格胜出，不是Current平局优先造成的**。
作为评分机制核对，若仅按未平滑的整数syntaxCost计算，该支持下SP两候选均为8；
KeepHit对near-up的每份16单位折扣，使p=2最终严格领先32。这里的32或8都不是实际CABAC bit。
若删除该折扣，旧整数评分的平局仍会保留候选顺序在前的Current=p2；因此不能据此推断仅移除near-up折扣便可修复此点。

该系数使gt1从0变成1，同时多编码parity=0与gt2=0。随后scan35、39仍使用p=1，q和remap也均为1，
但它们共享的gt1 context（id1320）已被scan31的不同bin更新，编码同一个0也变贵。

| CG / scan | syntax变化 | EQ cost frac | SP cost frac | SP−EQ frac | SP−EQ bit |
|---|---|---:|---:|---:|---:|
| 1 / 31 | gt1：0→1，入口context相同 | 11611 | 72060 | 60449 | +1.844757080078 |
| 1 / 31 | SP新增 parity=0 | 0 | 7542 | 7542 | +0.230163574219 |
| 1 / 31 | SP新增 gt2=0 | 0 | 3596 | 3596 | +0.109741210938 |
| 2 / 35 | gt1均为0，context不同 | 10560 | 23189 | 12629 | +0.385406494141 |
| 2 / 39 | gt1均为0，context不同 | 9759 | 16064 | 6305 | +0.192413330078 |
| 合计 | 只有以上5个事件有cost差额 | | | **90521** | **+2.762481689453** |

其中直接差额71587/32768=2.184661865234 bit，后续context传播18934/32768=0.577819824219 bit。
本 TU 没有 Rice remainder 或 bypass 事件；significance、sign、CG flag 均无差额。
额外两个regular bin让CG1结束预算从EQ400变成SP398，TU结束为354/352；预算始终充足，
三遍扫描的边界完全相同，没有转入不同bypass路径。不能笼统说“budget也相同”。

| 同 q / 同入口的 TSRC 分支 | fractional units | estimated bits |
|---|---:|---:|
| Current（反事实，非独立anchor编码） | 1788834 | 54.590881347656 |
| EQ（与真实estimator精确相等） | 1652118 | 50.418640136719 |
| SP（仅替换predictor） | 1742639 | 53.181121826172 |

旧日志中的整个transform trial累计rate，比此处TSRC函数单独rate分别多239285个fractional units：
`1891403−1652118 = 1981924−1742639 = 239285`。
因此本次逐bin分解与原先2.762482 bit是同一个差额，统计范围虽不同，差值没有变化。

所有非零系数及全部有评分位置见[逐项表](results/r13_pred_detail_20261025/trace_tables.md)；
[全部256个系数](results/r13_pred_detail_20261025/coefficient_process.csv)、
[逐候选逐邻居贡献](results/r13_pred_detail_20261025/candidate_process.csv)、
[5个差异bin及状态](results/r13_pred_detail_20261025/changed_bins.csv)同时保留。
scan35/39分别位于(860,386)/(861,386)，这里的后续指TS扫描顺序，不是简单像素行序。

这次定位到的是一个局部反例：空间加权以很小的代理评分优势选中了会增大实际TSRC代价的p=2，
并通过CABAC context影响后续系数。它解释该次搜索代价扰动，不证明所有空间加权选择都错误，
也不单凭此点增加新threshold或修改正式算法。

## 复现接口与记录文件

观察接口默认关闭；环境变量 `TS_R13_PRED_DETAIL=/path/to/prefix` 指定输出前缀。
当前过滤器特意固定到上面的单个候选，不是通用逐系数日志开关。

```bash
cmake --build build/ts-r14 --target EncoderApp -j 6
python3 scripts/ts_r13_search_replay.py \
  --done runs/r13_diagnosis_20261024/diag_followup/johnny_q32_f17_r13_keep_hit_uniform/r13_1_keep_hit_uniform/LBeu_Johnny/LBeu_Johnny_QP32.done.json \
  --encoder build/ts-r14/bin/EncoderApp \
  --decoder runs/r13_followup_20261024/bin/DecoderApp_verified \
  --output runs/r13_pred_detail_repeat --poc 16 --ctu 36 --pred-detail
python3 scripts/ts_r13_pred_detail_analysis.py runs/r13_pred_detail_repeat/detail \
  --output-dir runs/r13_pred_detail_repeat/analysis
```

运行包装复用既有成功 marker 的配置、输入和帧数，禁用其它 TS 观察，不输出重建视频。
结束时检查全部码流 byte-exact、逐帧 bits/hex PSNR/MD5 一致，以及独立解码17帧MD5。
目标必须只出现一次，且 SP−EQ 必须恰好90521 fractional units，否则不标为成功。

源码：`CommonLib/TsR13PredDetail.h` 记录完整三遍 TS 语法，每个 CG 与既有 `replayRateCG` 的 rate、
pass、budget、context 公开概率字段再次交叉核对；实际 EQ 分支总 rate 必须等于原生 estimator。
`EncoderLib/InterSearch.cpp` 仅添加定点入口与观察调用。
分析脚本独立复算 H、权重、候选顺序、逐样本评分、平局、pred/remap，并检查 coefficient/CG/TU/bin 的 rate 守恒。

## 本次验证

- EncoderApp构建通过；新观察头文件在总实验宏开/关时均通过独立编译。
- 36个合成TU（Current/EQ/SP各12个）覆盖稀疏、密集、不同Rice和预算耗尽情况，
  重放与native estimator精确相等，q、真实context及其bit累计均未改变。
- 4项Python分析测试通过；真实捕获进一步通过邻域、候选、分数、remap和全部rate守恒检查。
- 单次实际17帧EQ短测，最终码流与此前关闭本观察的EQ码流byte-exact，全部17帧bits/hex PSNR/MD5相同，
  独立Decoder校验17帧MD5全部通过。目标只捕获一次。没有新增SP编码或完整300帧编码。
- 本地`runs/r13_pred_detail_20261025/complete.json`保存命令、源码/二进制/输入指纹和验证状态；
  小体积副本见[验证记录](results/r13_pred_detail_20261025/run_validation.json)。
  首次启动曾发生在链接结束之前，被系统拒绝、未开始编码；保留于`runs/r13_pred_detail_20261025_launch_incomplete/`，
  成功证据只使用链接完成后的本次运行。

本记录解释的是固定 q 的 predictor-side TSRC 估计码率差；不能据此把整条300帧BD-rate损失全部归因于该系数。
