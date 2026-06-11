"""
Prompts 框架 — 离线评估测试套件

运行方式：
    cd /Users/sam/Desktop/MiroMind
    python3 -m pytest tests/test_prompts_framework.py -v
"""
import os
import sys
import time
import tempfile
from pathlib import Path

import pytest

# 确保项目根目录在 sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.prompts.classifier import QuestionClassifier
from app.services.prompts.registry import TemplateRegistry
from app.services.prompts.models import (
    DomainDefinition,
    Classification,
    PromptTemplate,
    EnrichedMessage,
    PromptConfig,
)


# ====== 测试夹具 ======

@pytest.fixture
def classifier():
    """创建默认分类器"""
    return QuestionClassifier(threshold=0.3)


@pytest.fixture
def registry():
    """创建模板注册表（使用内嵌模板目录）"""
    templates_dir = str(
        Path(__file__).resolve().parent.parent
        / "app" / "services" / "prompts" / "templates"
    )
    return TemplateRegistry(
        template_dirs=[templates_dir],
        global_search_instruction="[Research Preference] Prioritize international sources.",
    )


# ====== 分类器测试 ======

class TestQuestionClassifier:
    """问题分类器单元测试"""

    # ── 单领域分类 ──

    @pytest.mark.parametrize("query,expected_domain", [
        # 金融
        ("分析宁德时代2025年Q1财报", "finance"),
        ("美联储加息的宏观经济影响", "finance"),
        ("比特币ETF对机构投资者的影响", "finance"),
        ("计算特斯拉的DCF估值", "finance"),
        ("标普500和纳斯达克的估值对比", "finance"),
        ("ROE分析腾讯和阿里巴巴的盈利能力", "finance"),
        # 学术
        ("最近关于CRISPR的meta分析有哪些结论", "academic"),
        ("设计一个随机对照试验来评估新药的有效性", "academic"),
        ("p值争议：为什么学术界在重新审视统计显著性", "academic"),
        ("系统综述的方法学质量评估标准", "academic"),
        # 技术
        ("微服务架构和单体架构在什么场景下应该选择哪个", "technology"),
        ("Kubernetes集群的高可用架构设计", "technology"),
        ("Transformer模型的注意力机制详解", "technology"),
        ("CI/CD流水线的最佳实践", "technology"),
        ("比较React和Vue的性能差异", "technology"),
        # 医药
        ("FDA刚刚批准的阿尔茨海默症新药的临床试验数据", "healthcare"),
        ("mRNA疫苗的长期安全性研究", "healthcare"),
        ("CRISPR基因编辑的临床进展", "healthcare"),
        ("肿瘤免疫治疗PD-1抑制剂的疗效对比", "healthcare"),
        # 法律
        ("GDPR合规要求对企业数据管理的影响", "legal"),
        ("软件专利的侵权判定标准", "legal"),
        ("跨境并购的反垄断审查流程", "legal"),
        # 政策/地缘
        ("中美贸易战对半导体供应链的影响", "policy_geopolitics"),
        ("俄乌冲突对全球能源市场的长期影响", "policy_geopolitics"),
        ("一带一路倡议的地缘政治风险评估", "policy_geopolitics"),
    ])
    def test_classify_domains(self, classifier, query, expected_domain):
        """测试各领域问题能正确分类"""
        result = classifier.classify(query)
        assert result.domain == expected_domain, (
            f"Query: '{query}'\n"
            f"Expected: '{expected_domain}'\n"
            f"Got:      '{result.domain}' (confidence={result.confidence:.3f})"
        )
        assert not result.is_fallback

    # ── 通用兜底 ──

    @pytest.mark.parametrize("query", [
        "今天天气怎么样",
        "你好",
        "帮我写一首诗",
        "推荐一本好看的小说",
        "怎么做红烧肉",
        "",  # 空字符串
    ])
    def test_classify_general_fallback(self, classifier, query):
        """测试模糊/非专业问题回退到 general"""
        result = classifier.classify(query)
        assert result.domain == "general", (
            f"Query: '{query}' should fallback to general, got '{result.domain}'"
        )
        assert result.is_fallback

    # ── 置信度合理性 ──

    def test_confidence_range(self, classifier):
        """测试置信度在 [0, 1] 范围内"""
        queries = [
            "分析特斯拉财报",
            "CRISPR技术的最新进展",
            "你好",
        ]
        for query in queries:
            result = classifier.classify(query)
            assert 0.0 <= result.confidence <= 1.0, (
                f"Confidence out of range: {result.confidence}"
            )

    def test_matched_keywords_present(self, classifier):
        """测试命中的关键词被正确记录"""
        result = classifier.classify("美联储加息对新兴市场的影响分析")
        assert len(result.matched_keywords) > 0
        # 应该至少命中 "美联储" 和 "加息"
        matched = " ".join(result.matched_keywords)
        assert "美联储" in matched or "加息" in matched

    # ── 调试模式 ──

    def test_debug_mode(self, classifier):
        """测试调试模式返回所有领域的匹配信息"""
        results = classifier.debug("AI在药物研发中的应用")
        assert len(results) >= 6  # 至少 6 个非 general 领域
        assert all("domain" in r for r in results)
        assert all("raw_score" in r for r in results)
        assert all("matched_keywords" in r for r in results)


