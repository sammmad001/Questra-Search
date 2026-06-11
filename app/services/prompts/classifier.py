"""
Prompts 框架 — 问题分类器

纯规则分类器：加权关键词匹配 + 正则模式匹配 + Softmax 归一化
时间复杂度 O(n*m)，n=消息长度, m=关键词总数(<300)，毫秒级完成

支持从 YAML 配置加载关键词，修改 keywords.yaml 后可热更新。
"""
import math
import re
from functools import lru_cache
from pathlib import Path
from typing import Optional

import yaml

from app.services.prompts.models import DomainDefinition, Classification


# ====== 内置兜底定义（仅在 YAML 加载失败时使用）======

_FALLBACK_DOMAINS: list[DomainDefinition] = [
    DomainDefinition(
        domain="finance",
        label_zh="金融与投资",
        keywords=[
            # 金融市场
            ("股票", 1.0), ("基金", 0.9), ("ETF", 1.0), ("纳斯达克", 1.2),
            ("标普500", 1.2), ("道琼斯", 1.2), ("港股", 0.9), ("A股", 0.9),
            ("期货", 0.8), ("期权", 1.0), ("债券", 0.8), ("外汇", 0.8),
            # 财务分析
            ("财报", 1.0), ("ROE", 1.2), ("市盈率", 1.0), ("估值", 0.8),
            ("贴现", 1.0), ("DCF", 1.2), ("现金流", 0.9), ("EBITDA", 1.2),
            ("毛利率", 0.9), ("净利率", 0.9), ("资产负债表", 1.0),
            # 投资策略
            ("投资组合", 0.9), ("对冲", 0.7), ("做空", 0.8), ("做多", 0.7),
            ("技术分析", 0.7), ("基本面", 0.8), ("量化", 0.8),
            # 宏观经济
            ("GDP", 0.8), ("CPI", 0.8), ("通胀", 0.7), ("加息", 0.8),
            ("降息", 0.8), ("美联储", 0.5), ("央行", 0.5), ("货币政策", 0.9),
            ("财政政策", 0.9), ("收益率", 0.8), ("利差", 0.8),
        ],
        patterns=[
            r"证券.*分析", r"投资.*回报", r"资产.*配置",
            r"SEC\s*(EDGAR|filing)", r"10-K|10-Q",
        ],
        priority=0,
    ),
    DomainDefinition(
        domain="academic",
        label_zh="学术研究",
        keywords=[
            ("论文", 1.0), ("文献", 0.9), ("期刊", 0.8), ("引用", 0.6),
            ("meta分析", 1.2), ("系统综述", 1.2), ("假设检验", 1.0),
            ("p值", 1.2), ("置信区间", 1.0), ("效应量", 1.0),
            ("研究方法", 0.8), ("实验设计", 0.9), ("对照组", 1.0),
            ("随机对照", 1.2), ("双盲", 1.2), ("队列研究", 1.0),
            ("回归分析", 0.8), ("相关性", 0.6), ("因果", 0.7),
            ("影响因子", 1.0), ("预印本", 1.0), ("同行评审", 0.9),
            ("理论框架", 0.7), ("学术贡献", 0.8),
        ],
        patterns=[
            r"文献.*综述", r"学术.*研究", r"博士.*论文",
            r"arXiv|PubMed|Google\s*Scholar", r"Semantic\s*Scholar",
        ],
        priority=0,
    ),
    DomainDefinition(
        domain="technology",
        label_zh="技术架构",
        keywords=[
            # 编程
            ("代码", 0.7), ("API", 0.8), ("SDK", 0.8), ("框架", 0.6),
            ("Python", 0.8), ("React", 0.9), ("Kubernetes", 1.2),
            ("Docker", 1.0), ("微服务", 1.0), ("GraphQL", 1.0),
            ("REST", 0.9), ("WebSocket", 1.0), ("gRPC", 1.0),
            # 架构
            ("架构设计", 1.0), ("系统设计", 0.9), ("高可用", 1.0),
            ("分布式", 0.9), ("负载均衡", 1.0), ("数据库", 0.7),
            ("缓存", 0.7), ("消息队列", 0.9), ("CI/CD", 1.0),
            # AI/ML
            ("深度学习", 0.9), ("神经网络", 0.8), ("Transformer", 1.2),
            ("LLM", 1.2), ("大模型", 1.0), ("NLP", 1.0),
            ("训练", 0.7), ("推理", 0.6), ("向量", 0.7),
            # 性能
            ("算法复杂度", 0.9), ("时间复杂度", 0.9), ("优化", 0.5),
            ("吞吐量", 0.8), ("延迟", 0.6),
        ],
        patterns=[
            r"(码|写|开发|实现)\s*(一段|一个).*代码",
            r"技术.*选型", r"方案.*设计",
            r"(GitHub|GitLab|Bitbucket)\s*(repo|仓库)",
            r"K8s|k8s",
        ],
        priority=0,
    ),
    DomainDefinition(
        domain="healthcare",
        label_zh="生物医药",
        keywords=[
            ("临床试验", 1.2), ("临床研究", 1.1), ("药物", 0.8),
            ("FDA", 1.2), ("EMA", 1.2), ("NMPA", 1.0),
            ("副作用", 0.9), ("不良反应", 0.9), ("安全性", 0.6),
            ("有效性", 0.7), ("疗效", 0.8), ("剂量", 0.8),
            ("基因组", 0.9), ("基因编辑", 1.2), ("CRISPR", 1.2),
            ("mRNA", 1.2), ("疫苗", 0.9), ("免疫", 0.8),
            ("癌症", 0.8), ("肿瘤", 0.8), ("靶向", 0.9),
            ("生物标志物", 1.0), ("体外诊断", 1.0), ("IVD", 1.2),
            ("流行病", 1.0), ("公共卫生", 0.9), ("WHO", 0.8),
            ("病原体", 1.0), ("耐药性", 1.0),
        ],
        patterns=[
            r"临床.*(试验|研究|数据|结果)",
            r"药物.*(研发|开发|获批)",
            r"(一期|二期|三期|I期|II期|III期)\s*临床",
            r"ClinicalTrials\.gov",
        ],
        priority=0,
    ),
    DomainDefinition(
        domain="legal",
        label_zh="法律合规",
        keywords=[
            ("法律", 0.8), ("法规", 0.8), ("条款", 0.7),
            ("合规", 0.9), ("监管", 0.8), ("知识产权", 1.0),
            ("专利", 0.9), ("商标", 0.9), ("著作权", 0.9),
            ("GDPR", 1.2), ("CCPA", 1.2), ("数据隐私", 0.9),
            ("合同", 0.8), ("判例", 1.0), ("司法解释", 1.0),
            ("诉讼", 0.8), ("仲裁", 0.9), ("侵权", 0.8),
            ("反垄断", 1.0), ("并购", 0.8), ("尽职调查", 0.9),
            ("公司法", 0.9), ("证券法", 0.9), ("劳动法", 0.9),
            ("出口管制", 1.0), ("制裁", 0.8),
        ],
        patterns=[
            r"法律.*(风险|分析|意见)",
            r"合规.*(要求|审查|检查)",
            r"GDPR\s*(合规|罚款|处罚)",
            r"知识产权.*保护",
        ],
        priority=0,
    ),
    DomainDefinition(
        domain="policy_geopolitics",
        label_zh="政策与地缘政治",
        keywords=[
            ("政策", 0.4), ("政府", 0.6), ("白宫", 1.0), ("国会", 1.0),
            ("财政部", 0.9),
            ("经济制裁", 1.1), ("关税", 1.0), ("贸易战", 1.2),
            ("贸易协定", 1.0), ("WTO", 1.0), ("IMF", 1.0),
            ("地缘政治", 1.2), ("地缘", 1.1), ("外交", 0.8),
            ("国际关系", 0.9), ("同盟", 0.8), ("北约", 1.0),
            ("供应链安全", 1.2), ("能源安全", 1.1), ("粮食安全", 1.0),
            ("出口管制", 1.0), ("技术封锁", 1.2),
            ("半导体", 0.8), ("芯片", 0.8), ("稀土", 1.0),
            ("一带一路", 1.2), ("印太", 1.1),
            ("冲突", 0.5), ("战争", 0.5), ("军事", 0.9),
            ("能源市场", 0.9), ("石油", 0.7), ("天然气", 0.7),
            ("全球能源", 0.9), ("中东", 0.8), ("俄罗斯", 0.7),
        ],
        patterns=[
            r"地缘.*(政治|冲突|风险|格局)",
            r"(中美|美中|中欧|俄乌).*关系",
            r"政策.*(影响|分析|走向|趋势)",
            r"制裁.*(影响|后果|效果)",
        ],
        priority=0,
    ),
    DomainDefinition(
        domain="general",
        label_zh="通用",
        keywords=[],
        patterns=[],
        priority=-999,  # 最低优先级，兜底
    ),
]


