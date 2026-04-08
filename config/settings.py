"""
config/settings.py - 采集系统全局设置
从环境变量加载，支持 .env 文件
"""
import os
from pathlib import Path

# 基础路径
ROOT_DIR = Path(__file__).parent.parent.resolve()

# ── 环境变量加载 ───────────────────────────────────────────────────────────────
try:
    from dotenv import load_dotenv
    env_file = ROOT_DIR / ".env"
    if env_file.exists():
        load_dotenv(env_file, override=True)
except ImportError:
    pass

# ── 浏览器配置 ────────────────────────────────────────────────────────────────
BROWSER_HEADLESS = os.getenv("BROWSER_HEADLESS", "true").lower() != "false"
BROWSER_STEALTH = os.getenv("BROWSER_STEALTH", "true").lower() != "false"
BROWSER_SLOW_MO = int(os.getenv("BROWSER_SLOW_MO", "0"))
BROWSER_TIMEOUT = int(os.getenv("BROWSER_TIMEOUT", "30000"))

# ── 采集目标配置 ──────────────────────────────────────────────────────────────
TARGET_URL = os.getenv(
    "TARGET_URL",
    "https://ggzy.sw.co.me.cn"
)

# ── 关键词配置 ────────────────────────────────────────────────────────────────
KEYWORDS = [
    "招标", "采购", "投标", "中标", "竞争性磋商",
    "竞争性谈判", "询价", "单一来源"
]
EXCLUDE_KEYWORDS = [
    "预告", "需求", "意向", "结果公告"
]

# ── 输出配置 ──────────────────────────────────────────────────────────────────
OUTPUT_DIR = os.getenv("OUTPUT_DIR", str(ROOT_DIR / "output"))

# ── 数据库配置 ───────────────────────────────────────────────────────────────
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://lewellyn:lewellyn@localhost:5432/procurement"
)

# ── Redis 配置 ───────────────────────────────────────────────────────────────
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# ── 限流配置 ──────────────────────────────────────────────────────────────────
RATE_LIMIT_PER_SECOND = float(os.getenv("RATE_LIMIT_PER_SECOND", "5.0"))
MAX_CONCURRENT = int(os.getenv("MAX_CONCURRENT", "20"))

# ── 兼容旧接口的 settings 对象 ─────────────────────────────────────────────────
class Settings:
    TARGET_URL = TARGET_URL
    HEADLESS = BROWSER_HEADLESS
    SLOW_MO = BROWSER_SLOW_MO
    KEYWORDS = KEYWORDS
    EXCLUDE_KEYWORDS = EXCLUDE_KEYWORDS
    OUTPUT_DIR = OUTPUT_DIR
    DATABASE_URL = DATABASE_URL
    REDIS_URL = REDIS_URL

settings = Settings()
