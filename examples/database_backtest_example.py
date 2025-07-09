# examples/database_backtest_example.py
# 
# 使用改进版回测脚本的示例
# 展示如何使用SQLite数据库进行高性能回测

import sys
from pathlib import Path

# 添加src目录到Python路径
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / 'src'))

from stock_analysis.run_backtest import main, configure_data_source

def run_database_backtest():
    """
    使用数据库模式运行回测的示例
    """
    print("=== 数据库模式回测示例 ===")
    print()
    
    # 强制使用数据库模式
    configure_data_source(use_database=True)
    
    # 运行回测
    main()

def run_csv_backtest():
    """
    使用CSV模式运行回测的示例（用于性能对比）
    """
    print("=== CSV模式回测示例 ===")
    print()
    
    # 强制使用CSV模式
    configure_data_source(use_database=False)
    
    # 运行回测
    main()

def performance_comparison():
    """
    性能对比示例
    """
    import time
    
    print("=== 性能对比测试 ===")
    print("将分别使用数据库模式和CSV模式运行回测，对比性能差异")
    print()
    
    # 测试数据库模式
    print("1. 测试数据库模式...")
    start_time = time.time()
    try:
        configure_data_source(use_database=True)
        main()
        db_time = time.time() - start_time
        print(f"数据库模式总耗时: {db_time:.2f}秒")
    except Exception as e:
        print(f"数据库模式失败: {e}")
        db_time = None
    
    print("\n" + "="*50 + "\n")
    
    # 测试CSV模式
    print("2. 测试CSV模式...")
    start_time = time.time()
    try:
        configure_data_source(use_database=False)
        main()
        csv_time = time.time() - start_time
        print(f"CSV模式总耗时: {csv_time:.2f}秒")
    except Exception as e:
        print(f"CSV模式失败: {e}")
        csv_time = None
    
    # 性能对比结果
    print("\n" + "="*50)
    print("性能对比结果:")
    if db_time and csv_time:
        speedup = csv_time / db_time
        time_saved = csv_time - db_time
        percent_saved = (time_saved / csv_time) * 100
        
        print(f"数据库模式: {db_time:.2f}秒")
        print(f"CSV模式:   {csv_time:.2f}秒")
        print(f"性能提升:  {speedup:.2f}x")
        print(f"时间节省:  {time_saved:.2f}秒 ({percent_saved:.1f}%)")
    else:
        print("无法完成性能对比（某个模式失败）")

if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='数据库回测示例')
    parser.add_argument('--mode', choices=['db', 'csv', 'compare'], default='db',
                       help='运行模式: db=数据库模式, csv=CSV模式, compare=性能对比')
    
    args = parser.parse_args()
    
    if args.mode == 'db':
        run_database_backtest()
    elif args.mode == 'csv':
        run_csv_backtest()
    elif args.mode == 'compare':
        performance_comparison()