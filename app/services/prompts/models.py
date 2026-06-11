"""
Prompts 框架 — 数据模型定义
"""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class DomainDefinition:
    """领域定义：分类关键词 + 匹配权重"""
    domain: str                        # e.g. "finance"
    label_zh: str                      # e.g. "金融与投资"
    keywords: list[tuple[str, float]]  # [(keyword, weight), ...]
    patterns: list[str]                # 正则模式列表
    priority: int = 0                  # 优先级，越大越优先匹配


@dataclass
class Classification:
    """分类结果"""
    domain: str                        # 匹配的领域标识
    label_zh: str                      # 中文标签
    confidence: float                  # 置信度 0.0~1.0
    matched_keywords: list[str]        # 命中的关键词
    is_fallback: bool = False          # 是否回退到 general
    all_scores: dict[str, float] = field(default_factory=dict)  # 所有领域得分（调试用）


@dataclass
class PromptTemplate:
    """单个 Prompt 模板"""
    name: str                          # 模板名称
    domain: str                        # 所属领域
    version: str = "1.0.0"             # 版本号
    description: str = ""              # 模板描述
    use_cases: list[str] = field(default_factory=list)  # 适用场景
    role: str = ""                     # 系统角色设定
    instruction: str = ""              # 领域专业指令
    output_format: str = ""            # 输出结构要求
    constraints: str = ""              # 领域约束
    search_guidance: str = ""          # 领域特定搜索引导
    max_tokens: int = 500              # Token 预算上限


@dataclass
class EnrichedMessage:
    """富化后的消息 — 最终传给 MiroMind API"""
    system_prompt: str                 # 组装好的完整 system prompt
    user_message: str                  # 原始用户消息（不变）
    classification: Classification     # 分类信息（用于日志/统计）
    template_used: str                 # 使用的模板名称


@dataclass
class PromptConfig:
    """Prompts 框架配置容器"""
    enabled: bool = True
    templates_dir: str = "templates"
    classification_threshold: float = 0.3
    max_system_tokens: int = 500
    verbose_log: bool = False
    global_search_instruction: str = ""

    @classmethod
    def from_env(cls) -> "PromptConfig":
        """从 app.config 加载配置"""
        from app.config import (
            PROMPTS_ENABLED, PROMPTS_TEMPLATES_DIR,
            PROMPTS_CLASSIFICATION_THRESHOLD, PROMPTS_MAX_SYSTEM_TOKENS,
            PROMPTS_VERBOSE_LOG, SEARCH_INSTRUCTION,
        )
        return cls(
            enabled=PROMPTS_ENABLED,
            templates_dir=PROMPTS_TEMPLATES_DIR,
            classification_threshold=PROMPTS_CLASSIFICATION_THRESHOLD,
            max_system_tokens=PROMPTS_MAX_SYSTEM_TOKENS,
            verbose_log=PROMPTS_VERBOSE_LOG,
            global_search_instruction=SEARCH_INSTRUCTION,
        )
