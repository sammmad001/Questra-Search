"""
页面路由 - 提供 HTML 页面
"""
from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from app.config import BASE_PATH

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def index():
    with open("static/index.html", "r", encoding="utf-8") as f:
        html = f.read()
    # 注入 base path 到 </head> 之前
    inject = (
        '<script>'
        f'window.__BASE_PATH__ = "{BASE_PATH}";'
        '</script>'
    )
    html = html.replace('</head>', inject + '</head>', 1)
    return html
