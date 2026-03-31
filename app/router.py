"""
Smart Router - 智能路由，整合 Health Score + Fallback 逻辑
"""
import asyncio
from typing import Optional, AsyncIterator, Literal
from app.providers import (
    ChatGPTProvider, DeepSeekProvider, MoonshotProvider,
    ClaudeProvider, GeminiProvider, QwenProvider,
    ProviderError
)
from app.database import get_best_account, update_account_stats, get_fallback_models, get_fallback_providers


# Provider 映射
PROVIDERS = {
    "chatgpt": ChatGPTProvider(),
    "deepseek": DeepSeekProvider(),
    "moonshot": MoonshotProvider(),
    "claude": ClaudeProvider(),
    "gemini": GeminiProvider(),
    "qwen": QwenProvider(),
}

# 模型到 Provider 的映射
MODEL_SOURCE_MAP = {
    # OpenAI
    "gpt-4": "chatgpt", "gpt-3.5": "chatgpt",
    "gpt-4o": "chatgpt", "gpt-4o-mini": "chatgpt",
    # DeepSeek
    "deepseek-chat": "deepseek", "deepseek-coder": "deepseek",
    # Moonshot
    "moonshot-v1": "moonshot",
    # Claude
    "claude-3": "claude", "claude-3.5": "claude",
    # Gemini
    "gemini": "gemini", "gemini-1.5": "gemini",
    # Qwen
    "qwen": "qwen", "qwen-turbo": "qwen",
}

# Model fallback chains
MODEL_FALLBACK_CHAIN = {
    "gpt-4o": ["gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"],
    "gpt-4o-mini": ["gpt-3.5-turbo", "claude-3-sonnet"],
    "claude-3-opus": ["claude-3-sonnet", "claude-3-haiku"],
    "claude-3-sonnet": ["claude-3-haiku", "gpt-4o-mini"],
    "gemini-1.5-pro": ["gemini-1.5-flash", "gemini-pro"],
}

# Provider fallback chains
PROVIDER_FALLBACK_CHAIN = {
    "chatgpt": ["deepseek", "moonshot", "openai"],
    "claude": ["chatgpt", "deepseek"],
    "gemini": ["chatgpt", "deepseek"],
    "deepseek": ["moonshot", "openai"],
    "moonshot": ["openai", "deepseek"],
    "openai": ["chatgpt", "deepseek"],
    "qwen": ["deepseek", "chatgpt"],
}


def get_source_for_model(model: str) -> str:
    """根据模型名称获取 source"""
    model_lower = model.lower()
    for key, source in MODEL_SOURCE_MAP.items():
        if key in model_lower:
            return source
    return "chatgpt"  # 默认


class SmartRouter:
    """智能路由器 - 整合健康评分和回退逻辑"""
    
    def __init__(self):
        self.providers = PROVIDERS
        self.model_fallback = MODEL_FALLBACK_CHAIN
        self.provider_fallback = PROVIDER_FALLBACK_CHAIN
        self._circuit_breaker = {}  # 熔断器: source -> fail_count
    
    async def route(
        self,
        model: str,
        messages: list,
        stream: bool = False,
        **kwargs
    ) -> dict | AsyncIterator[dict]:
        """
        智能路由：
        1. 获取最优账户
        2. 尝试请求，失败则模型回退
        3. 模型耗尽则 Provider 回退
        4. 更新健康评分
        """
        source = get_source_for_model(model)
        account = None
        
        try:
            # 获取最优账户
            account = get_best_account(source)
            api_key = account.get("tokens", {}).get("api_key") if account else kwargs.get("api_key")
            
            if not api_key:
                raise ProviderError(source, "No API key available")
            
            # 尝试执行
            return await self._try_complete(source, model, messages, stream, api_key, account, **kwargs)
            
        except Exception as e:
            # 记录失败
            if account:
                update_account_stats(account["id"], success=False)
            
            # 模型回退
            fallback_models = self.model_fallback.get(model, [])
            for fallback_model in fallback_models:
                try:
                    return await self._try_complete(source, fallback_model, messages, stream, api_key, account, **kwargs)
                except ProviderError:
                    continue
            
            # Provider 回退
            fallback_sources = self.provider_fallback.get(source, [])
            for fallback_source in fallback_sources:
                try:
                    fallback_account = get_best_account(fallback_source)
                    fallback_key = fallback_account.get("tokens", {}).get("api_key") if fallback_account else kwargs.get("api_key")
                    if fallback_key:
                        return await self._try_complete(fallback_source, model, messages, stream, fallback_key, fallback_account, **kwargs)
                except ProviderError:
                    continue
            
            raise ProviderError(source, f"All providers failed: {str(e)}")
    
    async def _try_complete(
        self,
        source: str,
        model: str,
        messages: list,
        stream: bool,
        api_key: str,
        account: dict = None,
        **kwargs
    ) -> dict | AsyncIterator[dict]:
        """尝试执行单个 provider"""
        provider = self.providers.get(source)
        if not provider:
            raise ProviderError(source, f"Provider {source} not found")
        
        try:
            start_time = asyncio.get_event_loop().time()
            result = await provider.completion(model, messages, stream, api_key, **kwargs)
            latency = (asyncio.get_event_loop().time() - start_time) * 1000
            
            # 记录成功
            if account:
                update_account_stats(account["id"], success=True, latency=latency)
            
            # 重置熔断计数
            if source in self._circuit_breaker:
                del self._circuit_breaker[source]
            
            return result
            
        except ProviderError as e:
            # 增加熔断计数
            self._circuit_breaker[source] = self._circuit_breaker.get(source, 0) + 1
            
            # 超过阈值则标记账户为失败
            if account and self._circuit_breaker[source] >= 5:
                update_account_stats(account["id"], success=False)
            
            raise


# 全局路由器实例
router = SmartRouter()
