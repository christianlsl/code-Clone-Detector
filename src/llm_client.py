import os
from openai import OpenAI
from dotenv import load_dotenv
from typing import List, Dict, Any, Optional

# 加载 .env 文件中的环境变量
load_dotenv()

class LLMClient:
    def __init__(self, model: str = None, apiKey: str = None, baseUrl: str = None, timeout: int = None):
        """
        初始化客户端。优先使用传入参数，如果未提供，则从环境变量加载。
        """
        self.model = model or os.getenv("LLM_MODEL_ID")
        apiKey = apiKey or os.getenv("LLM_API_KEY")
        baseUrl = baseUrl or os.getenv("LLM_BASE_URL")
        timeout = timeout or int(os.getenv("LLM_TIMEOUT", 60))
        
        if not all([self.model, apiKey, baseUrl]):
            raise ValueError("模型ID、API密钥和服务地址必须被提供或在.env文件中定义。")

        self.client = OpenAI(api_key=apiKey, base_url=baseUrl, timeout=timeout)

    def think(self, messages: List[Dict[str, str]], temperature: float = 0) -> str:
        # print(f"🧠 正在调用 {self.model} 模型...")
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                stream=True,
            )
            
            # 处理流式响应
            # print("✅ 大语言模型响应成功:")
            collected_content = []
            for chunk in response:
                content = chunk.choices[0].delta.content or ""
                print(content, end="", flush=True)
                collected_content.append(content)
            print()  # 在流式输出结束后换行
            return "".join(collected_content)

        except Exception as e:
            print(f"❌ 调用LLM API时发生错误: {e}")
            return None

    def summarize_func_group(self, func_group: List[Dict[str, Any]]) -> Optional[str]:
        """
        对相似函数簇生成 JSON 格式总结。

        Args:
            func_group: 结果中的 func_group 字段

        Returns:
            JSON 字符串，失败时返回 None
        """
        if not func_group:
            return None

        messages = [
            {
                "role": "system",
                "content": (
                    "你是资深代码分析助手。"
                    "请基于给定的一组相似函数，输出简洁、准确的中文 JSON 总结。"
                    "输出必须是一个合法 JSON 对象，且只能包含以下 4 个字段："
                    "\"共同职责\"、\"共同功能\"、\"主要差异点\"、\"可能的复用方向\"。"
                    "每个字段的值都是Markdown字符串。"
                    "不要输出代码块，不要添加 JSON 之外的任何解释。"
                    "不要编造未提供的信息。"
                ),
            },
            {
                "role": "user",
                "content": self._build_func_group_prompt(func_group),
            },
        ]
        return self.think(messages)

    def _build_func_group_prompt(self, func_group: List[Dict[str, Any]]) -> str:
        """构造函数簇总结提示词，限制上下文大小。"""
        max_functions = 8
        max_code_chars = 1200
        prompt_parts = [
            (
                f"以下是一个包含 {len(func_group)} 个 javascript 相似函数的克隆簇。"
                "请严格输出一个 JSON 对象，字段固定为："
                "\"共同职责\"、\"共同功能\"、\"主要差异点\"、\"可能的复用方向\"。"
            )
        ]

        for idx, func in enumerate(func_group[:max_functions], start=1):
            code = (func.get("code") or "").strip()
            if len(code) > max_code_chars:
                code = code[:max_code_chars] + "\n... [truncated]"

            prompt_parts.append(
                "\n".join([
                    f"函数 {idx}:",
                    f"file_path: {func.get('file_path', '')}",
                    # f"start_line: {func.get('start_line', '')}",
                    # f"end_line: {func.get('end_line', '')}",
                    "code:",
                    code or "[empty]",
                ])
            )

        if len(func_group) > max_functions:
            prompt_parts.append(
                f"\n其余 {len(func_group) - max_functions} 个函数未展开，请结合已提供样本进行簇级别总结。"
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
