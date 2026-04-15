# JS 代码克隆检测器

基于 SAGA 的 JavaScript 代码克隆检测工具。程序会调用 SAGA 扫描输入目录，解析克隆结果，并进一步做 Type-1 分组和可选的 LLM 总结。

## 功能概览

- 读取 [config.yaml](config.yaml) 中的 `data_path`、`output_path`、`log_path`、`llm.provider`
- 运行前自动清理 SAGA 历史产物目录（`result`、`tokenData`、`logs`）
- 解析 SAGA 输出为结构化 JSON 克隆结果
- 对每个克隆组构建 Type-1 子组（去除注释与空白差异）
- 计算 Type-1 子组之间的相似度（两两比较）
- 可选调用 LLM 生成 Type-1 组摘要和组间差异摘要

## 环境要求

- Python 3.12+
- Java 8+
- 可执行的 SAGA JAR 文件：`thirdparty/saga/SAGACloneDetector.jar`

## 快速开始

1. 安装依赖

```bash
uv sync
```

2. 准备配置文件（默认已提供）

```yaml
data_path: ./testcases
output_path: ./output
log_path: ./logs
llm:
  provider: env
```

3. saga配置

   + 选择系统对应saga脚本

     在`thirdparty/saga/executable`中选取与运行操作系统对应的脚本，填入`thirdparty/saga/config.properties`中`exe`字段

   + properties

     + **threshold**

       + 0.65
         1. 部分代码段前后顺序颠倒
         2. 核心功能相似，但>=3个参数/调用服务类型/数据处理逻辑/状态校验等不同（e.g. 记录详细日志&记录错误日志）

       + 0.7 
         1. 除了空字符，几乎完全一致的函数
            1. 内嵌调用
            2. 部分通用型&专业型脚本函数（e.g. 获取0-30天后需要提醒的邮件列表&获取30天后需要提醒的邮件列表 ；多一些额外的处理逻辑，如解析判断每个接收者前面包含USER前缀）
            3. 功能相似，但<=2个参数/服务类型不同（e.g. 获取模型名称&获取流程名称；中间一个调用的api不同，但基本的处理逻辑一致）

4. 运行

```bash
python main.py
```

运行成功后，默认会生成：

- `output/clone_detection_result.json`
- `output/clone_detection_unprocess_result.json`（仅在启用 LLM 摘要时写入）

## 数据目录约定

`data_path` 下每个一级子目录视为一个独立项目，建议命名为 `{num}.{project_name}`，例如：

```text
testcases/
├── 01.datahub/
├── 02.sdm_df/
└── 2.inf_cent/
```

输出字段 `relevent_projects` 会从目录名前缀中提取项目名：

- `01.datahub` -> `datahub`
- `02.sdm_df` -> `sdm_df`
- `2.inf_cent` -> `inf_cent`

## 命令行参数

当前入口 [main.py](main.py) 支持以下参数：

| 参数             | 说明                     |
| ---------------- | ------------------------ |
| `-i`, `--input`  | 覆盖配置中的 `data_path` |
| `-o`, `--output` | 覆盖默认输出文件路径     |
| `--no-summary`   | 跳过 LLM 摘要阶段        |

示例：

```bash
python main.py -i ./testcases -o ./output/result.json --no-summary
```

## LLM 配置

通过 [config.yaml](config.yaml) 的 `llm.provider` 切换后端：

- `env`：OpenAI 兼容接口
- `hw`：华为接口（Qwen3）

### provider=env

需要在 `.env` 中配置：

- `LLM_MODEL_ID`
- `LLM_API_KEY`
- `LLM_BASE_URL`
- `LLM_TIMEOUT`（可选，默认 60 秒）

### provider=hw

需要在 `.env` 中配置：

- `HW_AUTH_TOKEN`

说明：当前华为客户端使用固定模型 `Qwen3-32B`。

## 执行流程

1. 加载配置并解析命令行参数
2. 调用 SAGA 前清理旧输出目录
3. 执行 SAGA 克隆检测
4. 解析 `type123_method_group_result.csv` 与 `MeasureIndex.csv`
5. 组装 `func_group`，并提取函数源码
6. 构建 `type1_group`（按去注释、去空白后的代码归并）
7. 计算 `type1_group_similarity`
8. 可选调用 LLM：
   - 生成每个 Type-1 组的 `group_name` 和 `functionality`
   - 生成组间 `summary`
9. 保存最终 JSON 结果

## 输出结构

主输出文件默认是 `output/clone_detection_result.json`。

```json
[
  {
    "func_group": [
      {
        "file_path": "01.datahub/modules/split/ngModel.js",
        "start_line": 396,
        "end_line": 401,
        "code": "...",
        "function_name": ["$setPristine"]
      }
    ],
    "relevent_projects": ["datahub"],
    "type1_group": [
      {
        "group_name": "...",
        "functionality": "...",
        "functions": [
          {
            "file_path": "01.datahub/modules/split/ngModel.js",
            "start_line": 396,
            "end_line": 401,
            "code": "...",
            "function_name": ["$setPristine"]
          }
        ]
      }
    ],
    "type1_group_similarity": [
      {
        "group_a_index": 0,
        "group_b_index": 1,
        "similarity": 0.8731
      }
    ],
    "summary": {
      "group_name": "...",
      "overall_functionality": "...",
      "type1_group_differences": "...",
      "reuse_opportunities": "..."
    }
  }
]
```

字段说明：

- `func_group`：一个克隆组中的函数片段列表
- `function_name`：基于正则从代码片段中提取的函数名（可能有多个）
- `relevent_projects`：该克隆组涉及的项目名集合
- `type1_group`：同一 `func_group` 内按 Type-1 规则聚类后的子组
- `type1_group_similarity`：Type-1 子组两两相似度（`SequenceMatcher`）
- `summary`：LLM 生成的组间摘要；若关闭或失败则可能为 `null`

## 关键模块

- [main.py](main.py)：命令行入口，负责参数解析、日志初始化、启动流水线
- [src/pipeline.py](src/pipeline.py)：总流程编排（SAGA -> 解析 -> 分组 -> 相似度 -> LLM -> 保存）
- [src/saga_runner.py](src/saga_runner.py)：清理旧结果并执行 SAGA
- [src/result_parser.py](src/result_parser.py)：解析 SAGA 结果并提取源码
- [src/llm_client.py](src/llm_client.py)：封装 LLM 调用（`env` / `hw`）

## 常见问题

1. 提示找不到 SAGA JAR

- 检查 `thirdparty/saga/SAGACloneDetector.jar` 是否存在。

2. LLM 摘要没有生成

- 检查 `.env` 变量是否齐全。
- 可先运行 `python main.py --no-summary` 验证纯检测流程。

3. 输出为空或很少

- 检查 `data_path` 是否正确。
- 检查输入目录中是否包含可被 SAGA 识别的源码文件。

## 备注

- 每次运行都会删除 `thirdparty/saga/result`、`thirdparty/saga/tokenData`、`thirdparty/saga/logs` 旧数据。
- 程序默认使用 `INFO` 级别日志输出。
