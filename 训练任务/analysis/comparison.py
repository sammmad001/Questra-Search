"""跨策略对比分析 — 传统量化 vs ML策略

对比维度:
1. 最佳策略指标对比
2. 收敛速度分析
3. 稳定性对比 (Top-10 Sharpe的方差)
4. 过拟合风险对比 (WF通过率 / DSR)
5. 最终胜者判定
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from analysis.metrics_normalizer import MetricsNormalizer
from strategies.base_strategy import RoundResult


@dataclass
class StrategyProfile:
    """单策略画像"""
    name: str
    total_rounds: int = 0
    successful_rounds: int = 0

    # 最佳指标
    best_sharpe: float = 0.0
    best_annual_return: float = 0.0
    best_max_drawdown: float = 0.0
    best_calmar: float = 0.0
    best_round_idx: int = 0

    # 平均指标
    avg_sharpe: float = 0.0
    avg_annual_return: float = 0.0
    avg_max_drawdown: float = 0.0

    # 稳定性
    std_sharpe: float = 0.0
    top10_avg_sharpe: float = 0.0

    # 过拟合
    wf_pass_rate: float = 0.0
    avg_overfitting_score: float = 0.0
    avg_dsr: float = 0.0

    # 收敛
    convergence_round: int = 0  # 首次达到目标的轮次 (0=未达到)

    # 达标
    meets_targets: bool = False
    best_config: dict = field(default_factory=dict)


@dataclass
class ComparisonResult:
    """对比分析结果"""
    traditional: StrategyProfile
    ml: StrategyProfile
    winner: str = ""  # "traditional" | "ml" | "tie"
    winner_confidence: float = 0.0  # 胜出置信度 [0, 1]

    # 差异分析
    sharpe_diff: float = 0.0
    return_diff: float = 0.0
    drawdown_diff: float = 0.0
    wf_pass_diff: float = 0.0
    convergence_diff: int = 0  # 正数=传统更快

    # 建议
    recommendation: str = ""


class ComparisonAnalyzer:
    """跨策略对比分析器"""

    def analyze(
        self,
        trad_results: list[RoundResult],
        ml_results: list[RoundResult],
    ) -> ComparisonResult:
        """执行全面对比分析"""
        trad_profile = self._build_profile("traditional", trad_results)
        ml_profile = self._build_profile("ml", ml_results)

        # 差异计算
        sharpe_diff = trad_profile.best_sharpe - ml_profile.best_sharpe
        return_diff = trad_profile.best_annual_return - ml_profile.best_annual_return
        drawdown_diff = ml_profile.best_max_drawdown - trad_profile.best_max_drawdown  # 越小越好
        wf_pass_diff = trad_profile.wf_pass_rate - ml_profile.wf_pass_rate
        convergence_diff = (
            (ml_profile.convergence_round - trad_profile.convergence_round)
            if trad_profile.convergence_round > 0 and ml_profile.convergence_round > 0
            else 0
        )

        # 胜者判定 — 综合评分
        trad_score = self._compute_score(trad_profile)
        ml_score = self._compute_score(ml_profile)

        if trad_score > ml_score + 0.1:
            winner = "traditional"
        elif ml_score > trad_score + 0.1:
            winner = "ml"
        else:
            winner = "tie"

        confidence = min(abs(trad_score - ml_score) / 2.0, 1.0)

        # 建议
        recommendation = self._generate_recommendation(
            trad_profile, ml_profile, winner,
        )

        return ComparisonResult(
            traditional=trad_profile,
            ml=ml_profile,
            winner=winner,
            winner_confidence=round(confidence, 4),
            sharpe_diff=round(sharpe_diff, 4),
            return_diff=round(return_diff, 4),
            drawdown_diff=round(drawdown_diff, 4),
            wf_pass_diff=round(wf_pass_diff, 4),
            convergence_diff=convergence_diff,
            recommendation=recommendation,
        )

    def _build_profile(self, name: str, results: list[RoundResult]) -> StrategyProfile:
        """从 RoundResult 列表构建策略画像"""
        profile = StrategyProfile(
            name=name,
            total_rounds=len(results),
        )

        successful = [r for r in results if r.success]
        profile.successful_rounds = len(successful)

        if not successful:
            return profile

        # 最佳指标
        best = max(successful, key=lambda r: r.sharpe_ratio)
        profile.best_sharpe = best.sharpe_ratio
        profile.best_annual_return = best.annual_return
        profile.best_max_drawdown = best.max_drawdown
        profile.best_calmar = best.calmar_ratio
        profile.best_round_idx = best.round_idx
        profile.best_config = best.config_snapshot
        profile.meets_targets = best.meets_targets

        # 平均指标
        sharpes = [r.sharpe_ratio for r in successful]
        returns = [r.annual_return for r in successful]
        drawdowns = [r.max_drawdown for r in successful]

        profile.avg_sharpe = float(np.mean(sharpes))
        profile.avg_annual_return = float(np.mean(returns))
        profile.avg_max_drawdown = float(np.mean(drawdowns))

        # 稳定性
        profile.std_sharpe = float(np.std(sharpes))
        top10 = sorted(sharpes, reverse=True)[:10]
        profile.top10_avg_sharpe = float(np.mean(top10))

        # 过拟合
        wf_passes = sum(1 for r in successful if r.walk_forward_valid)
        profile.wf_pass_rate = wf_passes / len(successful)
        of_scores = [r.overfitting_score for r in successful if r.overfitting_score > 0]
        profile.avg_overfitting_score = float(np.mean(of_scores)) if of_scores else 0.0
        dsr_vals = [r.dsr for r in successful if r.dsr > 0]
        profile.avg_dsr = float(np.mean(dsr_vals)) if dsr_vals else 0.0

        # 收敛 — 首次达标轮次
        for r in successful:
            if r.meets_targets:
                profile.convergence_round = r.round_idx + 1
                break

        return profile

    def _compute_score(self, profile: StrategyProfile) -> float:
        """计算综合评分 (0-1)"""
        score = 0.0

        # Sharpe (权重最高 0.35)
        if profile.best_sharpe >= 1.3:
            score += 0.35
        elif profile.best_sharpe >= 0.8:
            score += 0.20
        elif profile.best_sharpe >= 0.5:
            score += 0.10

        # 收益 (0.25)
        if profile.best_annual_return >= 0.30:
            score += 0.25
        elif profile.best_annual_return >= 0.15:
            score += 0.15

        # 回撤 (0.20) — 越小越好
        if profile.best_max_drawdown <= 0.15:
            score += 0.20
        elif profile.best_max_drawdown <= 0.20:
            score += 0.15
        elif profile.best_max_drawdown <= 0.30:
            score += 0.05

        # 稳定性 (0.10)
        if profile.top10_avg_sharpe >= 1.0:
            score += 0.10
        elif profile.top10_avg_sharpe >= 0.5:
            score += 0.05

        # WF通过率 (0.10)
        score += profile.wf_pass_rate * 0.10

        return score

    def _generate_recommendation(
        self,
        trad: StrategyProfile,
        ml: StrategyProfile,
        winner: str,
    ) -> str:
        """生成推荐建议"""
        if winner == "traditional":
            return (
                f"传统量化策略胜出 (置信度中高)。"
                f"最佳Sharpe={trad.best_sharpe:.2f}, "
                f"年化收益={trad.best_annual_return:.2%}, "
                f"最大回撤={trad.best_max_drawdown:.2%}。"
                f"建议使用传统策略的最佳配置进行实盘部署。"
            )
        elif winner == "ml":
            return (
                f"ML策略胜出 (置信度中高)。"
                f"最佳Sharpe={ml.best_sharpe:.2f}, "
                f"年化收益={ml.best_annual_return:.2%}, "
                f"最大回撤={ml.best_max_drawdown:.2%}。"
                f"建议使用ML策略的最佳配置，但需关注过拟合风险。"
            )
        else:
            return (
                f"两种策略表现接近。"
                f"传统最佳Sharpe={trad.best_sharpe:.2f}, "
                f"ML最佳Sharpe={ml.best_sharpe:.2f}。"
                f"建议综合使用两种策略的优势配置进行组合部署。"
            )