def _load_domains_from_yaml(yaml_path: str) -> list[DomainDefinition]:
    """从 YAML 文件加载领域定义"""
    try:
        with open(yaml_path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)
        if not raw or "domains" not in raw:
            raise ValueError("keywords.yaml 缺少 'domains' 根节点")

        domains = []
        for domain_id, domain_data in raw["domains"].items():
            keywords = [
                (str(kw[0]), float(kw[1]))
                for kw in domain_data.get("keywords", [])
            ]
            domains.append(DomainDefinition(
                domain=domain_id,
                label_zh=domain_data.get("label_zh", domain_id),
                keywords=keywords,
                patterns=domain_data.get("patterns", []),
                priority=domain_data.get("priority", 0),
            ))
        return domains
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(
            "无法加载 keywords.yaml (%s)，使用内置兜底关键词", e
        )
        return _FALLBACK_DOMAINS


def _get_default_keywords_path() -> str:
    """获取默认的关键词 YAML 路径（相对于本模块）"""
    module_dir = Path(__file__).resolve().parent
    return str(module_dir / "keywords.yaml")


class QuestionClassifier:
    """纯规则分类器 — 加权关键词 + 正则模式 + Softmax 归一化

    用法：
        classifier = QuestionClassifier(threshold=0.3)
        result = classifier.classify("分析特斯拉Q2财报")
        # result.domain → "finance"
        # result.confidence → 0.85
    """

    def __init__(
        self,
        domains: Optional[list[DomainDefinition]] = None,
        keywords_path: Optional[str] = None,
        threshold: float = 0.3,
    ):
        """
        Args:
            domains: 领域定义列表（None 则从 YAML 加载）
            keywords_path: YAML 关键词文件路径（None 则用默认路径）
            threshold: 置信度阈值，低于此值回退到 general
        """
        if domains is not None:
            self._domains = domains
        else:
            path = keywords_path or _get_default_keywords_path()
            self._domains = _load_domains_from_yaml(path)
            self._keywords_path = path
        self._threshold = threshold
        # 预编译正则
        self._compiled_patterns: dict[str, list[re.Pattern]] = {}
        for d in self._domains:
            self._compiled_patterns[d.domain] = [
                re.compile(p, re.IGNORECASE) for p in d.patterns
            ]
        # 简易 LRU 缓存：{text_hash: Classification}
        self._cache: dict[int, Classification] = {}
        self._cache_maxsize = 128
        self._cache_hits = 0
        self._cache_misses = 0

    def classify(self, text: str) -> Classification:
        """对文本进行分类，返回最佳匹配领域。

        带 LRU 缓存：相同文本在短时间内重复查询直接返回缓存结果。

        Args:
            text: 用户输入文本

        Returns:
            Classification 对象，包含 domain/confidence/matched_keywords
        """
        if not text or not text.strip():
            return Classification(
                domain="general",
                label_zh="通用",
                confidence=1.0,
                matched_keywords=[],
                is_fallback=True,
            )

        # 超长输入保护：截取前 10000 字符分类（足够准确）
        if len(text) > 10000:
            text = text[:10000]

        # LRU 缓存检查
        cache_key = hash(text)
        if cache_key in self._cache:
            self._cache_hits += 1
            return self._cache[cache_key]
        self._cache_misses += 1

        result = self._classify_impl(text)

        # 写入缓存（LRU 淘汰）
        if len(self._cache) >= self._cache_maxsize:
            # 删除最早插入的条目
            oldest_key = next(iter(self._cache))
            del self._cache[oldest_key]
        self._cache[cache_key] = result

        return result

    def _classify_impl(self, text: str) -> Classification:

        text_lower = text.lower()

        # 非 general 领域参与评分
        non_general = [d for d in self._domains if d.domain != "general"]
        raw_scores: dict[str, float] = {}
        all_matched: dict[str, list[str]] = {}

        for domain_def in non_general:
            score, matched = self._score_domain(text_lower, domain_def)
            raw_scores[domain_def.domain] = score
            all_matched[domain_def.domain] = matched

        # Softmax 归一化
        normalized = self._normalize_scores(raw_scores)

        # 找最高分
        best_domain = max(normalized, key=normalized.get)
        best_confidence = normalized[best_domain]

        # 低于阈值 → 回退 general
        if best_confidence < self._threshold or best_domain == "general":
            general_def = next(
                (d for d in self._domains if d.domain == "general"), None
            )
            return Classification(
                domain="general",
                label_zh=general_def.label_zh if general_def else "通用",
                confidence=1.0,
                matched_keywords=[],
                is_fallback=True,
                all_scores=normalized,
            )

        # 获取匹配领域的标签
        matched_def = next(
            (d for d in self._domains if d.domain == best_domain), None
        )
        return Classification(
            domain=best_domain,
            label_zh=matched_def.label_zh if matched_def else best_domain,
            confidence=round(best_confidence, 3),
            matched_keywords=all_matched.get(best_domain, []),
            is_fallback=False,
            all_scores=normalized,
        )

    def _score_domain(
        self, text_lower: str, domain: DomainDefinition
    ) -> tuple[float, list[str]]:
        """计算单个领域的匹配分数

        Returns:
            (score, matched_keywords)
        """
        score = 0.0
        matched: list[str] = []

        # 1. 关键词匹配（主要信号）
        for keyword, weight in domain.keywords:
            if keyword.lower() in text_lower:
                score += weight
                matched.append(keyword)

        # 2. 正则模式匹配（补充信号，学术领域模式权重更高）
        pattern_weight = 1.0 if domain.domain == "academic" else 0.5
        for pattern in self._compiled_patterns.get(domain.domain, []):
            if pattern.search(text_lower):
                score += pattern_weight
                matched.append(f"pattern:{pattern.pattern}")

        return score, matched

    def _normalize_scores(self, raw_scores: dict[str, float]) -> dict[str, float]:
        """Softmax 归一化，使最高分领域更突出"""
        scores = list(raw_scores.values())
        if not scores:
            return {}

        # 防止溢出：减去最大值
        max_score = max(scores)
        if max_score == 0:
            # 所有都为 0，均匀分布
            n = len(scores)
            return {
                domain: 1.0 / n
                for domain in raw_scores
            }

        exps = [math.exp(s - max_score) for s in scores]
        total = sum(exps)
        if total == 0:
            return {domain: 0.0 for domain in raw_scores}

        return {
            domain: round(exp_val / total, 4)
            for domain, exp_val in zip(raw_scores.keys(), exps)
        }

    def debug(self, text: str) -> list[dict]:
        """调试模式：返回所有领域的详细匹配信息"""
        text_lower = text.lower()
        results = []
        for domain_def in self._domains:
            if domain_def.domain == "general":
                continue
            score, matched = self._score_domain(text_lower, domain_def)
            results.append({
                "domain": domain_def.domain,
                "label_zh": domain_def.label_zh,
                "raw_score": round(score, 2),
                "matched_keywords": matched,
            })
        results.sort(key=lambda x: x["raw_score"], reverse=True)
        return results

    @property
    def domains(self) -> list[str]:
        """返回所有已加载的领域标识"""
        return [d.domain for d in self._domains]

    @property
    def threshold(self) -> float:
        """返回当前置信度阈值"""
        return self._threshold

    def reload_keywords(self):
        """热重载关键词配置（从 YAML 重新加载，无需重启）"""
        if hasattr(self, '_keywords_path'):
            self._domains = _load_domains_from_yaml(self._keywords_path)
            # 重新编译正则
            self._compiled_patterns = {}
            for d in self._domains:
                self._compiled_patterns[d.domain] = [
                    re.compile(p, re.IGNORECASE) for p in d.patterns
                ]
            # 清除缓存
            self._cache.clear()

    def cache_info(self) -> dict:
        """返回缓存统计信息"""
        return {
            "size": len(self._cache),
            "maxsize": self._cache_maxsize,
            "hits": self._cache_hits,
            "misses": self._cache_misses,
        }

    def cache_clear(self):
        """清除分类缓存"""
        self._cache.clear()
        self._cache_hits = 0
        self._cache_misses = 0
