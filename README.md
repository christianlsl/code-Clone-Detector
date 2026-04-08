# JS 代码克隆检测器

基于 SAGA 的 JavaScript 代码克隆检测工具。

## 1. 功能说明

- 从 `config.yaml` 读取 `data_path`、`output_path`、`log_path`
- 支持通过命令行参数覆盖配置（包含 `-i/--input`）
- 运行 SAGA：`java -jar thirdparty/saga/SAGACloneDetector.jar {data_path}`
- 自动清理 SAGA 历史输出目录：`result`、`tokenData`、`logs`
- 解析 SAGA 结果并输出 JSON

## 2. 目录结构

```text
.
├── main.py
├── config.yaml
├── src/
│   ├── config.py
│   ├── logger_setup.py
│   ├── saga_runner.py
│   ├── result_parser.py
│   └── pipeline.py
└── thirdparty/saga/
    └── SAGACloneDetector.jar
```

## 3. 配置文件

`config.yaml` 示例：

```yaml
data_path: ./testcases
output_path: ./output
log_path: ./logs
```

`data_path` 下每个子目录视为一个项目，目录名建议为 `{num}.{project_name}`，例如：

```text
testcases/
├── 01.datahub/
├── 02.sdm_df/
└── 2.inf_cent/
```

## 4. 运行方式

### 4.1 基础运行

```bash
python3 main.py
```

### 4.2 指定输入路径（新增）

```bash
python3 main.py -i /path/to/js_projects
```

说明：`-i/--input` 会覆盖 `config.yaml` 里的 `data_path`。

### 4.3 常用组合

```bash
python3 main.py -c config.yaml -i ./testcases -o ./output/result.json -l INFO
```

### 4.4 参数列表

| 参数                | 含义                                            |
| ------------------- | ----------------------------------------------- |
| `-c`, `--config`    | 配置文件路径，默认 `config.yaml`                |
| `-i`, `--input`     | 输入目录（JS 项目根目录），覆盖 `data_path`     |
| `-o`, `--output`    | 输出 JSON 文件路径，覆盖 `output_path` 默认文件 |
| `-l`, `--log-level` | 日志级别：`DEBUG/INFO/WARNING/ERROR`            |

## 5. 输出结果格式

输出文件默认位于：`output/clone_detection_result.json`

```json
[
  {
    "func_paths": {
      "01.datahub/modules/split/ngModel.js": [
        [120, 160],
        [300, 340]
      ],
      "02.sdm_df/messageFormatParser.js": [[80, 110]]
    },
    "relevent_projects": ["datahub", "sdm_df"],
    "pair_similarity": [
      {
        "index_pair": [10, 25],
        "similarity": 0.9354839
      }
    ]
  }
]
```

说明：

- `func_paths` 现在按“文件路径 -> 函数区间列表”存储，避免同一文件多个函数被覆盖。
- `relevent_projects` 按 `{num}.{project_name}` 提取项目名（仅保留 `project_name`）。

## 6. 执行流程

1. 读取配置和命令行参数
2. 清理 `thirdparty/saga` 下旧的 `result`、`tokenData`、`logs`
3. 调用 SAGA 分析 `data_path`
4. 解析：
   - `type123_method_group_result.csv`
   - `MeasureIndex.csv`
   - `type123_method_pair_result.csv`
5. 写出 JSON 结果

## 7. 依赖

- Python >= 3.12
- Java 运行环境
- `pyyaml`

安装依赖：

```bash
pip install pyyaml
```

## 8. 常见问题

### 8.1 找不到 SAGA JAR

确认文件存在：

```bash
ls thirdparty/saga/SAGACloneDetector.jar
```

### 8.2 没有输出结果

- 检查 `data_path` 是否存在 JS 文件
- 检查日志目录中的日志文件
- 用 `-l DEBUG` 运行查看详细日志

### 8.3 Java 不可用

确认 Java 已安装：

```bash
java -version
```

**Key Class**: `Config`

- Loads configuration from YAML file
- Provides properties for data_path, output_path, log_path

### logger_setup.py

Sets up logging with both console and file handlers.

**Key Function**: `setup_logger()`

- Configures logging with specified level
- Creates log files in the specified directory

### saga_runner.py

Manages SAGA program execution and cleanup.

**Key Class**: `SAGARunner`

- Verifies SAGA JAR exists
- Cleans previous output directories
- Executes SAGA with error handling
- 1-hour timeout to prevent infinite runs

### result_parser.py

Parses SAGA output files and generates JSON results.

**Key Class**: `ResultParser`

- Loads MeasureIndex.csv (function locations)
- Loads pair similarity scores
- Groups related clones
- Extracts project names from paths
- Generates structured JSON output

### pipeline.py

Orchestrates the entire clone detection process.

