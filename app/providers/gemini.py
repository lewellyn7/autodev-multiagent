"""
Gemini Provider - Google Gemini API 包装器
"""

import httpx

from . import BaseProvider, ProviderError


class GeminiProvider(BaseProvider):
    """Google Gemini API"""

    BASE_URL = "https://generativelanguage.googleapis.com/v1beta"

    def __init__(self):
        super().__init__("gemini", self.BASE_URL)

    async def completion(self, model: str, messages: list, stream: bool = False, api_key: str = None, **kwargs):
        if not api_key:
            raise ProviderError(self.name, "API key required", 401)

        # Map model name
        model_id = model.replace("gemini-", "models/")
        url = f"{self.base_url}/{model_id}:generateContent?key={api_key}"

        # Convert messages to Gemini format
        contents = []
        for msg in messages:
            if msg.get("role") == "user":
                contents.append({"role": "user", "parts": [{"text": msg.get("content", "")}]})
            elif msg.get("role") == "model":
                contents.append({"role": "model", "parts": [{"text": msg.get("content", "")}]})

        data = {
            "contents": contents,
            "generationConfig": {
                "temperature": kwargs.get("temperature", 0.9),
                "maxOutputTokens": kwargs.get("max_tokens", 1024),
            },
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.post(url, json=data)
                if response.status_code != 200:
                    raise ProviderError(self.name, response.text, response.status_code)
                result = response.json()
                # Convert Gemini format to OpenAI format
                text = result["candidates"][0]["content"]["parts"][0]["text"]
                return {
                    "id": f"gemini-{hash(text) % 1000000}",
                    "model": model,
                    "choices": [
                        {"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": "stop"}
                    ],
                    "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                }
            except httpx.TimeoutException:
                raise ProviderError(self.name, "Request timeout", 408)
            except httpx.HTTPError as e:
                raise ProviderError(self.name, str(e))
