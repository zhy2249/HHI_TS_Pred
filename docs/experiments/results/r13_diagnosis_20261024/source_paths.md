# R13诊断：已启用的Y→UV传播路径与stage解释

范围：只读当前源码、LBeu实际命令配置和上传服务器日志。以下区分“配置启用/源码允许”与“某帧/块实际获选”；工具开关本身不能证明其造成了损失。没有追加编码任务。

## 配置核对

- 本地probe5的done.json实际命令使用 `scripts/HHI测试cfg/LBeu/cfg/encoder_lowdelay_nx2High.cfg`，并已核验Current/R13-2前5帧逐项复现服务器bits、hex PSNR与MD5。
- 上传 `experiments/ts_predictor_r13/Johnny_32_R13_2:7` 显示 SAO=1、CCSAO=1、ALF=1、AlfImprovements=1、CCALF=1、ALFCCCM=1、BIF=1、ChromaBIF=1、NNLF=0；第8行 LMChroma=1、CCCM=1、DualITree=1、JointCbCr=1、Reshape=1(SDR,CSoffset=1)。
- 对应LBeu cfg行73–76为LMCSEnable=1、LMCSOffset=1、SignalType=0、UpdateCtrl=2；88–99含CCSAO=2/SAO=1/ALF=1/ALFCCCM=1/CCALF=1；123 DualITree=1、143 CCCM=1、168 LMChroma=1。
- **CCSAO配置2、TOOL显示1不是冲突**：`source/App/EncoderApp/EncAppCfg.cpp:5725`将非零CCSAO打印为布尔1。真实process仍接收整数mode，见`source/Lib/EncoderLib/EncGOP.cpp:3945`。
- **ALFCCCM就是LFCCCM**：`source/App/EncoderApp/EncAppCfg.cpp:1605`映射到`m_lfCccm`，`source/Lib/EncoderLib/EncLib.cpp:1860`设置SPS的`m_lfCccmEnabledFlag`。

## 源码机制表

| 通道 | 本轮状态及必要门控 | Y如何影响UV | 准确源码位置 | 预期首次可见stage |
|---|---|---|---|---|
| LMCS chroma residual scaling | 配置开启；还需slice LMCS flag、picture chromaScale flag及块条件 | 已重建左/上luma均值决定chromaScale，进而改变UV residual缩放、RDOQ lambda与逆缩放 | `CommonLib/Reshape.cpp:98`，其中`:122`读reco Y、`:160`求scale；`EncoderLib/IntraSearch.cpp:1073`门控，`:1096`求scale，`:3872`调lambda，`:3916`逆缩放；inter为`EncoderLib/InterSearch.cpp:7557`、`:7284` | `before_dbf` |
| CCLM / CCCM intra prediction | LMChroma/CCCM配置开启，具体CU仍要RDO选择；也用于B帧中的intra CU | CCLM直接取已重建Y；CCCM从Y及邻域建立/应用跨分量模型，改变UV预测、残差与模式决策 | `EncoderLib/IntraSearch.cpp:1919`建立CCLM luma refs，`:2004`CCCM开关、`:2022`refs；`CommonLib/IntraPrediction.cpp:5275`读取reco luma，`:7594`CCCM refs、`:7646`读取reco Y | `before_dbf` |
| 共享CU/RD/参考帧反馈 | I/B编码本身的闭环；不是额外一个滤波开关 | Y量化/重建/比特变化可改变后续选择；之后帧会使用已变化的参考图像。没有最终UV TS也不排除UV搜索路径变化 | `EncoderLib/EncGOP.cpp:3713`完整slice编码结束；stage观测在其后 | `before_dbf`，但POC0没有前帧反馈 |
| CCSAO | 配置开启；每分量/CTU仍由RDO选择 | chroma分类显式使用Y/U/V band或cross-component edge；Y变化可改变分类、参数训练和最终UV offset | `EncoderLib/EncSampleAdaptiveOffset.cpp:102`读取srcY并形成chroma class；`:2054`RDO+apply；`EncGOP.cpp:3877`保存DBF后的共同分类源、`:3945`CCSAO调用、`:3956`联合clip | `after_ccsao_clip`；与SAO/BIF共享clip，不能把raw→clipped SSE全算成CCSAO收益/损失 |
| ALF / CCALF | ALF1、AlfImprovements1、CCALF1；CCALF另需luma ALF获选及QP门控 | CCALF明确从Y邻域差值形成UV校正；参数训练也可能全帧传播变化。当前stage将普通ALF和CCALF合并观测 | `EncoderLib/EncAdaptiveLoopFilterEcm.cpp:807`CCALF gate，`:818`分别derive Cb/Cr，`:829`apply；`CommonLib/AdaptiveLoopFilterEcm.cpp:1941`chroma filter、`:1959`读Y、`:2007`起Y差值加权；`EncGOP.cpp:4011`ALFProcess，`:4034`stage | `after_alf`；不能仅凭该stage锁定CCALF |
| LFCCCM（配置名ALFCCCM） | 配置开启，但**只对非I帧进入RDO**；之后slice/CTU可关闭 | post-SAO的Y/U/V训练模型并形成chroma correction；先以修正target辅助ALF训练，再把correction加回UV | `EncGOP.cpp:3981`非I门控、`:3986`RDO、`:3998`修正ALF target、`:4101`把Cb/Cr correction加回；`CommonLib/LoopFilterCccm.cpp:562`读取Y/U/V；`EncoderLib/EncLoopFilterCccm.cpp:326`RDO关闭 | 加回动作在`after_lfcccm`；但若启用，它在`after_alf`之前已改变ALF训练target，所以其间接作用可能更早体现 |
| NNLF | TOOL CFG为0 | 本轮不参与 | `EncGOP.cpp:3881`一带运行门控 | 不应出现有效`after_nnlf`活动 |

