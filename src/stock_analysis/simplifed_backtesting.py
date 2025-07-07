# Import required libraries
import yfinance as yf
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
import time
import warnings
warnings.filterwarnings("ignore", category=FutureWarning)

# 1. Define your portfolio (tickers and weights)
portfolio = {
    'SPY': 0.15,
    'TSLA': 0.10,
    'GOOG': 0.08,
    'JNJ': 0.07,
    'XOM': 0.06,
    'RTX': 0.06,
    'CVX': 0.05,
    'CRM': 0.05,
    'PFE': 0.05,
    'META': 0.05,
    'BOMN': 0.04,
    'INTC': 0.04,
    'CMCSA': 0.04,
    'GE': 0.04,
    'ASLE': 0.02,
    'IBM': 0.03,
    'AAPL': 0.03,
    'PYPL': 0.02,
    'T': 0.02,
}

# Check if weights sum to 1 (100%)
assert abs(sum(portfolio.values()) - 1.0) < 1e-9, "Error: Portfolio weights do not sum to 1."
print(f"Sum of weights: {sum(portfolio.values()):.2%}")


# 2. Set backtesting parameters
# Use first trading day after 2019-01-01 to avoid holiday issues
from pandas.tseries.holiday import USFederalHolidayCalendar
start_date = pd.Timestamp('2019-01-01')
nyse = pd.tseries.offsets.CustomBusinessDay(calendar=USFederalHolidayCalendar())
start_date = (start_date + nyse)  # This will be 2019-01-02
end_date = pd.to_datetime('today').strftime('%Y-%m-%d')
initial_capital = 100000
benchmark_ticker = 'SPY' # S&P 500 ETF as benchmark

# 3. Fetch price data
tickers = list(portfolio.keys())
# Ensure benchmark ticker is included only once
if benchmark_ticker not in tickers:
    all_tickers = tickers + [benchmark_ticker]
else:
    all_tickers = tickers

# Download data with retry mechanism to handle timeouts
def download_with_retry(tickers, start, end, max_retries=3, **kwargs):
    for attempt in range(max_retries):
        data = yf.download(tickers, start=start, end=end, threads=False,
                          progress=False, auto_adjust=True, **kwargs)
        failed = [t for t in tickers if t not in data['Close'].columns]
        if not failed:
            return data
        if attempt < max_retries-1:
            print(f"Retrying {failed} ...")
            time.sleep(2)  # small back-off
            tickers = failed  # only retry the misses
    raise ValueError(f"Couldn't download {failed}")

# Download data with retry mechanism
raw_data = download_with_retry(all_tickers, start=start_date, end=end_date)

# CRITICAL FIX: Use the 'Close' column, which is already adjusted.
if raw_data.empty:
    raise SystemExit("Error: Failed to download any stock data. Check tickers and network connection.")
    
data = raw_data['Close'].copy()  # avoid SettingWithCopyWarning
data.dropna(axis=0, how='all', inplace=True) # Drop rows where all tickers have no data

# 4. Handle stocks with incomplete history (e.g., BOMN, listed later)
# Find tickers that have valid price data on the start date
valid_tickers_at_start = data.iloc[0].dropna().index.tolist()

if benchmark_ticker not in valid_tickers_at_start:
    raise ValueError(f"Error: Benchmark '{benchmark_ticker}' has no price data on start date {start_date}.")

# Filter the original portfolio to include only stocks available at the start
portfolio_at_start = {k: v for k, v in portfolio.items() if k in valid_tickers_at_start}

# Re-calculate weights to sum to 1 (normalization)
weight_sum = sum(portfolio_at_start.values())
normalized_portfolio = {k: v / weight_sum for k, v in portfolio_at_start.items()}

print("\nAvailable stocks at backtest start with normalized weights:")
for ticker, weight in normalized_portfolio.items():
    print(f"{ticker}: {weight:.2%}")

