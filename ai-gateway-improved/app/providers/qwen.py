"""
Qwen Provider - Alibaba Qwen/Tongyi API 包装器
"""
import httpx
from . import BaseProvider, ProviderError


class QwenProvider(BaseProvider):
    """Alibaba Qwen/DashScope API"""
    
    BASE_URL = "https://dashscope.aliyuncs.com/api/v1"
    
    def __init__(self):
        super().__init__("qwen", self.BASE_URL)
    
    async def completion(self, model: str, messages: list, stream: bool = False, api_key: str = None, **kwargs):
        if not api_key:
            raise ProviderError(self.name, "API key required", 401)
        
        url = f"{self.base_url}/services/aigc/text-generation/generation"
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        data = {
            "model": model,
            "input": {"messages": messages},
            "parameters": {
                "stream": stream,
                "temperature": kwargs.get("temperature", 0.9),
                "max_tokens": kwargs.get("max_tokens", 1024)
            }
        }
        
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.post(url, headers=headers, json=data)
                if response.status_code != 200:
                    raise ProviderError(self.name, response.text, response.status_code)
                result = response.json()
                return {
                    "id": result.get("request_id", "qwen"),
                    "model": model,
                    "choices": [{
                        "index": 0,
                        "message": {"role": "assistant", "content": result["output"]["text"]},
                        "finish_reason": "stop"
                    }],
                    "usage": result.get("usage", {})
                }
            except httpx.TimeoutException:
                raise ProviderError(self.name, "Request timeout", 408)
            except httpx.HTTPError as e:
                raise ProviderError(self.name, str(e))
