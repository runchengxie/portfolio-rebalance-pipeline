import pandas as pd
import numpy as np
import tushare as ts
from scipy.stats import zscore
import time
from datetime import datetime, timedelta

# --- Configuration ---
TUSHARE_TOKEN = 'YOUR_TUSHARE_TOKEN' # Replace with your token
START_YEAR = 2015 # Start year for factor calculation (needs data from START_YEAR-1)
END_YEAR = 2022   # Last year for factor calculation (portfolio formed in YEAR+1)
HOLDING_PERIOD_START_MONTH = 5 # e.g., Form portfolio end of April (using prior year's annual data)
# Features to use for the factor
# Tushare fields: oancf, income_tax, total_hldr_eqy_exc_min_int, total_assets, account_rec
FEATURES = ['cfo', 'txt', 'ceq', 'at', 'rect']
# Signs for combining Z-scores into the factor: Z(cfo) + Z(ceq) + Z(txt) + Z(Δtxt) - Z(Δat) - Z(Δrect)
# Note: This requires calculating deltas first
FACTOR_WEIGHTS = {'cfo': 1, 'ceq': 1, 'txt': 1, 'd_txt': 1, 'd_at': -1, 'd_rect': -1}
# Quantile groups for analysis
N_QUANTILES = 5

# --- Tushare Initialization ---
ts.set_token(TUSHARE_TOKEN)
pro = ts.pro_api()

# --- Helper Functions ---

def get_stock_list(exchange='SSE'):
    """Gets a basic list of stocks (e.g., Shanghai Stock Exchange)."""
    print("Fetching stock list...")
    try:
        # Get stocks listed ('L'), excluding Beijing ('BSE') for now
        df_stocks = pro.stock_basic(exchange=exchange, list_status='L', fields='ts_code,symbol,name,industry,list_date')
        # Optional: Filter out ST stocks or specific industries if needed
        # df_stocks = df_stocks[~df_stocks['name'].str.contains('ST')]
        print(f"Fetched {len(df_stocks)} stocks from {exchange}.")
        return df_stocks['ts_code'].tolist()
    except Exception as e:
        print(f"Error fetching stock list: {e}")
        return []

def fetch_financial_data(ts_codes, year, report_type='1231'):
    """Fetches key financial data for a list of stocks for a given year."""
    print(f"Fetching financial data for {year}...")
    all_income = []
    all_balance = []
    all_cashflow = []

    # Tushare often requires iterating through codes or dates for bulk data
    # We fetch by end_date for annual reports (adjust 'report_type' if needed)
    end_date = f"{year}{report_type}" # Assuming annual reports end Dec 31

    # Fetch Income Statement Data
    try:
        # income_vip needed for oancf; use income otherwise
        # Note: Adjust fields based on your Tushare permission level
        # Using 'income' for txt
        income_df = pro.income(ann_date='', end_date=end_date, fields='ts_code,end_date,income_tax') # Use income_tax for txt
        if not income_df.empty:
            all_income.append(income_df)
            print(f"Fetched income data for {len(income_df)} stocks for {year}.")
        else:
            print(f"No income data found for {year}.")
    except Exception as e:
        print(f"Error fetching income data for {year}: {e}")
        # Add delay to handle potential API rate limits
        time.sleep(1)

    # Fetch Balance Sheet Data
    try:
        balance_df = pro.balancesheet(end_date=end_date, fields='ts_code,end_date,total_hldr_eqy_exc_min_int,total_assets,account_rec') # ceq, at, rect
        if not balance_df.empty:
            all_balance.append(balance_df)
            print(f"Fetched balance sheet data for {len(balance_df)} stocks for {year}.")
        else:
            print(f"No balance sheet data found for {year}.")
    except Exception as e:
        print(f"Error fetching balance sheet data for {year}: {e}")
        time.sleep(1)

    # Fetch Cash Flow Data
    try:
        # oancf might be in cashflow_vip for some users
        cashflow_df = pro.cashflow(end_date=end_date, fields='ts_code,end_date,n_cashflow_act') # Use n_cashflow_act for cfo
        if not cashflow_df.empty:
            all_cashflow.append(cashflow_df)
            print(f"Fetched cash flow data for {len(cashflow_df)} stocks for {year}.")
        else:
            print(f"No cash flow data found for {year}.")

    except Exception as e:
        print(f"Error fetching cash flow data for {year}: {e}")
        time.sleep(1)


    # Combine data for the year
    if not all_income or not all_balance or not all_cashflow:
         print(f"Warning: Missing some financial data types for {year}.")
         # Return empty if essential data is missing, or handle partial data
         # For simplicity, returning empty if any part is missing
         if not all_income or not all_balance or not all_cashflow:
            return pd.DataFrame()


    df_income = pd.concat(all_income).drop_duplicates(subset=['ts_code'])
    df_balance = pd.concat(all_balance).drop_duplicates(subset=['ts_code'])
    df_cashflow = pd.concat(all_cashflow).drop_duplicates(subset=['ts_code'])

    # Rename columns for clarity
    df_income = df_income.rename(columns={'income_tax': 'txt'})
    df_balance = df_balance.rename(columns={'total_hldr_eqy_exc_min_int': 'ceq',
                                            'total_assets': 'at',
                                            'account_rec': 'rect'})
    df_cashflow = df_cashflow.rename(columns={'n_cashflow_act': 'cfo'})


    # Merge data
    df_merged = pd.merge(df_income[['ts_code', 'txt']], df_balance[['ts_code', 'ceq', 'at', 'rect']], on='ts_code', how='inner')
    df_merged = pd.merge(df_merged, df_cashflow[['ts_code', 'cfo']], on='ts_code', how='inner')
    df_merged['year'] = year

    # Convert to numeric, coercing errors
    num_cols = ['txt', 'ceq', 'at', 'rect', 'cfo']
    for col in num_cols:
        df_merged[col] = pd.to_numeric(df_merged[col], errors='coerce')

    # Basic sanity check - replace large negative values or zeros where inappropriate (e.g., assets, equity)
    # For simplicity, we'll handle NaNs later, but in practice more cleaning is needed
    df_merged.loc[df_merged['at'] <= 0, 'at'] = np.nan
    df_merged.loc[df_merged['ceq'] <= 0, 'ceq'] = np.nan


    return df_merged[['ts_code', 'year'] + FEATURES]

