"""
Claude Provider - Anthropic Claude API 包装器
"""

import httpx

from . import BaseProvider, ProviderError


class ClaudeProvider(BaseProvider):
    """Anthropic Claude API"""

    BASE_URL = "https://api.anthropic.com/v1"

    def __init__(self):
        super().__init__("claude", self.BASE_URL)

    async def completion(self, model: str, messages: list, stream: bool = False, api_key: str = None, **kwargs):
        if not api_key:
            raise ProviderError(self.name, "API key required", 401)

        url = f"{self.base_url}/messages"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        }
        # Convert OpenAI format to Anthropic format
        system_msg = ""
        anthropic_messages = []
        for msg in messages:
            if msg.get("role") == "system":
                system_msg = msg.get("content", "")
            else:
                anthropic_messages.append({"role": msg.get("role", "user"), "content": msg.get("content", "")})

        data = {
            "model": model,
            "messages": anthropic_messages,
            "max_tokens": kwargs.get("max_tokens", 1024),
            "stream": stream,
            "system": system_msg if system_msg else None,
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.post(url, headers=headers, json=data)
                if response.status_code != 200:
                    raise ProviderError(self.name, response.text, response.status_code)
                result = response.json()
                # Convert Anthropic format to OpenAI format
                return {
                    "id": result.get("id"),
                    "model": result.get("model"),
                    "choices": [
                        {
                            "index": 0,
                            "message": {"role": "assistant", "content": result["content"][0]["text"]},
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": result.get("usage", {}),
                }
            except httpx.TimeoutException:
                raise ProviderError(self.name, "Request timeout", 408)
            except httpx.HTTPError as e:
                raise ProviderError(self.name, str(e))
