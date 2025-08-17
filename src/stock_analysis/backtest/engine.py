"""回测引擎模块

提供统一的回测运行器、策略类和报告生成功能。
"""

import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

import backtrader as bt
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import pandas as pd

from ..utils.logging import StrategyLogger
from ..utils.paths import OUTPUTS_DIR


class PointInTimeStrategy(bt.Strategy):
    """统一的时点策略类
    
    整合了AI版本和未精选版本的策略逻辑，通过参数控制差异。
    """
    
    params = (
        ("portfolios", None),
        ("use_logging", True),  # 控制是否使用logging还是print
        ("logger_name", "strategy"),
    )
    
    def __init__(self):
        self.rebalance_dates = sorted(self.p.portfolios.keys())
        self.next_rebalance_idx = 0
        self.get_next_rebalance_date()
        self.timeline = self.datas[0]
        self.rebalance_log = []
        
        # 初始化日志器
        self.strategy_logger = StrategyLogger(
            use_logging=self.p.use_logging,
            logger_name=self.p.logger_name
        )
    
    def log(self, txt, dt=None):
        """记录日志"""
        dt = dt or self.timeline.datetime.date(0)
        self.strategy_logger.log(txt, dt)
    
    def get_next_rebalance_date(self):
        """获取下一个调仓日期"""
        if self.next_rebalance_idx < len(self.rebalance_dates):
            self.next_rebalance_date = self.rebalance_dates[self.next_rebalance_idx]
        else:
            self.next_rebalance_date = None
    
    def next(self):
        """策略主逻辑"""
        current_date = self.timeline.datetime.date(0)
        
        if self.next_rebalance_date and current_date >= self.next_rebalance_date:
            self.log(
                f"--- Rebalancing on {current_date} for signal date {self.next_rebalance_date} ---"
            )
            
            target_tickers_df = self.p.portfolios[self.next_rebalance_date]
            target_tickers = set(target_tickers_df["Ticker"])
            
            self.log(
                f"Diagnosis: Model selected {len(target_tickers)} tickers: {target_tickers}"
            )
            
            available_data_tickers = {d._name for d in self.datas}
            
            final_target_tickers = target_tickers.intersection(available_data_tickers)
            missing_tickers = target_tickers - available_data_tickers
            
            self.log(
                f"Diagnosis: {len(available_data_tickers)} tickers have price data available in the database."
            )
            self.log(
                f"Diagnosis: Intersection has {len(final_target_tickers)} tickers: "
                f"{final_target_tickers if final_target_tickers else 'EMPTY'}"
            )
            
            # 记录诊断信息
            log_entry = {
                "rebalance_date": self.next_rebalance_date,
                "model_tickers": len(target_tickers),
                "available_tickers": len(final_target_tickers),
                "missing_tickers_list": ", ".join(missing_tickers),
            }
            self.rebalance_log.append(log_entry)
            
            if not final_target_tickers:
                self.log(
                    "CRITICAL WARNING: All-cash period. No selected tickers were found in the price database."
                )
                if missing_tickers:
                    self.log(
                        f"CRITICAL WARNING: The following {len(missing_tickers)} tickers were missing price data: {missing_tickers}"
                    )
                
                self.next_rebalance_idx += 1
                self.get_next_rebalance_date()
                return
            
            # 平仓不在目标组合中的持仓
            current_positions = {
                data._name for data in self.datas if self.getposition(data).size > 0
            }
            
            for ticker in current_positions:
                if ticker not in final_target_tickers:
                    data = self.getdatabyname(ticker)
                    self.log(f"Closing position in {ticker}")
                    self.order_target_percent(data=data, target=0.0)
            
            # 等权重建仓
            target_percent = 1.0 / len(final_target_tickers)
            for ticker in final_target_tickers:
                data = self.getdatabyname(ticker)
                self.log(
                    f"Setting target position for {ticker} to {target_percent:.2%}"
                )
                self.order_target_percent(data=data, target=target_percent)
            
            self.next_rebalance_idx += 1
            self.get_next_rebalance_date()
            self.log("--- Rebalancing Complete ---")
    
    def stop(self):
        """策略结束时的处理"""
        self.log("--- Backtest Finished ---")
        log_df = pd.DataFrame(self.rebalance_log)
        if not log_df.empty:
            log_path = OUTPUTS_DIR / "rebalancing_diagnostics_log.csv"
            log_df.to_csv(log_path, index=False)
            self.log(f"Rebalancing diagnostics saved to: {log_path}")