def get_forward_returns(ts_codes, factor_year):
    """Calculates forward 1-year returns starting from HOLDING_PERIOD_START_MONTH."""
    print(f"Calculating forward returns starting after year {factor_year}...")
    start_date = f"{factor_year + 1}{HOLDING_PERIOD_START_MONTH:02d}01"
    # Find the last trading day of the previous month
    try:
        trade_cal = pro.trade_cal(exchange='SSE', start_date=f"{factor_year+1}0101", end_date=start_date)
        # Go back until we find an open day before the start month
        portfolio_formation_date_dt = datetime.strptime(start_date, '%Y%m%d')
        potential_formation_date = (portfolio_formation_date_dt - timedelta(days=1)).strftime('%Y%m%d')
        while True:
            cal_day = trade_cal[trade_cal['cal_date'] == potential_formation_date]
            if not cal_day.empty and cal_day['is_open'].iloc[0] == 1:
                portfolio_formation_date = potential_formation_date
                break
            potential_formation_date_dt = datetime.strptime(potential_formation_date, '%Y%m%d')
            potential_formation_date = (potential_formation_date_dt - timedelta(days=1)).strftime('%Y%m%d')
            if potential_formation_date_dt.year == factor_year: # Safety break
                 print("Warning: Could not find suitable formation date.")
                 portfolio_formation_date = f"{factor_year + 1}0430" # Fallback
                 break

    except Exception as e:
        print(f"Error getting trading calendar, using default end of April: {e}")
        portfolio_formation_date = f"{factor_year + 1}0430" # Default to end of April if calendar fails

    end_date_dt = datetime.strptime(portfolio_formation_date, '%Y%m%d') + timedelta(days=365)
    end_date = end_date_dt.strftime('%Y%m%d')
    print(f"Portfolio formation date (approx): {portfolio_formation_date}")
    print(f"Return calculation end date (approx): {end_date}")


    returns = {}
    codes_to_fetch = list(ts_codes) # Copy the list
    batch_size = 100 # Adjust based on API limits / typical performance

    while codes_to_fetch:
        batch = codes_to_fetch[:batch_size]
        codes_to_fetch = codes_to_fetch[batch_size:]
        print(f"Fetching price data for batch of {len(batch)} stocks...")

        try:
             # Fetch daily data around the period
             # Using pro_bar for adjusted prices ('adj=qfq' for forward adjusted)
            df_prices_start = ts.pro_bar(ts_code=','.join(batch), adj='qfq',
                                         start_date=(datetime.strptime(portfolio_formation_date, '%Y%m%d') - timedelta(days=10)).strftime('%Y%m%d'),
                                         end_date=portfolio_formation_date,
                                         asset='E', freq='D') # Asset E for stocks

            df_prices_end = ts.pro_bar(ts_code=','.join(batch), adj='qfq',
                                       start_date=(datetime.strptime(end_date, '%Y%m%d') - timedelta(days=10)).strftime('%Y%m%d'),
                                       end_date=end_date,
                                       asset='E', freq='D')


            if df_prices_start is None or df_prices_end is None:
                print(f"Warning: Price data fetch returned None for batch.")
                time.sleep(2) # Wait longer if None returned
                continue

            if df_prices_start.empty or df_prices_end.empty:
                 print(f"Warning: Empty price data for batch between {portfolio_formation_date} and {end_date}")
                 time.sleep(1)
                 continue

             # Get the closest price ON or BEFORE the target date
            df_prices_start = df_prices_start.sort_values(by=['ts_code', 'trade_date'], ascending=[True, False])
            start_prices = df_prices_start.drop_duplicates(subset=['ts_code'], keep='first')

            df_prices_end = df_prices_end.sort_values(by=['ts_code', 'trade_date'], ascending=[True, False])
            end_prices = df_prices_end.drop_duplicates(subset=['ts_code'], keep='first')


            # Merge start and end prices
            df_merged_prices = pd.merge(start_prices[['ts_code', 'close']], end_prices[['ts_code', 'close']], on='ts_code', suffixes=('_start', '_end'), how='inner')


            # Calculate return
            df_merged_prices['fwd_return'] = (df_merged_prices['close_end'] / df_merged_prices['close_start']) - 1

            # Store results
            for idx, row in df_merged_prices.iterrows():
                returns[row['ts_code']] = row['fwd_return']

            print(f"Calculated returns for {len(df_merged_prices)} stocks in batch.")
            time.sleep(0.6) # Respect Tushare frequency limits (e.g., 200 calls/min)

        except Exception as e:
            print(f"Error fetching/processing price data for batch: {e}")
            time.sleep(2) # Wait longer after an error

    # Convert dict to DataFrame
    df_returns = pd.DataFrame(list(returns.items()), columns=['ts_code', 'fwd_return'])
    df_returns['factor_year'] = factor_year # Year of financials used for factor
    return df_returns

