"""Real PostgreSQL fixtures used by the opt-in integration suite."""

import os

import pytest
import pytest_asyncio
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import Base
import app.models  # noqa: F401 - register every table on Base.metadata


@pytest_asyncio.fixture
async def postgres_test_engine():
    database_url = os.getenv("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("設定 TEST_DATABASE_URL 並啟動測試 PostgreSQL 才會執行整合測試")

    parsed_url = make_url(database_url)
    if not parsed_url.database or not parsed_url.database.lower().startswith("test_"):
        pytest.fail("整合測試只允許使用名稱以 test_ 開頭的資料庫")
    if parsed_url.get_backend_name() != "postgresql":
        pytest.fail("訂單／庫存整合測試必須使用 PostgreSQL")

    engine = create_async_engine(database_url, pool_pre_ping=True)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def postgres_session(postgres_test_engine):
    """每個測試重建隔離測試資料庫中的 schema，再交付真實 AsyncSession。"""
    async with postgres_test_engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(postgres_test_engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
        await session.rollback()
