# Code Clone Detector (基于 UniXcoder 的 JS 代码克隆检测工具)

本项目是一款针对 JavaScript 源码的克隆检测工具。它利用 **UniXcoder** 模型提取代码语义特征，并结合 **Tree-sitter** 进行精确的代码结构分析，支持文件级和函数级的相似度比对。

## 核心特性

- **结构化拆分**：使用 Tree-sitter 对 JavaScript 代码进行解析，自动拆分为顶层代码块（函数声明、类、变量定义等）。
- **语义嵌入**：集成 UniXcoder 模型，通过 `<encoder-only>` 模式为每个代码块生成高维语义向量。
- **自动命名提取**：自动提取函数名、类名及变量名，并在结果中清晰展示。
- **批量递归检测**：支持递归扫描指定目录下的所有 `.js` 文件，进行两两比对。
- **双重阈值过滤**：
    - **整体相似度**：过滤出高度疑似克隆的文件对。
    - **函数相似度**：在相似文件中进一步比对并过滤出相似的函数片段。
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
similarity_threshold: 0.9            # 相似度阈值 (0-1)
log_path: logs/process.log           # 日志输出路径
output_path: output/results.json     # 结果 JSON 保存路径
```

## 快速开始

1. **安装依赖**：
   ```bash
   uv sync
   ```
   + 初次使用如遇网络问题，建议使用mirror源
    `.venv/lib/python3.12/site-packages/huggingface_hub`中找到`constants.py`
    ```python
    # 将原来的默认网址修改为镜像网址
    # _HF_DEFAULT_ENDPOINT = "https://huggingface.co"
    _HF_DEFAULT_ENDPOINT = "https://hf-mirror.com"
    ```

2. **命令行运行检测**：
   ```bash
   uv run python main.py [你的JS代码目录路径]
   ```
   例如：
   ```bash
   uv run python main.py dataset/crcn
   ```

3. **作为 Python 库调用**：
   你可以直接在代码中导入并使用该工具：
   ```python
   from main import run_clone_detection

   # 运行检测并将结果保存到 config.yaml 中定义的路径
   results = run_clone_detection("dataset/crcn")

   # 遍历结果
   for pair in results:
       print(f"文件 A: {pair['file_a']} <-> 文件 B: {pair['file_b']}")
       print(f"相似度: {pair['total_similarity']:.4f}")
   ```

## 输出结果说明

### 日志 (`logs/process.log`)
记录了程序的运行状态、设备信息、模型加载情况、文件扫描进度以及发现的相似对摘要。

### 结果文件 (`output/results.json`)
包含以下结构的详细数据：
- `config`: 运行时使用的配置快照。
- `results`: 相似文件对列表，每个项包含：
    - `file_a` / `file_b`: 文件路径。
    - `total_similarity`: 文件整体余弦相似度。
    - `function_similarities`: 相似度超过阈值的函数对列表（包含名称、相似度及源代码）。

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
