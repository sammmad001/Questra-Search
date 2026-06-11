"""
历史记录路由 - 分页浏览和搜索
"""
from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from aiosqlite import Connection

from app.auth import require_user
from app.database import get_db

router = APIRouter(prefix="/api/history", tags=["history"])


@router.get("")
async def list_history(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    search: str = Query("", max_length=100),
    user: dict = Depends(require_user),
    db: Connection = Depends(get_db),
):
    """分页获取历史消息（仅当前用户）"""
    if isinstance(user, JSONResponse):
        return user

    offset = (page - 1) * limit
    user_id = user["id"]

    if search:
        # 搜索模式：匹配消息内容或会话标题
        like = f"%{search}%"
        count_sql = """
            SELECT COUNT(*) as cnt FROM messages m
            JOIN sessions s ON m.session_id = s.id
            WHERE s.user_id = ? AND s.is_deleted = 0
            AND (m.content LIKE ? OR s.title LIKE ?)
        """
        query_sql = """
            SELECT m.id, m.session_id, s.title as session_title, m.role, m.content,
                   m.model, m.total_tokens, m.created_at
            FROM messages m
            JOIN sessions s ON m.session_id = s.id
            WHERE s.user_id = ? AND s.is_deleted = 0
            AND (m.content LIKE ? OR s.title LIKE ?)
            ORDER BY m.created_at DESC
            LIMIT ? OFFSET ?
        """
        params_count = (user_id, like, like)
        params_query = (user_id, like, like, limit, offset)
    else:
        # 列表模式：获取所有消息
        count_sql = """
            SELECT COUNT(*) as cnt FROM messages m
            JOIN sessions s ON m.session_id = s.id
            WHERE s.user_id = ? AND s.is_deleted = 0
        """
        query_sql = """
            SELECT m.id, m.session_id, s.title as session_title, m.role, m.content,
                   m.model, m.total_tokens, m.created_at
            FROM messages m
            JOIN sessions s ON m.session_id = s.id
            WHERE s.user_id = ? AND s.is_deleted = 0
            ORDER BY m.created_at DESC
            LIMIT ? OFFSET ?
        """
        params_count = (user_id,)
        params_query = (user_id, limit, offset)

    cursor = await db.execute(count_sql, params_count)
    total = (await cursor.fetchone())["cnt"]

    cursor = await db.execute(query_sql, params_query)
    rows = await cursor.fetchall()

    items = [
        {
            "id": r["id"],
            "session_id": r["session_id"],
            "session_title": r["session_title"],
            "role": r["role"],
            "content": r["content"][:200] if r["role"] == "user" else r["content"][:500],
            "model": r["model"],
            "total_tokens": r["total_tokens"],
            "created_at": r["created_at"],
        }
        for r in rows
    ]

    return {"items": items, "total": total, "page": page, "limit": limit}


@router.get("/{message_id}")
async def get_message(
    message_id: int,
    user: dict = Depends(require_user),
    db: Connection = Depends(get_db),
):
    """获取单条消息详情"""
    if isinstance(user, JSONResponse):
        return user

    import json
    cursor = await db.execute(
        """SELECT m.*, s.title as session_title
           FROM messages m
           JOIN sessions s ON m.session_id = s.id
           WHERE m.id = ? AND s.user_id = ?""",
        (message_id, user["id"])
    )
    r = await cursor.fetchone()
    if not r:
        return JSONResponse(status_code=404, content={"detail": "消息不存在"})

    return {
        "id": r["id"],
        "session_id": r["session_id"],
        "session_title": r["session_title"],
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