# --- Main Logic ---

# 1. Get Stock List (e.g., Shanghai Main Board)
# Consider adding Shenzhen ('SZSE') as well for broader coverage
stock_codes_sse = get_stock_list('SSE')
stock_codes_szse = get_stock_list('SZSE')
all_stock_codes = list(set(stock_codes_sse + stock_codes_szse))
print(f"Total unique stocks in pool: {len(all_stock_codes)}")

# 2. Fetch Financial Data for all required years
all_financials = []
for year in range(START_YEAR - 1, END_YEAR + 1): # Need prior year data for deltas
    df_year = fetch_financial_data(all_stock_codes, year)
    if not df_year.empty:
        all_financials.append(df_year)
    time.sleep(1) # Pause between years

if not all_financials:
    print("Error: No financial data fetched. Exiting.")
    exit()

df_financials = pd.concat(all_financials, ignore_index=True)
print("\nRaw Financial Data Sample:")
print(df_financials.head())
print(f"\nShape of fetched financials: {df_financials.shape}")
print(f"\nMissing values per column:\n{df_financials.isnull().sum()}")

# 3. Calculate Deltas (Changes)
df_financials = df_financials.sort_values(by=['ts_code', 'year'])
delta_features = {}
for feat in ['txt', 'at', 'rect']: # Features we need deltas for
    # Use shift() grouped by stock code
    df_financials[f'd_{feat}'] = df_financials.groupby('ts_code')[feat].diff()
    delta_features[f'd_{feat}'] = FACTOR_WEIGHTS.get(f'd_{feat}', 0) # Get weight

print("\nFinancial Data with Deltas Sample:")
print(df_financials.head())

# 4. Calculate Factor Scores and Evaluate
quantile_returns = []

