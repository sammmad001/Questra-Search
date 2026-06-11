"""传统量化策略100轮迭代Runner — 薄封装 etf-signal 回测引擎

核心复用:
- etf_signal.run_signal_driven_backtest()  → 回测
- etf_signal.WalkForwardValidator           → 防过拟合验证
- etf_signal.generate_momentum_report()     → HTML报告
- ParamEvolver                              → 参数进化 (自研)
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

# 确保 etf_signal 包可导入
_PROJECT_ROOT = str(Path(__file__).resolve().parents[2])
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)
_QUANTFLOW = "/Users/sam/Desktop/QuantFlow/etf-signal"
if _QUANTFLOW not in sys.path:
    sys.path.insert(0, _QUANTFLOW)

from etf_signal.backtest.walk_forward import WalkForwardValidator, WFValidationConfig
from etf_signal.portfolio.models import SignalDrivenConfig
from etf_signal.portfolio.signal_engine import run_signal_driven_backtest
from etf_signal.report.portfolio_report import generate_momentum_report

# 本地模块
from strategies.base_strategy import RoundResult, normalize_from_signal_result
from strategies.traditional.param_evolver import ParamEvolver


class TraditionalRunner:
    """传统量化策略100轮迭代Runner

    每轮:
    1. 获取滚动窗口数据 (DataManager)
    2. 调用 run_signal_driven_backtest(config) (etf-signal)
    3. Walk-Forward 验证 (每10轮)
    4. 生成 HTML 报告 (etf-signal)
    5. 参数进化 (ParamEvolver)
    """

    def __init__(
        self,
        data_manager,  # DataManager 实例
        output_dir: str | Path,
        params=None,   # TraditionalParams
    ):
        self.data_mgr = data_manager
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.params = params
        self.evolver = ParamEvolver()
        self.history: list[RoundResult] = []
        self._best_sharpe = -np.inf

    def run_all(self, rounds: int = 100) -> list[RoundResult]:
        """执行N轮传统策略迭代训练"""
        print(f"\n{'='*60}")
        print(f"  传统量化策略训练启动 — 共 {rounds} 轮")
        print(f"{'='*60}")

        # 初始配置 — 从 TraditionalParams 映射到 SignalDrivenConfig
        current_config = self._build_initial_config()

        for i in range(rounds):
            round_start = time.time()
            print(f"\n  [传统] 第 {i+1}/{rounds} 轮...")

            try:
                result = self._run_one_round(i, current_config)
            except Exception as e:
                print(f"  [传统] 第 {i+1} 轮失败: {e}")
                result = RoundResult(
                    round_idx=i,
                    strategy_type="traditional",
                    success=False,
                    elapsed_seconds=time.time() - round_start,
                )
                result.config_snapshot = current_config.model_dump()

            self.history.append(result)

            # 更新最佳
            if result.success and result.sharpe_ratio > self._best_sharpe:
                self._best_sharpe = result.sharpe_ratio
                print(f"  [传统] 新最佳! Sharpe={result.sharpe_ratio:.4f}")

            print(f"  [传统] {result.summary()} ({result.elapsed_seconds:.1f}s)")

            # 参数进化
            current_config = self.evolver.evolve(
                current_config,
                last_result=result if result.success else None,
                history=self.history,
            )

        # 保存汇总
        self._save_summary()
        return self.history

    def _build_initial_config(self) -> SignalDrivenConfig:
        """从 TraditionalParams 构建初始 SignalDrivenConfig"""
        kwargs = {}
        if self.params:
            kwargs["initial_capital"] = self.params.initial_capital
            kwargs["stop_loss_pct"] = self.params.stop_loss_pct
            kwargs["take_profit_pct"] = self.params.take_profit_pct
            kwargs["commission_rate"] = self.params.commission_rate
            kwargs["slippage_pct"] = self.params.slippage_pct
        return SignalDrivenConfig(**kwargs)

    def _run_one_round(
        self,
        round_idx: int,
        config: SignalDrivenConfig,
    ) -> RoundResult:
        """执行单轮: 数据 → 回测 → 验证 → 报告"""
        start = time.time()

        # 1. 获取滚动窗口数据
        all_history, all_names = self.data_mgr.get_all_for_backtest(round_idx + 1)
        if not all_history:
            raise ValueError(f"第{round_idx+1}轮: 无可用数据")

        # 2. 调用 etf-signal 回测 (核心!)
        result = run_signal_driven_backtest(
            all_history=all_history,
            all_names=all_names,
            config=config,
        )

        # 3. Walk-Forward 验证 (每10轮)
        wf_valid = False
        wf_decay = 0.0
        if round_idx % 10 == 0 and len(result.daily_returns) > 630:
            try:
                validator = WalkForwardValidator(
                    WFValidationConfig(n_splits=6),
                )
                wf_result = validator.validate_from_returns(
                    result.daily_returns, result.dates,
                )
                wf_valid = wf_result.passed
                wf_decay = wf_result.wf_decay_ratio
                print(f"  [传统] WF验证: {'PASS' if wf_valid else 'FAIL'} (decay={wf_decay:.4f})")
            except Exception as e:
                print(f"  [传统] WF验证跳过: {e}")

        # 4. 生成 HTML 报告
        report_path = self.output_dir / f"round_{round_idx+1:03d}.html"
        try:
            generate_momentum_report(
                result,
                report_path,
                title=f"传统策略 第{round_idx+1}轮",
            )
        except Exception as e:
            print(f"  [传统] 报告生成失败: {e}")
            report_path = Path("")

        elapsed = time.time() - start

        # 5. 统一为 RoundResult
        return normalize_from_signal_result(
            result=result,
            round_idx=round_idx,
            elapsed=elapsed,
            config_snapshot=config.model_dump(),
            report_path=str(report_path),
            wf_valid=wf_valid,
            wf_decay=wf_decay,
        )

    def _save_summary(self):
        """保存汇总JSON和CSV"""
        # JSON
        summary = {
            "strategy": "traditional",
            "total_rounds": len(self.history),
            "successful_rounds": sum(1 for r in self.history if r.success),
            "best_sharpe": self._best_sharpe,
            "history": [
                {
                    "round": r.round_idx,
                    "success": r.success,
                    "annual_return": round(r.annual_return, 6),
                    "max_drawdown": round(r.max_drawdown, 6),
                    "sharpe_ratio": round(r.sharpe_ratio, 6),
                    "calmar_ratio": round(r.calmar_ratio, 6),
                    "walk_forward_valid": r.walk_forward_valid,
                    "elapsed": round(r.elapsed_seconds, 1),
                    "meets_targets": r.meets_targets,
                    "config": r.config_snapshot,
                }
                for r in self.history
            ],
        }
        json_path = self.output_dir / "summary.json"
        json_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False, default=str))
        print(f"  [传统] 汇总已保存: {json_path}")

        # CSV
        csv_path = self.output_dir / "history.csv"
        lines = ["round,success,annual_return,max_drawdown,sharpe,calmar,wf_valid,elapsed"]
        for r in self.history:
            lines.append(
                f"{r.round_idx},{r.success},{r.annual_return:.6f},"
                f"{r.max_drawdown:.6f},{r.sharpe_ratio:.4f},"
                f"{r.calmar_ratio:.4f},{'Y' if r.walk_forward_valid else 'N'},"
                f"{r.elapsed_seconds:.1f}"
            )
        csv_path.write_text("\n".join(lines))
