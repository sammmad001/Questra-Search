"""
PDF 生成器 - Markdown → HTML → PDF (WeasyPrint)
"""
import io
import json
import logging
import os
from datetime import datetime
from typing import Optional

from markdown_it import MarkdownIt

from app.config import MODELS

logger = logging.getLogger("questra_search.pdf")


def _md_to_html(markdown_text: str) -> str:
    """Markdown 转 HTML，启用扩展插件"""
    md = MarkdownIt("commonmark", {"html": True, "typographer": True})
    md.enable(["table", "strikethrough"])

    # mdit-py-plugins 扩展（可选依赖）
    try:
        from mdit_py_plugins.deflist import deflist_plugin
        from mdit_py_plugins.superscript import superscript_plugin
        md.use(deflist_plugin)
        md.use(superscript_plugin)
    except ImportError:
        pass

    return md.render(markdown_text)


def _get_model_name(model_id: str) -> str:
    """获取模型显示名称"""
    for m in MODELS:
        if m["id"] == model_id:
            return m["name"]
    return model_id


def _get_font_face_css() -> str:
    """
    增强版字体检测：多路径回退 + 跨发行版支持。
    优先级：嵌入字体 > 系统字体路径
    """
    candidates = [
        # 本地嵌入字体
        os.path.join(os.path.dirname(__file__), '..', '..', 'static', 'fonts', 'NotoSansSC-Regular.ttf'),
        # CentOS/RHEL (dnf install google-noto-sans-cjk-ttc-fonts)
        '/usr/share/fonts/google-noto-cjk/NotoSansCJKsc-Regular.otf',
        '/usr/share/fonts/noto-cjk/NotoSansCJKsc-Regular.otf',
        # Debian/Ubuntu (apt install fonts-noto-cjk)
        '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
        '/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc',
    ]

    for font_path in candidates:
        normalized = os.path.normpath(font_path)
        if os.path.exists(normalized):
            return f"""
        @font-face {{
            font-family: 'NotoSansSC';
            src: url('file://{normalized}') format('truetype');
            font-weight: normal;
            font-style: normal;
        }}
        """

    logger.warning("No embedded CJK font found, falling back to system fonts")
    return ""


def _highlight_code(html: str) -> str:
    """
    对 HTML 中的代码块使用 Pygments 进行语法高亮。
    使用内联样式（noclasses=True），确保 WeasyPrint 兼容。
    """
    try:
        from pygments import highlight
        from pygments.lexers import get_lexer_by_name, guess_lexer
        from pygments.formatters import HtmlFormatter
        from bs4 import BeautifulSoup
    except ImportError:
        logger.warning("Pygments or BeautifulSoup not installed, skipping code highlighting")
        return html

    try:
        soup = BeautifulSoup(html, 'lxml')
    except Exception:
        try:
            soup = BeautifulSoup(html, 'html.parser')
        except Exception:
            return html

    changed = False
    for pre in soup.find_all('pre'):
        code = pre.find('code')
        if not code:
            continue

        lang = None
        if code.get('class'):
            for cls in code['class']:
                if cls.startswith('language-'):
                    lang = cls.replace('language-', '')
                    break

        raw = code.get_text()
        if not raw.strip():
            continue

        try:
            if lang:
                lexer = get_lexer_by_name(lang, stripall=True)
            else:
                lexer = guess_lexer(raw)
        except Exception:
            lexer = get_lexer_by_name('text', stripall=True)

        formatter = HtmlFormatter(style='monokai', noclasses=True)
        highlighted = highlight(raw, lexer, formatter)
        new_pre = BeautifulSoup(highlighted, 'html.parser')
        pre.replace_with(new_pre)
        changed = True

    return str(soup) if changed else html


def _add_heading_ids(html: str) -> str:
    """为 HTML 中的标题添加 ID，用于 TOC 锚点链接"""
    import re
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return html

    try:
        soup = BeautifulSoup(html, 'lxml')
    except Exception:
        try:
            soup = BeautifulSoup(html, 'html.parser')
        except Exception:
            return html

    counter = {}
    for tag in soup.find_all(['h1', 'h2', 'h3', 'h4']):
        text = tag.get_text().strip()
        if not text:
            continue
        slug = re.sub(r'[^\w\u4e00-\u9fff\-]', '-', text.lower())[:60]
        level = int(tag.name[1])
        counter[level] = counter.get(level, 0) + 1
        tag['id'] = f"{slug}-{counter[level]}"

    return str(soup)


