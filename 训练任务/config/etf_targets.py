"""训练目标ETF池配置"""

# A股核心宽基ETF
TARGET_A_SHARE = [
    "510300",  # 沪深300ETF
    "510500",  # 中证500ETF
    "159915",  # 创业板ETF
    "510050",  # 上证50ETF
]

# 美股核心宽基ETF
TARGET_US = [
    "SPY",  # SPDR标普500
    "QQQ",  # 纳斯达克100
]

# 全部训练目标
ALL_TARGETS = TARGET_A_SHARE + TARGET_US

# ETF名称映射
ETF_NAMES = {
    "510300": "沪深300ETF",
    "510500": "中证500ETF",
    "159915": "创业板ETF",
    "510050": "上证50ETF",
    "SPY": "SPDR标普500",
    "QQQ": "纳斯达克100",
}

# 基准ETF (用于Beta/信息比率计算)
BENCHMARK_CODE = "510300"


def get_training_codes(market: str = "all") -> list[str]:
    """获取训练目标ETF代码列表"""
    if market == "a":
        return TARGET_A_SHARE
    elif market == "us":
        return TARGET_US
    return ALL_TARGETS
