"""训练超参数配置"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class TrainingParams:
    """通用训练参数"""

    total_rounds: int = 100
    train_window: int = 504  # 训练窗口(2年交易日)
    val_window: int = 126  # 验证窗口(半年交易日)
    test_window: int = 126  # 测试窗口(半年交易日)
    initial_capital: float = 1_000_000.0
    label_days: int = 5  # 未来N日收益标签
    early_stop_patience: int = 15  # 早停耐心轮数
    min_improvement: float = 0.01  # 最小改善幅度
    lookback_days: int = 1000  # 数据回看天数
    commission_rate: float = 0.00025  # 佣金万2.5
    slippage_pct: float = 0.001  # 滑点0.1%
    stop_loss_pct: float = 0.08  # 默认止损8%
    take_profit_pct: float = 0.15  # 默认止盈15%


@dataclass
class TraditionalParams(TrainingParams):
    """传统量化策略参数"""

    # 参数搜索空间
    param_grid: dict[str, list[Any]] = field(default_factory=lambda: {
        "short_window": [5, 10, 15, 20],
        "long_window": [30, 40, 50, 60],
        "stop_loss_pct": [0.05, 0.08, 0.10, 0.12, 0.15],
        "take_profit_pct": [0.10, 0.15, 0.20, 0.25],
        "rsi_overbought": [65, 70, 75, 80],
        "rsi_oversold": [20, 25, 30, 35],
        "bollinger_std": [1.5, 2.0, 2.5, 3.0],
        "atr_multiplier": [1.5, 2.0, 2.5, 3.0],
        "position_size": [0.80, 0.85, 0.90, 0.95],
    })
    # 每轮随机搜索次数
    n_random_search: int = 20


@dataclass
class MLParams(TrainingParams):
    """ML策略参数"""

    # LightGBM超参
    lgbm_params: dict[str, Any] = field(default_factory=lambda: {
        "objective": "regression",
        "metric": "rmse",
        "num_leaves": 31,
        "learning_rate": 0.05,
        "feature_fraction": 0.8,
        "bagging_fraction": 0.8,
        "bagging_freq": 5,
        "max_depth": -1,
        "min_child_samples": 20,
        "lambda_l1": 0.1,
        "lambda_l2": 0.1,
        "n_estimators": 200,
        "verbose": -1,
    })

    # 随机森林超参
    rf_params: dict[str, Any] = field(default_factory=lambda: {
        "n_estimators": 200,
        "max_depth": 10,
        "min_samples_split": 10,
        "min_samples_leaf": 5,
        "max_features": "sqrt",
        "random_state": 42,
    })

    # DQN超参
    dqn_params: dict[str, Any] = field(default_factory=lambda: {
        "state_dim": 20,
        "action_dim": 3,  # 买入/持有/卖出
        "hidden_dim": 64,
        "learning_rate": 0.001,
        "gamma": 0.95,
        "epsilon_start": 1.0,
        "epsilon_end": 0.01,
        "epsilon_decay": 0.995,
        "buffer_size": 10000,
        "batch_size": 64,
        "episodes_per_round": 50,
    })

    # 特征选择
    feature_selection_k: int = 20
