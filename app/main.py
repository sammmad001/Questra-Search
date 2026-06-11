"""
Questra-Search - FastAPI 应用
"""
import logging
from contextlib import asynccontextmanager
import aiosqlite
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.database import init_db
from app.config import DATABASE_PATH, PROMPTS_ENABLED
from app.routers import pages, auth, chat, sessions, history, export
from app.services.kb_retry import KbRetrySender

logger = logging.getLogger("questra_search.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时初始化数据库 + KB 重试调度器"""
    await init_db()

    # 创建独立的数据库连接供 KB 重试调度器使用
    kb_db = await aiosqlite.connect(DATABASE_PATH)
    kb_db.row_factory = aiosqlite.Row
    await kb_db.execute("PRAGMA foreign_keys=ON")

    kb_sender = KbRetrySender(kb_db, interval_seconds=300)
    kb_sender.start()

    # ── 初始化 Prompts 框架 ──
    if PROMPTS_ENABLED:
        try:
            from app.services.prompts.engine import PromptEngine, set_prompt_engine
            engine = PromptEngine.from_config()
            set_prompt_engine(engine)
            logger.info("Prompts 框架已初始化 (%d 个领域)", len(engine.domains))
        except Exception:
            logger.warning("Prompts 框架初始化失败，已禁用", exc_info=True)

    yield

    # 关闭 KB 重试调度器 + 释放数据库连接
    kb_sender.stop()
    await kb_db.close()


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