def _generate_toc(html: str) -> str:
    """
    从 HTML 中提取标题并生成目录（TOC）HTML。
    仅在 full 模式使用。
    """
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return ""

    try:
        soup = BeautifulSoup(html, 'lxml')
    except Exception:
        try:
            soup = BeautifulSoup(html, 'html.parser')
        except Exception:
            return ""

    headings = soup.find_all(['h1', 'h2', 'h3'])
    if not headings:
        return ""

    toc_items = []
    for h in headings:
        level = int(h.name[1])
        text = h.get_text().strip()
        hid = h.get('id', '')
        if not hid:
            continue
        indent = (level - 1) * 12
        toc_items.append(
            f'<div class="toc-item toc-level-{level}" style="margin-left:{indent}px;">'
            f'<a href="#{hid}">{text}</a>'
            f'<span class="toc-pagenum"></span>'
            f'</div>'
        )

    return f'''
    <div class="toc-section" style="page-break-after:always;">
        <h2 class="toc-title">目录</h2>
        {"".join(toc_items)}
    </div>
    '''


def generate_pdf(
    question: str,
    answer: str,
    model: str,
    created_at: str,
    thinking_text: str = "",
    tool_events: str = "[]",
    total_tokens: int = 0,
    duration_ms: int = 0,
    mode: str = "answer",
) -> bytes:
    """
    生成 PDF 文档
    mode: "answer" 仅答案 | "full" 完整分析过程
    """
    answer_html = _md_to_html(answer)
    question_html = _md_to_html(question)
    model_name = _get_model_name(model)
    duration_s = f"{duration_ms / 1000:.1f}s" if duration_ms else "N/A"
    font_face = _get_font_face_css()

    # 构建推理过程 HTML
    reasoning_html = ""
    if mode == "full":
        parts = []

        if thinking_text:
            thinking_html = _md_to_html(thinking_text)
            parts.append(f"""
            <div class="section">
                <h2>处理过程</h2>
                <div class="thinking-box">{thinking_html}</div>
            </div>
            """)

        try:
            events = json.loads(tool_events) if isinstance(tool_events, str) else tool_events
        except (json.JSONDecodeError, TypeError):
            events = []

        if events:
            events_html = ""
            for evt in events:
                evt_type = evt.get("type", "")
                if evt_type == "search":
                    kws = evt.get("keywords", [])
                    if kws:
                        tags = ", ".join(kws) if isinstance(kws, list) else str(kws)
                        events_html += f'<div class="event-item"><b>搜索:</b> {tags}</div>'
                elif evt_type == "fetch":
                    url = evt.get("content", "")[:100]
                    events_html += f'<div class="event-item"><b>读取:</b> {url}</div>'
                elif evt_type in ("python", "command"):
                    events_html += f'<div class="event-item"><b>{evt_type.upper()}:</b> 已执行</div>'
                elif evt_type == "tool_done":
                    name = evt.get("name", "")
                    if name:
                        events_html += f'<div class="event-item"><b>工具:</b> {name}</div>'

            if events_html:
                parts.append(f"""
                <div class="section">
                    <h2>工具调用</h2>
                    {events_html}
                </div>
                """)

        reasoning_html = "".join(parts)

        # full 模式：为回答内容添加标题 ID，生成 TOC
        answer_html_with_ids = _add_heading_ids(answer_html)
        toc_html = _generate_toc(answer_html_with_ids)
    else:
        answer_html_with_ids = answer_html
        toc_html = ""

    # 组装完整 HTML
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    html = f"""
    <html>
    <head>
        <meta charset="utf-8">
        <title>Questra-Search 研究报告</title>
        <style>
            {font_face}
            @page {{
                size: A4;
                margin: 2cm 2cm 3cm 2cm;
                @bottom-center {{
                    content: "— " counter(page) " —";
                    font-size: 9pt;
                    color: #999;
                    font-family: "NotoSansSC", "Noto Sans CJK SC", "PingFang SC", sans-serif;
                }}
                @top-right {{
                    content: "Questra-Search 研究平台";
                    font-size: 8pt;
                    color: #bbb;
                    font-family: "NotoSansSC", "Noto Sans CJK SC", "PingFang SC", sans-serif;
                }}
            }}
            @page:first {{
                @top-right {{ content: none; }}
            }}
            body {{
                font-family: "NotoSansSC", "Noto Sans CJK SC", "Noto Sans SC",
                             "PingFang SC", "Microsoft YaHei", "WenQuanYi Micro Hei",
                             "Source Han Sans SC", "SimHei",
                             "Helvetica Neue", Arial, sans-serif;
                font-size: 11pt;
                line-height: 1.6;
                color: #333;
            }}
            .header {{
                text-align: center;
                padding-bottom: 15px;
                border-bottom: 2px solid #3b82f6;
                margin-bottom: 20px;
            }}
            .header h1 {{
                color: #1e40af;
                font-size: 18pt;
                margin: 0 0 5px 0;
            }}
            .header .meta {{
                font-size: 9pt;
                color: #888;
            }}
            .question-box {{
                background: #eff6ff;
                border-left: 3px solid #3b82f6;
                padding: 10px 15px;
                margin-bottom: 20px;
                border-radius: 0 6px 6px 0;
            }}
            .question-box h3 {{
                margin: 0 0 5px 0;
                color: #1e40af;
                font-size: 10pt;
            }}
            .section {{
                margin-bottom: 20px;
            }}
            .section h2 {{
                color: #555;
                font-size: 12pt;
                border-bottom: 1px solid #ddd;
                padding-bottom: 5px;
            }}
            .thinking-box {{
                background: #f9f9f9;
                padding: 10px;
                border-radius: 4px;
                font-size: 9pt;
                color: #666;
            }}
            .event-item {{
                padding: 4px 0;
                font-size: 9pt;
                color: #555;
                border-bottom: 1px dotted #ddd;
            }}
            .answer-content {{
                font-size: 11pt;
            }}
            .answer-content h1 {{ font-size: 15pt; color: #1e3a5f; margin: 15px 0 8px; page-break-after: avoid; }}
            .answer-content h2 {{ font-size: 13pt; color: #333; margin: 12px 0 6px; page-break-after: avoid; }}
            .answer-content h3 {{ font-size: 12pt; color: #555; margin: 10px 0 4px; page-break-after: avoid; }}
            .answer-content h4 {{ font-size: 11pt; color: #666; margin: 8px 0 4px; page-break-after: avoid; }}
            .answer-content h1 + *, .answer-content h2 + *, .answer-content h3 + *, .answer-content h4 + * {{
                page-break-before: avoid;
            }}
            .answer-content code {{
                background: #f0f0f0;
                padding: 1px 4px;
                border-radius: 3px;
                font-size: 10pt;
            }}
            .answer-content pre {{
                padding: 10px;
                border-radius: 4px;
                font-size: 9pt;
                overflow-x: auto;
                white-space: pre-wrap;
                word-wrap: break-word;
                max-width: 100%;
                page-break-inside: avoid;
            }}
            .answer-content pre code {{
                background: none;
                padding: 0;
            }}
            .answer-content table {{
                width: 100%;
                border-collapse: collapse;
                margin: 10px 0;
                font-size: 10pt;
            }}
            .answer-content th, .answer-content td {{
                border: 1px solid #ddd;
                padding: 6px 10px;
                text-align: left;
            }}
            .answer-content th {{
                background: #eff6ff;
                font-weight: bold;
                color: #1e40af;
            }}
            .answer-content tr:nth-child(even) {{ background: #f9fafb; }}
            .answer-content tr {{ page-break-inside: avoid; }}
            .answer-content thead {{ display: table-header-group; }}
            .answer-content ul, .answer-content ol {{
                padding-left: 20px;
                margin: 5px 0;
            }}
            .answer-content blockquote {{
                border-left: 3px solid #3b82f6;
                padding-left: 12px;
                color: #888;
                margin: 8px 0;
            }}
            .answer-content del, .answer-content s {{ text-decoration: line-through; color: #999; }}
            .answer-content ins {{ text-decoration: underline; }}
            .answer-content sup {{ font-size: 0.8em; vertical-align: super; }}
            .answer-content sub {{ font-size: 0.8em; vertical-align: sub; }}
            .answer-content dl {{ margin: 8px 0; }}
            .answer-content dt {{ font-weight: bold; margin-top: 8px; }}
            .answer-content dd {{ margin-left: 20px; color: #555; }}
            .answer-content img {{
                max-width: 100%;
                height: auto;
                page-break-inside: avoid;
            }}
            .footer {{
                margin-top: 20px;
                padding-top: 10px;
                border-top: 1px solid #ddd;
                font-size: 8pt;
                color: #999;
                text-align: center;
            }}
            .toc-section {{
                margin-bottom: 30px;
            }}
            .toc-title {{
                font-size: 14pt;
                color: #1e40af;
                border-bottom: 2px solid #3b82f6;
                padding-bottom: 8px;
                margin-bottom: 12px;
            }}
            .toc-item {{
                padding: 3px 0;
                font-size: 10pt;
                line-height: 1.5;
            }}
            .toc-item a {{
                color: #1e40af;
                text-decoration: none;
            }}
            .toc-item a::after {{
                content: target-counter(attr(href), page);
                float: right;
                color: #999;
            }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>Questra-Search 研究平台</h1>
            <div class="meta">模型: {model_name} | 生成时间: {now}</div>
        </div>

        <div class="question-box">
            <h3>研究问题</h3>
            {question_html}
        </div>

        {reasoning_html}

        {toc_html}

        <div class="section">
            <h2>回答</h2>
            <div class="answer-content">{answer_html_with_ids}</div>
        </div>

        <div class="footer">
            Token 用量: {total_tokens} | 耗时: {duration_s} | 导出时间: {now}
        </div>
    </body>
    </html>
    """

    # 后处理：代码语法高亮（Pygments）
    html = _highlight_code(html)

    # WeasyPrint 渲染
    try:
        from weasyprint import HTML
    except ImportError:
        raise RuntimeError("WeasyPrint 未安装，请运行 pip install weasyprint 并安装系统依赖")

    pdf_bytes = HTML(string=html).write_pdf()
    return pdf_bytes
