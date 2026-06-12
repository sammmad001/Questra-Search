"""
pytest fixtures — FastAPI TestClient + 临时文件数据库
"""
import os
import sys
import tempfile
import pytest
from fastapi.testclient import TestClient

# 确保项目根目录在 sys.path 中
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 测试环境变量（不在这里设 DATABASE_PATH，由 fixture 动态分配临时文件）
os.environ.setdefault("JWT_SECRET", "test-secret-for-pytest")
os.environ.setdefault("JWT_ALGORITHM", "HS256")
os.environ.setdefault("JWT_EXPIRE_HOURS", "168")
os.environ.setdefault("COOKIE_SECURE", "false")
os.environ.setdefault("PORT", "8900")
os.environ.setdefault("KB_AUTO_INGEST", "false")


@pytest.fixture
def client():
    """返回 FastAPI TestClient（使用临时文件数据库以确保连接间数据共享）"""
    import app.config as config

    # 创建临时数据库文件
    fd, db_path = tempfile.mkstemp(suffix=".db", prefix="questra_test_")
    os.close(fd)

    # 覆盖 DATABASE_PATH
    original_db_path = config.DATABASE_PATH
    config.DATABASE_PATH = db_path
    # 也覆盖模块级变量（database.py 中的 _db_path）
    import app.database as database_mod
    database_mod._db_path = db_path
    os.environ["DATABASE_PATH"] = db_path

    # 显式初始化数据库表结构（防御性：确保 TestClient lifespan 触发前表已存在）
    from app.database import init_db
    import asyncio
    asyncio.run(init_db())

    from app.main import app
    with TestClient(app) as c:
        yield c

    # 清理
    config.DATABASE_PATH = original_db_path
    database_mod._db_path = original_db_path
    try:
        os.unlink(db_path)
    except OSError:
        pass


@pytest.fixture
def auth_headers(client):
    """注册测试用户并登录，返回带 Cookie 的 auth headers"""
    # 注册（需要邀请码，先通过数据库直插邀请码）
    import asyncio
    import aiosqlite
    from app.database import _db_path, _ensure_db_path
    from app.config import DATABASE_PATH

    async def _setup():
        db = await aiosqlite.connect(DATABASE_PATH)
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys=ON")
        await db.execute(
            "INSERT INTO invite_codes (code, created_by) VALUES (?, ?)",
            ("TESTCODE123", None),
        )
        await db.commit()
        await db.close()

    asyncio.run(_setup())

    # 通过 API 注册
    resp = client.post("/api/auth/register", json={
        "username": "testuser",
        "password": "testpass123",
        "display_name": "Test User",
        "email": "test@example.com",
        "invite_code": "TESTCODE123",
    })
    if resp.status_code == 200:
        cookie = resp.headers.get("set-cookie", "")
        if cookie:
            return {"Cookie": cookie}

    # 备选：直接登录
    resp = client.post("/api/auth/login", json={
        "username": "testuser",
        "password": "testpass123",
    })
    cookie = resp.headers.get("set-cookie", "")
    return {"Cookie": cookie}
