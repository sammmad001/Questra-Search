"""指标归一化 — 将两种策略不同格式的指标统一为标准dict

传统策略 (etf-signal MultiStrategyResult):
  - annual_return / max_drawdown / win_rate = 百分比形式 (如 30.5)
  - total_return = 百分比形式

ML策略 (etf-ml PerformanceMetrics):
  - annualized_return / max_drawdown / win_rate = 小数形式 (如 0.305)
  - total_return = 小数形式

统一输出: 全部使用小数形式
"""

from __future__ import annotations

from typing import Any

from strategies.base_strategy import RoundResult


class MetricsNormalizer:
    """指标归一化工具"""

    @staticmethod
    def from_round_result(r: RoundResult) -> dict[str, Any]:
        """从 RoundResult 提取标准指标dict"""
        return {
            "annual_return": r.annual_return,
            "max_drawdown": r.max_drawdown,
            "sharpe_ratio": r.sharpe_ratio,
            "calmar_ratio": r.calmar_ratio,
            "sortino_ratio": r.sortino_ratio,
            "total_return": r.total_return,
            "win_rate": r.win_rate,
            "total_trades": r.total_trades,
            "volatility": r.volatility,
            "profit_loss_ratio": r.profit_loss_ratio,
            "walk_forward_valid": r.walk_forward_valid,
            "wf_decay_ratio": r.wf_decay_ratio,
            "overfitting_score": r.overfitting_score,
            "dsr": r.dsr,
            "dsr_significant": r.dsr_significant,
        }

    @staticmethod
    def from_traditional_raw(result) -> dict[str, Any]:
        """从 etf-signal MultiStrategyResult 直接转换

        注意: MultiStrategyResult 使用百分比形式
        """
        return {
            "annual_return": getattr(result, "annual_return", 0.0) / 100.0,
            "max_drawdown": getattr(result, "max_drawdown", 0.0) / 100.0,
            "sharpe_ratio": getattr(result, "sharpe_ratio", 0.0),
            "calmar_ratio": getattr(result, "calmar_ratio", 0.0),
            "sortino_ratio": getattr(result, "sortino_ratio", 0.0),
            "total_return": getattr(result, "total_return", 0.0) / 100.0,
            "win_rate": getattr(result, "win_rate", 0.0) / 100.0,
            "total_trades": getattr(result, "n_trades", 0),
            "profit_loss_ratio": getattr(result, "profit_loss_ratio", 0.0),
        }

    @staticmethod
    def from_ml_raw(perf) -> dict[str, Any]:
        """从 etf-ml PerformanceMetrics 直接转换

        注意: PerformanceMetrics 已使用小数形式
        """
        return {
            "annual_return": getattr(perf, "annualized_return", 0.0),
            "max_drawdown": getattr(perf, "max_drawdown", 0.0),
            "sharpe_ratio": getattr(perf, "sharpe_ratio", 0.0),
            "calmar_ratio": getattr(perf, "calmar_ratio", 0.0),
            "total_return": getattr(perf, "total_return", 0.0),
            "win_rate": getattr(perf, "win_rate", 0.0),
            "total_trades": getattr(perf, "total_trades", 0),
            "volatility": getattr(perf, "volatility", 0.0),
            "walk_forward_valid": getattr(perf, "walk_forward_valid", False),
            "overfitting_score": getattr(perf, "overfitting_score", 0.0),
            "dsr": getattr(perf, "dsr", 0.0),
            "dsr_significant": getattr(perf, "dsr_significant", False),
        }

    @staticmethod
    def summarize_list(results: list[RoundResult]) -> dict[str, Any]:
        """汇总一组 RoundResult 的统计信息"""
        if not results:
            return {}

        import numpy as np

        successful = [r for r in results if r.success]
        if not successful:
            return {"total_rounds": len(results), "successful_rounds": 0}

        sharpes = [r.sharpe_ratio for r in successful]
        returns = [r.annual_return for r in successful]
        drawdowns = [r.max_drawdown for r in successful]
        wf_passes = sum(1 for r in successful if r.walk_forward_valid)

        best = max(successful, key=lambda r: r.sharpe_ratio)

        return {
            "total_rounds": len(results),
            "successful_rounds": len(successful),
            "best_sharpe": round(max(sharpes), 4),
            "avg_sharpe": round(float(np.mean(sharpes)), 4),
            "std_sharpe": round(float(np.std(sharpes)), 4),
            "best_annual_return": round(max(returns), 4),
            "avg_annual_return": round(float(np.mean(returns)), 4),
            "avg_max_drawdown": round(float(np.mean(drawdowns)), 4),
            "wf_pass_rate": round(wf_passes / len(successful), 4),
            "best_round": best.round_idx,
            "best_meets_targets": best.meets_targets,
        }
