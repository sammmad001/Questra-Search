"""
Questra-Search - FastAPI 应用
"""
import asyncio
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


async def _cleanup_stale_streams():
    """后台任务：定期将超时的 streaming 消息标记为 interrupted"""
    while True:
        await asyncio.sleep(60)
        try:
            if not DATABASE_PATH:
                continue
            async with aiosqlite.connect(DATABASE_PATH) as db:
                cursor = await db.execute(
                    """UPDATE messages SET status = 'interrupted'
                       WHERE status = 'streaming'
                       AND created_at < datetime('now', '-5 minutes')"""
                )
                if cursor.rowcount > 0:
                    logger.info("清理 %d 条过期 streaming 消息", cursor.rowcount)
                await db.commit()
        except Exception:
            logger.debug("streaming 清理异常", exc_info=True)


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

    # ── 启动过期流式消息清理任务 ──
    cleanup_task = asyncio.ensure_future(_cleanup_stale_streams())

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

    # 关闭后台任务 + KB 重试调度器 + 释放数据库连接
    cleanup_task.cancel()
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
