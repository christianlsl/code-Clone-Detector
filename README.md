# Code Clone Detector (基于 UniXcoder 的 JS 代码克隆检测工具)

本项目是一款针对 JavaScript 源码的克隆检测工具。它利用 **UniXcoder** 模型提取代码语义特征，并结合 **DBSCAN** 对文件向量进行无监督聚类，自动发现相似代码簇。

## 核心特性

- **结构化拆分**：使用 Tree-sitter 对 JavaScript 代码进行解析，自动拆分为顶层代码块（函数声明、类、变量定义等）。
- **语义嵌入**：集成 UniXcoder 模型，通过 `<encoder-only>` 模式为每个代码块生成高维语义向量。
- **批量递归检测**：支持递归扫描指定目录下的所有 `.js` 文件。
- **DBSCAN 聚类**：基于余弦距离对文件级 embedding 自动聚类，无需预设聚类数量。
- **可调聚类粒度**：通过相似度阈值与 `dbscan_min_samples` 控制聚类松紧和最小簇规模。
- **模型本地化**：支持自动下载并保存 UniXcoder 模型到本地，后续运行无需联网，极速加载。
- **结构化输出**：处理过程详细记录于日志文件，最终比对结果以 JSON 格式保存，方便集成和二次分析。

## 环境要求

- Python >= 3.12
- 依赖项：`torch`, `transformers`, `tree-sitter`, `tree-sitter-javascript`, `pyyaml` 等（详见 `pyproject.toml`）。

推荐使用 [uv](https://github.com/astral-sh/uv) 管理环境。

## 配置说明 (`config.yaml`)

修改项目根目录下的 `config.yaml` 来调整模型和输出相关的运行参数：

```yaml
model_name: microsoft/unixcoder-base # 模型名 (Hugging Face)
model_local_path: models/unixcoder-base # 模型本地保存/加载路径
max_length: 512                      # Token 最大长度
similarity_threshold: 0.9            # 相似度阈值 (0-1)，内部转换为 DBSCAN eps=1-threshold
dbscan_min_samples: 2                # DBSCAN 最小样本数
log_path: logs/process.log           # 日志输出路径
output_path: output/results.json     # 结果 JSON 保存路径
```

## 快速开始

1. **安装依赖**：
   ```bash
   uv sync
   ```
   + 初次使用如遇网络问题，建议使用 mirror 源
    在 `.venv/lib/python3.12/site-packages/huggingface_hub` 中找到 `constants.py`
    ```python
    # 将原来的默认网址修改为镜像网址
    # _HF_DEFAULT_ENDPOINT = "https://huggingface.co"
    _HF_DEFAULT_ENDPOINT = "https://hf-mirror.com"
    ```

2. **命令行运行检测**：

   该工具提供两种运行模式，默认为 **模式 0**（项目批量检测模式）。

   **模式 0：项目批量检测（默认模式）**
   适用于包含多个子项目的根目录。程序会根据预定义的目录结构自动识别每个项目中的 `PAGE` 和 `SERVICE` 文件并分别进行分析：
   ```bash
   uv run python main.py [你的项目根目录路径]
   //等同于uv run python main.py [你的项目根目录路径] --mode 0
   ```
   例如：
   ```bash
   uv run python main.py dataset/projects --mode 0
   ```

   **模式 1：单目录递归检测**
   适用于普通的 JS 代码文件夹，会对该目录及其子目录下所有 `.js` 文件进行统一分析：
   ```bash
   uv run python main.py [你的代码目录路径] --mode 1
   ```
   例如：
   ```bash
   uv run python main.py dataset/crcn --mode 1
   ```

3. **作为 Python 库调用**：
   你可以直接在代码中导入并使用相应的模式函数：
   ```python
   from main import run_mode_1, run_mode_0

   # 运行单目录检测
   results = run_mode_1("dataset/crcn")

   # 运行项目批量检测
   run_mode_0("dataset/projects")
   ```

## 运行模式说明

### 模式 0：项目批量检测
该模式专门为具有特定结构的低代码项目设计。它会扫描输入目录下的每个子文件夹（代表一个项目），并提取其中的 `PAGE` 和 `SERVICE` 脚本进行独立分析。

- **目录结构要求**：
    每个项目文件夹必须包含 `modules` 子目录。
    ```text
    {root_path}/
    ├── {project_A}/
    │   └── modules/
    │       ├── {module1}/
    │       │   └── general_work/
    │       │       ├── PAGE/
    │       │       │   └── script/
    │       │       │       └── *.js
    │       │       └── SERVICE/
    │       │           └── **/*.js
    ...
    ```
- **分类逻辑**：
    - `PAGE` 脚本：位于 `modules/*/general_work/PAGE/script/*.js`
    - `SERVICE` 脚本：位于 `modules/*/general_work/SERVICE/**/*.js`
- **输出**：为每个项目生成一个单独的 JSON 结果文件，例如 `output/project_A_results.json`，其中包含 `PAGE_results` 和 `SERVICE_results`。

### 模式 1：单目录递归检测
这是传统的文件夹扫描模式。
- **逻辑**：递归扫描指定目录下的所有 `.js` 文件，不进行 `PAGE` 或 `SERVICE` 的分类，将所有文件作为一个整体进行克隆检测。
- **输出**：生成一个全局结果文件，路径由 `config.yaml` 中的 `output_path` 指定。

## 输出结果说明

### 日志 (`logs/process.log`)
记录了程序的运行状态、设备信息、模型加载情况以及详细的文件处理进度。

### 结果文件 (`output/*.json`)

#### 模式 1 的输出结果
包含以下结构的详细数据：
- `config`: 运行时使用的配置快照。
- `results`: 聚类结果列表。

#### 模式 0 的输出结果 (`{project_name}_results.json`)
- `config`: 运行时使用的配置快照。
- `PAGE_results`: 该项目中 `PAGE` 类型脚本的聚类结果。
- `SERVICE_results`: 该项目中 `SERVICE` 类型脚本的聚类结果。

每个聚类结果项包含：
- `cluster_id`: 聚类编号，`-1` 表示噪声点。
- `cluster_type`: `cluster` 或 `noise`。
- `size`: 该簇内文件数量。
- `files`: 文件路径列表。

## 项目结构

```text
.
├── src/
│   ├── tokenizer.py    # 代码分块、命名提取与 Embedding 生成
│   ├── calculate.py    # 相似度计算核心逻辑
│   └── unixcoder.py    # UniXcoder 模型封装类
├── main.py             # 程序主入口与批量处理接口
├── config.yaml         # 配置文件
└── pyproject.toml      # 项目配置与依赖管理
```