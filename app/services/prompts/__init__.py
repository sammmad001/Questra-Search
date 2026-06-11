"""
Prompts 框架 — 问题自动分类 + 领域模板匹配 + 结构化 prompt 组装

用法：
    from app.services.prompts.engine import PromptEngine, get_prompt_engine

    engine = PromptEngine.from_config()
    result = await engine.enrich("分析特斯拉Q2财报")
    # result.system_prompt → 完整的领域 prompt
    # result.classification → 分类详情
"""

from app.services.prompts.models import (
    DomainDefinition,
    Classification,
    PromptTemplate,
    EnrichedMessage,
    PromptConfig,
)
from app.services.prompts.classifier import QuestionClassifier
from app.services.prompts.registry import TemplateRegistry
from app.services.prompts.engine import PromptEngine, get_prompt_engine, set_prompt_engine

__all__ = [
    "DomainDefinition",
    "Classification",
    "PromptTemplate",
    "EnrichedMessage",
    "PromptConfig",
    "QuestionClassifier",
    "TemplateRegistry",
    "PromptEngine",
    "get_prompt_engine",
    "set_prompt_engine",
]
