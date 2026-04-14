import json
import time
from typing import Optional, List, Dict

import requests

import re

def clean_think_tag(raw):
    return re.sub(r'<think>.*?</think>', '', raw, flags=re.S)


###########################################################
# Qwen3 API 封装
###########################################################

class Qwen3:

    def __init__(self):
        self.url = "https://apigw.huawei.com/stream/mategpt/v3/chat/completions"
        self.headers = {
            "Content-Type": "application/json",
            "X-HW-ID": "com.huawei.adc.copilot",
            "X-HW-APPKEY": "4bWZesPOKm8uycaoBkU7IQ==",
            "Model-Id": "Qwen3-32B",
            "X-Auth-Token": "Epj6Rh_8W-yE78qkqE5V6kC2cYwonPOB7gRQO-QLOFX0SqVhBtDv8xlKeGXrSRwlKpsYriFsAJNRZZYvsouOncILyGeLvkO2qapOGdY0fKV3-c9qKSicuFzuXoiNxVq4GrK3IV0Dixa8hk8ZBQLYcXATuZaQEPZXEvYrXAI7tyXlLjBQoxSmgysW0TziGz_xxoIclT5mlU_AmgcHP578Hm471CO7Lyw0zV3j2PDtvdeBdEKyO2-x8xlcTMFWZvm9QvpxU8eVd-19nYdabVXruHDXDjyYJ95qw9oBdopHEKybExqPRgXOMM7WdrZomjBJDFediZ6N9nhCnwXGqweAtw"
        }
        self.timeout = 120

    def generate(self, content: str):

        data = {
            "model": "Qwen3-32B",
            "messages": [
                {
                    "role": "user",
                    "content": f"{content}<no_think>"
                }
            ],
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

    # 拼接 system + user
    content = f"""
[系统指令]
{system_prompt}

[用户输入]
{user_prompt}
"""

    for attempt in range(MAX_RETRIES + 1):

        try:

            result = qwen3.generate(content)

            result = clean_think_tag(result)

            return result.strip()

        except Exception as e:

            if attempt >= MAX_RETRIES:
                raise RuntimeError(f"LLM API 调用失败: {e}")

            print("LLM 调用失败，重试中...")
            time.sleep(1)

    return ""