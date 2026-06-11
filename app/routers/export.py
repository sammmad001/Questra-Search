"""
PDF 导出路由
"""
import asyncio
import json
import logging
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse, JSONResponse
from aiosqlite import Connection

from app.auth import require_user
from app.database import get_db
from app.models import ExportPdfRequest
from app.services.pdf_generator import generate_pdf

logger = logging.getLogger("questra_search.export")

router = APIRouter(prefix="/api/export", tags=["export"])


@router.post("/pdf")
async def export_pdf(
    body: ExportPdfRequest,
    user: dict = Depends(require_user),
    db: Connection = Depends(get_db),
):
    """导出消息为 PDF"""
    if isinstance(user, JSONResponse):
        return user

    # 获取消息
    cursor = await db.execute(
        """SELECT m.*, s.title as session_title
           FROM messages m
           JOIN sessions s ON m.session_id = s.id
           WHERE m.id = ? AND s.user_id = ?""",
        (body.message_id, user["id"])
    )
    msg = await cursor.fetchone()
    if not msg:
        return JSONResponse(status_code=404, content={"detail": "消息不存在"})

    if msg["role"] != "assistant":
        return JSONResponse(status_code=400, content={"detail": "只能导出AI回答"})

    # 获取对应的用户问题（同会话中前一条 user 消息）
    cursor = await db.execute(
        """SELECT content FROM messages
           WHERE session_id = ? AND role = 'user' AND id < ?
           ORDER BY id DESC LIMIT 1""",
        (msg["session_id"], msg["id"])
    )
    q_row = await cursor.fetchone()
    question = q_row["content"] if q_row else msg["session_title"]

    # 生成 PDF（异步化，避免阻塞事件循环）
    try:
        pdf_bytes = await asyncio.to_thread(
            generate_pdf,
            question=question,
            answer=msg["content"],
            model=msg["model"] or "",
            created_at=msg["created_at"],
            thinking_text=msg["thinking_text"] or "",
            tool_events=msg["tool_events"] or "[]",
            total_tokens=msg["total_tokens"],
            duration_ms=msg["duration_ms"],
            mode=body.mode,
        )
    except RuntimeError as e:
        logger.error(f"PDF generation runtime error: {e}")
        return JSONResponse(status_code=500, content={"detail": f"PDF 生成失败: {str(e)}"})
    except Exception as e:
        logger.exception("PDF generation failed")
        return JSONResponse(status_code=500, content={"detail": "PDF 生成失败，请稍后重试"})

    filename = f"questra_search_{msg['session_title'][:20]}_{msg['created_at'][:10]}.pdf"
    from urllib.parse import quote
    encoded_filename = quote(filename)

    return StreamingResponse(
        iter([pdf_bytes]),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}",
        },
    )