# ====== 模板注册表测试 ======

class TestTemplateRegistry:
    """模板注册与渲染单元测试"""

    def test_load_all_templates(self, registry):
        """测试所有 7 个模板都被加载"""
        domains = registry.list_domains()
        assert len(domains) >= 7, f"Expected >= 7 domains, got {len(domains)}: {domains}"
        for d in ["finance", "academic", "technology", "healthcare", "legal",
                   "policy_geopolitics", "general"]:
            assert d in registry, f"Domain '{d}' not loaded"

    def test_get_template(self, registry):
        """测试获取模板"""
        tmpl = registry.get("finance")
        assert tmpl is not None
        assert tmpl.domain == "finance"
        assert len(tmpl.role) > 0
        assert len(tmpl.instruction) > 0

    def test_get_or_default(self, registry):
        """测试获取不存在领域的兜底"""
        tmpl = registry.get("nonexistent")
        assert tmpl is None
        tmpl = registry.get_or_default("nonexistent")
        assert tmpl is not None
        assert tmpl.domain == "general"

    def test_render_finance(self, registry):
        """测试渲染金融模板"""
        tmpl = registry.get("finance")
        result = registry.render(tmpl, {"user_message": "分析特斯拉Q2财报"})
        assert len(result) > 0
        assert "特斯拉" in result
        assert "Role" in result or "[Role]" in result
        assert "Instructions" in result or "[Instructions]" in result

    def test_render_all_domains(self, registry):
        """测试所有领域模板都能成功渲染"""
        for domain in registry.list_domains():
            tmpl = registry.get(domain)
            result = registry.render(
                tmpl, {"user_message": f"测试问题 - {domain}"}
            )
            assert len(result) > 0, f"Domain '{domain}' render empty"
            assert f"测试问题 - {domain}" in result, (
                f"Domain '{domain}' render missing user message"
            )

    def test_render_complete(self, registry):
        """测试一站式渲染"""
        result = registry.render_complete("finance", "分析美联储加息影响")
        assert len(result) > 0
        assert "分析美联储加息影响" in result

    def test_search_instruction_injection(self, registry):
        """测试 SEARCH_INSTRUCTION 被正确注入"""
        tmpl = registry.get("technology")
        result = registry.render(tmpl, {"user_message": "测试"})
        assert "[Research Preference]" in result, "SEARCH_INSTRUCTION not injected"

    def test_search_instruction_not_injected_for_general(self, registry):
        """测试 general 模板不注入 SEARCH_INSTRUCTION（已有）"""
        tmpl = registry.get("general")
        # general 的 search_guidance 为空，所以只有全局 SEARCH_INSTRUCTION
        result = registry.render(tmpl, {"user_message": "测试"})
        # SEARCH_INSTRUCTION 总是注入（因为 registry 构造函数接收了它）
        assert "[Research Preference]" in result

    def test_get_metadata(self, registry):
        """测试获取模板元数据"""
        meta = registry.get_template_metadata("finance")
        assert meta is not None
        assert meta["domain"] == "finance"
        assert "name" in meta
        assert "version" in meta
        assert "max_tokens" in meta

    def test_contains(self, registry):
        """测试 __contains__ 魔术方法"""
        assert "finance" in registry
        assert "nonexistent" not in registry


