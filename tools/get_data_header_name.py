import os

import pandas as pd


def get_csv_headers():
    """
    Reads CSV files from the data directory and prints their headers.
    """
    # The script is in the 'tools' directory, so the data directory is one level up.
    data_folder = os.path.join(os.path.dirname(__file__), "..", "data")

    files_to_process = {
        "Balance Sheet": "us-balance-ttm.csv",
        "Cash Flow": "us-cashflow-ttm.csv",
        "Income Statement": "us-income-ttm.csv",
    }

    for name, filename in files_to_process.items():
        file_path = os.path.join(data_folder, filename)
        print(f"--- {name} Headers ({filename}) ---")
        try:
            # Read only the header of the csv file to get the columns
            df = pd.read_csv(file_path, sep=";", nrows=0)
            headers = df.columns.tolist()
            for header in headers:
                print(header)
        except FileNotFoundError:
            print(f"Error: File not found at '{file_path}'.")
            print(
                "Please make sure the 'data' directory exists in the project root and contains the required CSV files."
            )
        except Exception as e:
            print(f"An error occurred while processing {filename}: {e}")
        print("\n")


if __name__ == "__main__":
    get_csv_headers()
