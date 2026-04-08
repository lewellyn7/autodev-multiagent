"""
Session Memory 配置模块
"""

from typing import Optional
from pydantic import BaseModel, Field


class SessionMemoryConfig(BaseModel):
    """Session Memory 配置
    
    Attributes:
        enabled: 功能开关
        message_count_trigger: 首次触发阈值（消息数）
        message_count_update: 增量更新阈值（消息数）
        minimum_tokens_to_init: 首次触发的 token 阈值
        minimum_tokens_between_update: 增量更新的 token 阈值
        tool_calls_between_updates: 工具调用次数阈值
        max_index_lines: 索引文件最大行数
        max_index_bytes: 索引文件最大字节数
        sessions_dir: 会话摘要存储目录
        summary_model: 摘要生成使用的模型
        summary_max_tokens: 摘要最大 token 数
    """
    
    # 功能开关
    enabled: bool = Field(default=True, description="是否启用 Session Memory")
    
    # 触发阈值
    message_count_trigger: int = Field(
        default=50, 
        description="首次触发摘要的消息数阈值",
        ge=10,
        le=500
    )
    message_count_update: int = Field(
        default=20, 
        description="增量更新摘要的消息数阈值",
        ge=5,
        le=100
    )
    minimum_tokens_to_init: int = Field(
        default=10000, 
        description="首次触发的 token 阈值",
        ge=1000
    )
    minimum_tokens_between_update: int = Field(
        default=5000, 
        description="增量更新的 token 阈值",
        ge=500
    )
    tool_calls_between_updates: int = Field(
        default=3, 
        description="工具调用次数阈值",
        ge=1,
        le=20
    )
    
    # 索引限制
    max_index_lines: int = Field(
        default=200, 
        description="MEMORY.md 最大行数",
        ge=50,
        le=500
    )
    max_index_bytes: int = Field(
        default=25_000, 
        description="MEMORY.md 最大字节数",
        ge=5000
    )
    
    # 存储路径
    sessions_dir: str = Field(
        default="sessions", 
        description="会话摘要存储目录名"
    )
    
    # 摘要模型配置
    summary_model: str = Field(
        default="default", 
        description="摘要生成使用的模型"
    )
    summary_max_tokens: int = Field(
        default=2000, 
        description="摘要最大 token 数",
        ge=500,
        le=4000
    )
    
    class Config:
        env_prefix = "SESSION_MEMORY_"
        case_sensitive = False


def get_default_config() -> SessionMemoryConfig:
    """获取默认配置"""
    return SessionMemoryConfig()


def load_config_from_env() -> SessionMemoryConfig:
    """从环境变量加载配置"""
    import os
    
    config_kwargs = {}
    
    # 从环境变量读取配置
    env_mappings = {
        'SESSION_MEMORY_ENABLED': ('enabled', bool),
        'SESSION_MEMORY_MESSAGE_COUNT_TRIGGER': ('message_count_trigger', int),
        'SESSION_MEMORY_MESSAGE_COUNT_UPDATE': ('message_count_update', int),
        'SESSION_MEMORY_MINIMUM_TOKENS_TO_INIT': ('minimum_tokens_to_init', int),
        'SESSION_MEMORY_MINIMUM_TOKENS_BETWEEN_UPDATE': ('minimum_tokens_between_update', int),
        'SESSION_MEMORY_TOOL_CALLS_BETWEEN_UPDATES': ('tool_calls_between_updates', int),
        'SESSION_MEMORY_MAX_INDEX_LINES': ('max_index_lines', int),
        'SESSION_MEMORY_MAX_INDEX_BYTES': ('max_index_bytes', int),
        'SESSION_MEMORY_SESSIONS_DIR': ('sessions_dir', str),
        'SESSION_MEMORY_SUMMARY_MODEL': ('summary_model', str),
        'SESSION_MEMORY_SUMMARY_MAX_TOKENS': ('summary_max_tokens', int),
    }
    
    for env_key, (config_key, value_type) in env_mappings.items():
        value = os.environ.get(env_key)
        if value is not None:
            try:
                if value_type == bool:
                    config_kwargs[config_key] = value.lower() in ('true', '1', 'yes')
                else:
                    config_kwargs[config_key] = value_type(value)
            except (ValueError, TypeError):
                pass
    
    return SessionMemoryConfig(**config_kwargs)