class BuyAndHoldStrategy(bt.Strategy):
    """买入并持有策略
    
    用于基准测试，如SPY基准。
    """
    
    def __init__(self):
        self.bought = False
    
    def next(self):
        if not self.bought:
            self.order_target_percent(target=0.99)
            self.bought = True


def run_quarterly_backtest(
    portfolios: Dict[datetime.date, pd.DataFrame],
    data_feeds: Dict[str, bt.feeds.PandasData],
    initial_cash: float,
    start_date: datetime.date,
    end_date: datetime.date,
    use_logging: bool = True,
    add_observers: bool = False,
    add_annual_return: bool = False
) -> Tuple[pd.Series, Dict[str, Any]]:
    """运行季度调仓回测
    
    Args:
        portfolios: 投资组合字典
        data_feeds: 数据源字典
        initial_cash: 初始资金
        start_date: 开始日期
        end_date: 结束日期
        use_logging: 是否使用logging（True）还是print（False）
        add_observers: 是否添加观察器
        add_annual_return: 是否添加年化收益分析器
        
    Returns:
        Tuple[pd.Series, Dict]: 投资组合价值序列和指标字典
    """
    print(f"\n--- Running Quarterly {'AI Pick' if use_logging else 'Point-in-Time'} Strategy (Total Return) ---")
    
    # 创建Cerebro实例
    cerebro = bt.Cerebro(stdstats=not add_observers if add_observers else True)
    cerebro.broker.set_cash(initial_cash)
    
    # 添加数据源
    for name in sorted(data_feeds.keys()):
        cerebro.adddata(data_feeds[name], name=name)
    
    # 添加策略
    cerebro.addstrategy(
        PointInTimeStrategy,
        portfolios=portfolios,
        use_logging=use_logging
    )
    
    # 添加分析器
    cerebro.addanalyzer(bt.analyzers.TimeReturn, _name="time_return")
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name="drawdown")
    cerebro.addanalyzer(bt.analyzers.Returns, _name="returns")
    
    if add_annual_return:
        cerebro.addanalyzer(bt.analyzers.AnnualReturn, _name="annual_return")
    
    # 添加观察器（如果需要）
    if add_observers:
        cerebro.addobserver(bt.observers.Broker)
        cerebro.addobserver(bt.observers.Trades)
        cerebro.addobserver(bt.observers.BuySell)
    
    # 运行回测
    results = cerebro.run()
    strat = results[0]
    
    # 提取指标
    final_value = cerebro.broker.getvalue()
    total_return = strat.analyzers.returns.get_analysis().get("rtot", 0.0)
    max_drawdown = strat.analyzers.drawdown.get_analysis().max.drawdown
    
    # 计算年化收益率
    duration_in_days = (end_date - start_date).days
    annualized_return = 0.0
    if duration_in_days > 0:
        duration_in_years = duration_in_days / 365.25
        if duration_in_years > 0:
            annualized_return = ((1 + total_return) ** (1 / duration_in_years)) - 1
    
    # 生成投资组合价值序列
    tr_analyzer = strat.analyzers.getbyname("time_return")
    returns = pd.Series(tr_analyzer.get_analysis())
    cumulative_returns = (1 + returns).cumprod()
    portfolio_value = initial_cash * cumulative_returns
    
    # 添加初始值
    first_date = returns.index.min() if not returns.empty else start_date
    start_date_ts = pd.to_datetime(first_date) - pd.Timedelta(days=1)
    portfolio_value = pd.concat(
        [pd.Series({start_date_ts: initial_cash}), portfolio_value]
    )
    
    # 组装指标字典
    metrics = {
        "start_date": start_date,
        "end_date": end_date,
        "initial_value": initial_cash,
        "final_value": final_value,
        "total_return": total_return,
        "annualized_return": annualized_return,
        "max_drawdown": max_drawdown,
    }
    
    # 添加年化收益分析（如果有）
    if add_annual_return:
        annual_returns = strat.analyzers.getbyname("annual_return").get_analysis()
        metrics["annual_returns"] = annual_returns
    
    return portfolio_value, metrics