for year in range(START_YEAR, END_YEAR + 1):
    print(f"\n--- Processing Year {year} Factor ---")

    # Select financial data for the current year 'year'
    df_year_data = df_financials[df_financials['year'] == year].copy()

    # Identify necessary factor component columns
    factor_components = list(FACTOR_WEIGHTS.keys())
    df_year_data = df_year_data[['ts_code', 'year'] + factor_components].copy()

    # Handle missing values for factor calculation (e.g., drop rows with any NA in components)
    initial_count = len(df_year_data)
    df_year_data = df_year_data.dropna(subset=factor_components)
    print(f"Dropped {initial_count - len(df_year_data)} stocks due to missing factor components for year {year}.")

    if len(df_year_data) < N_QUANTILES * 5: # Need enough stocks for meaningful analysis
        print(f"Skipping year {year}: Not enough valid data points ({len(df_year_data)}).")
        continue

    # Standardize (Z-score) each factor component cross-sectionally
    standardized_features = {}
    for component in factor_components:
        # Apply zscore; handle potential division by zero if std dev is 0
        std_dev = df_year_data[component].std()
        if std_dev == 0:
             standardized_features[f'z_{component}'] = 0.0 # Assign 0 if no variation
             print(f"Warning: Zero standard deviation for {component} in year {year}.")
        else:
            # Use numpy's nan handling version of zscore if needed, or rely on dropna above
            # zscore directly might produce NaNs if input has NaNs, but we dropped them
             standardized_features[f'z_{component}'] = zscore(df_year_data[component])

    df_zscores = pd.DataFrame(standardized_features, index=df_year_data.index)

    # Calculate the combined factor score
    df_year_data['factor_score'] = 0.0
    for component, weight in FACTOR_WEIGHTS.items():
        df_year_data['factor_score'] += df_zscores[f'z_{component}'] * weight

    print("Factor Score Calculation Sample:")
    print(df_year_data[['ts_code', 'factor_score']].head())

    # Get forward returns for the period starting after 'year'
    df_fwd_returns = get_forward_returns(df_year_data['ts_code'].tolist(), year)

    if df_fwd_returns.empty:
        print(f"Skipping year {year}: Could not calculate forward returns.")
        continue

    # Merge factor scores with forward returns
    df_eval = pd.merge(df_year_data[['ts_code', 'year', 'factor_score']], df_fwd_returns,
                       on=['ts_code'], how='inner') # factor_year from returns matches 'year' here

    if df_eval.empty or 'fwd_return' not in df_eval.columns or df_eval['fwd_return'].isnull().all():
         print(f"Skipping year {year}: Merge failed or no valid forward returns.")
         continue

    # Handle potential NaN returns after merge
    df_eval = df_eval.dropna(subset=['factor_score', 'fwd_return'])

    if len(df_eval) < N_QUANTILES * 5:
         print(f"Skipping year {year}: Not enough valid data points after merging returns ({len(df_eval)}).")
         continue


    # Perform Quantile Analysis
    try:
        df_eval['quantile'] = pd.qcut(df_eval['factor_score'], N_QUANTILES, labels=False, duplicates='drop') + 1
        # Calculate mean forward return per quantile
        avg_quantile_return = df_eval.groupby('quantile')['fwd_return'].mean()
        print(f"\nAverage Forward Return by Factor Quantile for factor year {year}:")
        print(avg_quantile_return)
        quantile_returns.append(avg_quantile_return)
    except Exception as e:
        # qcut can fail if too few distinct values
        print(f"Error during quantile analysis for year {year}: {e}")
        print("Factor score distribution:")
        print(df_eval['factor_score'].describe())


# 5. Aggregate and Display Results
if quantile_returns:
    df_quantile_summary = pd.concat(quantile_returns, axis=1).mean(axis=1)
    print("\n--- Overall Quantile Performance (Average Annual Forward Return) ---")
    print(df_quantile_summary)

    # Check monotonicity and top-bottom spread
    if len(df_quantile_summary) == N_QUANTILES:
        top_bottom_spread = df_quantile_summary.iloc[-1] - df_quantile_summary.iloc[0]
        print(f"\nAverage Top Quantile Return: {df_quantile_summary.iloc[-1]:.4f}")
        print(f"Average Bottom Quantile Return: {df_quantile_summary.iloc[0]:.4f}")
        print(f"Average Top-Bottom Spread: {top_bottom_spread:.4f}")
    else:
        print("Could not calculate top-bottom spread due to inconsistent quantile results across years.")

else:
    print("\nNo valid quantile results generated across the specified years.")