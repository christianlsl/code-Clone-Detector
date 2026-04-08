# JS 代码克隆检测器

基于 SAGA 的 JavaScript 代码克隆检测工具。程序读取配置和命令行参数，调用 SAGA 对输入目录中的 JS 项目进行分析，然后解析 SAGA 输出并生成 JSON 结果。

## 功能

- 从 `config.yaml` 读取 `data_path`、`output_path`、`log_path`
- 支持通过 `-i/--input` 覆盖 `data_path`
- 调用 SAGA 执行克隆检测
- 每次运行前自动清理 `thirdparty/saga/result`、`thirdparty/saga/tokenData` 和 `thirdparty/saga/logs`
- 将 SAGA 结果解析为结构化 JSON
- 支持同一文件中的多个函数克隆结果

## 目录结构

```text
.
├── main.py
├── config.yaml
├── README.md
├── pyproject.toml
├── src/
│   ├── __init__.py
│   ├── config.py
│   ├── logger_setup.py
│   ├── saga_runner.py
│   ├── result_parser.py
│   └── pipeline.py
└── thirdparty/
    └── saga/
        ├── SAGACloneDetector.jar
        ├── result/
        ├── tokenData/
        └── logs/
```

## 配置文件

`config.yaml` 默认内容如下：

```yaml
data_path: ./testcases
output_path: ./output
log_path: ./logs
```

### data_path 组织方式

`data_path` 目录下的每个子目录都视为一个独立项目。推荐使用如下命名方式：`{num}.{project_name}`。

```text
testcases/
├── 01.datahub/
├── 02.sdm_df/
└── 2.inf_cent/
```

其中，输出结果中的 `relevent_projects` 会从目录名中提取 `project_name`，例如：

- `01.datahub` -> `datahub`
- `02.sdm_df` -> `sdm_df`
- `2.inf_cent` -> `inf_cent`

## 安装

### 依赖

- Python 3.12+
- JDK 1.8 or higher 
- `pyyaml`

### 安装 Python 依赖

```bash
pip install pyyaml
```

如果使用虚拟环境，建议先激活后再安装依赖。

## 运行方式

### 选择系统对应saga脚本

在`thirdparty/saga/executable`中选取与运行操作系统对应的脚本，填入`thirdparty/saga/config.properties`中`exe`字段

### 基础运行

```bash
python3 main.py
```

### 指定输入路径

```bash
python3 main.py -i /path/to/js_projects
```

`-i/--input` 会覆盖 `config.yaml` 中的 `data_path`。

### 指定输出文件

```bash
python3 main.py -o ./output/result.json
```

### 指定日志级别

```bash
python3 main.py -l DEBUG
```

支持的日志级别：`DEBUG`、`INFO`、`WARNING`、`ERROR`

### 常用组合

```bash
python3 main.py -c config.yaml -i ./testcases -o ./output/result.json -l INFO
```

## 命令行参数

| 参数                | 说明                                         |
| ------------------- | -------------------------------------------- |
| `-c`, `--config`    | 配置文件路径，默认 `config.yaml`             |
| `-i`, `--input`     | 输入 JS 项目根目录，覆盖配置中的 `data_path` |
| `-o`, `--output`    | 输出 JSON 文件路径，覆盖默认输出             |
| `-l`, `--log-level` | 日志级别                                     |

## 执行流程

1. 读取配置文件和命令行参数
2. 使用 SAGA 前清理旧输出目录
3. 调用 SAGA 分析 `data_path`
4. 解析 SAGA 输出文件：
   - `type123_method_group_result.csv`
   - `MeasureIndex.csv`
   - `type123_method_pair_result.csv`
5. 生成 JSON 文件并写入输出目录

## 输出结果格式

默认输出文件为 `output/clone_detection_result.json`。

```json
[
  {
    "func_group": [
      {
        "file_path": "01.datahub/modules/split/ngModel.js",
        "start_line": 120,
        "end_line": 160,
        "code": "function foo() { ... }"
      },
      {
        "file_path": "01.datahub/modules/split/ngModel.js",
        "start_line": 300,
        "end_line": 340,
        "code": "function bar() { ... }"
      }
    ],
    "relevent_projects": ["datahub", "sdm_df"],
    "pair_similarity": [
      {
        "index_pair": [
          "01.datahub/modules/split/ngModel.js_120_160",
          "02.sdm_df/messageFormatParser.js_80_110"
        ],
        "similarity": 0.9354839
      }
    ]
  }
]
```

### 字段说明

- `func_group`：一个克隆组中的函数列表。
- `file_path`：相对 `data_path` 的文件路径。
- `start_line` / `end_line`：函数在源文件中的起止行号。
- `code`：根据 `start_line` 和 `end_line` 从对应文件中提取的源码片段。
- `relevent_projects`：克隆组涉及的项目名列表。
- `pair_similarity`：该组内函数两两之间的相似度信息。
- `index_pair`：使用 `file_path_startLine_endLine` 组成的稳定标识，便于直接定位具体函数。

## 项目模块

### `src/config.py`

负责读取 `config.yaml` 并暴露 `data_path`、`output_path` 和 `log_path`。

### `src/logger_setup.py`

负责配置控制台和文件日志。

### `src/saga_runner.py`

负责清理旧输出并调用 SAGA 执行分析。

### `src/result_parser.py`

负责解析 SAGA 输出文件，生成最终 JSON。

### `src/pipeline.py`

负责编排整体流程：配置读取、SAGA 执行、结果解析与保存。

## 注意事项

- 运行前请确认 `thirdparty/saga/SAGACloneDetector.jar` 存在
- 运行目录建议为项目根目录
- 如果结果不符合预期，可使用 `-l DEBUG` 查看详细日志
- 每次运行会清理 SAGA 旧结果，请确保不需要保留历史输出

## 示例

```bash
python3 main.py -i ./testcases -o ./output/clone_detection_result.json
```

运行后会在输出目录生成 JSON 结果，并在日志目录写入运行日志。
