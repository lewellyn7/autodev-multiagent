"""
会话管理器

负责：
1. 会话生命周期管理
2. 消息计数与摘要触发
3. 上下文加载
"""

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
import logging

from .config import SessionMemoryConfig
from .session_summarizer import SessionSummarizer, SessionSummary, Message
from .memory_index import MemoryIndex

logger = logging.getLogger(__name__)


@dataclass
class SessionState:
    """会话状态"""
    session_id: str
    session_type: str  # 'main' | 'subagent'
    start_time: datetime = field(default_factory=datetime.now)
    message_count: int = 0
    tool_call_count: int = 0
    last_summary_index: int = 0
    last_summary_time: Optional[datetime] = None
    has_tool_calls_in_last_turn: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'session_id': self.session_id,
            'session_type': self.session_type,
            'start_time': self.start_time.isoformat(),
            'message_count': self.message_count,
            'tool_call_count': self.tool_call_count,
            'last_summary_index': self.last_summary_index,
            'last_summary_time': self.last_summary_time.isoformat() if self.last_summary_time else None,
        }


class SessionManager:
    """会话生命周期管理器"""
    
    def __init__(
        self,
        config: SessionMemoryConfig,
        summarizer: SessionSummarizer,
        index: MemoryIndex
    ):
        self.config = config
        self.summarizer = summarizer
        self.index = index
        self._sessions: Dict[str, SessionState] = {}
        self._message_buffers: Dict[str, List[Message]] = {}
        
        # LLM 客户端（用于生成摘要）
        self._llm_client = None
    
    def set_llm_client(self, client: Any):
        """设置 LLM 客户端"""
        self._llm_client = client
    
    def create_session(
        self, 
        session_id: str, 
        session_type: str = 'main'
    ) -> SessionState:
        """创建新会话"""
        state = SessionState(
            session_id=session_id,
            session_type=session_type,
            start_time=datetime.now()
        )
        self._sessions[session_id] = state
        self._message_buffers[session_id] = []
        
        logger.debug(f"创建会话: {session_id[:8]} (type={session_type})")
        
        return state
    
    def get_or_create_session(
        self, 
        session_id: str,
        session_type: str = 'main'
    ) -> SessionState:
        """获取或创建会话"""
        if session_id not in self._sessions:
            return self.create_session(session_id, session_type)
        return self._sessions[session_id]
    
    def on_message(
        self, 
        session_id: str,
        role: str,
        content: str,
        metadata: Dict[str, Any] = None
    ):
        """消息事件处理（同步版本）"""
        state = self.get_or_create_session(session_id)
        
        # 记录消息
        message = Message(
            role=role,
            content=content,
            timestamp=datetime.now(),
            metadata=metadata or {}
        )
        
        if session_id in self._message_buffers:
            self._message_buffers[session_id].append(message)
        
        # 更新状态
        state.message_count += 1
        
        # 检查是否有工具调用
        if role == 'assistant' and metadata and 'tool_calls' in metadata:
            state.tool_call_count += len(metadata['tool_calls'])
            state.has_tool_calls_in_last_turn = True
        else:
            state.has_tool_calls_in_last_turn = False
        
        logger.debug(
            f"消息计数: session={session_id[:8]}, "
            f"messages={state.message_count}, tools={state.tool_call_count}"
        )
    
    async def check_and_summarize(self, session_id: str) -> Optional[SessionSummary]:
        """检查并生成摘要（异步）"""
        if not self.config.enabled:
            return None
        
        state = self._sessions.get(session_id)
        if not state:
            return None
        
        # 检查是否需要摘要
        if not self.summarizer.should_summarize(
            session_id=session_id,
            message_count=state.message_count,
            tool_call_count=state.tool_call_count,
            has_tool_calls_in_last_turn=state.has_tool_calls_in_last_turn
        ):
            return None
        
        # 生成摘要
        return await self._generate_and_save_summary(session_id)
    
    async def _generate_and_save_summary(
        self, 
        session_id: str
    ) -> Optional[SessionSummary]:
        """生成并保存摘要"""
        state = self._sessions.get(session_id)
        if not state:
            return None
        
        # 获取消息范围
        messages = self._message_buffers.get(session_id, [])
        
        if len(messages) < state.last_summary_index:
            logger.warning(f"消息缓冲区异常: {session_id[:8]}")
            return None
        
        # 只处理新消息
        new_messages = messages[state.last_summary_index:]
        
        if not new_messages:
            return None
        
        # 构建 prompt
        prompt = self.summarizer.build_summary_prompt(new_messages)
        
        # 调用 LLM 生成摘要
        try:
            if self._llm_client:
                response = await self._llm_client.generate(
                    prompt,
                    max_tokens=self.config.summary_max_tokens
                )
            else:
                # 如果没有 LLM 客户端，生成简单摘要
                response = self._generate_simple_summary(new_messages)
            
            # 解析摘要
            summary = self.summarizer.parse_summary_response(
                response=response,
                session_id=session_id,
                session_type=state.session_type,
                start_time=state.start_time,
                message_range=(state.last_summary_index, state.message_count),
                message_count=state.message_count
            )
            
            # 保存摘要
            filepath = self.summarizer.save_summary(summary)
            
            # 更新索引
            self.index.update_session_index(summary)
            
            # 更新状态
            state.last_summary_index = state.message_count
            state.last_summary_time = datetime.now()
            state.tool_call_count = 0  # 重置工具调用计数
            
            logger.info(f"摘要已生成: {session_id[:8]} -> {filepath.name}")
            
            return summary
            
        except Exception as e:
            logger.error(f"生成摘要失败: {session_id[:8]}: {e}")
            return None
    
    def _generate_simple_summary(self, messages: List[Message]) -> str:
        """生成简单摘要（无 LLM 时使用）"""
        import json
        
        # 提取基本信息
        user_messages = [m for m in messages if m.role == 'user']
        assistant_messages = [m for m in messages if m.role == 'assistant']
        
        # 生成 JSON 格式摘要
        summary_data = {
            'decisions': [],
            'todos': [],
            'context_points': [
                f"对话包含 {len(user_messages)} 条用户消息和 {len(assistant_messages)} 条助手回复"
            ],
            'key_dialogues': [
                {'role': m.role, 'content': m.content[:100]}
                for m in messages[:5]  # 前 5 条
            ],
            'related_files': [],
            'next_steps': []
        }
        
        return f"```json\n{json.dumps(summary_data, ensure_ascii=False)}\n```"
    
    def load_context(self, session_id: str) -> str:
        """加载会话上下文
        
        用于新会话启动时注入历史摘要
        """
        # 获取相关摘要
        summaries = self.index.get_relevant_summaries(limit=3)
        
        if not summaries:
            return ""
        
        # 构建上下文
        return self.index.build_summary_context(summaries)
    
    def end_session(self, session_id: str) -> Optional[SessionSummary]:
        """结束会话并生成最终摘要"""
        state = self._sessions.get(session_id)
        if not state:
            return None
        
        # 如果有未摘要的消息，强制生成
        messages = self._message_buffers.get(session_id, [])
        if state.message_count > state.last_summary_index:
            # 同步执行（在异步环境中使用 asyncio.run）
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = None
            
            if loop and loop.is_running():
                # 已有事件循环，创建任务
                task = loop.create_task(self._generate_and_save_summary(session_id))
                # 等待完成（简化处理）
                import time
                for _ in range(50):  # 最多等待 5 秒
                    if task.done():
                        break
                    time.sleep(0.1)
                
                return task.result() if task.done() else None
            else:
                # 没有事件循环，同步执行
                return asyncio.run(self._generate_and_save_summary(session_id))
        
        return None
    
    def get_session_stats(self, session_id: str) -> Optional[Dict[str, Any]]:
        """获取会话统计信息"""
        state = self._sessions.get(session_id)
        if not state:
            return None
        
        return {
            'session_id': session_id[:8],
            'session_type': state.session_type,
            'message_count': state.message_count,
            'tool_call_count': state.tool_call_count,
            'last_summary_index': state.last_summary_index,
            'messages_since_summary': state.message_count - state.last_summary_index,
            'uptime_seconds': (datetime.now() - state.start_time).total_seconds()
        }
    
    def cleanup_session(self, session_id: str):
        """清理会话资源"""
        if session_id in self._sessions:
            del self._sessions[session_id]
        if session_id in self._message_buffers:
            del self._message_buffers[session_id]
        
        logger.debug(f"会话已清理: {session_id[:8]}")
