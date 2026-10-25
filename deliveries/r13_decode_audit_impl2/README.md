# R13 双来源审计：可下载交付副本

用户于2026-10-25例外授权上传R13码流。本目录保存真实Git文件，不是LFS指针；不改变全局.gitignore。
仅此固定交付：96条正式流（R13-1/2各48条）、2条既有17帧验证前缀、Linux解码器、脚本及构建/输入指纹。
不包含原始视频、重建、工作簿或运行日志。原件继续保留，本目录不作为新实验输出目录。

代码实现提交 `22e61aed7f5c00c57b47b7217cba663751ec12e9`。
Decoder SHA256 `54e66385447d7ecd513c0e676b3f47a1571d9eecd9678b116d1eb6d1d81f182b`。
源版本/编译器/动态库在build_info.json，每条流身份和SHA256在manifest.json，全部交付文件见SHA256SUMS。
Linux x86_64，最低SSE4.1；本机构建GCC11.4/glibc2.35；Python3.10+标准库。其它发行版/ABI未认证，可按源码构建DecoderApp。

仓库根目录执行（本目录也可单独复制到其它路径）：

```bash
cd deliveries/r13_decode_audit_impl2
sha256sum -c SHA256SUMS
python3 scripts/ts_decode_score_audit.py inspect --manifest manifest.json
python3 scripts/ts_decode_score_audit.py decode-pair --manifest manifest.json --pair Johnny_QP32_prefix17 --first-poc 0 --last-poc 16 --verify-off --output ../../runs/r13_remote_prefix
python3 scripts/ts_decode_score_audit.py batch --manifest manifest.json --pairs all --jobs 4 --first-poc 0 --last-poc 299 --verify-off --output ../../runs/r13_remote_all --dry-run
```

去掉--dry-run才开始正式解码；相同请求增加--resume续跑。all排除验证前缀；无EncoderApp、无YUV输出。
若单独复制本目录，--output改为你选择的新目录即可，不依赖开发机器绝对路径。

最新交付和远端下载验收见仓库：
[交付记录](../../docs/experiments/results/r13_dual_decoder_audit_impl2_20261025/remote_delivery.json)。
本目录docs/是生成便携包时的历史实现文档，关于“本地、未上传”的描述记录当时状态；最新发布状态以上述记录为准。

原始服务器编码配置/输入身份有未知项，manifest保留null；成功解码不能替代完整编码来源核验。
原生/七方法/单点/快照/输出需分别核验，固定q评分不是BD-rate。统计限制沿用impl2验收文档。
