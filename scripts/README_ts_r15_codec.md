# R15 闭环编码准备

从仓库根目录运行。算法和编号见 [实现文档](../docs/experiments/TS_Predictor_R15_Codec_Implementation.md)。本文件给出用户后续运行命令；助手本次没有启动视频编码。

## 构建与开启

直接编辑 `source/Lib/CommonLib/TypeDef.h`：master=1，`JVET_BJUT_TS_R15_MODE=1..18`；其它算法默认宏=0，`R15_STATS=0`，`R15_ANALYSIS=0`。不传实验参数时使用宏。保持 R15_MODE=0 也可以通过批量 `--fixed-predictors` 覆盖；它会给编码器和解码器传同一 runtime。

```bash
cmake -S . -B build/ts-r15-codec -DCMAKE_BUILD_TYPE=Release -DNX2_TOPLEVEL_OUTPUT_DIRS=OFF -DNX2_ENABLE_LINK_TIME_OPT=OFF
cmake --build build/ts-r15-codec --target EncoderApp DecoderApp -j2
```

CMake 只负责构建，不选择实验。Linux/GCC 11、C++17、Python >=3.10 为本地验证环境；工作簿写入复用现有 openpyxl 依赖。无需引入新第三方库。

## 本地库测试，无视频输入

```bash
cmake --build build/ts-r15-codec --target TsR15NativeTest TsR13NativeTest -j2
python3 scripts/test_ts_r15_native.py --build-dir build/ts-r15-codec --output-dir runs/r15_codec_checks
PYTHONPATH=scripts python3 -m unittest test_ts_r15_defaults test_ts_r15_batch
```

测试只调用局部编解码库，不调用 EncoderApp；顺序执行，至多三个 1 MiB 哈希缓冲。若保留了旧构建，可以增加 `--legacy-build-dir build/ts-r14`；若另外构建了 master 关闭的测试程序，可以增加 `--master-off-build-dir build/ts-r15-master-off`。这两个检查未提供相应构建时不会冒充已执行。

## 运行现有批量脚本

先 dry-run，以下一次计划三组、共 84 个 CE/QP 任务。输入目录自行设置；该命令不运行 Current anchor：

```bash
python3 scripts/batch_test.py --preset LBeu --class C,E --qps 22,27,32,37 \
  --fixed-predictors r15_g_eq_k2,r15_g_eq_k3,r15_g_sp_k3 \
  --encoder build/ts-r15-codec/bin/EncoderApp --decoder build/ts-r15-codec/bin/DecoderApp \
  --input-dir /path/to/videos --jobs 4 --decode-md5 --no-recon \
  --xlsm-report --xlsm-template scripts/JVET-hhi.xlsm \
  --out-dir runs/r15_codec_LB_CE_half --dry-run --allow-missing-input
```

正式运行删除 `--dry-run --allow-missing-input`。短测额外给 `--frames 8`，并使用单独目录；正式 LB 使用配置中半帧数，不加 `--full-sequence`。同一命令再次运行会核验身份并跳过已完成任务。程序、配置、观察开关或版本变化会使旧标记失效。

多个方法共用原有任务池，有空位即可启动下一组任务；各组完成时分别复制并写入工作簿。`--no-recon` 同时作用于编码与 MD5 解码，未生成重建视频。需要自定义组合只改 `--fixed-predictors`，不要分成多个串行脚本。

结果默认位于 `runs/.../r15_<编号>_<名称>/`。外部结果按原有 `experiments/ts_predictor_r15/NN_name/` 收件；别把固定 q 条件费用 CSV 当作正式编码统计。正式 BD-rate 仍逐分量计算后按 `(6Y+U+V)/8` 加权，Current 为基线。

观察只需显式 `TS_R15_STATS=1`；公平时间比较保持默认 0。旧 R13/R14 统计、审计和 shadow 环境变量应关闭，不能混用；发现不支持的旧观察组合会报错。
