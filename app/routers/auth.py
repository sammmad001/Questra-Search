"""
认证路由 - 登录、注册、账户管理、邀请码管理
"""
import secrets

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from aiosqlite import Connection

from app.auth import verify_password, create_token, get_current_user, require_user, hash_password
from app.database import get_db
from app.config import COOKIE_SECURE
from app.models import (
    LoginRequest, RegisterRequest, UpdateProfileRequest, ChangePasswordRequest,
    InviteCodeCreate,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


# ============ 登录 / 登出 ============

@router.post("/login")
async def login(body: LoginRequest, db: Connection = Depends(get_db)):
    """用户登录"""
    cursor = await db.execute(
        "SELECT id, username, display_name, email, password_hash FROM users WHERE username = ? AND is_active = 1",
        (body.username,)
    )
    row = await cursor.fetchone()
    if not row or not verify_password(body.password, row["password_hash"]):
        return JSONResponse(status_code=401, content={"ok": False, "detail": "用户名或密码错误"})

    # 更新最后登录时间
    await db.execute(
        "UPDATE users SET last_login_at = datetime('now') WHERE id = ?",
        (row["id"],)
    )
    await db.commit()

    # 签发 JWT
    token = create_token(row["id"], row["username"])

    response = JSONResponse(content={
        "ok": True,
        "token": token,
        "user": {
            "id": row["id"],
            "username": row["username"],
            "display_name": row["display_name"],
            "email": row["email"] or "",
        }
    })
    # 设置 HttpOnly Cookie
    response.set_cookie(
        key="questra_search_token",
        value=token,
        httponly=True,
        samesite="lax",
        secure=COOKIE_SECURE,
        path="/",
        max_age=60 * 60 * 24 * 7,  # 7天
    )
    return response


@router.post("/logout")
async def logout():
    """登出 - 清除 Cookie"""
    response = JSONResponse(content={"ok": True})
    response.delete_cookie(key="questra_search_token", path="/")
    return response


# ============ 注册 ============

@router.post("/register")
async def register(body: RegisterRequest, db: Connection = Depends(get_db)):
    """用户注册（需要邀请码）"""
    # 1. 验证邀请码
    cursor = await db.execute(
        "SELECT id, used_by FROM invite_codes WHERE code = ?",
        (body.invite_code,)
    )
    code_row = await cursor.fetchone()
    if not code_row:
        return JSONResponse(status_code=400, content={"ok": False, "detail": "邀请码无效"})
    if code_row["used_by"] is not None:
        return JSONResponse(status_code=400, content={"ok": False, "detail": "邀请码已被使用"})

    # 2. 检查用户名是否已存在
    cursor = await db.execute(
        "SELECT id FROM users WHERE username = ?",
        (body.username,)
    )
    if await cursor.fetchone():
        return JSONResponse(status_code=400, content={"ok": False, "detail": "用户名已存在"})

    # 3. 检查邮箱是否已被使用（如果提供了邮箱）
    if body.email:
        cursor = await db.execute(
            "SELECT id FROM users WHERE email = ? AND email != ''",
            (body.email,)
        )
        if await cursor.fetchone():
            return JSONResponse(status_code=400, content={"ok": False, "detail": "该邮箱已被注册"})

    # 4. 创建用户
    display_name = body.display_name or body.username
    password_hash = hash_password(body.password)

    cursor = await db.execute(
        "INSERT INTO users (username, password_hash, display_name, email) VALUES (?, ?, ?, ?)",
        (body.username, password_hash, display_name, body.email)
    )
    user_id = cursor.lastrowid

    # 5. 标记邀请码已使用
    await db.execute(
        "UPDATE invite_codes SET used_by = ?, used_at = datetime('now') WHERE id = ?",
        (user_id, code_row["id"])
    )
    await db.commit()

    # 6. 自动登录
    token = create_token(user_id, body.username)

    response = JSONResponse(content={
        "ok": True,
        "token": token,
        "user": {
            "id": user_id,
            "username": body.username,
            "display_name": display_name,
            "email": body.email or "",
        }
    })
    response.set_cookie(
        key="questra_search_token",
        value=token,
        httponly=True,
        samesite="lax",
        secure=COOKIE_SECURE,
        path="/",
        max_age=60 * 60 * 24 * 7,
    )
    return response


# ============ 账户信息 ============

@router.get("/me")
async def me(user: dict = Depends(get_current_user), db: Connection = Depends(get_db)):
    """获取当前登录用户的完整账户信息（含统计）"""
    if not user:
        return JSONResponse(status_code=401, content={"detail": "未登录"})

    user_id = user["id"]

    # 基本信息
    cursor = await db.execute(
        "SELECT id, username, display_name, email, is_active, created_at, last_login_at FROM users WHERE id = ?",
        (user_id,)
    )
    row = await cursor.fetchone()
    if not row:
        return JSONResponse(status_code=404, content={"detail": "用户不存在"})

    # 统计信息
    cursor = await db.execute(
        "SELECT COUNT(*) as cnt FROM sessions WHERE user_id = ? AND is_deleted = 0",
        (user_id,)
    )
    total_sessions = (await cursor.fetchone())["cnt"]

    cursor = await db.execute(
        """SELECT COUNT(*) as cnt, COALESCE(SUM(m.total_tokens), 0) as total_tokens
           FROM messages m JOIN sessions s ON m.session_id = s.id
           WHERE s.user_id = ? AND s.is_deleted = 0""",
        (user_id,)
    )
    stats = await cursor.fetchone()

    return {
        "id": row["id"],
        "username": row["username"],
        "display_name": row["display_name"] or "",
        "email": row["email"] or "",
        "is_active": row["is_active"],
        "created_at": row["created_at"] or "",
        "last_login_at": row["last_login_at"] or "",
        "total_sessions": total_sessions,
        "total_messages": stats["cnt"],
        "total_tokens": stats["total_tokens"],
    }


# ============ 账户管理 ============

@router.put("/profile")
async def update_profile(
    body: UpdateProfileRequest,
    user: dict = Depends(require_user),
    db: Connection = Depends(get_db),
):
    """更新个人资料（昵称、邮箱）"""
    if isinstance(user, JSONResponse):
        return user

    updates = []
    params = []

    if body.display_name is not None:
        updates.append("display_name = ?")
        params.append(body.display_name.strip())

    if body.email is not None:
        email = body.email.strip()
        # 检查邮箱是否已被其他用户使用
        if email:
            cursor = await db.execute(
                "SELECT id FROM users WHERE email = ? AND id != ? AND email != ''",
                (email, user["id"])
            )
            if await cursor.fetchone():
                return JSONResponse(status_code=400, content={"ok": False, "detail": "该邮箱已被其他用户使用"})
        updates.append("email = ?")
        params.append(email)

    if not updates:
        return {"ok": True, "detail": "无变更"}

    params.append(user["id"])
    await db.execute(
        f"UPDATE users SET {', '.join(updates)} WHERE id = ?",
        params
    )
    await db.commit()
    return {"ok": True, "detail": "资料更新成功"}


@router.post("/change-password")
async def change_password(
    body: ChangePasswordRequest,
    user: dict = Depends(require_user),
    db: Connection = Depends(get_db),
):
    """修改密码"""
    if isinstance(user, JSONResponse):
        return user

    cursor = await db.execute(
        "SELECT password_hash FROM users WHERE id = ?", (user["id"],)
    )
    row = await cursor.fetchone()
    if not row or not verify_password(body.old_password, row["password_hash"]):
        return JSONResponse(status_code=400, content={"ok": False, "detail": "旧密码错误"})

    await db.execute(
        "UPDATE users SET password_hash = ? WHERE id = ?",
        (hash_password(body.new_password), user["id"]),
    )
    await db.commit()
    return {"ok": True, "detail": "密码修改成功"}


# ============ 邀请码管理（仅管理员/已登录用户可用） ============

@router.post("/invite-codes")
async def create_invite_codes(
    body: InviteCodeCreate,
    user: dict = Depends(require_user),
    db: Connection = Depends(get_db),
):
    """生成邀请码（登录用户可生成，用于邀请新用户）"""
    if isinstance(user, JSONResponse):
        return user

    count = min(body.count, 10)  # 最多一次生成10个
    codes = []

    for _ in range(count):
        code = secrets.token_urlsafe(8)[:10].upper()  # 10位大写码
        await db.execute(
            "INSERT INTO invite_codes (code, created_by) VALUES (?, ?)",
            (code, user["id"])
        )
        codes.append(code)

    await db.commit()
    return {"ok": True, "codes": codes}


@router.get("/invite-codes")
async def list_invite_codes(
    user: dict = Depends(require_user),
    db: Connection = Depends(get_db),
):
    """查看当前用户创建的邀请码"""
    if isinstance(user, JSONResponse):
        return user

    cursor = await db.execute(
        """SELECT ic.id, ic.code, ic.used_by, ic.used_at, ic.created_at,
           u.username as used_by_username
           FROM invite_codes ic
           LEFT JOIN users u ON ic.used_by = u.id
           WHERE ic.created_by = ?
           ORDER BY ic.created_at DESC""",
        (user["id"],)
    )
    rows = await cursor.fetchall()
    items = [
        {
            "id": r["id"],
            "code": r["code"],
            "used": r["used_by"] is not None,
            "used_by": r["used_by_username"] or None,
            "used_at": r["used_at"] or "",
            "created_at": r["created_at"] or "",
        }
        for r in rows
    ]
    return {"items": items}
