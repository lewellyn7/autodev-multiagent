"""
会话摘要生成器

负责：
1. 判断是否需要生成摘要
2. 调用 LLM 生成结构化摘要
3. 保存摘要到文件
"""

import re
import os
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
import json
import logging

from .config import SessionMemoryConfig

logger = logging.getLogger(__name__)


@dataclass
class Message:
    """消息数据结构"""
    role: str  # 'user' | 'assistant' | 'system'
    content: str
    timestamp: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'role': self.role,
            'content': self.content,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
            'metadata': self.metadata
        }


@dataclass
class TodoItem:
    """待办事项"""
    content: str
    done: bool = False
    priority: str = 'normal'  # 'high' | 'normal' | 'low'
    
    def to_markdown(self) -> str:
        checkbox = '[x]' if self.done else '[ ]'
        return f"- {checkbox} {self.content}"


@dataclass
class Decision:
    """决策记录"""
    topic: str
    context: str
    choice: str
    reason: str
    
    def to_markdown(self) -> str:
        return f"**{self.topic}**: {self.choice}\n  - 背景: {self.context}\n  - 理由: {self.reason}"


@dataclass
class SessionSummary:
    """会话摘要数据结构"""
    session_id: str
    session_type: str  # 'main' | 'subagent'
    start_time: datetime
    summary_time: datetime
    message_range: tuple  # (first_msg_idx, last_msg_idx)
    
    # 结构化内容
    decisions: List[Decision] = field(default_factory=list)
    todos: List[TodoItem] = field(default_factory=list)
    context_points: List[str] = field(default_factory=list)
    key_dialogues: List[Dict[str, str]] = field(default_factory=list)
    related_files: List[Dict[str, str]] = field(default_factory=list)
    next_steps: List[str] = field(default_factory=list)
    
    # 元数据
    file_path: Optional[str] = None
    message_count: int = 0
    
    def to_markdown(self) -> str:
        """转换为 Markdown 格式"""
        lines = [
            f"# Session Memory: {self.session_id[:8]}",
            "",
            "## 元信息",
            f"- **会话ID**: `{self.session_id}`",
            f"- **类型**: {self.session_type}",
            f"- **开始时间**: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}",
            f"- **摘要时间**: {self.summary_time.strftime('%Y-%m-%d %H:%M:%S')}",
            f"- **消息范围**: #{self.message_range[0]} - #{self.message_range[1]}",
            f"- **消息总数**: {self.message_count}",
            "",
        ]
        
        # 关键决策
        if self.decisions:
            lines.append("## 关键决策")
            for i, decision in enumerate(self.decisions, 1):
                lines.append(f"{i}. {decision.to_markdown()}")
            lines.append("")
        
        # 待办事项
        if self.todos:
            lines.append("## 待办事项")
            for todo in self.todos:
                lines.append(todo.to_markdown())
            lines.append("")
        
        # 上下文要点
        if self.context_points:
            lines.append("## 上下文要点")
            for point in self.context_points:
                lines.append(f"- {point}")
            lines.append("")
        
        # 重要对话片段
        if self.key_dialogues:
            lines.append("## 重要对话片段")
            for dialogue in self.key_dialogues:
                lines.append(f"> **{dialogue.get('role', 'User')}**: {dialogue.get('content', '')}")
            lines.append("")
        
        # 关联文件
        if self.related_files:
            lines.append("## 关联文件")
            for file_info in self.related_files:
                lines.append(f"- `{file_info.get('path', '')}`: {file_info.get('description', '')}")
            lines.append("")
        
        # 下一步建议
        if self.next_steps:
            lines.append("## 下一步建议")
            for i, step in enumerate(self.next_steps, 1):
                lines.append(f"{i}. {step}")
            lines.append("")
        
        return '\n'.join(lines)
    
    def to_json(self) -> Dict[str, Any]:
        """转换为 JSON 格式"""
        return {
            'session_id': self.session_id,
            'session_type': self.session_type,
            'start_time': self.start_time.isoformat(),
            'summary_time': self.summary_time.isoformat(),
            'message_range': list(self.message_range),
            'message_count': self.message_count,
            'decisions': [
                {'topic': d.topic, 'context': d.context, 'choice': d.choice, 'reason': d.reason}
                for d in self.decisions
            ],
            'todos': [
                {'content': t.content, 'done': t.done, 'priority': t.priority}
                for t in self.todos
            ],
            'context_points': self.context_points,
            'key_dialogues': self.key_dialogues,
            'related_files': self.related_files,
            'next_steps': self.next_steps,
            'file_path': self.file_path
        }


