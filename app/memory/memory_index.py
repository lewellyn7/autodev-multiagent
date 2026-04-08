"""
Memory 索引管理器

负责：
1. 管理 MEMORY.md 索引文件
2. 硬截断保护（≤200行/25KB）
3. 会话摘要索引维护
"""

import re
import os
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any
import logging
import json

from .config import SessionMemoryConfig
from .session_summarizer import SessionSummary

logger = logging.getLogger(__name__)


class MemoryIndex:
    """MEMORY.md 索引管理器"""
    
    # 索引章节标记
    SESSION_SECTION_START = "## 📋 会话记忆索引"
    SESSION_SECTION_END = "---"
    
    def __init__(
        self, 
        workspace_path: Path, 
        config: SessionMemoryConfig
    ):
        self.workspace_path = workspace_path
        self.config = config
        self.memory_file = workspace_path / "MEMORY.md"
        self.sessions_dir = workspace_path / config.sessions_dir
        self.index_file = self.sessions_dir / "session-index.json"
        
        self._ensure_directories()
    
    def _ensure_directories(self):
        """确保必要目录存在"""
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.sessions_dir, 0o700)
        except OSError:
            pass
    
    def _read_memory(self) -> str:
        """读取 MEMORY.md 内容"""
        if not self.memory_file.exists():
            return self._create_default_memory()
        return self.memory_file.read_text(encoding='utf-8')
    
    def _create_default_memory(self) -> str:
        """创建默认 MEMORY.md 模板"""
        return """# MEMORY.md - Long-Term Memory

> Your curated memories. Distill from daily notes. Remove when outdated.

---

## About [Human Name]

### Key Context
[Important background that affects how you help them]

### Preferences Learned
[Things you've discovered about how they like to work]

### Important Dates
[Birthdays, anniversaries, deadlines they care about]

---

## Lessons Learned

### [Date] - [Topic]
[What happened and what you learned]

---

## Ongoing Context

### Active Projects
[What's currently in progress]

### Key Decisions Made
[Important decisions and their reasoning]

### Things to Remember
[Anything else important for continuity]

---

## Relationships & People

### [Person Name]
[Who they are, relationship to human, relevant context]

---

## 📋 会话记忆索引

> 自动生成的会话摘要索引，按时间倒序排列

_Session Memory 功能已启用，长会话将自动生成摘要_

---

*Review and update periodically. Daily notes are raw; this is curated.*
"""
    
    def _write_memory(self, content: str):
        """写入 MEMORY.md"""
        self.memory_file.write_text(content, encoding='utf-8')
        logger.debug(f"MEMORY.md 已更新 ({len(content)} bytes)")
    
    def _create_index_entry(self, summary: SessionSummary) -> str:
        """创建索引条目"""
        timestamp = summary.summary_time.strftime('%Y-%m-%d %H:%M')
        decisions_count = len(summary.decisions)
        todos_total = len(summary.todos)
        todos_done = sum(1 for t in summary.todos if t.done)
        
        # 状态图标
        type_icon = '🔵' if summary.session_type == 'main' else '🟡'
        
        entry = f"""### {type_icon} [{timestamp}] {summary.session_type}

- **ID**: `{summary.session_id[:8]}`
- **消息**: #{summary.message_range[0]} - #{summary.message_range[1]} ({summary.message_count} 条)
- **决策**: {decisions_count} 项
- **待办**: {todos_total} 项 ({todos_done} 已完成)
- **摘要**: [{summary.file_path.split('/')[-1] if summary.file_path else 'N/A'}](./{self.config.sessions_dir}/{summary.file_path.split('/')[-1] if summary.file_path else ''})

"""
        return entry
    
    def update_session_index(self, summary: SessionSummary):
        """更新会话索引"""
        content = self._read_memory()
        
        # 创建新条目
        new_entry = self._create_index_entry(summary)
        
        # 查找会话索引章节
        if self.SESSION_SECTION_START in content:
            # 找到章节位置
            section_start = content.find(self.SESSION_SECTION_START)
            section_end = content.find(self.SESSION_SECTION_END, section_start)
            
            if section_end == -1:
                section_end = len(content)
            
            # 提取章节内容
            before_section = content[:section_start]
            section_content = content[section_start:section_end]
            after_section = content[section_end:]
            
            # 在章节开头插入新条目（在标题行之后）
            lines = section_content.split('\n')
            insert_pos = 0
            for i, line in enumerate(lines):
                if line.startswith('_') or line.strip() == '':
                    insert_pos = i
                    break
            
            lines.insert(insert_pos, '\n' + new_entry)
            new_section = '\n'.join(lines)
            
            # 重组内容
            content = before_section + new_section + after_section
        else:
            # 添加新章节
            content += f"\n\n{self.SESSION_SECTION_START}\n\n{new_entry}\n{self.SESSION_SECTION_END}\n"
        
        # 硬截断保护
        content = self._truncate_if_needed(content)
        
        # 写入文件
        self._write_memory(content)
        
        # 更新 JSON 索引
        self._update_json_index(summary)
    
    def _truncate_if_needed(self, content: str) -> str:
        """硬截断保护"""
        lines = content.split('\n')
        
        # 检查行数
        if len(lines) > self.config.max_index_lines:
            lines = self._smart_truncate(lines)
        
        content = '\n'.join(lines)
        
        # 检查字节
        content_bytes = content.encode('utf-8')
        if len(content_bytes) > self.config.max_index_bytes:
            # 字节截断
            content = content[:self.config.max_index_bytes]
            logger.warning(f"MEMORY.md 已截断至 {self.config.max_index_bytes} bytes")
        
        return content
    
    def _smart_truncate(self, lines: List[str]) -> List[str]:
        """智能截断，保留重要章节"""
        # 分类行
        header_lines = []      # 头部元信息
        session_lines = []     # 会话索引
        other_lines = []       # 其他内容
        
        in_session_section = False
        current_section = 'header'
        
        for line in lines:
            if self.SESSION_SECTION_START in line:
                in_session_section = True
                current_section = 'session'
                session_lines.append(line)
            elif in_session_section:
                if line.startswith('## ') and self.SESSION_SECTION_START not in line:
                    in_session_section = False
                    current_section = 'other'
                    other_lines.append(line)
                else:
                    session_lines.append(line)
            elif current_section == 'header':
                header_lines.append(line)
            else:
                other_lines.append(line)
        
        # 计算可用空间
        reserved = len(header_lines) + len(other_lines)
        available = self.config.max_index_lines - reserved - 20  # 预留缓冲
        
        # 保留最近的会话条目
        # 找到条目的起始位置
        entry_starts = []
        for i, line in enumerate(session_lines):
            if line.startswith('### '):
                entry_starts.append(i)
        
        if entry_starts and len(session_lines) > available:
            # 计算可以保留的条目数
            avg_entry_len = len(session_lines) / len(entry_starts) if entry_starts else 20
            max_entries = int(available / avg_entry_len)
            
            # 保留最新的条目
            keep_from = entry_starts[-max_entries] if max_entries < len(entry_starts) else 0
            session_lines = session_lines[:3] + session_lines[keep_from:]  # 保留标题行
        
        logger.info(f"智能截断: {len(lines)} -> {len(header_lines) + len(session_lines) + len(other_lines)} lines")
        
        return header_lines + session_lines + other_lines
    
    def _update_json_index(self, summary: SessionSummary):
        """更新 JSON 索引文件"""
        # 读取现有索引
        index_data = self._load_json_index()
        
        # 添加新条目
        entry = {
            'id': summary.session_id[:8],
            'full_id': summary.session_id,
            'type': summary.session_type,
            'start_time': summary.start_time.isoformat() if summary.start_time else None,
            'summary_time': summary.summary_time.isoformat(),
            'message_count': summary.message_count,
            'decisions': len(summary.decisions),
            'todos': len(summary.todos),
            'todos_done': sum(1 for t in summary.todos if t.done),
            'file': summary.file_path.split('/')[-1] if summary.file_path else None
        }
        
        # 检查是否已存在，更新或添加
        existing_idx = None
        for i, e in enumerate(index_data['sessions']):
            if e['full_id'] == summary.session_id:
                existing_idx = i
                break
        
        if existing_idx is not None:
            index_data['sessions'][existing_idx] = entry
        else:
            index_data['sessions'].insert(0, entry)  # 新条目在最前面
        
        # 限制条目数
        max_entries = 100
        if len(index_data['sessions']) > max_entries:
            index_data['sessions'] = index_data['sessions'][:max_entries]
        
        # 更新清理时间
        index_data['last_cleanup'] = datetime.now().isoformat()
        
        # 写入文件
        self._save_json_index(index_data)
    
    def _load_json_index(self) -> Dict[str, Any]:
        """加载 JSON 索引"""
        if not self.index_file.exists():
            return {'sessions': [], 'last_cleanup': None}
        
        try:
            return json.loads(self.index_file.read_text(encoding='utf-8'))
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"无法加载索引文件: {e}")
            return {'sessions': [], 'last_cleanup': None}
    
    def _save_json_index(self, data: Dict[str, Any]):
        """保存 JSON 索引"""
        self.index_file.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding='utf-8'
        )
    
    def get_relevant_summaries(
        self, 
        query: str = None,
        session_type: str = None,
        limit: int = 5
    ) -> List[Path]:
        """获取相关会话摘要文件
        
        Args:
            query: 查询关键词（目前仅支持简单匹配）
            session_type: 会话类型过滤 ('main' | 'subagent')
            limit: 最大返回数量
            
        Returns:
            摘要文件路径列表
        """
        # 获取所有摘要文件
        pattern = "session-*.md"
        summaries = list(self.sessions_dir.glob(pattern))
        
        # 按修改时间排序（最新优先）
        summaries.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        
        # 类型过滤
        if session_type:
            summaries = [
                s for s in summaries 
                if f"session-{session_type}-" in s.name
            ]
        
        # 简单关键词匹配（如果提供了查询）
        if query:
            matched = []
            for s in summaries:
                try:
                    content = s.read_text(encoding='utf-8').lower()
                    if query.lower() in content:
                        matched.append(s)
                except IOError:
                    continue
            summaries = matched
        
        return summaries[:limit]
    
    def get_recent_summaries(self, days: int = 7, limit: int = 10) -> List[Path]:
        """获取最近 N 天的摘要"""
        import time
        
        cutoff_time = time.time() - (days * 24 * 60 * 60)
        
        summaries = []
        for f in self.sessions_dir.glob("session-*.md"):
            if f.stat().st_mtime >= cutoff_time:
                summaries.append(f)
        
        # 按修改时间排序
        summaries.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        
        return summaries[:limit]
    
    def cleanup_old_summaries(self, max_age_days: int = 30, keep_count: int = 50):
        """清理过期摘要
        
        Args:
            max_age_days: 最大保留天数
            keep_count: 最少保留数量
        """
        import time
        
        cutoff_time = time.time() - (max_age_days * 24 * 60 * 60)
        
        summaries = list(self.sessions_dir.glob("session-*.md"))
        summaries.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        
        deleted = 0
        for i, f in enumerate(summaries):
            # 保留最新的 keep_count 个
            if i < keep_count:
                continue
            
            # 删除过期的
            if f.stat().st_mtime < cutoff_time:
                try:
                    f.unlink()
                    deleted += 1
                    logger.debug(f"已删除过期摘要: {f.name}")
                except OSError as e:
                    logger.warning(f"删除失败: {f.name}: {e}")
        
        if deleted > 0:
            logger.info(f"清理了 {deleted} 个过期摘要")
        
        return deleted
    
    def build_summary_context(self, summaries: List[Path]) -> str:
        """构建摘要上下文文本
        
        用于注入到新会话的系统提示中
        """
        if not summaries:
            return ""
        
        context_parts = ["## 历史会话摘要\n"]
        
        for i, summary_path in enumerate(summaries[:3]):  # 最多加载 3 个
            try:
                content = summary_path.read_text(encoding='utf-8')
                # 提取关键部分
                lines = content.split('\n')
                
                # 获取元信息
                meta_info = []
                for line in lines[:15]:  # 前 15 行通常包含元信息
                    if line.startswith('- **'):
                        meta_info.append(line)
                
                context_parts.append(f"### [{summary_path.name}]\n")
                context_parts.append('\n'.join(meta_info[:5]))
                context_parts.append("\n[...]\n\n")
                
            except IOError as e:
                logger.warning(f"无法读取摘要: {summary_path}: {e}")
                continue
        
        return '\n'.join(context_parts)
