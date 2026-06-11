"""
Prompts 框架 — 核心编排器

职责：接收用户消息 → 分类 → 选择模板 → 渲染 → 返回 EnrichedMessage

用法：
    engine = PromptEngine.from_config()
    set_prompt_engine(engine)

    result = await engine.enrich("分析特斯拉Q2财报")
    # result.system_prompt → 完整的领域 prompt
    # result.classification     → 分类详情
    # result.template_used      → 使用的模板名
"""
import logging
import os
from pathlib import Path
from typing import Optional

from app.services.prompts.models import (
    EnrichedMessage,
    Classification,
    PromptConfig,
)
from app.services.prompts.classifier import QuestionClassifier
from app.services.prompts.registry import TemplateRegistry

logger = logging.getLogger(__name__)

# 模块级单例
_engine: Optional["PromptEngine"] = None


def get_prompt_engine() -> Optional["PromptEngine"]:
    """获取全局 PromptEngine 实例"""
    return _engine


def set_prompt_engine(engine: "PromptEngine"):
    """设置全局 PromptEngine 实例"""
    global _engine
    _engine = engine


class PromptEngine:
    """Prompts 框架核心入口

    协调分类器和模板注册表，将用户问题富化为领域化的 prompt。
    """

    def __init__(
        self,
        classifier: QuestionClassifier,
        registry: TemplateRegistry,
        config: PromptConfig,
    ):
        self.classifier = classifier
        self.registry = registry
        self.config = config

    @classmethod
    def from_config(cls, config: Optional[PromptConfig] = None) -> "PromptEngine":
        """工厂方法：从配置自动初始化所有组件

        Args:
            config: 配置对象，None 则从环境变量加载

        Returns:
            初始化完成的 PromptEngine 实例
        """
        cfg = config or PromptConfig.from_env()

        if not cfg.enabled:
            raise RuntimeError("Prompts 框架未启用 (PROMPTS_ENABLED=false)")

        # 配置校验
        if not (0.0 <= cfg.classification_threshold <= 1.0):
            raise ValueError(
                f"PROMPTS_CLASSIFICATION_THRESHOLD must be in [0.0, 1.0], "
                f"got {cfg.classification_threshold}"
            )
        if cfg.max_system_tokens < 100:
            raise ValueError(
                f"PROMPTS_MAX_SYSTEM_TOKENS must be >= 100, "
                f"got {cfg.max_system_tokens}"
            )

        # 分类器
        classifier = QuestionClassifier(threshold=cfg.classification_threshold)

        # 模板注册表
        templates_path = cls._resolve_templates_dir(cfg.templates_dir)
        registry = TemplateRegistry(
            template_dirs=[templates_path],
            global_search_instruction=cfg.global_search_instruction,
        )

        if len(registry) == 0:
            logger.warning(
                "未加载任何模板，Prompts 框架将使用 general 兜底模板。"
                "请检查模板目录: %s", templates_path
            )

        logger.info(
            "Prompts 框架已初始化: domains=%d, threshold=%.2f, max_tokens=%d",
            len(registry),
            cfg.classification_threshold,
            cfg.max_system_tokens,
        )

        return cls(classifier=classifier, registry=registry, config=cfg)

    @staticmethod
    def _resolve_templates_dir(templates_dir: str) -> str:
        """解析模板目录路径（相对于本模块）"""
        path = Path(templates_dir)
        if path.is_absolute():
            return str(path)

        # 相对于 prompts 模块目录
        module_dir = Path(__file__).resolve().parent
        resolved = module_dir / templates_dir
        if resolved.is_dir():
            return str(resolved)

        # 相对于项目根目录
        project_root = module_dir.parent.parent.parent
        resolved = project_root / templates_dir
        if resolved.is_dir():
            return str(resolved)

        logger.warning("模板目录未找到: %s，回退到模块内嵌目录", templates_dir)
        return str(module_dir / "templates")

    def enrich(self, user_message: str) -> EnrichedMessage:
        """主流程：分类 → 取模板 → 渲染 → 返回 EnrichedMessage

        Args:
            user_message: 用户原始消息

        Returns:
            EnrichedMessage 包含组装好的 system_prompt 和分类信息

        Raises:
            RuntimeError: 分类或渲染失败时抛出
        """
        if not user_message or not user_message.strip():
            raise ValueError("用户消息不能为空")

        # 1. 分类
        try:
            classification = self.classifier.classify(user_message)
        except Exception as e:
            logger.error("问题分类失败: %s", e, exc_info=True)
            # 降级为 general
            classification = Classification(
                domain="general",
                label_zh="通用",
                confidence=1.0,
                matched_keywords=[],
                is_fallback=True,
            )

        if self.config.verbose_log:
            logger.info(
                "prompt_classification domain=%s confidence=%.3f matched=%s",
                classification.domain,
                classification.confidence,
                classification.matched_keywords[:5],
            )

        # 2. 获取模板
        template = self.registry.get_or_default(classification.domain)

        # 3. 渲染
        try:
            system_prompt = self.registry.render(
                template,
                params={"user_message": user_message},
            )
        except Exception as e:
            logger.error("模板渲染失败: %s", e, exc_info=True)
            # 最低限度兜底
            system_prompt = (
                f"{self.config.global_search_instruction}\n\n{user_message}"
                if self.config.global_search_instruction
                else user_message
            )

        return EnrichedMessage(
            system_prompt=system_prompt,
            user_message=user_message,
            classification=classification,
            template_used=template.name,
        )

    def get_classification(self, user_message: str) -> Classification:
        """公开的分类方法，供调试/API 使用"""
        return self.classifier.classify(user_message)

    async def reload_templates(self):
        """热重载模板（不重启服务）"""
        templates_path = self._resolve_templates_dir(self.config.templates_dir)
        self.registry.reload([templates_path])
        logger.info("模板已热重载，当前 %d 个领域", len(self.registry))

    def reload_all(self):
        """热重载全部配置：模板 + 关键词（不重启服务）"""
        templates_path = self._resolve_templates_dir(self.config.templates_dir)
        self.registry.reload([templates_path])
        self.classifier.reload_keywords()
        logger.info(
            "全部配置已热重载: %d 个模板, %d 个领域关键词",
            len(self.registry),
            len(self.classifier.domains),
        )

    @property
    def domains(self) -> list[str]:
        """已加载的领域列表"""
        return self.registry.list_domains()
