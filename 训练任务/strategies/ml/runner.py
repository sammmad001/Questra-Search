"""ML策略100轮Runner — 薄封装 etf-ml 的 StrategyIterationEngine

核心复用:
- etf_ml.StrategyIterationEngine.run()  → 完整100轮迭代训练
  (内部自动: Trainer.train × 100轮 → FactorEvoAgent进化 → HTML报告 → 防过拟合验证)
- etf_ml.IterationConfig               → 迭代配置
- etf_ml.data.local_store.LocalDataStore → 数据持久化

本模块仅做配置映射 + 数据桥接 + 结果格式转换
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import os
import pandas as pd

# 确保包可导入
_PROJECT_ROOT = str(Path(__file__).resolve().parents[2])
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)
_ETF_ML = "/Users/sam/Desktop/QuantFlow/etf-ml"
if _ETF_ML not in sys.path:
    sys.path.insert(0, _ETF_ML)

from etf_ml.training.strategy_iteration import IterationConfig, StrategyIterationEngine

# 本地模块
from strategies.base_strategy import RoundResult, normalize_from_ml_history

# Parquet列规范
PARQUET_COLUMNS = ["date", "open", "high", "low", "close", "volume", "amount"]


class MLRunner:
    """ML策略100轮Runner — 极简封装 StrategyIterationEngine

    几乎不做新逻辑，仅:
    1. 将 DataManager 的数据写入 LocalDataStore 格式
    2. 配置 IterationConfig (从训练参数映射)
    3. 调用 engine.run() (etf-ml自动100轮)
    4. 将结果转换为 RoundResult 列表
    """

    def __init__(
        self,
        data_manager,  # DataManager 实例
        output_dir: str | Path,
        params=None,   # MLParams
        tushare_token: str = "",
        resume_offset: int = 0,  # 断点续训: 从第几轮开始 (0=从头)
    ):
        self.data_mgr = data_manager
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.params = params
        self._token = tushare_token
        self._resume_offset = resume_offset

    def run_all(self, rounds: int = 100) -> list[RoundResult]:
        """执行N轮ML策略迭代训练"""
        print(f"\n{'='*60}")
        print(f"  ML策略训练启动 — 共 {rounds} 轮")
        print(f"{'='*60}")

        start = time.time()

        # Step 1: 准备本地数据 (DataManager → LocalDataStore格式)
        print("  [ML] 准备数据...")
        local_store = self._prepare_local_store()

        # Step 2: 构建 IterationConfig
        iter_config = self._build_iter_config(rounds)

        # Step 3: 调用 etf-ml 的 StrategyIterationEngine (核心!)
        print(f"  [ML] 启动 StrategyIterationEngine ({rounds}轮)...")
        engine = StrategyIterationEngine(
            config=iter_config,
            local_store=local_store,
        )
        engine_result = engine.run()  # 自动跑100轮 + 进化 + 生成报告

        elapsed = time.time() - start
        print(f"  [ML] 训练完成! 耗时 {elapsed:.1f}s")

        # Step 3.5: 续训重映射 — 将 _resume_tmp/iter_{i} → iterations/iter_{offset+i}
        if self._resume_offset > 0:
            self._remap_resume_iterations()

        # Step 4: 转换为统一的 RoundResult 列表
        results = self._convert_results(engine_result)

        # Step 5: 保存汇总
        self._save_summary(engine_result, results, elapsed)

        return results

    def _remap_resume_iterations(self):
        """续训: 将 _resume_tmp/iter_{i} 重命名为 iterations/iter_{offset+i}"""
        import shutil
        tmp_dir = self.output_dir / "iterations" / "_resume_tmp"
        iter_base = self.output_dir / "iterations"

        if not tmp_dir.exists():
            return

        # 收集临时目录中的迭代
        tmp_iters = sorted(
            [d for d in os.listdir(tmp_dir) if d.startswith("iter_") and d[5:].isdigit()],
            key=lambda x: int(x[5:]),
        )

        for tmp_name in tmp_iters:
            local_i = int(tmp_name[5:])
            global_i = self._resume_offset + local_i
            src = tmp_dir / tmp_name
            dst = iter_base / f"iter_{global_i}"
            if dst.exists():
                shutil.rmtree(dst)
            shutil.move(str(src), str(dst))

        # 移动 reports 和其他文件
        for item in tmp_dir.iterdir():
            if item.name.startswith("iter_"):
                continue
            dst = iter_base / item.name
            if dst.exists() and dst.is_dir():
                shutil.rmtree(dst)
            elif dst.exists():
                dst.unlink()
            shutil.move(str(item), str(dst))

        # 删除临时目录
        tmp_dir.rmdir()
        print(f"  [续训] 重映射完成: {len(tmp_iters)} 轮 → iter_{self._resume_offset}~iter_{self._resume_offset + len(tmp_iters) - 1}")

    def _prepare_local_store(self):
        """将 DataManager 的数据写入 LocalDataStore 格式

        DataManager 持有 _raw_dfs (dict[str, DataFrame]),
        需要写入到 LocalDataStore 的 raw/{code}.parquet 格式。
        """
        from etf_ml.data.local_store import LocalDataStore

        store_dir = self.output_dir / "data"
        store = LocalDataStore(root_dir=str(store_dir))
        raw_dir = store_dir / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)

        codes_written = []
        for code in self.data_mgr.codes:
            df = self.data_mgr.get_raw_df(code)
            if df.empty:
                continue

            # 确保列格式正确
            for col in PARQUET_COLUMNS:
                if col not in df.columns:
                    if col == "amount":
                        df["amount"] = df.get("volume", 0) * df.get("close", 0)
                    else:
                        df[col] = 0.0

            df = df[PARQUET_COLUMNS].copy()
            df.to_parquet(raw_dir / f"{code}.parquet", index=False)
            codes_written.append(code)

        # 写入 manifest
        manifest = {
            "etf_codes": codes_written,
            "sync_time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "total_etfs": len(codes_written),
        }
        manifest_path = store_dir / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2))

        print(f"  [ML] 数据准备完成: {len(codes_written)} 只ETF")
        return store

    def _build_iter_config(self, rounds: int) -> IterationConfig:
        """从 MLParams / 默认值 构建 IterationConfig

        续训时: 输出到临时目录 _resume_tmp, 完成后重命名 iter_{offset+i} → 正确编号
        """
        if self._resume_offset > 0:
            # 续训模式: 输出到临时目录
            iter_output = str(self.output_dir / "iterations" / "_resume_tmp")
        else:
            iter_output = str(self.output_dir / "iterations")
        kwargs = {
            "max_iterations": rounds,
            "etf_codes": self.data_mgr.codes,
            "output_dir": iter_output,
            "generate_html_reports": True,
            # 默认PPO (ETF>8时DQN动作空间爆炸)
            "agent_types": ["ppo"],
            # 初始训练参数
            "initial_steps": 50_000,
            "steps_multiplier": 1.5,
            "max_steps": 500_000,
            "eval_episodes": 10,
            # 目标指标
            "target_annual_return": 0.30,
            "target_max_drawdown": 0.20,
            "target_sharpe": 1.3,
            "target_calmar": 1.0,
        }

        # 从 MLParams 覆盖
        if self.params:
            kwargs["lookback_days"] = self.params.lookback_days

        return IterationConfig(**kwargs)

    def _convert_results(self, engine_result: dict) -> list[RoundResult]:
        """将 engine.run() 的返回 dict 转换为 RoundResult 列表"""
        results = []
        iteration_history = engine_result.get("iteration_history", [])

        for rec in iteration_history:
            # 确定报告路径 (etf-ml自动生成的)
            iter_idx = rec.get("iteration", 0)
            # 续训: 全局迭代编号 = 偏移 + 局部编号
            global_iter_idx = self._resume_offset + iter_idx
            report_path = str(
                self.output_dir / "iterations" / "reports" / f"iter_{global_iter_idx:03d}.html"
            )

            rr = normalize_from_ml_history(rec, report_path=report_path)
            rr.round_idx = global_iter_idx
            results.append(rr)

        print(f"  [ML] 转换了 {len(results)} 轮结果")

        # 报告最佳结果
        if results:
            best = max(results, key=lambda r: r.sharpe_ratio)
            print(f"  [ML] 最佳: {best.summary()}")

        return results

    def _save_summary(
        self,
        engine_result: dict,
        results: list[RoundResult],
        elapsed: float,
    ):
        """保存汇总信息"""
        bp = engine_result.get("best_performance", {})
        summary = {
            "strategy": "ml",
            "total_rounds": len(results),
            "successful_rounds": sum(1 for r in results if r.success),
            "total_elapsed_seconds": round(elapsed, 1),
            "best_performance": bp,
            "best_config": engine_result.get("best_config", {}),
            "targets_met": engine_result.get("targets_met", False),
            "history": [
                {
                    "round": r.round_idx,
                    "success": r.success,
                    "annual_return": round(r.annual_return, 6),
                    "max_drawdown": round(r.max_drawdown, 6),
                    "sharpe_ratio": round(r.sharpe_ratio, 6),
                    "calmar_ratio": round(r.calmar_ratio, 6),
                    "walk_forward_valid": r.walk_forward_valid,
                    "overfitting_score": round(r.overfitting_score, 6),
                    "dsr": round(r.dsr, 6),
                    "meets_targets": r.meets_targets,
                }
                for r in results
            ],
        }
        json_path = self.output_dir / "summary.json"
        json_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False, default=str))
        print(f"  [ML] 汇总已保存: {json_path}")

        # CSV
        csv_path = self.output_dir / "history.csv"
        lines = ["round,success,annual_return,max_drawdown,sharpe,calmar,wf_valid,dsr,overfitting"]
        for r in results:
            lines.append(
                f"{r.round_idx},{r.success},{r.annual_return:.6f},"
                f"{r.max_drawdown:.6f},{r.sharpe_ratio:.4f},"
                f"{r.calmar_ratio:.4f},{'Y' if r.walk_forward_valid else 'N'},"
                f"{r.dsr:.4f},{r.overfitting_score:.4f}"
            )
        csv_path.write_text("\n".join(lines))
