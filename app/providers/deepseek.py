"""
DeepSeek Provider - DeepSeek API 包装器
"""
import httpx
from typing import AsyncIterator
from . import BaseProvider, ProviderError, stream_response


class DeepSeekProvider(BaseProvider):
    """DeepSeek API"""
    
    BASE_URL = "https://api.deepseek.com/v1"
    
    def __init__(self):
        super().__init__("deepseek", self.BASE_URL)
    
    async def completion(
        self,
        model: str,
        messages: list,
        stream: bool = False,
        api_key: str = None,
        **kwargs
    ):
        """调用 DeepSeek API"""
        if not api_key:
            raise ProviderError(self.name, "API key required", 401)
        
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        data = {
            "model": model,
            "messages": messages,
            "stream": stream,
            **kwargs
        }
        
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.post(url, headers=headers, json=data)
                
                if response.status_code != 200:
                    raise ProviderError(self.name, response.text, response.status_code)
                
                if stream:
                    return stream_response(response)
                else:
                    return response.json()
                    
            except httpx.TimeoutException:
                raise ProviderError(self.name, "Request timeout", 408)
            except httpx.HTTPError as e:
                raise ProviderError(self.name, str(e))