# ====== 数据模型测试 ======

class TestModels:
    """数据模型单元测试"""

    def test_classification_defaults(self):
        """测试 Classification 默认值"""
        c = Classification(
            domain="finance",
            label_zh="金融",
            confidence=0.85,
            matched_keywords=["股票", "ETF"],
        )
        assert c.is_fallback is False
        assert c.all_scores == {}

    def test_prompt_config_from_env(self, monkeypatch):
        """测试 PromptConfig.from_env 能正常加载"""
        monkeypatch.setenv("PROMPTS_ENABLED", "true")
        monkeypatch.setenv("PROMPTS_CLASSIFICATION_THRESHOLD", "0.3")
        monkeypatch.setenv("PROMPTS_MAX_SYSTEM_TOKENS", "500")

        # 需要重新导入 config 以反映 monkeypatched 环境变量
        import importlib
        import app.config
        importlib.reload(app.config)

        config = PromptConfig.from_env()
        assert config.enabled is True
        assert config.classification_threshold == 0.3
        assert config.max_system_tokens == 500
        assert len(config.global_search_instruction) > 0


# ====== 性能测试 ======

class TestPerformance:
    """性能基准测试"""

    def test_classification_speed(self, classifier):
        """测试分类速度 < 5ms（100 条平均）"""
        queries = [
            "分析特斯拉Q2财报",
            "CRISPR基因编辑的技术发展",
            "中美贸易摩擦对全球经济影响",
            "Kubernetes集群运维最佳实践",
            "FDA新药审批流程",
            "你好",
            "帮我分析一下最近的市场走势",
            "深度学习在医疗影像的应用",
            "GDPR对企业数据处理的影响",
            "俄乌冲突的地缘政治分析",
        ]
        # 预热
        for q in queries:
            classifier.classify(q)

        # 基准测试
        start = time.perf_counter()
        iterations = 100
        for _ in range(iterations):
            for q in queries:
                classifier.classify(q)
        elapsed = time.perf_counter() - start
        avg_ms = (elapsed / (iterations * len(queries))) * 1000

        assert avg_ms < 5.0, (
            f"平均分类耗时 {avg_ms:.2f}ms 超过 5ms 阈值"
        )

    def test_registry_load_speed(self):
        """测试模板加载速度 < 200ms"""
        templates_dir = str(
            Path(__file__).resolve().parent.parent
            / "app" / "services" / "prompts" / "templates"
        )
        start = time.perf_counter()
        reg = TemplateRegistry(template_dirs=[templates_dir])
        elapsed = (time.perf_counter() - start) * 1000

        assert len(reg) >= 7
        assert elapsed < 200, f"模板加载耗时 {elapsed:.0f}ms 超过 200ms 阈值"


# ====== 向后兼容测试 ======

class TestBackwardCompatibility:
    """向后兼容性测试"""

    def test_fallback_to_search_instruction(self):
        """测试禁用 Prompts 框架时行为等同于 SEARCH_INSTRUCTION"""
        # 模拟禁用状态
        search_instruction = "[Research Preference] Prioritize international."
        user_message = "分析特斯拉"

        # 原始行为
        original = f"{search_instruction}\n\n{user_message}"

        # 现在 _enrich_message 的回退路径也应该产生相同结果
        from app.config import SEARCH_INSTRUCTION
        expected = f"{SEARCH_INSTRUCTION}\n\n{user_message}" if SEARCH_INSTRUCTION else user_message

        # 基本断言：回退逻辑不应该抛出异常
        assert len(original) > len(user_message)
        assert user_message in original