def run_benchmark_backtest(
    data: pd.DataFrame,
    initial_cash: float,
    ticker: str = "SPY"
) -> Tuple[pd.Series, Dict[str, Any]]:
    """运行基准回测（买入并持有）
    
    Args:
        data: 价格数据
        initial_cash: 初始资金
        ticker: 股票代码
        
    Returns:
        Tuple[pd.Series, Dict]: 投资组合价值序列和指标字典
    """
    print(f"\n--- Running {ticker} Buy-and-Hold Backtest (Total Return) ---")
    
    cerebro = bt.Cerebro()
    cerebro.broker.set_cash(initial_cash)
    
    # 准备数据源
    bt_feed = bt.feeds.PandasData(dataname=data, openinterest=None)
    cerebro.adddata(bt_feed)
    
    cerebro.addstrategy(BuyAndHoldStrategy)
    
    # 添加分析器
    cerebro.addanalyzer(bt.analyzers.TimeReturn, _name="time_return")
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name="drawdown")
    cerebro.addanalyzer(bt.analyzers.Returns, _name="returns")
    
    results = cerebro.run()
    strat = results[0]
    
    # 提取指标
    final_value = cerebro.broker.getvalue()
    total_return = strat.analyzers.returns.get_analysis().get("rtot", 0.0)
    max_drawdown = strat.analyzers.drawdown.get_analysis().max.drawdown
    
    start_date = data.index.min().date()
    end_date = data.index.max().date()
    
    # 计算年化收益率
    duration_in_days = (end_date - start_date).days
    annualized_return = 0.0
    if duration_in_days > 0:
        duration_in_years = duration_in_days / 365.25
        if duration_in_years > 0:
            annualized_return = ((1 + total_return) ** (1 / duration_in_years)) - 1
    
    # 生成投资组合价值序列
    tr_analyzer = strat.analyzers.getbyname("time_return")
    returns = pd.Series(tr_analyzer.get_analysis())
    cumulative_returns = (1 + returns).cumprod()
    portfolio_value = initial_cash * cumulative_returns
    start_date_ts = data.index.min() - pd.Timedelta(days=1)
    portfolio_value = pd.concat(
        [pd.Series({start_date_ts: initial_cash}), portfolio_value]
    )
    
    # 组装指标字典
    metrics = {
        "start_date": start_date,
        "end_date": end_date,
        "initial_value": initial_cash,
        "final_value": final_value,
        "total_return": total_return,
        "annualized_return": annualized_return,
        "max_drawdown": max_drawdown,
    }
    
    return portfolio_value, metrics


def generate_report(
    metrics: Dict[str, Any],
    title: str,
    portfolio_value: pd.Series,
    output_png: Optional[Path] = None,
    benchmark_value: Optional[pd.Series] = None,
    benchmark_label: str = "Benchmark"
) -> None:
    """生成统一的回测报告
    
    Args:
        metrics: 指标字典
        title: 报告标题
        portfolio_value: 投资组合价值序列
        output_png: 输出图片路径（可选）
        benchmark_value: 基准价值序列（可选）
        benchmark_label: 基准标签
    """
    # 打印文本报告
    print("\n" + "=" * 50)
    print(f"{title:^50}")
    print("=" * 50)
    print(
        f"Time Period Covered:     {metrics['start_date'].strftime('%Y-%m-%d')} to {metrics['end_date'].strftime('%Y-%m-%d')}"
    )
    print(f"Initial Portfolio Value: ${metrics['initial_value']:,.2f}")
    print(f"Final Portfolio Value:   ${metrics['final_value']:,.2f}")
    print("-" * 50)
    print(f"Total Return:            {metrics['total_return'] * 100:.2f}%")
    print(f"Annualized Return:       {metrics['annualized_return'] * 100:.2f}%")
    print(f"Max Drawdown:            {metrics['max_drawdown']:.2f}%")
    print("=" * 50)
    
    # 生成图表
    print("\nGenerating plot...")
    plt.style.use("seaborn-v0_8-whitegrid")
    fig, ax = plt.subplots(figsize=(14, 8))
    
    # 绘制主策略
    portfolio_value.plot(
        ax=ax,
        label=title.split("(")[0].strip(),
        color="steelblue",
        lw=2
    )
    
    # 绘制基准（如果提供）
    if benchmark_value is not None:
        benchmark_value.plot(
            ax=ax,
            label=benchmark_label,
            color="darkorange",
            lw=2
        )
    
    # 格式化图表
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, p: f"${x:,.0f}"))
    ax.set_title(title, fontsize=16)
    ax.set_xlabel("Date", fontsize=12)
    ax.set_ylabel("Portfolio Value ($)", fontsize=12)
    ax.legend(fontsize=12)
    ax.grid(True, alpha=0.3)
    
    plt.tight_layout()
    
    # 保存图片
    if output_png:
        plt.savefig(output_png, dpi=300, bbox_inches="tight")
        print(f"Plot saved to: {output_png}")
    
    plt.show()