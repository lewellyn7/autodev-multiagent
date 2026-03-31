"""
Config - 统一配置管理，消除硬编码
"""
import os
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """应用配置"""
    
    # Admin
    admin_user: str = "admin"
    admin_password: str = "password"
    session_key: str = os.urandom(32).hex()
    
    # Database
    db_type: str = "sqlite"
    database_url: Optional[str] = None
    db_file: str = "data/gateway.db"
    
    # Rate Limiting
    rate_limit_requests: int = 60
    rate_limit_window: int = 60
    admin_rate_limit: int = 30
    
    # OAuth
    github_client_id: str = ""
    github_client_secret: str = ""
    github_redirect_uri: str = "http://localhost:8000/oauth/github/callback"
    
    # API Keys
    encryption_key: str = os.urandom(32).hex()
    
    # Security
    secret_key: str = os.urandom(32).hex()
    
    # CORS
    cors_origins: list = ["*"]
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


# 全局配置实例
settings = Settings()
