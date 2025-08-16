# tools/create_top_5_previews.py

from pathlib import Path

import pandas as pd


def create_previews():
    """
    Finds all CSV files in the '../data' directory, reads the first 5 data rows
    from each, and saves them to a new .txt file in the same directory.
    """
    try:
        # 1. 定义路径
        # Path(__file__) 是当前脚本的路径 (e.g., .../tools/create_top_100_previews.py)
        # .resolve() 获取绝对路径
        # .parent 获取父目录 (e.g., .../tools/)
        # .parent.parent 获取祖父目录, 即项目根目录
        project_root = Path(__file__).resolve().parent.parent
        data_dir = project_root / "data"

        print(f"[*] Searching for CSV files in: {data_dir}")

        # 2. 检查data目录是否存在
        if not data_dir.is_dir():
            print(f"[!] Error: Data directory not found at {data_dir}")
            return

        # 3. 查找所有CSV文件
        csv_files = list(data_dir.glob("*.csv"))

        if not csv_files:
            print(f"[*] No CSV files found in {data_dir}.")
            return

        print(f"[*] Found {len(csv_files)} CSV file(s) to process.")

        # 4. 遍历并处理每个CSV文件
        for csv_path in csv_files:
            print(f"    -> Processing '{csv_path.name}'...")

            try:
                # 使用 pandas 读取前5行数据。nrows=5 非常高效，它只读取文件的开头部分。
                # 这会读取表头（header）和接下来的5行数据。
                df = pd.read_csv(
                    csv_path, nrows=5, encoding="utf-8", on_bad_lines="skip"
                )

                # 5. 定义输出文件名和路径
                # csv_path.stem 会获取不带扩展名的文件名 (e.g., 'us-balance-quarterly')
                output_filename = f"top_5_sample_{csv_path.stem}.txt"
                output_path = data_dir / output_filename

                # 6. 将数据帧（DataFrame）以美观的文本格式写入新文件
                # to_string() 方法可以生成一个适合阅读的文本表示
                with open(output_path, "w", encoding="utf-8") as f:
                    f.write(df.to_string())

                print(f"    <- Successfully created '{output_filename}'")

            except Exception as e:
                print(f"    [!] Error processing file {csv_path.name}: {e}")

        print("\n[*] Script finished successfully.")

    except Exception as e:
        print(f"[!] An unexpected error occurred: {e}")


# 当直接运行这个脚本时，执行create_previews函数
if __name__ == "__main__":
    create_previews()
