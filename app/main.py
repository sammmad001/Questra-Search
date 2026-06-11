"""
Questra-Search - FastAPI 应用
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse

from app.database import init_db, get_db
from app.routers import pages, auth, chat, sessions, history, export
from app.services.kb_retry import KbRetrySender


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时初始化数据库 + KB 重试调度器"""
    await init_db()

    # 启动 KB 重试调度器（每 5 分钟扫描未发送消息）
    db_gen = get_db()
    db = await db_gen.__anext__()
    kb_sender = KbRetrySender(db, interval_seconds=300)
    kb_sender.start()

    yield

    # 关闭 KB 重试调度器
    kb_sender.stop()
    await db.close()


app = FastAPI(title="Questra-Search", lifespan=lifespan)

# 静态文件
app.mount("/static", StaticFiles(directory="static"), name="static")

# 注册路由
app.include_router(pages.router)
app.include_router(auth.router)
app.include_router(chat.router)
app.include_router(sessions.router)
app.include_router(history.router)
app.include_router(export.router)
