"""ETF双策略训练任务 — 主入口

用法:
  python run.py                           # 全量运行 (默认100轮)
  python run.py --rounds 10               # 10轮试运行
  python run.py --strategy traditional    # 仅传统策略
  python run.py --strategy ml             # 仅ML策略
  python run.py --mode sequential         # 串行模式 (资源受限)
  python run.py --mode parallel           # 并行模式 (默认)

流程:
  1. 数据加载 (一次, 缓存到Parquet)
  2. 并行训练 (传统100轮 + ML100轮)
  3. 对比分析 + 综合报告
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

# 确保 项目根目录 在 sys.path
_PROJECT_ROOT = str(Path(__file__).resolve().parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from config.etf_targets import ALL_TARGETS
from data.data_manager import DataManager
from strategies.base_strategy import RoundResult


def parse_args():
    parser = argparse.ArgumentParser(description="ETF双策略训练任务")
    parser.add_argument("--rounds", type=int, default=100, help="每种策略的训练轮数 (默认100)")
    parser.add_argument("--strategy", type=str, default="both",
                        choices=["traditional", "ml", "both"], help="策略选择")
    parser.add_argument("--mode", type=str, default="parallel",
                        choices=["parallel", "sequential"], help="执行模式")
    parser.add_argument("--output", type=str, default=None, help="输出目录")
    parser.add_argument("--etf-codes", type=str, default=None,
                        help="ETF代码列表 (逗号分隔, 默认全部)")
    parser.add_argument("--resume", type=str, default=None,
                        help="从指定输出目录恢复中断的训练 (如: ./output_100_v2)")
    return parser.parse_args()


def main():
    args = parse_args()

    # 配置
    etf_codes = args.etf_codes.split(",") if args.etf_codes else ALL_TARGETS
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = Path(args.output) if args.output else Path("output") / timestamp
    output_dir.mkdir(parents=True, exist_ok=True)
    cache_dir = str(output_dir / "cache")

    print("=" * 60)
    print("  ETF 双策略训练任务")
    print("=" * 60)
    print(f"  策略: {args.strategy}")
    print(f"  轮数: {args.rounds}")
    print(f"  模式: {args.mode}")
    print(f"  ETF: {etf_codes}")
    print(f"  输出: {output_dir}")
    print("=" * 60)

    total_start = time.time()

    # ── Step 1: 数据加载 ──
    print("\n[Step 1] 数据加载...")
    dm = DataManager(etf_codes=etf_codes, cache_dir=cache_dir)
    dm.load_all()

    # ── Step 2: 训练执行 ──
    trad_results: list[RoundResult] = []
    ml_results: list[RoundResult] = []

    # 断点续训: 从 checkpoint.json 恢复
    resume_info = None
    if args.resume:
        resume_dir = Path(args.resume)
        checkpoint_path = resume_dir / "checkpoint.json"
        if checkpoint_path.exists():
            resume_info = json.loads(checkpoint_path.read_text())
            print(f"  [续训] 检测到 checkpoint: {resume_info['ml']['completed_rounds']}/{resume_info['total_rounds']} 轮已完成")
            # 使用原始输出目录
            output_dir = resume_dir
        else:
            print(f"  [续训] 未找到 checkpoint.json, 将从头开始")

    if args.strategy == "both":
        if args.mode == "parallel":
            from training.parallel_executor import ParallelExecutor
            executor = ParallelExecutor(output_dir=output_dir)
            all_results = executor.run_parallel(
                cache_dir=cache_dir,
                etf_codes=etf_codes,
                rounds=args.rounds,
            )
            trad_results = all_results["traditional"]
            ml_results = all_results["ml"]
        else:
            from training.parallel_executor import ParallelExecutor
            executor = ParallelExecutor(output_dir=output_dir)
            all_results = executor.run_sequential(
                cache_dir=cache_dir,
                etf_codes=etf_codes,
                rounds=args.rounds,
                resume_info=resume_info,
            )
            trad_results = all_results["traditional"]
            ml_results = all_results["ml"]

    elif args.strategy == "traditional":
        from strategies.traditional.runner import TraditionalRunner
        runner = TraditionalRunner(data_manager=dm, output_dir=output_dir / "traditional")
        trad_results = runner.run_all(rounds=args.rounds)

    elif args.strategy == "ml":
        from strategies.ml.runner import MLRunner
        # 续训: 传入已完成的轮数偏移
        resume_offset = 0
        if resume_info and resume_info.get("ml", {}).get("status") == "interrupted":
            resume_offset = resume_info["ml"]["resume_from_iter"]
            remaining = resume_info["ml"]["remaining_rounds"]
            print(f"  [续训] ML 从第 {resume_offset} 轮继续, 剩余 {remaining} 轮")
        runner = MLRunner(data_manager=dm, output_dir=output_dir / "ml", resume_offset=resume_offset)
        ml_results = runner.run_all(rounds=args.rounds)

    # ── 续训: 合并已有结果 ──
    if resume_info:
        # 合并传统策略已有结果
        if resume_info.get("traditional", {}).get("status") == "completed":
            trad_summary_path = Path(resume_info["traditional"]["summary_path"])
            if trad_summary_path.exists():
                from strategies.base_strategy import RoundResult as _RR
                trad_data = json.loads(trad_summary_path.read_text())
                existing_trad = [
                    _RR(
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
                trad_results = existing_trad + [r for r in trad_results if r not in existing_trad]
                print(f"  [续训] 传统策略: 合并 {len(existing_trad)} 轮已有结果")

    # ── Step 3: 对比分析 + 综合报告 ──
    if trad_results and ml_results:
        print("\n[Step 3] 生成综合对比报告...")
        from training.parallel_executor import ParallelExecutor
        executor = ParallelExecutor(output_dir=output_dir)
        report_path = executor.generate_final_report(trad_results, ml_results)
    elif trad_results:
        print("\n[完成] 传统策略训练完成")
    elif ml_results:
        print("\n[完成] ML策略训练完成")

    total_elapsed = time.time() - total_start

    # ── 保存运行元数据 ──
    meta = {
        "timestamp": timestamp,
        "strategy": args.strategy,
        "rounds": args.rounds,
        "mode": args.mode,
        "etf_codes": etf_codes,
        "output_dir": str(output_dir),
        "total_elapsed_seconds": round(total_elapsed, 1),
        "traditional_rounds": len(trad_results),
        "ml_rounds": len(ml_results),
        "traditional_best_sharpe": max((r.sharpe_ratio for r in trad_results), default=0),
        "ml_best_sharpe": max((r.sharpe_ratio for r in ml_results), default=0),
    }
    meta_path = output_dir / "run_meta.json"
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False))

    print(f"\n{'='*60}")
    print(f"  全部完成! 总耗时 {total_elapsed:.1f}s")
    print(f"  传统策略: {len(trad_results)}轮, "
          f"最佳Sharpe={max((r.sharpe_ratio for r in trad_results), default=0):.4f}")
    print(f"  ML策略: {len(ml_results)}轮, "
          f"最佳Sharpe={max((r.sharpe_ratio for r in ml_results), default=0):.4f}")
    print(f"  输出目录: {output_dir}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
