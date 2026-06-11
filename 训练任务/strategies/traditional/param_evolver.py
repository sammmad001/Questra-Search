"""传统策略参数进化Agent — 根据 SignalDrivenConfig 参数空间进化

参照 etf_ml.FactorEvoAgent 的设计思路，针对 etf-signal 的
SignalDrivenConfig 参数空间进行智能调参。

进化维度 (9个核心参数):
- stop_loss_pct: 固定止损
- take_profit_pct: 止盈
- trailing_stop_pct: 追踪止损
- rebalance_interval: 调仓间隔
- top_n: 候选池大小
- atr_stop_mult: ATR止损倍数
- max_weight: 单ETF最大仓位
- use_regime_v2: 市场体制版本
- use_ic_weights: IC动态权重
"""

from __future__ import annotations

import copy

import numpy as np


# 参数搜索空间
PARAM_SPACE = {
    "stop_loss_pct": [0.05, 0.08, 0.10, 0.12, 0.15, 0.20],
    "take_profit_pct": [0.0, 0.10, 0.15, 0.20, 0.25],
    "trailing_stop_pct": [0.0, 0.05, 0.07, 0.08, 0.10],
    "rebalance_interval": [5, 7, 10, 15, 20],
    "top_n": [2, 3, 4, 5],
    "atr_stop_mult": [2.5, 3.0, 3.5, 4.0, 5.0],
    "max_weight": [0.25, 0.30, 0.35, 0.40, 0.45],
    "use_regime_v2": [True, False],
    "use_ic_weights": [True, False],
}


class ParamEvolver:
    """参数进化Agent — 基于历史表现的规则系统调参

    策略:
    1. Sharpe提升但回撤大 → 收紧止损 + 降仓
    2. Sharpe下降 → 调止损/切换regime版本
    3. 收益不足 → 放宽调仓间隔 + 扩大候选池
    4. 过拟合(WF invalid) → 减少自由度 + 切换IC权重
    5. 长期无改善 → 全局随机重启
    6. 15%概率随机扰动 (避免局部最优)
    """

    def __init__(self):
        self._iteration = 0
        self._no_improve_count = 0

    def evolve(
        self,
        current_config,  # SignalDrivenConfig (Pydantic model)
        last_result,     # RoundResult
        history: list,   # list[RoundResult]
    ) -> object:
        """根据上一轮表现进化 SignalDrivenConfig"""
        self._iteration += 1
        new_cfg = current_config.model_copy()

        # 首轮无历史 — 使用默认
        if last_result is None:
            return new_cfg

        # 计算改善
        if len(history) >= 2:
            improvement = last_result.sharpe_ratio - history[-2].sharpe_ratio
        else:
            improvement = 0.0

        if improvement > 0.01:
            self._no_improve_count = 0
        else:
            self._no_improve_count += 1

        # ── 规则1: 回撤过大 → 收紧风控 ──
        if last_result.max_drawdown > 0.20:
            self._tighten_risk(new_cfg)

        # ── 规则2: Sharpe不达标 → 调整止损/策略开关 ──
        if last_result.sharpe_ratio < 1.0:
            self._adjust_for_sharpe(new_cfg)

        # ── 规则3: 收益不足 → 放宽参数 ──
        if last_result.annual_return < 0.30:
            self._expand_params(new_cfg)

        # ── 规则4: 过拟合 → 减少自由度 ──
        if not last_result.walk_forward_valid:
            self._reduce_overfitting(new_cfg)

        # ── 规则5: 长期无改善 → 全局重启 ──
        if self._no_improve_count >= 15:
            self._random_restart(new_cfg)
            self._no_improve_count = 0
            return new_cfg

        # ── 规则6: 15%概率随机扰动 ──
        if np.random.random() < 0.15:
            self._random_perturbation(new_cfg)

        return new_cfg

    # ── 具体调整方法 ──

    def _tighten_risk(self, cfg):
        """收紧风控: 降低止损阈值 + 降低最大仓位"""
        # 选择更紧的止损
        current = cfg.stop_loss_pct
        candidates = [x for x in PARAM_SPACE["stop_loss_pct"] if x < current]
        if candidates:
            cfg.stop_loss_pct = max(candidates)

        # 降低单ETF最大仓位
        current = cfg.max_weight
        candidates = [x for x in PARAM_SPACE["max_weight"] if x < current]
        if candidates:
            cfg.max_weight = max(candidates)

        # 启用追踪止损
        if cfg.trailing_stop_pct == 0.0:
            cfg.trailing_stop_pct = 0.07

    def _adjust_for_sharpe(self, cfg):
        """提升Sharpe: 切换策略开关 + 调整ATR"""
        # 每3轮切换一次 regime 版本
        if self._iteration % 3 == 0:
            cfg.use_regime_v2 = not cfg.use_regime_v2

        # 每5轮切换 IC权重
        if self._iteration % 5 == 0:
            cfg.use_ic_weights = not cfg.use_ic_weights

        # 调整ATR倍数
        current = cfg.atr_stop_mult
        candidates = [x for x in PARAM_SPACE["atr_stop_mult"] if x != current]
        if candidates:
            cfg.atr_stop_mult = float(np.random.choice(candidates))

    def _expand_params(self, cfg):
        """放宽参数: 增大候选池 + 放宽调仓间隔"""
        # 增大候选池
        current = cfg.top_n
        candidates = [x for x in PARAM_SPACE["top_n"] if x > current]
        if candidates:
            cfg.top_n = min(candidates)

        # 放宽调仓间隔
        current = cfg.rebalance_interval
        candidates = [x for x in PARAM_SPACE["rebalance_interval"] if x > current]
        if candidates:
            cfg.rebalance_interval = min(candidates)

    def _reduce_overfitting(self, cfg):
        """减少过拟合: 减少自由度"""
        # 减小候选池
        current = cfg.top_n
        candidates = [x for x in PARAM_SPACE["top_n"] if x < current]
        if candidates:
            cfg.top_n = max(candidates)

        # 收紧仓位
        current = cfg.max_weight
        candidates = [x for x in PARAM_SPACE["max_weight"] if x < current]
        if candidates:
            cfg.max_weight = max(candidates)

    def _random_restart(self, cfg):
        """全局随机重启 — 从参数空间随机采样"""
        for param, values in PARAM_SPACE.items():
            setattr(cfg, param, values[np.random.randint(len(values))])

    def _random_perturbation(self, cfg):
        """随机扰动 — 随机选一个参数改变"""
        param = np.random.choice(list(PARAM_SPACE.keys()))
        values = PARAM_SPACE[param]
        current = getattr(cfg, param, None)
        candidates = [v for v in values if v != current]
        if candidates:
            setattr(cfg, param, candidates[np.random.randint(len(candidates))])