# 5. Execute the "Buy and Hold" backtest
# Calculate the number of shares to buy initially based on normalized weights
initial_investment_per_stock = {ticker: initial_capital * weight for ticker, weight in normalized_portfolio.items()}
shares_held = {ticker: initial_investment_per_stock[ticker] / data[ticker].iloc[0] for ticker in normalized_portfolio.keys()}

# Calculate the daily value of each component in the portfolio
portfolio_components_value = pd.DataFrame(index=data.index)
for ticker, shares in shares_held.items():
    portfolio_components_value[ticker] = data[ticker] * shares

# Calculate the total portfolio value each day
portfolio_total_value = portfolio_components_value.sum(axis=1)

# 6. Calculate benchmark performance
benchmark_initial_price = data[benchmark_ticker].iloc[0]
benchmark_shares = initial_capital / benchmark_initial_price
benchmark_value = data[benchmark_ticker] * benchmark_shares

# 7. Calculate and display results
# Calculate final returns
final_portfolio_value = portfolio_total_value.iloc[-1]
final_benchmark_value = benchmark_value.iloc[-1]
total_return_portfolio = (final_portfolio_value / initial_capital) - 1
total_return_benchmark = (final_benchmark_value / initial_capital) - 1

# Calculate Compound Annual Growth Rate (CAGR)
years = (data.index[-1] - data.index[0]).days / 365.25
cagr_portfolio = ((final_portfolio_value / initial_capital) ** (1/years)) - 1
cagr_benchmark = ((final_benchmark_value / initial_capital) ** (1/years)) - 1

print(f"\n--- Backtest Results ({start_date} to {end_date}) ---")
print(f"Initial Capital: ${initial_capital:,.2f}")
print(f"Investment Period: {years:.2f} years")

print("\n--- Your Portfolio ---")
print(f"Final Value: ${final_portfolio_value:,.2f}")
print(f"Total Return: {total_return_portfolio:.2%}")
print(f"Annualized Return (CAGR): {cagr_portfolio:.2%}")

print(f"\n--- {benchmark_ticker} Benchmark ---")
print(f"Final Value: ${final_benchmark_value:,.2f}")
print(f"Total Return: {total_return_benchmark:.2%}")
print(f"Annualized Return (CAGR): {cagr_benchmark:.2%}")

print("\n--- Performance Comparison ---")
print(f"Portfolio Alpha (vs Benchmark CAGR): {(cagr_portfolio - cagr_benchmark):.2%}")


# 8. Visualize and save the results (All English)
try:
    plt.style.use('seaborn-v0_8-darkgrid')
    fig, ax = plt.subplots(figsize=(14, 8))

    # Normalize all values to a starting point of $100 for comparison
    portfolio_normalized = (portfolio_total_value / initial_capital) * 100
    benchmark_normalized = (benchmark_value / initial_capital) * 100
    
    ax.plot(portfolio_normalized.index, portfolio_normalized, label=f'Your Portfolio (CAGR: {cagr_portfolio:.2%})', color='royalblue', linewidth=2)
    ax.plot(benchmark_normalized.index, benchmark_normalized, label=f'Benchmark: {benchmark_ticker} (CAGR: {cagr_benchmark:.2%})', color='grey', linestyle='--')
    
    ax.set_title('Portfolio Buy-and-Hold Performance vs. Benchmark', fontsize=16, weight='bold')
    ax.set_ylabel('Growth of $100', fontsize=12)
    ax.set_xlabel('Date', fontsize=12)
    ax.legend(loc='upper left', fontsize=12)
    
    # Format Y-axis with a dollar sign
    ax.yaxis.set_major_formatter(mtick.FuncFormatter(lambda x, p: f'${x:,.0f}'))
    
    plt.grid(True, which='both', linestyle='--', linewidth=0.5)
    plt.tight_layout()
    
    # Save the chart to a file in the outputs folder
    import os
    output_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'outputs')
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, 'portfolio_performance.png')
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    print(f"\nChart successfully saved to {output_path}")
    plt.close(fig) # Close the figure to prevent it from displaying in some environments

except Exception as e:
    print(f"\nError: Chart generation or saving failed: {e}")

print("\n=== Backtest Complete ===")