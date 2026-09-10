# 批量测试运行脚本规范

本目录用于沉淀项目正式批量测试脚本。`scripts_参考/` 仅作为历史参考目录；后续新增批量运行需求，默认复用 `batch_test.py` 的参数、任务清单和输出目录规范，不再把正式脚本放入 `scripts_参考/`。

## 编码与风格

- Python 脚本统一使用 Python 3，文件按 UTF-8 保存。
- 入口使用 `argparse`，路径处理使用 `pathlib.Path`。
- 文件读写显式使用 `encoding="utf-8"`；CSV 写入使用 `newline=""`。
- 外部命令使用 `subprocess.run([...], check=False)` 的列表参数形式，避免拼接 shell 字符串。
- 批量任务使用 `ThreadPoolExecutor` 控制外部进程并行数，默认 `--jobs 1`。

## 推荐入口

```bash
python3 scripts/batch_test.py --dry-run --allow-missing-input
python3 scripts/batch_test.py --preset RAeu --class D --qps 32 --dry-run --allow-missing-input
python3 scripts/batch_test.py --local-preset AI --sequences BasketballPass --qps 32 --frames 8 --dry-run
python3 scripts/batch_test.py --manifest scripts/batch_test_jobs.example.csv --dry-run
```

如果当前机器还没有测试 YUV，可以先加 `--allow-missing-input` 只检查批量规划：

```bash
python3 scripts/batch_test.py --manifest scripts/batch_test_jobs.example.csv --dry-run --allow-missing-input
```

实际运行前需要保证编码器/解码器可执行：

```bash
chmod +x bin/EncoderAppStatic bin/DecoderAppStatic
```

## 两种任务来源

1. 默认 HHI Config*.ini 模式：

不传普通模式参数时，脚本默认使用 `scripts/HHI测试cfg` 下的标准 CTC/HHI 配置，默认 preset 为 `AIeu`：

```bash
python3 scripts/batch_test.py --dry-run
python3 scripts/batch_test.py --preset AIeu --class C,E --dry-run
python3 scripts/batch_test.py --preset RAeu --class D --qps 32 --decode-md5
python3 scripts/batch_test.py --run AIeu:C --run LBeu:E --qps 32 --dry-run
```

HHI 模式默认路径：

```text
scripts/HHI测试cfg/AIeu/ConfigAI.ini
scripts/HHI测试cfg/RAeu/ConfigRA.ini
scripts/HHI测试cfg/LBeu/ConfigLB.ini
```

HHI 模式会读取 `Config*.ini` 中启用的序列、`#Class` 标记、`[Global] qps`、每个序列的 `cfg`、`framecount` 和 `segLen`。如果没有显式传 `--qps`，使用 ini 里的 `[Global] qps`；如果没有显式传 `--frames`，优先使用序列的 `framecount`，否则使用 `segLen`。

2. 普通自动展开模式：

```bash
python3 scripts/batch_test.py \
  --local-preset AI \
  --sequences BasketballPass,BQMall \
  --qps 22,27,32,37 \
  --frames 16 \
  --decode-md5 \
  --jobs 2
```

`--local-preset` 映射：

- `AI` -> `cfg/encoder_intra_nx2.cfg`
- `RA` -> `cfg/encoder_randomaccess_nx2.cfg`
- `LB` -> `cfg/encoder_lowdelay_nx2.cfg`
- `LDP` -> `cfg/encoder_lowdelay_P_nx2.cfg`
- 带 `_HIGH` 的 preset 对应 `*nx2High.cfg`

3. CSV 清单模式：

```bash
python3 scripts/batch_test.py --manifest scripts/batch_test_jobs.example.csv --jobs 2
```

CSV 字段规范：

- `enabled`: `1/0`，是否启用该行。
- `name`: 任务名，会作为输出子目录名的一部分。
- `cfgs`: 公共 cfg 列表，多个 cfg 用英文分号 `;` 分隔，传参顺序保持不变。
- `sequence_cfg`: 单序列 cfg，例如 `cfg/per-sequence/BasketballPass.cfg`。
- `input`: 输入视频路径；可填绝对路径、项目相对路径，或只填文件名让脚本在 `--input-dir` 下递归查找。
- `qps`: QP 列表，例如 `22,27,32,37`。
- `frames`: 可选，传给 EncoderApp 的 `-f`；留空则不覆盖 cfg。
- `extra_args`: 可选，覆盖默认 EncoderApp 附加参数。
- `decode_md5`: `1/0`，是否编码后解码校验。
- `decoder_args`: 可选，覆盖默认 DecoderApp 附加参数。
- `xlsm_tag`: 可选，写入 `JVET-hhi.xlsm` 时匹配 column A 的条件后缀，例如 `ai/ra/lb`。

## Excel 报表

如果 `scripts/JVET-hhi.xlsm` 存在，脚本会在实际运行结束后自动复制模板并回填 `Test` sheet，输出到批次目录：

```text
runs/batch_test/<run-id>/JVET-hhi.xlsm
```

也可以显式控制：

```bash
python3 scripts/batch_test.py --sequences BasketballPass --qps 32 --xlsm-report
python3 scripts/batch_test.py --sequences BasketballPass --qps 32 --no-xlsm-report
python3 scripts/batch_test.py --sequences BasketballPass --qps 32 --xlsm-template scripts/JVET-hhi.xlsm
```

HHI 模式会按 `--preset` 推导 `xlsm_tag`：`AIeu -> ai`，`RAeu -> ra`，`LBeu -> lb`。普通自动展开模式会按 `--local-preset` 推导 `xlsm_tag`：`AI -> ai`，`RA -> ra`，`LB/LDP -> lb`。CSV 清单模式建议显式填写 `xlsm_tag`。同一批次如果包含多个 tag，脚本会依次写入同一个 `JVET-hhi.xlsm`，由表格内部的不同行区分配置条件。

## 输出规范

默认输出根目录：

```text
runs/batch_test/YYYYMMDD_HHMMSS/
```

每个任务一个子目录：

```text
runs/batch_test/<run-id>/<task-name>/
  <task-name>_QP<qp>.bin
  <task-name>_QP<qp>.yuv
  <task-name>_QP<qp>.encode.log
  <task-name>_QP<qp>.decode.log
```

批次根目录生成统一汇总：

```text
runs/batch_test/<run-id>/summary.csv
```

`summary.csv` 至少包含任务名、cfg、输入、QP、输出码流、重建文件、编码/解码状态、返回码、耗时、PSNR、码率、日志路径和 `error_info`。

## 状态与退出码

- `0`: 全部任务成功或因已有输出被跳过。
- `2`: 参数、路径或任务规划错误。
- `3`: 至少一个编码或解码任务失败。
- `130`: 用户中断。

状态字段：

- `ok`: 成功。
- `skipped_exists`: 输出 bitstream 已存在且未指定 `--overwrite`。
- `failed`: 外部命令返回非 0 或 MD5/校验失败。
- `exception`: 脚本运行中出现未捕获到任务层的异常。

## 后续脚本约定

- 新实验优先写 CSV 清单，然后调用 `batch_test.py`。
- 如确需新增脚本，新脚本应只负责生成 manifest 或封装参数，不重新实现编码、解码、并行、日志和 summary 逻辑。
- 所有批量输出继续放在 `runs/batch_test/` 下，避免散落在项目根目录。
- 长任务先使用 `--dry-run` 检查任务数量、输入路径和 cfg 顺序。
