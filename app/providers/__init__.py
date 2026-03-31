"""
Provider Wrapper Base - 统一异步 API 调用接口
"""

import json
from collections.abc import AsyncIterator

import httpx


class ProviderError(Exception):
    """Provider 调用错误"""

    def __init__(self, provider: str, message: str, status_code: int = None):
        self.provider = provider
        self.message = message
        self.status_code = status_code
        super().__init__(f"[{provider}] {message}")


class BaseProvider:
    """Provider 基类"""

    def __init__(self, name: str, base_url: str = None):
        self.name = name
        self.base_url = base_url
        self.timeout = httpx.Timeout(60.0, connect=10.0)

    async def completion(
        self, model: str, messages: list, stream: bool = False, api_key: str = None, **kwargs
    ) -> dict | AsyncIterator[dict]:
        """发起 completion 请求"""
        raise NotImplementedError

    async def close(self):
        """关闭连接"""
        pass


async def stream_response(response: httpx.Response) -> AsyncIterator[dict]:
    """解析 SSE 流式响应"""
    async for line in response.aiter_lines():
        if line.startswith("data: "):
            data = line[6:]
            if data == "[DONE]":
                break
            yield json.loads(data)


def extract_model_from_error(error: Exception) -> str:
    """从错误中提取模型信息"""
    return "unknown"