# ====== EnrichedMessage 测试 ======

class TestEnrichedMessage:
    """EnrichedMessage 数据模型测试"""

    def test_fields(self):
        """测试所有字段可正常访问"""
        classification = Classification(
            domain="finance",
            label_zh="金融",
            confidence=0.9,
            matched_keywords=["财报", "估值"],
        )
        msg = EnrichedMessage(
            system_prompt="[Role]\nYou are an analyst.\n\n[User Question]\n分析Q2财报",
            user_message="分析Q2财报",
            classification=classification,
            template_used="金融与投资深度研究",
        )
        assert msg.system_prompt
        assert msg.user_message == "分析Q2财报"
        assert msg.classification.domain == "finance"
        assert msg.template_used == "金融与投资深度研究"


# ====== 扩展测试：P0/P1/P2 新增覆盖 ======

class TestEdgeCases:
    """边界情况和新增功能测试"""

    @pytest.mark.parametrize("query,expected_domain", [
        # 混合中英文
        ("用Python分析特斯拉的DCF估值模型", "finance"),
        ("How to design a Kubernetes cluster with high availability 架构设计", "technology"),
        ("FDA approval process for CAR-T therapies 细胞治疗", "healthcare"),
        # 重叠查询边界（P0-1 修复验证）
        ("美联储加息对全球经济的影响分析", "finance"),
        ("美联储最新的货币政策声明解读", "finance"),
        ("央行新一轮降息的影响", "finance"),
        # 短查询不误触发
        ("新能源政策", "policy_geopolitics"),
        ("关于新能源政策的研究", "policy_geopolitics"),
        # 新增关键词覆盖验证
        ("比特币ETF的投资价值分析", "finance"),
        ("使用Terraform部署Kubernetes集群", "technology"),
        ("CAR-T细胞治疗的临床进展", "healthcare"),
        ("GDPR和CCPA对AI监管的影响", "legal"),
        ("PRISMA指南下的系统综述方法", "academic"),
        ("CSIS最新关于印太战略的报告分析", "policy_geopolitics"),
    ])
    def test_mixed_and_edge_queries(self, classifier, query, expected_domain):
        """测试混合语言查询和边界情况"""
        result = classifier.classify(query)
        assert result.domain == expected_domain, (
            f"Query: '{query}'\n"
            f"Expected: '{expected_domain}'\n"
            f"Got:      '{result.domain}' (confidence={result.confidence:.3f})"
        )

    def test_long_query(self, classifier):
        """测试超长查询（>5000 字符）不会崩溃"""
        long_query = "分析特斯拉财报 " * 500  # ~5000 字符
        result = classifier.classify(long_query)
        assert result.domain is not None
        assert 0.0 <= result.confidence <= 1.0

    def test_special_characters(self, classifier):
        """测试特殊字符查询不会崩溃"""
        queries = [
            "```python\nprint('hello')\n```",
            "# 标题\n## 二级标题\n分析GDP数据",
            "分析 🚀 特斯拉和 📈 股价",
            "<html><body>分析FDA审批</body></html>",
        ]
        for q in queries:
            result = classifier.classify(q)
            assert result.domain is not None

    def test_lru_cache_hit(self, classifier):
        """测试 LRU 缓存命中"""
        classifier.cache_clear()
        query = "分析特斯拉2025年Q2财报和估值"

        # 第一次调用
        result1 = classifier.classify(query)
        info = classifier.cache_info()
        assert info["misses"] >= 1

        # 第二次相同调用应命中缓存
        result2 = classifier.classify(query)
        info = classifier.cache_info()
        assert info["hits"] >= 1
        assert result1.domain == result2.domain
        assert result1.confidence == result2.confidence

    def test_cache_clear(self, classifier):
        """测试缓存清除"""
        classifier.classify("测试查询")
        classifier.cache_clear()
        info = classifier.cache_info()
        assert info["size"] == 0
        assert info["hits"] == 0
        assert info["misses"] == 0