**Key Class**: `CloneDetectionPipeline`

- Coordinates all pipeline steps
- Provides clean error handling and logging
- Returns success/failure status

## Error Handling

- Configuration file validation
- SAGA JAR existence verification
- Result file existence checking
- Graceful handling of malformed data
- Detailed error logging

## Dependencies

- **Python**: >= 3.12
- **PyYAML**: >= 6.0 (for YAML parsing)
- **Java**: Required for running SAGA
- **SAGA**: SAGACloneDetector.jar in `thirdparty/saga/`

## Requirements

The system requires:

1. Java Runtime Environment (JRE) for SAGA execution
2. `SAGACloneDetector.jar` in the `thirdparty/saga/` directory
3. Write permissions for output and log directories

## Examples

### Example 1: Basic Clone Detection

Detect clones in JavaScript files using default configuration:

```bash
python3 main.py
```

Results will be saved to `./output/clone_detection_result.json` (as specified in config.yaml).

### Example 2: Scan Multiple Project Directories

Process different JavaScript projects:

```bash
# Scan project A
python3 main.py -i ./projects/project_a -o result_a.json

# Scan project B
python3 main.py -i ./projects/project_b -o result_b.json
```

### Example 3: Debug Mode

Run with detailed logging:

```bash
python3 main.py -l DEBUG
```

Logs will be saved to `./logs/clone_detector.log` (as specified in config.yaml).

### Example 4: Custom Configuration

Use alternative configuration file:

```bash
python3 main.py -c config_production.yaml
```

### Example 5: Parse Results Programmatically

```python
import json

with open('output/clone_detection_result.json') as f:
    results = json.load(f)

for i, group in enumerate(results):
    print(f"Clone Group {i+1}:")
    print(f"  Files: {len(group['func_paths'])}")
    print(f"  Projects: {group['relevent_projects']}")
    for file_path, lines in group['func_paths'].items():
        print(f"    {file_path}: lines {lines[0]}-{lines[1]}")
```

## Output Analysis

### JSON Structure

Each clone group in the output contains:

- **func_paths**: Dictionary mapping relative file paths to [start_line, end_line] pairs
- **relevent_projects**: List of project names where clones are found
- **pair_similarity**: List of similarity scores between function pairs

### Example Output

```json
{
  "func_paths": {
    "project_a/utils.js": [10, 25],
    "project_b/helpers.js": [5, 20]
  },
  "relevent_projects": ["project_a", "project_b"],
  "pair_similarity": [
    {
      "index_pair": [0, 1],
      "similarity": 0.9354839
    }
  ]
}
```

## Troubleshooting

### Issue: "SAGACloneDetector.jar not found"

**Solution**: Ensure the JAR file exists at `thirdparty/saga/SAGACloneDetector.jar`

```bash
ls -la thirdparty/saga/SAGACloneDetector.jar
```

### Issue: "No module named src"

**Solution**: Run the program from the project root directory

```bash
cd /path/to/code-Clone-Detector
python3 main.py
```

### Issue: Java command not found

**Solution**: Install Java Runtime Environment (JRE)

```bash
# macOS
brew install openjdk

# Ubuntu/Debian
sudo apt-get install default-jre

# Verify installation
java -version
```

### Issue: Permission denied for log/output directories

**Solution**: Ensure write permissions

```bash
chmod -R 755 ./logs ./output
```

### Issue: Output file not created

**Solution**: Check error logs

```bash
cat logs/clone_detector.log
```

Run with debug logging for more details:

```bash
python3 main.py -l DEBUG 2>&1 | tee debug_output.log
```

## Environment

### Tested On

- Python 3.12+
- macOS 10.15+
- Ubuntu 20.04+
- Windows 10+ (with Python and Java installed)

### Directory Structure Validation

The program expects the following structure:

```
code-Clone-Detector/
├── main.py
├── config.yaml
├── src/
│   ├── __init__.py
│   ├── config.py
│   ├── logger_setup.py
│   ├── saga_runner.py
│   ├── result_parser.py
│   └── pipeline.py
├── thirdparty/
│   └── saga/
│       └── SAGACloneDetector.jar
└── testcases/
    ├── 01.project_name/
    │   └── *.js
    └── 02.another_project/
        └── *.js
```

## Performance Considerations

- **Large datasets**: SAGA execution time depends on the number and size of files
- **Memory**: Java heap size can be adjusted by modifying SAGA execution parameters
- **Timeouts**: The pipeline has a 1-hour timeout for SAGA execution
- **Storage**: Ensure sufficient disk space for SAGA intermediate files and output

## Contributing

When modifying the code:

1. Maintain low coupling and high cohesion principles
2. Add docstrings to all functions and classes
3. Use type hints for better code clarity
4. Test changes before committing
5. Update documentation as needed
