"""
会话管理路由 - CRUD
"""
from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from aiosqlite import Connection

from app.auth import require_user
from app.database import get_db
from app.models import SessionCreate, SessionRename

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


@router.get("")
async def list_sessions(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    user: dict = Depends(require_user),
    db: Connection = Depends(get_db),
):
    """获取当前用户的会话列表"""
    if isinstance(user, JSONResponse):
        return user

    offset = (page - 1) * limit

    # 总数
    cursor = await db.execute(
        "SELECT COUNT(*) as cnt FROM sessions WHERE user_id = ? AND is_deleted = 0",
        (user["id"],)
    )
    total = (await cursor.fetchone())["cnt"]

    # 列表（含最后一条消息的摘要）
    cursor = await db.execute(
        """SELECT s.id, s.title, s.model, s.created_at, s.updated_at,
           (SELECT COUNT(*) FROM messages WHERE session_id = s.id) as msg_count
           FROM sessions s
           WHERE s.user_id = ? AND s.is_deleted = 0
           ORDER BY s.updated_at DESC
           LIMIT ? OFFSET ?""",
        (user["id"], limit, offset)
    )
    rows = await cursor.fetchall()
    items = [
        {
            "id": r["id"],
            "title": r["title"],
            "model": r["model"],
            "created_at": r["created_at"],
            "updated_at": r["updated_at"],
            "msg_count": r["msg_count"],
        }
        for r in rows
    ]

    return {"items": items, "total": total}


@router.post("")
async def create_session(
    body: SessionCreate,
    user: dict = Depends(require_user),
    db: Connection = Depends(get_db),
):
    """创建新会话"""
    if isinstance(user, JSONResponse):
        return user

    from app.config import DEFAULT_MODEL
    model = body.model or DEFAULT_MODEL

    cursor = await db.execute(
        "INSERT INTO sessions (user_id, title, model) VALUES (?, ?, ?)",
        (user["id"], body.title, model)
    )
    await db.commit()

    session_id = cursor.lastrowid
    cursor = await db.execute(
        "SELECT id, title, model, created_at, updated_at FROM sessions WHERE id = ?",
        (session_id,)
    )
    row = await cursor.fetchone()
    return {
        "id": row["id"],
        "title": row["title"],
        "model": row["model"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


@router.get("/{session_id}")
async def get_session(
    session_id: int,
    user: dict = Depends(require_user),
    db: Connection = Depends(get_db),
):
    """获取会话详情（含所有消息）"""
    if isinstance(user, JSONResponse):
        return user

    # 验证会话属于当前用户
    cursor = await db.execute(
        "SELECT id, title, model, created_at, updated_at FROM sessions WHERE id = ? AND user_id = ? AND is_deleted = 0",
        (session_id, user["id"])
    )
    session = await cursor.fetchone()
    if not session:
        return JSONResponse(status_code=404, content={"detail": "会话不存在"})

    # 获取消息列表
    import json
    cursor = await db.execute(
        """SELECT id, session_id, role, content, model, thinking_text, tool_events,
           prompt_tokens, completion_tokens, total_tokens, reasoning_tokens,
           duration_ms, status, created_at
           FROM messages WHERE session_id = ?
           ORDER BY created_at ASC""",
        (session_id,)
    )
    rows = await cursor.fetchall()
    messages = []
    for r in rows:
        msg = {
            "id": r["id"],
            "session_id": r["session_id"],
            "role": r["role"],
            "content": r["content"],
            "model": r["model"],
            "thinking_text": r["thinking_text"] or "",
            "tool_events": json.loads(r["tool_events"] or "[]"),
            "prompt_tokens": r["prompt_tokens"],
            "completion_tokens": r["completion_tokens"],
            "total_tokens": r["total_tokens"],
            "reasoning_tokens": r["reasoning_tokens"],
            "duration_ms": r["duration_ms"],
            "status": r["status"],
            "created_at": r["created_at"],
        }
        messages.append(msg)

    return {
        "id": session["id"],
        "title": session["title"],
        "model": session["model"],
        "created_at": session["created_at"],
        "updated_at": session["updated_at"],
        "messages": messages,
    }


@router.patch("/{session_id}")
async def rename_session(
    session_id: int,
    body: SessionRename,
    user: dict = Depends(require_user),
    db: Connection = Depends(get_db),
):
    """重命名会话"""
    if isinstance(user, JSONResponse):
        return user

    cursor = await db.execute(
        "SELECT id FROM sessions WHERE id = ? AND user_id = ? AND is_deleted = 0",
        (session_id, user["id"])
    )
    if not await cursor.fetchone():
        return JSONResponse(status_code=404, content={"detail": "会话不存在"})

    await db.execute(
        "UPDATE sessions SET title = ?, updated_at = datetime('now') WHERE id = ?",
        (body.title, session_id)
    )
    await db.commit()
    return {"ok": True}


@router.delete("/{session_id}")
async def delete_session(
    session_id: int,
    user: dict = Depends(require_user),
    db: Connection = Depends(get_db),
):
    """软删除会话"""
    if isinstance(user, JSONResponse):
        return user

    cursor = await db.execute(
        "SELECT id FROM sessions WHERE id = ? AND user_id = ? AND is_deleted = 0",
        (session_id, user["id"])
    )
    if not await cursor.fetchone():
        return JSONResponse(status_code=404, content={"detail": "会话不存在"})

    await db.execute(
        "UPDATE sessions SET is_deleted = 1, updated_at = datetime('now') WHERE id = ?",
        (session_id,)
    )
    await db.commit()
    return {"ok": True}
