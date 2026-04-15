import argparse
import json
import os
import re
import time
from typing import Dict, List

import requests
from dotenv import load_dotenv, find_dotenv


load_dotenv(find_dotenv())

def clean_think_tag(raw):
    return re.sub(r'<think>.*?</think>', '', raw, flags=re.S)


###########################################################
# Qwen3 API 封装
###########################################################

class Qwen3:

    def __init__(self):
        auth_token = os.getenv("HW_AUTH_TOKEN")
        if not auth_token:
            raise ValueError("HW_AUTH_TOKEN must be defined in the .env file.")

        self.url = "https://apigw.huawei.com/stream/mategpt/v3/chat/completions"
        self.headers = {
            "Content-Type": "application/json",
            "X-HW-ID": "com.huawei.adc.copilot",
            "X-HW-APPKEY": "4bWZesPOKm8uycaoBkU7IQ==",
            "Model-Id": "Qwen3-32B",
            "X-Auth-Token": auth_token,
        }
        self.timeout = 120

    def generate(self, messages: List[Dict[str, str]]):

        data = {
            "model": "Qwen3-32B",
            "messages": messages,
            "max_token": 30000
        }

        try:
            response = requests.post(
                self.url,
                headers=self.headers,
                json=data,
                stream=True,
                timeout=self.timeout
            )

            if response.status_code != 200:
                raise Exception(
                    f"API 请求失败，状态码: {response.status_code}, 响应: {response.text}"
                )

            result = ""

            for chunk in response.iter_lines():

                if chunk:
                    decoded_chunk = chunk.decode("utf-8")[5:]

                    try:
                        json_chunk = json.loads(decoded_chunk)
                        result += json_chunk["choices"][0].get(
                            "delta", {}
                        ).get("content", "")

                    except json.JSONDecodeError:
                        result += decoded_chunk

        except Exception as e:
            print(f"请求过程中发生错误: {str(e)}")
            raise

        return result


###########################################################
# 统一对外接口（保持不变）
###########################################################

MAX_RETRIES = 1


def call_llm_api(system_prompt: str, user_prompt: str) -> str:
    """
    统一的 LLM 调用接口
    """

    qwen3 = Qwen3()

    messages = [
        {
            "role": "system",
            "content": system_prompt,
        },
        {
            "role": "user",
            "content": user_prompt,
        },
    ]

    for attempt in range(MAX_RETRIES + 1):

        try:

            result = qwen3.generate(messages)

            result = clean_think_tag(result)

            return result.strip()

        except Exception as e:

            if attempt >= MAX_RETRIES:
                raise RuntimeError(f"LLM API 调用失败: {e}")

            print("LLM 调用失败，重试中...")
            time.sleep(1)

    return ""


def main():
    parser = argparse.ArgumentParser(description="调用 Qwen3 API 并输出结果")
    parser.add_argument(
        "--system-prompt",
        default="You are a helpful assistant.",
        help="system prompt 内容",
    )
    parser.add_argument(
        "--user-prompt",
        default="请简单介绍一下你自己。",
        help="user prompt 内容",
    )
    args = parser.parse_args()

    try:
        output = call_llm_api(args.system_prompt, args.user_prompt)
        print("\n===== LLM OUTPUT =====")
        print(output)
    except Exception as e:
        print(f"调用失败: {e}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()