# R14 v3 结果收件目录

本目录仅接收 `R14-NF-168-v3` 的 15 个活动模式。编号为公开 `JVET_BJUT_TS_R14_MODE` 值，
不是内部 policy=99+MODE。旧 v1/v2、TARGET2/DIR2 不映射到当前模式；旧 done 标记不得用于 v3。
本地生产接入及非视频局部验收已完成；没有 R14 视频编码结果，详见
[实施记录](../../docs/experiments/TS_Predictor_R14_Implementation.md)。

正式 anchor 为 Current；R13-1/2 是已有固定比例机制对照，不重新编码 Current。
R14-19 是固定近组评分，**不等价于 Current**；保留全五邻居候选及 n 定义。
阶段 B 指后续实验阶段，仍测试 CE，并非 Class B。

| MODE | runtime | K | 更新 | r0 | s0 | 阶段 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | `r14_g2_none_equal` | 2 | NONE | 2 | — | A |
| 4 | `r14_g4_none_equal` | 4 | NONE | 4 | — | A |
| 7 | `r14_g2_none_half` | 2 | NONE | 1 | — | B |
| 10 | `r14_g4_none_half` | 4 | NONE | 2 | — | B |
| 13 | `r14_g2_none_zero` | 2 | NONE | 0 | — | B |
| 16 | `r14_g4_none_zero` | 4 | NONE | 0 | — | B |
| 19 | `r14_fixed_near_only` | 2 | fixed | 0 | — | A |
| 20 | `r14_fixed_quarter` | 4 | fixed | 1 | — | A |
| 21 | `r14_fixed_threequarter` | 4 | fixed | 3 | — | A |
| 22 | `r14_g2_pair2_equal` | 2 | PAIR2 | 2 | 5 | A |
| 23 | `r14_g4_pair2_equal` | 4 | PAIR2 | 4 | 9 | A |
| 24 | `r14_g2_pair2_half` | 2 | PAIR2 | 1 | 2 | B |
| 25 | `r14_g4_pair2_half` | 4 | PAIR2 | 2 | 4 | B |
| 26 | `r14_g2_pair2_zero` | 2 | PAIR2 | 0 | 0 | B |
| 27 | `r14_g4_pair2_zero` | 4 | PAIR2 | 0 | 0 | B |

## 批量与续跑

复用 `scripts/batch_test.py`，薄入口 `scripts/run_ts_r14_lb_ce.sh`：
默认阶段 A 入队顺序 **19,1,22,20,21,4,23**，196 点。
显式 `--phase B` 规划 7,10,13,16,24,25,26,27，共 224 点；
`--phase all` 共 420 点，仅在阶段 A 证据支持后再运行 B。
脚本使用一个共享池，每组完成即单独写工作簿，无组间完成屏障。
保留 decode hash，不输出重建视频；原始 anchor 工作簿只作模板，写入输出副本。

LBeu 的原 INI 帧数已经是半帧：BasketballDrill 250、BQMall 300、PartyScene 250、
RaceHorsesC 150、FourPeople/Johnny/KristenAndSara 各 300。QP=22/27/32/37。
不再次除 2，不加 `--full-sequence`。每模式 28 点。
预期二进制位于 `build/ts-r14/bin/EncoderApp` 和 `DecoderApp`，支持路径覆盖。
本地已通过局部验收；服务器建议先做冻结短测/hash，再启动正式编码。以下只检查任务规划：

```bash
bash scripts/run_ts_r14_lb_ce.sh --dry-run --allow-missing-input
bash scripts/run_ts_r14_lb_ce.sh --phase B --dry-run --allow-missing-input
```

实际运行及续跑均复用同一命令和输出根目录，去掉 `--dry-run --allow-missing-input`，
并指定实际 `--input-dir`、`--jobs`。不要用 `--overwrite` 做普通续跑。
默认输出 `runs/ts_r14_nf168_v3_LB_CE_half/r14_<MODE>_<name>/`。
服务器回传时将各组结果放到同名收件目录的 `LB_CE/`，保留模式和来源文件对应关系。

## 身份与观察

优先直接设置 TypeDef.h 总开关及 R14_MODE；直接运行程序无需额外实验参数。
通用 batch 未输入 `--fixed-predictors` 时探测并使用宏默认，
薄入口为一次多实验运行而显式设置 runtime；用户提供的 `--fixed-predictors` 可覆盖入口默认名单。

R14 统计默认关闭：`TS_R14_STATS=0`、`TS_R14_TRACE=0`；
有界 detail limit 默认 64，POC 默认未设置（全部），显式 0 则仅 POC 0。
薄入口关闭旧实验观察；统计只用于 R14。统计和 trace 请求均参与续跑指纹。
计时实验关闭观察，并独立控制并发，不能把共享池墙钟时间视为算法复杂度。

每点 `.identity.json` 记录预期 v3 协议、K/grid、NONE/PAIR2/fixed、r0/完整 s0、
168 尺度、反馈 tie、targetActive、运行命令、实际请求帧数、QP、程序/config SHA 和输入 path/size/mtime。
输入视频默认不计算完整内容 SHA；源码 checkout/补丁快照**不等于已验证二进制编译来源**。
`.done.json` 仅在编码、模式/版本身份、帧数及所请求解码 hash 成功后生成；
其中 result 是实际完成状态。输入、程序、配置、参数或观察变化会使成功标记失效。

每组模板 `run_metadata.template.json` 只包含冻结定义，实际来源字段保留 null。
回传时复制填写 source commit/patch、程序 SHA、配置及输入身份、实际命令与帧数、
hash 结果；不要把模板视为运行证明。原始视频、码流、重建及大日志不自动上传。

设计与约束见 [实验设计](../../docs/experiments/TS_Predictor_R14_Experiment_Design.md)
及 [工程计划](../../docs/experiments/TS_Predictor_R14_Engineering_Plan.md)。
