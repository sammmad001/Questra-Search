"""
Prompts 框架 — 模板注册与渲染引擎

从 YAML 文件加载模板到内存，提供参数化渲染服务。
支持：
- YAML 文件批量加载
- Jinja2-lite 变量替换 {{ variable }}
- Token 预算检查与截断
- 热重载
"""
import logging
import os
import re
from pathlib import Path
from typing import Optional

import yaml

from app.services.prompts.models import PromptTemplate

logger = logging.getLogger(__name__)


# YAML 中的多行字符串使用 > 折叠，yaml.safe_load 会将其转为单行
# 但 > 会保留末尾换行为空格，需要处理


class TemplateRegistry:
    """从 YAML 文件加载模板，缓存后提供渲染服务"""

    def __init__(
        self,
        template_dirs: Optional[list[str]] = None,
        global_search_instruction: str = "",
    ):
        """
        Args:
            template_dirs: YAML 模板目录列表
            global_search_instruction: 全局搜索偏好指令（来自 SEARCH_INSTRUCTION）
        """
        self._templates: dict[str, PromptTemplate] = {}
        self._global_search_instruction = global_search_instruction

        if template_dirs:
            for td in template_dirs:
                self._load_directory(td)

    def _load_directory(self, template_dir: str):
        """加载目录中所有 .yaml / .yml 文件"""
        dir_path = Path(template_dir)
        if not dir_path.is_dir():
            logger.warning("模板目录不存在: %s", template_dir)
            return

        yaml_files = sorted(dir_path.glob("*.yaml")) + sorted(dir_path.glob("*.yml"))
        if not yaml_files:
            logger.warning("模板目录无 YAML 文件: %s", template_dir)
            return

        for yf in yaml_files:
            try:
                with open(yf, "r", encoding="utf-8") as f:
                    raw = yaml.safe_load(f)
                if not raw or not isinstance(raw, dict):
                    logger.warning("模板文件格式无效: %s", yf)
                    continue

                domain = raw.get("domain", "")
                if not domain:
                    logger.warning("模板缺少 domain 字段: %s", yf)
                    continue

                # 必填字段验证
                role = self._clean_multiline(raw.get("role", ""))
                instruction = self._clean_multiline(raw.get("instruction", ""))
                if len(role) < 20:
                    logger.error("模板 %s 的 role 字段过短（<20字符），跳过加载", yf)
                    continue
                if len(instruction) < 30:
                    logger.error("模板 %s 的 instruction 字段过短（<30字符），跳过加载", yf)
                    continue

                template = PromptTemplate(
                    name=raw.get("name", domain),
                    domain=domain,
                    version=raw.get("version", "1.0.0"),
                    description=raw.get("description", ""),
                    use_cases=raw.get("use_cases", []),
                    role=role,
                    instruction=instruction,
                    output_format=self._clean_multiline(raw.get("output_format", "")),
                    constraints=self._clean_multiline(raw.get("constraints", "")),
                    search_guidance=self._clean_multiline(
                        raw.get("search_guidance", "")
                    ),
                    max_tokens=raw.get("max_tokens", 500),
                )

                self._templates[domain] = template
                logger.info("已加载模板: domain=%s name=%s", domain, template.name)

            except yaml.YAMLError as e:
                logger.error("YAML 解析失败: %s: %s", yf, e)
            except Exception as e:
                logger.error("模板加载失败: %s: %s", yf, e)

    @staticmethod
    def _clean_multiline(text: str) -> str:
        """清理 YAML > 折叠多行字符串的格式"""
        if not text:
            return ""
        # 将多余空白规范化
        text = text.strip()
        # YAML > 折叠会将多行合并为单行，用空格连接
        # 将连续多个空格压缩为单个
        text = re.sub(r"\s+", " ", text)
        return text

    def get(self, domain: str) -> Optional[PromptTemplate]:
        """获取领域对应的模板，不存在则返回 None"""
        return self._templates.get(domain)

    def get_or_default(self, domain: str) -> PromptTemplate:
        """获取模板，域不存在时回退 general"""
        template = self._templates.get(domain)
        if template is None:
            template = self._templates.get("general")
        if template is None:
            # 兜底：硬编码 minimal 模板
            template = PromptTemplate(
                name="系统默认",
                domain="general",
                role="你是一个专业的研究助手。",
                instruction="请针对以下问题提供分析。",
                max_tokens=200,
            )
        return template

    def render(
        self,
        template: PromptTemplate,
        params: Optional[dict] = None,
    ) -> str:
        """渲染模板为最终 system prompt 字符串

        Args:
            template: 要渲染的模板
            params: 变量替换字典，支持 {{ key }}

        Returns:
            组装后的完整 prompt 字符串
        """
        params = params or {}
        parts = []

        # 1. 角色设定
        if template.role:
            parts.append(f"[Role]\n{template.role}")

        # 2. 领域指令
        if template.instruction:
            parts.append(f"\n\n[Instructions]\n{template.instruction}")

        # 3. 搜索引导（全局 SEARCH_INSTRUCTION 在前，领域特定在后）
        search_parts = []
        if self._global_search_instruction:
            search_parts.append(self._global_search_instruction)
        if template.search_guidance:
            search_parts.append(template.search_guidance)

        if search_parts:
            combined_search = "\n".join(search_parts)
            parts.append(f"\n\n[Search Guidance]\n{combined_search}")

        # 4. 输出格式
        if template.output_format:
            parts.append(f"\n\n[Output Format]\n{template.output_format}")

        # 5. 约束
        if template.constraints:
            parts.append(f"\n\n[Constraints]\n{template.constraints}")

        # 6. 用户问题
        user_msg = params.get("user_message", "")
        if user_msg:
            parts.append(f"\n\n[User Question]\n{user_msg}")

        combined = "\n".join(parts)

        # Token 预算检查（区分中英文的精确估算）
        # 中文字符 ~1.5 tokens/字, ASCII ~0.25 tokens/字符
        chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', combined))
        ascii_chars = len(combined) - chinese_chars
        estimated_tokens = int(chinese_chars * 1.5 + ascii_chars * 0.25)
        if estimated_tokens > template.max_tokens:
            combined = self._truncate_to_budget(combined, template.max_tokens)

        # 变量替换
        combined = self._apply_variables(combined, params)

        return combined

    def render_complete(
        self,
        domain: str,
        user_message: str,
        params: Optional[dict] = None,
    ) -> str:
        """一站式渲染：取模板 + 填参数 + 返回完整 prompt"""
        template = self.get_or_default(domain)
        params = params or {}
        params["user_message"] = user_message
        return self.render(template, params)

    def _truncate_to_budget(self, text: str, max_tokens: int) -> str:
        """截断文本以符合 token 预算"""
        max_chars = max_tokens * 4
        if len(text) <= max_chars:
            return text

        # 保留 Role + User Question，截断中间部分
        # 简单策略：从尾部截取 max_chars 字符
        logger.debug("Prompt 超出 token 预算，截断中 (estimated=%d, budget=%d)",
                      len(text) // 4, max_tokens)
        return text[-max_chars:]

    def _apply_variables(self, text: str, params: dict) -> str:
        """简单的 {{ variable }} 变量替换"""

        def replacer(match):
            key = match.group(1).strip()
            return str(params.get(key, match.group(0)))

        return re.sub(r"\{\{\s*(\w+)\s*\}\}", replacer, text)

    def list_domains(self) -> list[str]:
        """列出所有已加载的领域标识"""
        return list(self._templates.keys())

    def get_template_metadata(self, domain: str) -> Optional[dict]:
        """获取模板元数据"""
        tmpl = self._templates.get(domain)
        if tmpl is None:
            return None
        return {
            "name": tmpl.name,
            "domain": tmpl.domain,
            "version": tmpl.version,
            "max_tokens": tmpl.max_tokens,
        }

    def reload(self, template_dirs: list[str]):
        """热重载：清空缓存后重新加载所有模板"""
        self._templates.clear()
        for td in template_dirs:
            self._load_directory(td)
        logger.info("模板已热重载: %d 个领域", len(self._templates))

    def __len__(self) -> int:
        return len(self._templates)

    def __contains__(self, domain: str) -> bool:
        return domain in self._templates
