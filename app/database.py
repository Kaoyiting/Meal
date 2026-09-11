"""
Order Service 資料庫連接管理

提供 PostgreSQL 和 Redis 的非同步連接管理
支援連接池、健康檢查和優雅關閉
"""

import logging
from typing import AsyncGenerator, Optional

import redis.asyncio as redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession, 
    async_sessionmaker, 
    create_async_engine
)
from sqlalchemy.orm import declarative_base

from .config import get_settings
from .exceptions import DatabaseError

logger = logging.getLogger(__name__)

# 建立 SQLAlchemy Base 類別
Base = declarative_base()

# 全域變數
engine = None
async_session_maker = None
redis_client: Optional[redis.Redis] = None


async def init_database() -> None:
    """初始化資料庫連接"""
    global engine, async_session_maker
    
    settings = get_settings()
    
    try:
        # 建立 PostgreSQL 非同步引擎
        engine = create_async_engine(
            settings.DATABASE_URL,
            pool_size=settings.DATABASE_POOL_SIZE,
            max_overflow=settings.DATABASE_MAX_OVERFLOW,
            pool_pre_ping=True,  # 連接前檢查
            pool_recycle=3600,   # 1小時後回收連接
            echo=settings.DEBUG,  # 開發環境顯示 SQL
        )
        
        # 建立會話工廠
        async_session_maker = async_sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False
        )
        
        logger.info("PostgreSQL 資料庫連接已初始化")
        
    except Exception as e:
        logger.error(f"PostgreSQL 資料庫初始化失敗: {e}")
        raise DatabaseError(f"資料庫初始化失敗: {e}")


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """取得資料庫會話
    
    用於 FastAPI 依賴注入
    自動管理會話的開啟和關閉
    """
    if not async_session_maker:
        raise DatabaseError("資料庫未初始化")
    
    async with async_session_maker() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_redis() -> None:
    """初始化 Redis 連接"""
    global redis_client
    
    settings = get_settings()
    
    try:
        # 建立 Redis 非同步客戶端
        redis_client = redis.from_url(
            settings.REDIS_URL,
            password=settings.REDIS_PASSWORD,
            db=settings.REDIS_DB,
            decode_responses=True,  # 自動解碼回應為字串
            retry_on_timeout=True,
            socket_connect_timeout=5,
            socket_timeout=5,
        )
        
        # 測試連接
        await redis_client.ping()
        
        logger.info("Redis 連接已初始化")
        
    except Exception as e:
        logger.error(f"Redis 初始化失敗: {e}")
        raise DatabaseError(f"Redis 初始化失敗: {e}")


async def close_database() -> None:
    """關閉資料庫連接"""
    global engine, redis_client
    
    try:
        if engine:
            await engine.dispose()
            logger.info("PostgreSQL 連接已關閉")
        
        if redis_client:
            await redis_client.close()
            logger.info("Redis 連接已關閉")
            
    except Exception as e:
        logger.error(f"關閉資料庫連接時發生錯誤: {e}")


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """
    取得資料庫會話 (用於 FastAPI 依賴注入)
    
    使用方式：
    @app.get("/")
    async def read_data(db: AsyncSession = Depends(get_async_session)):
        result = await db.execute(select(Model))
        return result.scalars().all()
    """
    if not async_session_maker:
        raise DatabaseError("資料庫尚未初始化")
    
    async with async_session_maker() as session:
        try:
            yield session
        except Exception as e:
            await session.rollback()
            logger.error(f"資料庫會話錯誤: {e}")
            raise DatabaseError(f"資料庫操作失敗: {e}")
        finally:
            await session.close()


def get_redis() -> redis.Redis:
    """
    取得 Redis 客戶端 (用於 FastAPI 依賴注入)
    
    使用方式：
    @app.get("/")
    async def read_cache(redis: Redis = Depends(get_redis)):
        value = await redis.get("key")
        return {"value": value}
    """
    if not redis_client:
        raise DatabaseError("Redis 尚未初始化")
    
    return redis_client


async def check_database_health() -> dict:
    """檢查資料庫連接健康狀態"""
    health_status = {
        "postgresql": {"status": "unknown", "details": None},
        "redis": {"status": "unknown", "details": None}
    }
    
    # 檢查 PostgreSQL
    try:
        if engine:
            async with engine.begin() as conn:
                result = await conn.execute(text("SELECT 1"))
                if result.scalar() == 1:
                    health_status["postgresql"]["status"] = "healthy"
                else:
                    health_status["postgresql"]["status"] = "unhealthy"
                    health_status["postgresql"]["details"] = "查詢回應異常"
        else:
            health_status["postgresql"]["status"] = "not_initialized"
            health_status["postgresql"]["details"] = "資料庫引擎未初始化"
            
    except Exception as e:
        health_status["postgresql"]["status"] = "unhealthy"
        health_status["postgresql"]["details"] = str(e)
        logger.error(f"PostgreSQL 健康檢查失敗: {e}")
    
    # 檢查 Redis
    try:
        if redis_client:
            pong = await redis_client.ping()
            if pong:
                health_status["redis"]["status"] = "healthy"
            else:
                health_status["redis"]["status"] = "unhealthy"
                health_status["redis"]["details"] = "ping 回應異常"
        else:
            health_status["redis"]["status"] = "not_initialized"
            health_status["redis"]["details"] = "Redis 客戶端未初始化"
            
    except Exception as e:
        health_status["redis"]["status"] = "unhealthy"
        health_status["redis"]["details"] = str(e)
        logger.error(f"Redis 健康檢查失敗: {e}")
    
    return health_status


# Redis 基本操作 (符合需求文件的「基本操作」要求)