"""
Order Service 配置管理和日誌設定

使用 Pydantic Settings 管理環境變數配置
支援結構化日誌和多環境配置
"""

import logging
import sys
from functools import lru_cache
from typing import List, Optional

from pydantic import validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """應用程式設定"""
    
    # === 應用程式基本設定 ===
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "Order Service"
    
    # === 安全設定 ===
    SECRET_KEY: str = "your-super-secret-key-change-in-production"
    JWT_SECRET_KEY: str = "your-jwt-secret-key-change-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_HOURS: int = 24
    
    # === 資料庫設定 ===
    DATABASE_URL: str = "postgresql+asyncpg://order_user:order_password@localhost:5432/order_db"
    DATABASE_POOL_SIZE: int = 20
    DATABASE_MAX_OVERFLOW: int = 30
    
    # === Redis 設定 ===
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_PASSWORD: Optional[str] = None
    REDIS_DB: int = 0
    
    # === RabbitMQ 設定 ===
    RABBITMQ_URL: str = "amqp://order_user:order_password@localhost:5672/order_vhost"
    RABBITMQ_EXCHANGE: str = "order_events"
    RABBITMQ_QUEUE_PREFIX: str = "order_service"
    
    # === CORS 設定 ===
    BACKEND_CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8080",
    ]
    FRONTEND_URL: Optional[str] = None
    ALLOWED_HOSTS: List[str] = ["localhost", "127.0.0.1"]
    
    # === 日誌設定 ===
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"  # json 或 text
    
    # === 外部服務設定 ===
    AUTH_SERVICE_URL: str = "http://localhost:8001"
    MENU_SERVICE_URL: str = "http://localhost:8002"
    INVENTORY_SERVICE_URL: str = "http://localhost:8003"
    
    # === Saga 設定 ===
    SAGA_TIMEOUT_SECONDS: int = 300
    SAGA_RETRY_ATTEMPTS: int = 3
    SAGA_RETRY_DELAY_SECONDS: int = 5
    
    # === 訊息發布設定 ===
    OUTBOX_PUBLISHER_INTERVAL_SECONDS: int = 5
    OUTBOX_BATCH_SIZE: int = 100
    
    @validator("ENVIRONMENT")
    def validate_environment(cls, v):
        """驗證環境設定"""
        allowed = ["development", "testing", "staging", "production"]
        if v not in allowed:
            raise ValueError(f"ENVIRONMENT 必須是 {allowed} 其中之一")
        return v
    
    @validator("LOG_LEVEL")
    def validate_log_level(cls, v):
        """驗證日誌級別"""
        allowed = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if v.upper() not in allowed:
            raise ValueError(f"LOG_LEVEL 必須是 {allowed} 其中之一")
        return v.upper()
    
    @validator("LOG_FORMAT")
    def validate_log_format(cls, v):
        """驗證日誌格式"""
        allowed = ["json", "text"]
        if v not in allowed:
            raise ValueError(f"LOG_FORMAT 必須是 {allowed} 其中之一")
        return v
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


def get_async_database_url(database_url: Optional[str] = None) -> str:
    """Normalize managed PostgreSQL URLs for SQLAlchemy's asyncpg driver."""
    url = database_url or get_settings().DATABASE_URL
    if url.startswith("postgres://"):
        return "postgresql+asyncpg://" + url.removeprefix("postgres://")
    if url.startswith("postgresql://"):
        return "postgresql+asyncpg://" + url.removeprefix("postgresql://")
    return url


@lru_cache()
def get_settings() -> Settings:
    """取得設定實例（單例模式）"""
    return Settings()


def setup_logging() -> None:
    """設定日誌系統"""
    settings = get_settings()
    
    # 設定日誌級別
    log_level = getattr(logging, settings.LOG_LEVEL)
    
    # 移除預設的處理器
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)
    
    if settings.LOG_FORMAT == "json":
        # JSON 格式日誌（生產環境推薦）
        import json
        import datetime
        
        class JSONFormatter(logging.Formatter):
            def format(self, record):
                log_entry = {
                    "timestamp": datetime.datetime.fromtimestamp(record.created).isoformat(),
                    "level": record.levelname,
                    "logger": record.name,
                    "message": record.getMessage(),
                    "module": record.module,
                    "function": record.funcName,
                    "line": record.lineno,
                }
                
                # 新增例外資訊
                if record.exc_info:
                    log_entry["exception"] = self.formatException(record.exc_info)
                
                # 新增額外欄位
                if hasattr(record, "user_id"):
                    log_entry["user_id"] = record.user_id
                if hasattr(record, "request_id"):
                    log_entry["request_id"] = record.request_id
                
                return json.dumps(log_entry, ensure_ascii=False)
        
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JSONFormatter())
    else:
        # 文字格式日誌（開發環境）
        format_string = (
            "%(asctime)s - %(name)s - %(levelname)s - "
            "%(module)s:%(funcName)s:%(lineno)d - %(message)s"
        )
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter(format_string))
    
    # 設定根記錄器
    logging.root.setLevel(log_level)
    logging.root.addHandler(handler)
    
    # 設定特定記錄器級別
    logging.getLogger("uvicorn").setLevel(logging.INFO)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("aio_pika").setLevel(logging.WARNING)
    
    # 記錄啟動資訊
    logger = logging.getLogger(__name__)
    logger.info(
        "日誌系統已啟動",
        extra={
            "environment": settings.ENVIRONMENT,
            "log_level": settings.LOG_LEVEL,
            "log_format": settings.LOG_FORMAT
        }
    )


# 建立全域設定實例
settings = get_settings()