class SessionSummarizer:
    """会话摘要生成器"""
    
    # 敏感信息匹配模式
    SENSITIVE_PATTERNS = [
        (r"api[_-]?key\s*[=:]\s*['\"]?[\w\-]{20,}['\"]?", "[API_KEY_REDACTED]"),
        (r"password\s*[=:]\s*['\"]?[^\s'\"]{8,}['\"]?", "[PASSWORD_REDACTED]"),
        (r"token\s*[=:]\s*['\"]?[\w\-]{20,}['\"]?", "[TOKEN_REDACTED]"),
        (r"secret\s*[=:]\s*['\"]?[\w\-]{20,}['\"]?", "[SECRET_REDACTED]"),
        (r"Bearer\s+[\w\-\.]{20,}", "Bearer [TOKEN_REDACTED]"),
    ]
    
    def __init__(self, config: SessionMemoryConfig, sessions_dir: Path):
        self.config = config
        self.sessions_dir = sessions_dir
        self._summary_markers: Dict[str, Dict[str, Any]] = {}
        
        # 确保目录存在
        self._ensure_sessions_dir()
    
    def _ensure_sessions_dir(self):
        """确保会话目录存在并设置正确权限"""
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        # 设置目录权限：仅属主可读写执行
        try:
            os.chmod(self.sessions_dir, 0o700)
        except OSError as e:
            logger.warning(f"无法设置会话目录权限: {e}")
    
    def has_summary(self, session_id: str) -> bool:
        """检查会话是否已有摘要"""
        return self._find_summary_file(session_id) is not None
    
    def _find_summary_file(self, session_id: str) -> Optional[Path]:
        """查找会话摘要文件"""
        pattern = f"session-*-{session_id[:8]}*.md"
        matches = list(self.sessions_dir.glob(pattern))
        return matches[0] if matches else None
    
    def get_last_summary_marker(self, session_id: str) -> Optional[Dict[str, Any]]:
        """获取最后一次摘要标记"""
        return self._summary_markers.get(session_id)
    
    def save_summary_marker(self, session_id: str, message_count: int):
        """保存摘要标记"""
        self._summary_markers[session_id] = {
            'message_count': message_count,
            'timestamp': datetime.now().isoformat()
        }
    
    def should_summarize(
        self, 
        session_id: str, 
        message_count: int,
        tool_call_count: int = 0,
        has_tool_calls_in_last_turn: bool = False
    ) -> bool:
        """判断是否需要生成摘要
        
        Args:
            session_id: 会话 ID
            message_count: 当前消息数
            tool_call_count: 自上次摘要后的工具调用次数
            has_tool_calls_in_last_turn: 最后一轮是否有工具调用
            
        Returns:
            是否需要生成摘要
        """
        if not self.config.enabled:
            return False
        
        # 首次触发
        if not self.has_summary(session_id):
            if message_count >= self.config.message_count_trigger:
                logger.info(f"首次触发摘要: session={session_id[:8]}, messages={message_count}")
                return True
            return False
        
        # 增量更新
        last_marker = self.get_last_summary_marker(session_id)
        if not last_marker:
            return False
        
        new_messages = message_count - last_marker['message_count']
        met_message_threshold = new_messages >= self.config.message_count_update
        met_tool_threshold = tool_call_count >= self.config.tool_calls_between_updates
        
        # 在自然断点触发，避免 tool_use 链中间截断
        if met_message_threshold:
            if met_tool_threshold or not has_tool_calls_in_last_turn:
                logger.info(
                    f"增量触发摘要: session={session_id[:8]}, "
                    f"new_messages={new_messages}, tool_calls={tool_call_count}"
                )
                return True
        
        return False
    
    def _sanitize_content(self, content: str) -> str:
        """清理敏感信息"""
        sanitized = content
        for pattern, replacement in self.SENSITIVE_PATTERNS:
            sanitized = re.sub(pattern, replacement, sanitized, flags=re.IGNORECASE)
        return sanitized
    
    def _format_messages(self, messages: List[Message]) -> str:
        """格式化消息列表"""
        formatted = []
        for i, msg in enumerate(messages):
            role = msg.role.upper()
            content = self._sanitize_content(msg.content)
            # 截断过长的内容
            if len(content) > 500:
                content = content[:500] + "...[truncated]"
            formatted.append(f"[{i+1}] {role}: {content}")
        return '\n'.join(formatted)
    
    def build_summary_prompt(self, messages: List[Message]) -> str:
        """构建摘要提示词"""
        formatted_messages = self._format_messages(messages)
        
        return f"""请分析以下对话，生成结构化摘要。

## 对话内容
{formatted_messages}

## 输出要求

请严格按照以下 JSON 格式输出摘要：

```json
{{
  "decisions": [
    {{
      "topic": "决策主题",
      "context": "决策背景",
      "choice": "最终选择",
      "reason": "选择理由"
    }}
  ],
  "todos": [
    {{
      "content": "待办事项内容",
      "done": false,
      "priority": "normal"
    }}
  ],
  "context_points": [
    "关键上下文要点1",
    "关键上下文要点2"
  ],
  "key_dialogues": [
    {{
      "role": "User",
      "content": "重要问题或请求"
    }},
    {{
      "role": "Assistant",
      "content": "重要回答或行动"
    }}
  ],
  "related_files": [
    {{
      "path": "文件路径",
      "description": "文件用途或操作"
    }}
  ],
  "next_steps": [
    "建议的下一步行动1",
    "建议的下一步行动2"
  ]
}}
```

注意：
1. decisions 应包含对话中的重要决策点
2. todos 应提取所有提到的待办事项
3. context_points 应包含帮助后续对话理解的背景信息
4. key_dialogues 选择 3-5 条最重要的对话
5. related_files 列出涉及到的文件
6. next_steps 基于当前进展提出建议
"""
    
    def parse_summary_response(
        self, 
        response: str, 
        session_id: str,
        session_type: str,
        start_time: datetime,
        message_range: tuple,
        message_count: int
    ) -> SessionSummary:
        """解析 LLM 响应为 SessionSummary"""
        
        # 尝试提取 JSON
        json_match = re.search(r'```json\s*(.*?)\s*```', response, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            # 尝试直接解析
            json_str = response.strip()
        
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError:
            logger.warning(f"无法解析 JSON 响应，使用空摘要")
            data = {}
        
        # 构建 SessionSummary
        decisions = [
            Decision(
                topic=d.get('topic', ''),
                context=d.get('context', ''),
                choice=d.get('choice', ''),
                reason=d.get('reason', '')
            )
            for d in data.get('decisions', [])
        ]
        
        todos = [
            TodoItem(
                content=t.get('content', ''),
                done=t.get('done', False),
                priority=t.get('priority', 'normal')
            )
            for t in data.get('todos', [])
        ]
        
        return SessionSummary(
            session_id=session_id,
            session_type=session_type,
            start_time=start_time,
            summary_time=datetime.now(),
            message_range=message_range,
            message_count=message_count,
            decisions=decisions,
            todos=todos,
            context_points=data.get('context_points', []),
            key_dialogues=data.get('key_dialogues', []),
            related_files=data.get('related_files', []),
            next_steps=data.get('next_steps', [])
        )
    
    def save_summary(self, summary: SessionSummary) -> Path:
        """保存摘要到文件"""
        # 生成文件名
        timestamp = summary.summary_time.strftime('%Y-%m-%d-%H%M')
        short_id = summary.session_id[:8]
        filename = f"session-{summary.session_type}-{short_id}-{timestamp}.md"
        filepath = self.sessions_dir / filename
        
        # 写入文件
        filepath.write_text(summary.to_markdown(), encoding='utf-8')
        
        # 设置文件权限：仅属主可读写
        try:
            os.chmod(filepath, 0o600)
        except OSError as e:
            logger.warning(f"无法设置摘要文件权限: {e}")
        
        logger.info(f"摘要已保存: {filepath}")
        
        # 更新摘要文件路径
        summary.file_path = str(filepath)
        
        # 更新标记
        self.save_summary_marker(summary.session_id, summary.message_count)
        
        return filepath
    
    def load_summary(self, session_id: str) -> Optional[SessionSummary]:
        """加载会话摘要"""
        filepath = self._find_summary_file(session_id)
        if not filepath:
            return None
        
        content = filepath.read_text(encoding='utf-8')
        
        # 简单解析 Markdown 提取关键信息
        # 实际实现中可以使用更完善的解析器
        
        return SessionSummary(
            session_id=session_id,
            session_type='unknown',
            start_time=datetime.now(),
            summary_time=datetime.now(),
            message_range=(0, 0),
            file_path=str(filepath)
        )
