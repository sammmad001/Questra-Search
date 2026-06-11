"""综合对比HTML报告生成器 — 传统量化 vs ML策略

这是训练任务系统中唯一需要新写的大文件。
使用 Chart.js 渲染图表，风格与 etf-signal/etf-ml 的报告一致。

报告结构:
1. 总览卡片: 传统最佳 vs ML最佳
2. 收敛曲线: 200轮逐轮走势
3. 最佳策略详情
4. 过拟合评估对比
5. 推荐结论
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from analysis.comparison import ComparisonResult, StrategyProfile
from strategies.base_strategy import RoundResult


class ComparisonReportGenerator:
    """综合对比HTML报告生成器"""

    def generate(
        self,
        trad_results: list[RoundResult],
        ml_results: list[RoundResult],
        comparison: ComparisonResult,
        output_dir: Path,
    ) -> Path:
        """生成综合对比HTML报告"""
        output_dir.mkdir(parents=True, exist_ok=True)

        trad = comparison.traditional
        ml = comparison.ml

        # 提取图表数据
        trad_sharpes = json.dumps([round(r.sharpe_ratio, 4) for r in trad_results])
        ml_sharpes = json.dumps([round(r.sharpe_ratio, 4) for r in ml_results])
        trad_returns = json.dumps([round(r.annual_return, 4) for r in trad_results])
        ml_returns = json.dumps([round(r.annual_return, 4) for r in ml_results])
        trad_dds = json.dumps([round(r.max_drawdown, 4) for r in trad_results])
        ml_dds = json.dumps([round(r.max_drawdown, 4) for r in ml_results])
        trad_labels = json.dumps([f"T{r.round_idx+1}" for r in trad_results])
        ml_labels = json.dumps([f"M{r.round_idx+1}" for r in ml_results])

        # 合并标签 (用于对比图)
        all_labels = json.dumps(
            [f"T{i+1}" for i in range(len(trad_results))]
            + [f"M{i+1}" for i in range(len(ml_results))]
        )
        all_sharpes = json.dumps(
            [round(r.sharpe_ratio, 4) for r in trad_results]
            + [round(r.sharpe_ratio, 4) for r in ml_results]
        )
        all_colors = json.dumps(
            ["#2563eb"] * len(trad_results) + ["#16a34a"] * len(ml_results)
        )

        # 胜者样式
        winner_text = {
            "traditional": "传统量化策略胜出",
            "ml": "ML策略胜出",
            "tie": "势均力敌",
        }.get(comparison.winner, "未决")
        winner_class = "success" if comparison.winner != "tie" else "pending"

        # 构建表格
        trad_table = self._build_history_table(trad_results, "traditional")
        ml_table = self._build_history_table(ml_results, "ml")

        # 过拟合对比
        trad_wf_rate = f"{trad.wf_pass_rate:.0%}"
        ml_wf_rate = f"{ml.wf_pass_rate:.0%}"

        html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ETF策略训练综合对比报告</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
  :root {{ --green: #16a34a; --red: #dc2626; --amber: #f59e0b; --blue: #2563eb; --gray: #6b7280; --purple: #7c3aed; }}
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #f8fafc; color: #1e293b; padding: 24px; }}
  .header {{ text-align: center; padding: 32px; margin-bottom: 24px; background: linear-gradient(135deg, #1e40af, #7c3aed); color: white; border-radius: 16px; }}
  .header h1 {{ font-size: 32px; margin-bottom: 8px; }}
  .badge {{ display: inline-block; padding: 6px 18px; border-radius: 20px; font-weight: 600; font-size: 14px; }}
  .badge.success {{ background: rgba(255,255,255,0.2); color: #bbf7d0; }}
  .badge.pending {{ background: rgba(255,255,255,0.2); color: #fef08a; }}
  .vs-grid {{ display: grid; grid-template-columns: 1fr auto 1fr; gap: 16px; margin-bottom: 32px; align-items: center; }}
  .strategy-card {{ background: white; border-radius: 16px; padding: 24px; box-shadow: 0 4px 12px rgba(0,0,0,0.08); }}
  .strategy-card h2 {{ font-size: 18px; margin-bottom: 16px; padding-bottom: 8px; border-bottom: 2px solid #e2e8f0; }}
  .strategy-card.trad h2 {{ color: var(--blue); }}
  .strategy-card.ml h2 {{ color: var(--green); }}
  .vs-divider {{ font-size: 28px; font-weight: 800; color: var(--purple); text-align: center; }}
  .metric-row {{ display: flex; justify-content: space-between; padding: 10px 0; border-bottom: 1px solid #f1f5f9; font-size: 14px; }}
  .metric-row:last-child {{ border-bottom: none; }}
  .metric-label {{ color: var(--gray); }}
  .metric-value {{ font-weight: 700; }}
  .metric-value.good {{ color: var(--green); }}
  .metric-value.bad {{ color: var(--red); }}
  .section {{ background: white; border-radius: 16px; padding: 24px; margin-bottom: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); }}
  .section h2 {{ font-size: 18px; margin-bottom: 16px; color: var(--blue); border-bottom: 2px solid #e2e8f0; padding-bottom: 8px; }}
  .chart-container {{ position: relative; height: 320px; margin-bottom: 16px; }}
  .chart-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  th {{ background: #f1f5f9; padding: 10px 6px; text-align: center; font-weight: 600; position: sticky; top: 0; }}
  td {{ padding: 8px 6px; text-align: center; border-bottom: 1px solid #e2e8f0; }}
  tr.best td {{ background: #dcfce7; }}
  .table-wrap {{ max-height: 400px; overflow-y: auto; }}
  .recommendation {{ background: linear-gradient(135deg, #eff6ff, #f0fdf4); border-radius: 16px; padding: 24px; margin-bottom: 20px; border: 2px solid #93c5fd; }}
  .recommendation h2 {{ color: var(--blue); margin-bottom: 12px; }}
  .footer {{ text-align: center; color: var(--gray); font-size: 12px; margin-top: 24px; padding: 16px; }}
</style>
</head>
<body>

<div class="header">
  <h1>ETF策略训练综合对比报告</h1>
  <span class="badge {winner_class}">{winner_text}</span>
  <div style="margin-top:8px;font-size:13px;opacity:0.9;">
    传统 {trad.successful_rounds}轮 + ML {ml.successful_rounds}轮 | {datetime.now().strftime('%Y-%m-%d %H:%M')}
  </div>
</div>

<!-- ── VS 对比卡片 ── -->
<div class="vs-grid">
  <div class="strategy-card trad">
    <h2>传统量化策略</h2>
    <div class="metric-row"><span class="metric-label">最佳 Sharpe</span><span class="metric-value {self._color(trad.best_sharpe, 1.3)}">{trad.best_sharpe:.4f}</span></div>
    <div class="metric-row"><span class="metric-label">最佳年化收益</span><span class="metric-value {self._color(trad.best_annual_return, 0.30)}">{trad.best_annual_return:.2%}</span></div>
    <div class="metric-row"><span class="metric-label">最佳最大回撤</span><span class="metric-value {self._color_inv(trad.best_max_drawdown, 0.20)}">{trad.best_max_drawdown:.2%}</span></div>
    <div class="metric-row"><span class="metric-label">最佳 Calmar</span><span class="metric-value">{trad.best_calmar:.4f}</span></div>
    <div class="metric-row"><span class="metric-label">平均 Sharpe</span><span class="metric-value">{trad.avg_sharpe:.4f}</span></div>
    <div class="metric-row"><span class="metric-label">Sharpe 稳定性</span><span class="metric-value">{trad.std_sharpe:.4f}</span></div>
    <div class="metric-row"><span class="metric-label">WF通过率</span><span class="metric-value">{trad_wf_rate}</span></div>
    <div class="metric-row"><span class="metric-label">收敛轮次</span><span class="metric-value">{trad.convergence_round or '未达标'}</span></div>
    <div class="metric-row"><span class="metric-label">达标</span><span class="metric-value {'good' if trad.meets_targets else 'bad'}">{'YES' if trad.meets_targets else 'NO'}</span></div>
  </div>
  <div class="vs-divider">VS</div>
  <div class="strategy-card ml">
    <h2>ML策略</h2>
    <div class="metric-row"><span class="metric-label">最佳 Sharpe</span><span class="metric-value {self._color(ml.best_sharpe, 1.3)}">{ml.best_sharpe:.4f}</span></div>
    <div class="metric-row"><span class="metric-label">最佳年化收益</span><span class="metric-value {self._color(ml.best_annual_return, 0.30)}">{ml.best_annual_return:.2%}</span></div>
    <div class="metric-row"><span class="metric-label">最佳最大回撤</span><span class="metric-value {self._color_inv(ml.best_max_drawdown, 0.20)}">{ml.best_max_drawdown:.2%}</span></div>
    <div class="metric-row"><span class="metric-label">最佳 Calmar</span><span class="metric-value">{ml.best_calmar:.4f}</span></div>
    <div class="metric-row"><span class="metric-label">平均 Sharpe</span><span class="metric-value">{ml.avg_sharpe:.4f}</span></div>
    <div class="metric-row"><span class="metric-label">Sharpe 稳定性</span><span class="metric-value">{ml.std_sharpe:.4f}</span></div>
    <div class="metric-row"><span class="metric-label">WF通过率</span><span class="metric-value">{ml_wf_rate}</span></div>
    <div class="metric-row"><span class="metric-label">收敛轮次</span><span class="metric-value">{ml.convergence_round or '未达标'}</span></div>
    <div class="metric-row"><span class="metric-label">达标</span><span class="metric-value {'good' if ml.meets_targets else 'bad'}">{'YES' if ml.meets_targets else 'NO'}</span></div>
  </div>
</div>

<!-- ── 收敛曲线 ── -->
<div class="section">
  <h2>Sharpe 收敛曲线对比</h2>
  <div class="chart-container">
    <canvas id="sharpeChart"></canvas>
  </div>
</div>

<div class="section">
  <h2>年化收益走势对比</h2>
  <div class="chart-container">
    <canvas id="returnChart"></canvas>
  </div>
</div>

<div class="section">
  <h2>最大回撤走势对比</h2>
  <div class="chart-container">
    <canvas id="ddChart"></canvas>
  </div>
</div>

<!-- ── 差异分析 ── -->
<div class="section">
  <h2>差异分析</h2>
  <div style="display:grid;grid-template-columns:repeat(2,1fr);gap:12px;">
    <div class="metric-row"><span class="metric-label">Sharpe差异 (传统-ML)</span><span class="metric-value">{comparison.sharpe_diff:+.4f}</span></div>
    <div class="metric-row"><span class="metric-label">收益差异 (传统-ML)</span><span class="metric-value">{comparison.return_diff:+.2%}</span></div>
    <div class="metric-row"><span class="metric-label">WF通过率差异</span><span class="metric-value">{comparison.wf_pass_diff:+.2%}</span></div>
    <div class="metric-row"><span class="metric-label">胜出置信度</span><span class="metric-value">{comparison.winner_confidence:.0%}</span></div>
  </div>
</div>

<!-- ── 历史详情表 ── -->
<div class="chart-grid">
  <div class="section">
    <h2>传统策略历史 (Top rounds)</h2>
    <div class="table-wrap">{trad_table}</div>
  </div>
  <div class="section">
    <h2>ML策略历史 (Top rounds)</h2>
    <div class="table-wrap">{ml_table}</div>
  </div>
</div>

<!-- ── 推荐结论 ── -->
<div class="recommendation">
  <h2>推荐结论</h2>
  <p style="font-size:15px;line-height:1.8;">{comparison.recommendation}</p>
</div>

<div class="footer">
  ETF策略训练综合对比报告 | 传统{trad.successful_rounds}轮 + ML{ml.successful_rounds}轮 | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
</div>

<script>
// Sharpe收敛图
new Chart(document.getElementById('sharpeChart').getContext('2d'), {{
  type: 'line',
  data: {{
    labels: [...{trad_labels}, ...{ml_labels}],
    datasets: [
      {{ label: '传统Sharpe', data: {trad_sharpes}, borderColor: '#2563eb', borderWidth: 2, pointRadius: 1 }},
      {{ label: 'ML Sharpe', data: {ml_sharpes}, borderColor: '#16a34a', borderWidth: 2, pointRadius: 1 }}
    ]
  }},
  options: {{
    responsive: true, maintainAspectRatio: false,
    scales: {{ y: {{ title: {{ display: true, text: 'Sharpe Ratio' }} }} }},
    plugins: {{ annotation: {{ annotations: {{ target: {{ type: 'line', yMin: 1.3, yMax: 1.3, borderColor: '#dc2626', borderDash: [6,6], borderWidth: 1 }} }} }} }}
  }}
}});

// 年化收益图
new Chart(document.getElementById('returnChart').getContext('2d'), {{
  type: 'line',
  data: {{
    labels: [...{trad_labels}, ...{ml_labels}],
    datasets: [
      {{ label: '传统年化', data: {trad_returns}, borderColor: '#2563eb', borderWidth: 2, pointRadius: 1 }},
      {{ label: 'ML年化', data: {ml_returns}, borderColor: '#16a34a', borderWidth: 2, pointRadius: 1 }}
    ]
  }},
  options: {{
    responsive: true, maintainAspectRatio: false,
    scales: {{ y: {{ title: {{ display: true, text: '年化收益' }} }} }}
  }}
}});

// 回撤图
new Chart(document.getElementById('ddChart').getContext('2d'), {{
  type: 'line',
  data: {{
    labels: [...{trad_labels}, ...{ml_labels}],
    datasets: [
      {{ label: '传统MaxDD', data: {trad_dds}, borderColor: '#2563eb', borderWidth: 2, pointRadius: 1 }},
      {{ label: 'ML MaxDD', data: {ml_dds}, borderColor: '#16a34a', borderWidth: 2, pointRadius: 1 }}
    ]
  }},
  options: {{
    responsive: true, maintainAspectRatio: false,
    scales: {{ y: {{ title: {{ display: true, text: '最大回撤' }} }} }}
  }}
}});
</script>
</body>
</html>"""

        path = output_dir / "final_comparison.html"
        path.write_text(html, encoding="utf-8")
        return path

    # ── 辅助方法 ──

    @staticmethod
    def _color(value: float, target: float) -> str:
        return "good" if value >= target else "bad"

    @staticmethod
    def _color_inv(value: float, threshold: float) -> str:
        return "good" if value <= threshold else "bad"

    def _build_history_table(self, results: list[RoundResult], strategy: str) -> str:
        """构建历史表格HTML (只显示Top 20)"""
        sorted_results = sorted(results, key=lambda r: r.sharpe_ratio, reverse=True)[:20]
        rows = ""
        for i, r in enumerate(sorted_results):
            best_class = "best" if i == 0 else ""
            rows += f"""
            <tr class="{best_class}">
              <td>{r.round_idx+1}</td>
              <td>{r.sharpe_ratio:.4f}</td>
              <td>{r.annual_return:.2%}</td>
              <td>{r.max_drawdown:.2%}</td>
              <td>{r.calmar_ratio:.4f}</td>
              <td>{'Y' if r.walk_forward_valid else 'N'}</td>
            </tr>"""
        return f"""
        <table>
          <thead><tr><th>#</th><th>Sharpe</th><th>年化</th><th>MaxDD</th><th>Calmar</th><th>WF</th></tr></thead>
          <tbody>{rows}</tbody>
        </table>"""
