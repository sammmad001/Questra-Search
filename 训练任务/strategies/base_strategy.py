"""统一训练结果容器 — 跨策略归一化的数据类

两种策略（传统量化 / ML）共享 RoundResult 结构，
用于对比分析、报告生成和结果传递。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RoundResult:
    """一轮训练的统一结果 — 传统和ML策略共用"""

    round_idx: int
    strategy_type: str  # "traditional" | "ml"
    success: bool
    elapsed_seconds: float = 0.0

    # ── 核心金融指标 (统一为小数, 如 0.305 表示 30.5%) ──
    annual_return: float = 0.0
    max_drawdown: float = 0.0
    sharpe_ratio: float = 0.0
    calmar_ratio: float = 0.0
    sortino_ratio: float = 0.0
    total_return: float = 0.0
    win_rate: float = 0.0
    total_trades: int = 0
    volatility: float = 0.0
    profit_loss_ratio: float = 0.0

    # ── 防过拟合指标 ──
    walk_forward_valid: bool = False
    wf_decay_ratio: float = 0.0
    overfitting_score: float = 0.0
    dsr: float = 0.0
    dsr_significant: bool = False

    # ── 元数据 ──
    config_snapshot: dict[str, Any] = field(default_factory=dict)
    report_path: str = ""
    raw_result: Any = None  # MultiStrategyResult | TrainingResult

    # ── 目标达成 ──
    TARGET_ANN_RETURN: float = 0.30
    TARGET_MAX_DD: float = 0.20
    TARGET_SHARPE: float = 1.3
    TARGET_CALMAR: float = 1.0

    @property
    def meets_targets(self) -> bool:
        """是否达到核心目标"""
        return (
            self.annual_return >= self.TARGET_ANN_RETURN
            and self.max_drawdown <= self.TARGET_MAX_DD
            and self.sharpe_ratio >= self.TARGET_SHARPE
            and self.calmar_ratio >= self.TARGET_CALMAR
        )

    def summary(self) -> str:
        """可读摘要"""
        mark = "PASS" if self.meets_targets else "----"
        return (
            f"[{mark}] R{self.round_idx:03d} "
            f"Ann={self.annual_return:.2%} "
            f"MaxDD={self.max_drawdown:.2%} "
            f"Sharpe={self.sharpe_ratio:.2f} "
            f"Calmar={self.calmar_ratio:.2f} "
            f"WF={'Y' if self.walk_forward_valid else 'N'} "
            f"DSR={self.dsr:.2f}"
        )


def normalize_from_signal_result(
    result,  # MultiStrategyResult from etf-signal
    round_idx: int,
    elapsed: float,
    config_snapshot: dict,
    report_path: str,
    wf_valid: bool = False,
    wf_decay: float = 0.0,
) -> RoundResult:
    """从 etf-signal 的 MultiStrategyResult 转换为 RoundResult

    注意: MultiStrategyResult 的 annual_return / max_drawdown 是百分比形式
    (如 30.5 表示 30.5%)，需要除以100转为小数。
    """
    return RoundResult(
        round_idx=round_idx,
        strategy_type="traditional",
        success=True,
        elapsed_seconds=elapsed,
        annual_return=getattr(result, "annual_return", 0.0) / 100.0,
        max_drawdown=getattr(result, "max_drawdown", 0.0) / 100.0,
        sharpe_ratio=getattr(result, "sharpe_ratio", 0.0),
        calmar_ratio=getattr(result, "calmar_ratio", 0.0),
        sortino_ratio=getattr(result, "sortino_ratio", 0.0),
        total_return=getattr(result, "total_return", 0.0) / 100.0,
        win_rate=getattr(result, "win_rate", 0.0) / 100.0,
        total_trades=getattr(result, "n_trades", 0),
        profit_loss_ratio=getattr(result, "profit_loss_ratio", 0.0),
        walk_forward_valid=wf_valid,
        wf_decay_ratio=wf_decay,
        config_snapshot=config_snapshot,
        report_path=report_path,
        raw_result=result,
    )


def normalize_from_ml_history(
    record: dict,  # iteration_history 中的单条记录
    report_path: str = "",
) -> RoundResult:
    """从 etf-ml 的 iteration_history 记录转换为 RoundResult

    注意: etf-ml 的 PerformanceMetrics 已是小数形式。
    """
    return RoundResult(
        round_idx=record.get("iteration", 0),
        strategy_type="ml",
        success=True,
        elapsed_seconds=record.get("elapsed", 0.0),
        annual_return=record.get("annualized_return", 0.0),
        max_drawdown=record.get("max_drawdown", 0.0),
        sharpe_ratio=record.get("sharpe", 0.0),
        calmar_ratio=record.get("calmar_ratio", 0.0),
        total_return=0.0,  # etf-ml history 中未单独记录
        win_rate=0.0,
        walk_forward_valid=record.get("walk_forward_valid", False),
        overfitting_score=record.get("overfitting_score", 0.0),
        dsr=record.get("dsr", 0.0),
        config_snapshot=record.get("config", {}),
        report_path=report_path,
    )
