"""
JWT 认证工具 + FastAPI 依赖注入
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, Request
from fastapi.responses import JSONResponse
from aiosqlite import Connection

from app.config import JWT_SECRET, JWT_ALGORITHM, JWT_EXPIRE_HOURS
from app.database import get_db

# 密码哈希
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_token(user_id: int, username: str) -> str:
    """签发 JWT token"""
    expire = datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRE_HOURS)
    payload = {
        "sub": str(user_id),
        "username": username,
        "exp": expire,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    """解码 JWT token，失败返回 None"""
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except JWTError:
        return None


def _extract_token(request: Request) -> Optional[str]:
    """从 Cookie 或 Authorization header 提取 token"""
    # 优先 Cookie
    token = request.cookies.get("questra_search_token")
    if token:
        return token
    # 其次 Authorization header
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    return None


# 不需要认证的路径前缀
_PUBLIC_PATHS = {
    "/api/auth/login",
    "/api/auth/register",
    "/api/health",
    "/api/models",
}


async def get_current_user(request: Request, db: Connection = Depends(get_db)) -> Optional[dict]:
    """获取当前认证用户，未认证返回 None"""
    token = _extract_token(request)
    if not token:
        return None

    payload = decode_token(token)
    if not payload:
        return None

    user_id = payload.get("sub")
    if not user_id:
        return None

    cursor = await db.execute(
        "SELECT id, username, display_name, email, is_active FROM users WHERE id = ? AND is_active = 1",
        (int(user_id),)
    )
    row = await cursor.fetchone()
    if not row:
        return None

    return {
        "id": row["id"],
        "username": row["username"],
        "display_name": row["display_name"],
        "email": row["email"] or "",
    }


async def require_user(request: Request, db: Connection = Depends(get_db)) -> dict:
    """FastAPI 依赖：必须登录，否则返回 401"""
    user = await get_current_user(request, db)
    if not user:
        return JSONResponse(status_code=401, content={"detail": "未登录或登录已过期"})
    return user
