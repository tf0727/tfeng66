"""OpenAI-compatible streaming client."""

from collections.abc import Iterator
import os

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()


class QwenClient:
    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        self.api_key = api_key or os.getenv("DASHSCOPE_API_KEY")
        if not self.api_key:
            raise RuntimeError("未配置 DASHSCOPE_API_KEY，请复制 .env.example 为 .env 后填写。")
        self.model = model or os.getenv("QWEN_MODEL", "qwen-plus")
        self.client = OpenAI(
            api_key=self.api_key,
            base_url=os.getenv(
                "DASHSCOPE_BASE_URL",
                "https://dashscope.aliyuncs.com/compatible-mode/v1",
            ),
            timeout=30,
            max_retries=1,
        )

    def stream(self, messages: list[dict[str, str]], tools: list[dict] | None = None):
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            stream=True,
            temperature=0.3,
            tools=tools,
        )
        for chunk in response:
            if tools is not None:
                yield chunk
                continue
            text = chunk.choices[0].delta.content if chunk.choices else None
            if text:
                yield text

    def complete(self, messages, json_mode=False):
        options = {'response_format': {'type': 'json_object'}} if json_mode else {}
        response = self.client.chat.completions.create(model=self.model, messages=messages, temperature=0.2, max_tokens=3000, **options)
        return response.choices[0].message.content or ''

