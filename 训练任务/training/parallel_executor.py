"""并行执行器 — 同时运行传统量化策略和ML策略训练

两种并行策略:
- 模式A (并行): ProcessPoolExecutor, 两策略同时执行
- 模式B (串行): 依次执行, 适合资源受限场景

数据共享: 通过 Parquet 缓存文件, 子进程各自读取
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any

# 确保包可导入
_PROJECT_ROOT = str(Path(__file__).resolve().parents[1])
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from concurrent.futures import ProcessPoolExecutor, as_completed

from analysis.comparison import ComparisonAnalyzer
from report.comparison_report import ComparisonReportGenerator
from strategies.base_strategy import RoundResult


def _run_traditional_isolated(
    cache_dir: str,
    output_dir: str,
    etf_codes: list[str],
    rounds: int,
) -> list[dict]:
    """在子进程中运行传统策略 (隔离)"""
    from data.data_manager import DataManager
    from strategies.traditional.runner import TraditionalRunner

    # 从缓存加载数据
    dm = DataManager(etf_codes=etf_codes, cache_dir=cache_dir)
    dm.load_all()

    runner = TraditionalRunner(
        data_manager=dm,
        output_dir=output_dir,
    )
    results = runner.run_all(rounds=rounds)

    # 序列化为dict (子进程无法传递自定义对象)
    return [
        {
            "round_idx": r.round_idx,
            "strategy_type": r.strategy_type,
            "success": r.success,
            "annual_return": r.annual_return,
            "max_drawdown": r.max_drawdown,
            "sharpe_ratio": r.sharpe_ratio,
            "calmar_ratio": r.calmar_ratio,
            "sortino_ratio": r.sortino_ratio,
            "total_return": r.total_return,
            "win_rate": r.win_rate,
            "total_trades": r.total_trades,
            "walk_forward_valid": r.walk_forward_valid,
            "wf_decay_ratio": r.wf_decay_ratio,
            "overfitting_score": r.overfitting_score,
            "dsr": r.dsr,
            "config_snapshot": r.config_snapshot,
            "elapsed_seconds": r.elapsed_seconds,
        }
        for r in results
    ]


def _run_ml_isolated(
    cache_dir: str,
    output_dir: str,
    etf_codes: list[str],
    rounds: int,
) -> list[dict]:
    """在子进程中运行ML策略 (隔离)"""
    from data.data_manager import DataManager
    from strategies.ml.runner import MLRunner

    # 从缓存加载数据
    dm = DataManager(etf_codes=etf_codes, cache_dir=cache_dir)
    dm.load_all()

    runner = MLRunner(
        data_manager=dm,
        output_dir=output_dir,
    )
    results = runner.run_all(rounds=rounds)

    return [
        {
            "round_idx": r.round_idx,
            "strategy_type": r.strategy_type,
            "success": r.success,
            "annual_return": r.annual_return,
            "max_drawdown": r.max_drawdown,
            "sharpe_ratio": r.sharpe_ratio,
            "calmar_ratio": r.calmar_ratio,
            "sortino_ratio": r.sortino_ratio,
            "total_return": r.total_return,
            "win_rate": r.win_rate,
            "total_trades": r.total_trades,
            "walk_forward_valid": r.walk_forward_valid,
            "wf_decay_ratio": r.wf_decay_ratio,
            "overfitting_score": r.overfitting_score,
            "dsr": r.dsr,
            "config_snapshot": r.config_snapshot,
            "elapsed_seconds": r.elapsed_seconds,
        }
        for r in results
    ]


def _dict_to_round_result(d: dict) -> RoundResult:
    """将序列化的dict转回 RoundResult"""
    return RoundResult(
        round_idx=d["round_idx"],
        strategy_type=d["strategy_type"],
        success=d["success"],
        annual_return=d["annual_return"],
        max_drawdown=d["max_drawdown"],
        sharpe_ratio=d["sharpe_ratio"],
        calmar_ratio=d["calmar_ratio"],
        sortino_ratio=d.get("sortino_ratio", 0.0),
        total_return=d.get("total_return", 0.0),
        win_rate=d.get("win_rate", 0.0),
        total_trades=d.get("total_trades", 0),
        walk_forward_valid=d.get("walk_forward_valid", False),
        wf_decay_ratio=d.get("wf_decay_ratio", 0.0),
        overfitting_score=d.get("overfitting_score", 0.0),
        dsr=d.get("dsr", 0.0),
        config_snapshot=d.get("config_snapshot", {}),
        elapsed_seconds=d.get("elapsed_seconds", 0.0),
    )


class ParallelExecutor:
    """并行执行器"""

    def __init__(self, output_dir: str | Path):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def run_parallel(
        self,
        cache_dir: str,
        etf_codes: list[str],
        rounds: int = 100,
    ) -> dict[str, list[RoundResult]]:
        """并行执行两种策略"""
        trad_dir = str(self.output_dir / "traditional")
        ml_dir = str(self.output_dir / "ml")

        print(f"\n{'='*60}")
        print(f"  并行启动: 传统策略 + ML策略, 各{rounds}轮")
        print(f"{'='*60}")

        start = time.time()

        with ProcessPoolExecutor(max_workers=2) as pool:
            trad_future = pool.submit(
                _run_traditional_isolated,
                cache_dir, trad_dir, etf_codes, rounds,
            )
            ml_future = pool.submit(
                _run_ml_isolated,
                cache_dir, ml_dir, etf_codes, rounds,
            )

            # 等待完成
            trad_dicts = trad_future.result()
            ml_dicts = ml_future.result()

        elapsed = time.time() - start
        print(f"\n  并行训练完成! 总耗时 {elapsed:.1f}s")

        # 反序列化
        trad_results = [_dict_to_round_result(d) for d in trad_dicts]
        ml_results = [_dict_to_round_result(d) for d in ml_dicts]

        return {
            "traditional": trad_results,
            "ml": ml_results,
        }

    def run_sequential(
        self,
        cache_dir: str,
        etf_codes: list[str],
        rounds: int = 100,
        resume_info: dict | None = None,
    ) -> dict[str, list[RoundResult]]:
        """串行执行两种策略 (资源受限场景, 支持断点续训)"""
        from data.data_manager import DataManager
        from strategies.traditional.runner import TraditionalRunner
        from strategies.ml.runner import MLRunner

        trad_dir = self.output_dir / "traditional"
        ml_dir = self.output_dir / "ml"

        # 数据加载
        dm = DataManager(etf_codes=etf_codes, cache_dir=cache_dir)
        dm.load_all()

        # ── 传统策略: 如果已完成则跳过 ──
        trad_results = []
        if resume_info and resume_info.get("traditional", {}).get("status") == "completed":
            print(f"\n  [续训] 传统策略已完成, 跳过")
            trad_summary_path = trad_dir / "summary.json"
            if trad_summary_path.exists():
                import json
                trad_data = json.loads(trad_summary_path.read_text())
                trad_results = [
                    RoundResult(
                        round_idx=h["round"],
                        strategy_type="traditional",
                        success=h["success"],
                        annual_return=h.get("annual_return", 0),
                        max_drawdown=h.get("max_drawdown", 0),
                        sharpe_ratio=h.get("sharpe", 0),
                        calmar_ratio=h.get("calmar", 0),
                        walk_forward_valid=h.get("walk_forward_valid", False),
                        elapsed_seconds=h.get("elapsed", 0),
                    )
                    for h in trad_data.get("history", [])
                ]
        else:
            print(f"\n  串行模式: 先传统后ML")
            trad_runner = TraditionalRunner(data_manager=dm, output_dir=trad_dir)
            trad_results = trad_runner.run_all(rounds=rounds)

        # ── ML策略: 从断点继续 ──
        resume_offset = 0
        ml_rounds = rounds
        if resume_info and resume_info.get("ml", {}).get("status") == "interrupted":
            resume_offset = resume_info["ml"]["resume_from_iter"]
            ml_rounds = resume_info["ml"]["remaining_rounds"]
            print(f"  [续训] ML 从第 {resume_offset} 轮继续, 剩余 {ml_rounds} 轮")

        ml_runner = MLRunner(
            data_manager=dm, output_dir=ml_dir, resume_offset=resume_offset,
        )
        ml_results = ml_runner.run_all(rounds=ml_rounds)

        return {
            "traditional": trad_results,
            "ml": ml_results,
        }

    def generate_final_report(
        self,
        trad_results: list[RoundResult],
        ml_results: list[RoundResult],
    ) -> Path:
        """生成综合对比报告"""
        # 对比分析
        analyzer = ComparisonAnalyzer()
        comparison = analyzer.analyze(trad_results, ml_results)

        # 生成报告
        report_dir = self.output_dir / "comparison"
        generator = ComparisonReportGenerator()
        report_path = generator.generate(
            trad_results, ml_results, comparison, report_dir,
        )

        print(f"\n  综合对比报告: {report_path}")
        return report_path
