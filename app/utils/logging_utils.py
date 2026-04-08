"""
日志标准化工具
统一格式 + request_id 上下文追踪
"""

import logging
import sys
import uuid
from contextvars import ContextVar
from typing import Optional
from functools import wraps

from fastapi import Request

# ── Context ────────────────────────────────────────────────────────────────────

request_id_var: ContextVar[Optional[str]] = ContextVar("request_id", default=None)

def get_request_id() -> Optional[str]:
    return request_id_var.get()

def set_request_id(rid: Optional[str] = None) -> str:
    if rid is None:
        rid = uuid.uuid4().hex[:16]
    request_id_var.set(rid)
    return rid

def clear_request_id():
    request_id_var.set(None)

# ── Filter ─────────────────────────────────────────────────────────────────────

class RequestIdFilter(logging.Filter):
    """为每条日志注入 request_id 字段"""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id() or "-"
        return True

# ── Formatter ──────────────────────────────────────────────────────────────────

LOG_FORMAT = (
    "%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | "
    "[%(request_id)s] %(message)s"
)
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

def new_formatter() -> logging.Formatter:
    return logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT)

# ── Setup ──────────────────────────────────────────────────────────────────────

def setup_logging(
    level: int = logging.INFO,
    handlers: Optional[list[logging.Handler]] = None,
) -> None:
    """
    为 root logger 配置统一格式 + request_id filter。

    Args:
        level:   日志级别（默认 INFO）
        handlers: 额外追加的 handler；默认只加 StreamHandler(sys.stderr)
    """
    root = logging.getLogger()
    root.setLevel(level)

    # 避免重复添加 handler（reload 场景）
    if not any(isinstance(h, logging.StreamHandler) and h.stream == sys.stderr
               for h in root.handlers):
        _default_handler = logging.StreamHandler(sys.stderr)
        _default_handler.setFormatter(new_formatter())
        root.addHandler(_default_handler)

    if handlers:
        for h in handlers:
            h.setFormatter(new_formatter())
            root.addHandler(h)

    # 全局 filter
    _rid_filter = RequestIdFilter()
    if not any(isinstance(f, RequestIdFilter) for f in root.filters):
        root.addFilter(_rid_filter)

    # 第三方库降噪
    for _lib in ("uvicorn", "fastapi", "httpx", "httpcore"):
        logging.getLogger(_lib).setLevel(logging.WARNING)


# ── FastAPI 集成 ──────────────────────────────────────────────────────────────

async def inject_request_id_middleware(request: Request, call_next):
    """
    中间件：在每个请求入口自动生成 request_id，
    通过 X-Request-ID header 允许客户端传入。
    """
    rid = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:16]
    set_request_id(rid)
    request.state.request_id = rid  # type: ignore[attr-defined]

    response = await call_next(request)
    response.headers["X-Request-ID"] = rid
    return response


def get_logger(name: str) -> logging.Logger:
    """
    获取带 request_id 追踪能力的 logger。
    等价于 logging.getLogger(name)，但推荐用此函数替代。
    """
    logger = logging.getLogger(name)
    if not any(isinstance(f, RequestIdFilter) for f in logger.filters):
        logger.addFilter(RequestIdFilter())
    return logger
