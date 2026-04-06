# -*- coding: utf-8 -*-
"""
API Configuration - Pydantic Settings

Reads configuration from environment variables and .env file.
Fails fast on missing required settings.
"""
import os
from typing import Optional
from urllib.parse import quote_plus

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator


class Settings(BaseSettings):
    """Application settings loaded from .env"""

    model_config = SettingsConfigDict(
        env_file=os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env'),
        env_file_encoding='utf-8',
        case_sensitive=False,
        extra='ignore',
    )

    # ============================================================
    # Application
    # ============================================================
    api_host: str = Field(default='0.0.0.0', alias='API_HOST')
    api_port: int = Field(default=8000, alias='API_PORT')
    api_workers: int = Field(default=2, alias='API_WORKERS')
    api_debug: bool = Field(default=True, alias='API_DEBUG')
    api_base_url: str = Field(default='http://localhost:8000', alias='API_BASE_URL')
    app_name: str = 'myTrader API'
    app_version: str = '0.1.0'
    log_level: str = Field(default='INFO', alias='LOG_LEVEL')
    log_dir: str = Field(default='logs', alias='LOG_DIR')

    # ============================================================
    # Database (reuse existing LOCAL_DB_* / ONLINE_DB_* pattern)
    # ============================================================
    db_env: str = Field(default='local', alias='DB_ENV')

    local_db_host: str = Field(default='localhost', alias='LOCAL_DB_HOST')
    local_db_port: int = Field(default=3306, alias='LOCAL_DB_PORT')
    local_db_user: str = Field(default='root', alias='LOCAL_DB_USER')
    local_db_password: str = Field(default='', alias='LOCAL_DB_PASSWORD')
    local_db_name: str = Field(default='mytrader', alias='LOCAL_DB_NAME')

    online_db_host: str = Field(default='', alias='ONLINE_DB_HOST')
    online_db_port: int = Field(default=3306, alias='ONLINE_DB_PORT')
    online_db_user: str = Field(default='', alias='ONLINE_DB_USER')
    online_db_password: str = Field(default='', alias='ONLINE_DB_PASSWORD')
    online_db_name: str = Field(default='', alias='ONLINE_DB_NAME')

    # SQLAlchemy pool settings
    db_pool_size: int = 5
    db_pool_max_overflow: int = 10
    db_pool_recycle: int = 3600

    # ============================================================
    # Redis
    # ============================================================
    redis_host: str = Field(default='localhost', alias='REDIS_HOST')
    redis_port: int = Field(default=6379, alias='REDIS_PORT')
    redis_password: str = Field(default='', alias='REDIS_PASSWORD')
    redis_db: int = Field(default=0, alias='REDIS_DB')

    # ============================================================
    # JWT
    # ============================================================
    jwt_secret_key: str = Field(default='', alias='JWT_SECRET_KEY')
    jwt_algorithm: str = Field(default='HS256', alias='JWT_ALGORITHM')
    jwt_access_token_expire_minutes: int = Field(default=30, alias='JWT_ACCESS_TOKEN_EXPIRE_MINUTES')
    jwt_refresh_token_expire_days: int = Field(default=7, alias='JWT_REFRESH_TOKEN_EXPIRE_DAYS')

    # ============================================================
    # Celery
    # ============================================================
    celery_broker_url: str = Field(default='redis://localhost:6379/1', alias='CELERY_BROKER_URL')
    celery_result_backend: str = Field(default='redis://localhost:6379/2', alias='CELERY_RESULT_BACKEND')

    @property
    def database_url(self) -> str:
        """Build SQLAlchemy async database URL based on current env"""
        if self.db_env == 'online' and self.online_db_host:
            pwd = quote_plus(self.online_db_password)
            return (
                f"mysql+aiomysql://{self.online_db_user}:{pwd}"
                f"@{self.online_db_host}:{self.online_db_port}/{self.online_db_name}"
                f"?charset=utf8mb4"
            )
        pwd = quote_plus(self.local_db_password)
        return (
            f"mysql+aiomysql://{self.local_db_user}:{pwd}"
            f"@{self.local_db_host}:{self.local_db_port}/{self.local_db_name}"
            f"?charset=utf8mb4"
        )

    @property
    def sync_database_url(self) -> str:
        """Build SQLAlchemy sync database URL (for Alembic / legacy code)"""
        if self.db_env == 'online' and self.online_db_host:
            pwd = quote_plus(self.online_db_password)
            return (
                f"mysql+pymysql://{self.online_db_user}:{pwd}"
                f"@{self.online_db_host}:{self.online_db_port}/{self.online_db_name}"
                f"?charset=utf8mb4"
            )
        pwd = quote_plus(self.local_db_password)
        return (
            f"mysql+pymysql://{self.local_db_user}:{pwd}"
            f"@{self.local_db_host}:{self.local_db_port}/{self.local_db_name}"
            f"?charset=utf8mb4"
        )

    @property
    def redis_url(self) -> str:
        """Build Redis URL"""
        if self.redis_password:
            return f"redis://:{self.redis_password}@{self.redis_host}:{self.redis_port}/{self.redis_db}"
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"

    def validate_startup(self) -> list[str]:
        """Validate critical settings on startup. Returns list of errors."""
        errors = []
        if not self.jwt_secret_key or self.jwt_secret_key == 'change-me-to-a-random-secret-key':
            if not self.api_debug:
                errors.append('JWT_SECRET_KEY must be set in production')
        return errors


# Singleton instance
settings = Settings()


def get_settings() -> Settings:
    """Return the singleton settings instance."""
    return settings