表中CommonLib/EncoderLib路径均以`source/Lib/`为前缀。

LMCS model初始分析是基于内容，不是直接拿TS coefficient更新模型；这里明确存在的通道是重建Y→邻域scale。`EncGOP.cpp:2366`将slice和picture开关写入；`EncoderLib/EncReshape.cpp:482`会启用chroma adjustment，`:562`特定大图条件可关闭。不要把SPS开启当作所有块必然缩放。

## QP37的额外条件

`source/Lib/EncoderLib/EncCfg.h:1086`默认`CCALFQpTh=37`，配置未覆盖。`source/Lib/EncoderLib/EncAdaptiveLoopFilterEcm.cpp:4385`使用名义QP判断是否开启限制；`:4386`在名义QP>=37且sliceQP<=名义QP+1时关闭该分量CCALF。QP32即使B帧sliceQP达到39/41也不受这个门控；QP37的初始I帧按IntraQPOffset=-1应为36，满足限制。QP37没有上传逐帧日志，后续哪些帧实际开关只能视为源码条件，不能说已经测得。

## stage读数的正确判别方式

hook顺序来自 `source/Lib/EncoderLib/EncGOP.cpp`：inverse LMCS(`:3753`) → before_dbf(`:3869`) → after_dbf(`:3873`) → after_sao_bif(`:3938`) → after_ccsao_clip(`:3958`) → after_alf(`:4034`) → after_lfcccm(`:4112`) → final_clip(`:4121`)。

| 跨轨迹首次UV hash不同的位置 | 能支持的判断 | 尚不能断言 |
|---|---|---|
| `before_dbf` | 差异已在重建/搜索中出现；可检查LMCS scale、CCLM/CCCM、共享RD及后续帧参考传播 | 不能直接认定色度TS或某一种预测模式有错 |
| `after_dbf` | deblocking阶段新增/扩大差异，检查边界/模式/残差决定 | 不证明滤波器实现错误 |
| `after_sao_bif` | SAO/BIF及其RDO产生新增变化 | 此buffer标记clip_pending=1，raw SSE不能当最终合法范围PSNR |
| `after_ccsao_clip` | CCSAO+联合clip阶段新增变化；若之前UV hash一致而Y不同，支持cross-component传播 | 尚需区分CCSAO分类/参数与clip贡献 |
| `after_alf` | ALF家族阶段新增变化 | 不能区分普通ALF、CCALF、以及非I帧LFCCCM修正target的间接影响 |
| `after_lfcccm` | 加回LFCCCM correction阶段新增变化 | 不含已经在ALF训练阶段发生的LFCCCM间接影响 |
| 后续帧`before_dbf`差异逐渐扩大 | 与参考帧反馈相容 | 不能只据时序证明某一工具为根因 |

应优先比较reconstruction_hash，而不只比较SSE；不同重建可能恰好拥有相同SSE。原始hash相同且尺寸一致才可把SSE差当作同一目标的差异。跨stage的变化与跨算法的变化分开，不把本来应降低误差的滤波收益当作算法损失。

**POC0已知为I帧**，所以LFCCCM和跨帧参考反馈都不能解释首次POC0 U差异；若新stage显示before_dbf的UV也完全相同，则可进一步把初始责任范围收缩到后处理，而无需立即扩大实验集合。目前未按未完成stage数据预先定责。
