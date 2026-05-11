import json
import logging
import os
import re
from typing import List, Dict, Any, Optional

import requests
from dotenv import load_dotenv

from .config import Config

logger = logging.getLogger(__name__)

# 加载 .env 文件中的环境变量
load_dotenv(override=True)

def clean_think_tag(raw: str) -> str:
    """Remove <think>...</think> tags from LLM output."""
    return re.sub(r'<think>.*?</think>', '', raw, flags=re.S)

class LLMClient:
    def __init__(
        self,
        config: Optional[Config] = None,
        model: str = None,
        apiKey: str = None,
        baseUrl: str = None,
        timeout: int = None,
        provider: str = None,
    ):
        self.provider = (
            provider
            or (config.llm_provider if config else None)
            or os.getenv("LLM_PROVIDER")
            or "env"
        ).lower()

        if self.provider not in {"env", "hw"}:
            raise ValueError("LLM provider must be either 'env' or 'hw'.")

        if self.provider == "hw":
            self.model = model or os.getenv("HW_MODEL_ID", "Qwen3-32B")
            self.api_key = apiKey or os.getenv("HW_AUTH_TOKEN")
            self.base_url = baseUrl or os.getenv(
                "HW_BASE_URL",
                "https://apigw.huawei.com/stream/mategpt/v3",
            )
            self.timeout = timeout or int(os.getenv("HW_TIMEOUT", 120))
            if not self.api_key:
                raise ValueError("HW_AUTH_TOKEN must be defined in the .env file.")
        else:
            self.model = model or os.getenv("LLM_MODEL_ID")
            self.api_key = apiKey or os.getenv("LLM_API_KEY")
            self.base_url = baseUrl or os.getenv("LLM_BASE_URL")
            self.timeout = timeout or int(os.getenv("LLM_TIMEOUT", 60))
            if not all([self.model, self.api_key, self.base_url]):
                raise ValueError(
                    "模型ID、API密钥和服务地址必须被提供或在.env文件中定义。"
                )

    def think(self, messages: List[Dict[str, str]], temperature: float = 0) -> Optional[str]:
        try:
            url = f"{self.base_url.rstrip('/')}/chat/completions"

            if self.provider == "hw":
                headers = {
                    "Content-Type": "application/json",
                    "X-HW-ID": "com.huawei.adc.copilot",
                    "X-HW-APPKEY": "4bWZesPOKm8uycaoBkU7IQ==",
                    "Model-Id": self.model,
                    "X-Auth-Token": self.api_key,
                }
                data = {
                    "model": self.model,
                    "messages": messages,
                    "max_token": 30000,
                    "stream": True,
                }
            else:
                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.api_key}",
                }
                data = {
                    "model": self.model,
                    "messages": messages
                }

            response = requests.post(
                url, headers=headers, json=data, stream=True, timeout=self.timeout,
            )
            response.raise_for_status()

            # 检查是否为 SSE 流式响应
            content_type = response.headers.get("Content-Type", "")
            if "text/event-stream" in content_type:
                collected_content = []
                for line in response.iter_lines():
                    if not line:
                        continue
                    decoded = line.decode("utf-8")

                    # hw: "data:{json}", env: "data: {json}"
                    if decoded.startswith("data:"):
                        payload = decoded[5:].strip()
                    elif decoded.startswith("data: "):
                        payload = decoded[6:].strip()
                    else:
                        continue

                    if payload == "[DONE]":
                        break

                    try:
                        chunk = json.loads(payload)
                        delta = chunk["choices"][0].get("delta", {})
                        content = delta.get("content") or ""
                        collected_content.append(content)
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue

                result = clean_think_tag("".join(collected_content))
            else:
                # 非流式响应：直接从 JSON 中提取 content
                resp_json = response.json()
                logger.debug("API响应: %s", resp_json)
                result = clean_think_tag(
                    resp_json["choices"][0]["message"]["content"] or ""
                )
            logger.info("LLM响应: %s", result)
            return result

        except Exception as e:
            logger.error("调用LLM API时发生错误: %s", e, exc_info=True)
            return None

    def summarize_type1_group(self, functions: List[Dict[str, Any]]) -> Optional[str]:
        """总结一个 Type-1 函数组的名称和功能。"""
        if not functions:
            return None

        messages = [
            {
                "role": "system",
                "content": (
                    "你是资深代码分析助手。"
                    "请基于给定的一组 Type-1 克隆函数，输出简洁、准确的中文 JSON 总结。"
                    "输出必须是一个合法 JSON 对象，且只能包含以下 2 个字段："
                    "\"group_name\"、\"functionality\"。"
                    "每个字段的值都是字符串，并且字符串需要能被json.loads解析，不要出现未转义的特殊字符。"
                    "不要输出代码块，不要添加 JSON 之外的任何解释。"
                    "不要编造未提供的信息。"
                ),
            },
            {
                "role": "user",
                "content": self._build_type1_group_prompt(functions),
            },
        ]
        return self.think(messages)

    def compare_type1_groups(self, type1_groups: List[Dict[str, Any]]) -> Optional[str]:
        """比较同一 func_group 中多个 Type-1 组之间的差异。"""
        if not type1_groups:
            return None

        messages = [
            {
                "role": "system",
                "content": (
                    "你是资深代码分析助手。"
                    "请基于同一个克隆组中的多个相同函数组，输出简洁、准确的中文 JSON 总结。"
                    "输出必须是一个合法 JSON 对象，且只能包含以下 4 个字段："
                    "\"group_name\"、\"overall_functionality\"、\"type1_group_differences\"、\"reuse_opportunities\"。"
                    "每个字段的值都是Markdown字符串，并且字符串需要能被json.loads解析，不要出现未转义的特殊字符。"
                    "不要输出代码块，不要添加 JSON 之外的任何解释。"
                    "不要编造未提供的信息。"
                ),
            },
            {
                "role": "user",
                "content": self._build_type1_comparison_prompt(type1_groups),
            },
        ]
        return self.think(messages)

    def _build_type1_group_prompt(self, functions: List[Dict[str, Any]]) -> str:
        """构造 Type-1 函数组总结提示词。"""
        max_functions = 4
        max_code_chars = 800
        prompt_parts = [
            (
                f"以下是一个包含 {len(functions)} 个克隆函数的相同函数组。"
                "这些函数除空白字符和布局外完全一致。"
                "请严格输出一个 JSON 对象，字段固定为："
                "\"group_name\"、\"functionality\"。"
                "每个字段为简洁、准确的中文字符串。"
            )
        ]

        for idx, func in enumerate(functions[:max_functions], start=1):
            code = (func.get("code") or "").strip()
            if len(code) > max_code_chars:
                code = code[:max_code_chars] + "\n... [truncated]"

            prompt_parts.append(
                "\n".join([
                    f"函数 {idx}:",
                    f"file_path: {func.get('file_path', '')}",
                    "code:",
                    code or "[empty]",
                ])
            )

        if len(functions) > max_functions:
            prompt_parts.append(
                f"\n其余 {len(functions) - max_functions} 个函数未展开，请根据样本总结该相同函数组。"
            )

        return "\n\n".join(prompt_parts)

    def _build_type1_comparison_prompt(self, type1_groups: List[Dict[str, Any]]) -> str:
        """构造 Type-1 函数组间比较提示词。"""
        max_groups = 6
        max_code_chars = 800
        prompt_parts = [
            (
                f"以下是同一个 func_group 中的 {len(type1_groups)} 个相同函数组。"
                "请比较这些相同函数组之间的功能差异。"
                "请严格输出一个 JSON 对象，字段固定为："
                "\"group_name\"、\"overall_functionality\"、\"type1_group_differences\"、\"reuse_opportunities\"。"
                "每个字段为简洁、准确的中文字符串。"
            )
        ]

        for idx, group in enumerate(type1_groups[:max_groups], start=1):
            functions = group.get("functions", [])
            sample_code = ""
            if functions:
                sample_code = (functions[0].get("code") or "").strip()
            if len(sample_code) > max_code_chars:
                sample_code = sample_code[:max_code_chars] + "\n... [truncated]"

            prompt_parts.append(
                "\n".join([
                    f"Type1组 {idx}:",
                    f"group_name: {group.get('group_name', '')}",
                    f"functionality: {group.get('functionality', '')}",
                    f"function_count: {len(functions)}",
                    "sample_code:",
                    sample_code or "[empty]",
                ])
            )

        if len(type1_groups) > max_groups:
            prompt_parts.append(
                f"\n其余 {len(type1_groups) - max_groups} 个相同函数组未展开，请基于已提供信息完成组间比较。"
            )

        return "\n\n".join(prompt_parts)

# --- 客户端使用示例 ---
if __name__ == '__main__':
    try:
        llmClient = LLMClient()
        
        exampleMessages = [
            {"role": "system", "content": "You are a helpful assistant that writes Python code."},
            {"role": "user", "content": "写一个快速排序算法"}
        ]
        
        print("--- 调用LLM ---")
        responseText = llmClient.think(exampleMessages)
        if responseText:
            print("\n\n--- 完整模型响应 ---")
            print(responseText)

    except ValueError as e:
        print(e)
