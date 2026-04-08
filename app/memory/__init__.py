"""
Session Memory 自动摘要系统

基于 Claude Code 的 Memory 设计，实现会话记忆的自动摘要和管理。

核心组件：
- SessionSummarizer: 会话摘要生成器
- MemoryIndex: MEMORY.md 索引管理器
- SessionManager: 会话生命周期管理
"""

from .config import SessionMemoryConfig
from .session_summarizer import SessionSummarizer, SessionSummary
from .memory_index import MemoryIndex
from .session_manager import SessionManager

__all__ = [
    'SessionMemoryConfig',
    'SessionSummarizer',
    'SessionSummary',
    'MemoryIndex',
    'SessionManager',
]

__version__ = '1.0.0'