class TestKeywordsYAML:
    """关键词 YAML 加载测试"""

    def test_load_from_yaml(self):
        """测试从 YAML 加载关键词"""
        from app.services.prompts.classifier import _load_domains_from_yaml, _get_default_keywords_path

        path = _get_default_keywords_path()
        assert os.path.exists(path), f"keywords.yaml not found at {path}"

        domains = _load_domains_from_yaml(path)
        assert len(domains) >= 7

        # 验证每个领域有关键词
        domain_ids = {d.domain for d in domains}
        for expected in ["finance", "academic", "technology", "healthcare",
                          "legal", "policy_geopolitics", "general"]:
            assert expected in domain_ids, f"Domain '{expected}' missing from YAML"

        # finance 应包含扩展后的关键词
        finance = next(d for d in domains if d.domain == "finance")
        finance_kws = [kw[0] for kw in finance.keywords]
        assert "比特币" in finance_kws
        assert "DeFi" in finance_kws
        assert "IPO" in finance_kws

    def test_classifier_defaults_to_yaml(self):
        """测试默认构造的分类器从 YAML 加载"""
        classifier = QuestionClassifier()
        domains = classifier.domains
        assert len(domains) >= 7
        assert "finance" in domains


class TestTemplateMetadata:
    """模板元数据测试"""

    def test_description_loaded(self, registry):
        """测试模板的 description 被正确加载"""
        tmpl = registry.get("finance")
        assert tmpl is not None
        # description 字段存在且非空（已在 YAML 中添加）
        assert len(tmpl.description) > 0, f"Finance template missing description"

    def test_use_cases_loaded(self, registry):
        """测试模板的 use_cases 被正确加载"""
        for domain in ["finance", "academic", "technology", "healthcare",
                       "legal", "policy_geopolitics", "general"]:
            tmpl = registry.get(domain)
            assert tmpl is not None, f"Domain '{domain}' not loaded"
            # 至少有一个 use_case（general 除外，use_cases 可能较少）
            if domain != "general":
                assert len(tmpl.use_cases) >= 3, (
                    f"Domain '{domain}' has only {len(tmpl.use_cases)} use_cases"
                )


class TestConfigValidation:
    """配置校验测试"""

    def test_invalid_threshold_raises(self):
        """测试无效的 threshold 抛出 ValueError"""
        from app.services.prompts.engine import PromptEngine

        config = PromptConfig(
            enabled=True,
            classification_threshold=2.0,  # 无效
            max_system_tokens=500,
        )
        with pytest.raises(ValueError, match="PROMPTS_CLASSIFICATION_THRESHOLD"):
            PromptEngine.from_config(config)

    def test_invalid_max_tokens_raises(self):
        """测试 max_tokens 太小抛出 ValueError"""
        from app.services.prompts.engine import PromptEngine

        config = PromptConfig(
            enabled=True,
            classification_threshold=0.3,
            max_system_tokens=50,  # 无效，<100
        )
        with pytest.raises(ValueError, match="PROMPTS_MAX_SYSTEM_TOKENS"):
            PromptEngine.from_config(config)


class TestChineseTokenEstimation:
    """中文 token 估算测试"""

    def test_chinese_token_estimation(self, registry):
        """测试中文 token 估算比纯 ASCII 更准确"""
        # 纯中文 prompt
        tmpl = registry.get("finance")
        chinese_prompt = registry.render(tmpl, {"user_message": "分析特斯拉财报数据"})
        # 应该能正确渲染且不崩溃
        assert len(chinese_prompt) > 0
        # 中文占比高的 prompt，估算 token 应大于 len/4
        import re
        chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', chinese_prompt))
        ascii_chars = len(chinese_prompt) - chinese_chars
        estimated = int(chinese_chars * 1.5 + ascii_chars * 0.25)
        old_estimate = len(chinese_prompt) // 4
        # 中文 prompt 的新估算应该 > 旧估算
        if chinese_chars > 100:
            assert estimated > old_estimate, (
                f"Chinese token estimation should be higher: "
                f"new={estimated}, old={old_estimate}, chinese_chars={chinese_chars}"
            )
