import os
import json
from pathlib import Path
from typing import Set, Optional

# --- CONFIGURATION ---
try:
    # Assumes the script is in a 'tools' folder inside the project root
    PROJECT_ROOT = Path(__file__).resolve().parent.parent
except NameError:
    # Fallback for interactive environments
    PROJECT_ROOT = Path.cwd()

OUTPUT_FILENAME = "full_project_source.txt"

# Directories to exclude by an exact match
EXCLUDE_DIRS_EXACT: Set[str] = {
    ".git",
    "__pycache__",
    "cache",
    "output",
    ".vscode",
    ".idea",
    "venv",
    ".venv",
    "env",
    "build",
    "dist",
    "logs",
    "data",
    "renv"
}

# Directory name patterns to exclude (e.g., any directory ending with .egg-info)
EXCLUDE_DIRS_PATTERNS: tuple[str, ...] = (".egg-info",)

EXCLUDE_EXTS: Set[str] = {
    ".pyc",
    ".pyo",
    ".so",
    ".dll",
    ".exe",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".ico",
    ".svg",
    ".parquet",
    ".arrow",
    ".feather",
    ".csv",
    ".zip",
    ".gz",
    ".tar",
    ".rar",
    ".7z",
    ".db",
    ".sqlite3",
    ".pdf",
    ".docx",
    ".xlsx",
}

EXCLUDE_FILES: Set[str] = {
    OUTPUT_FILENAME,
    "full_code_text.txt",  # Exclude the old file name just in case
    ".DS_Store",
    "Thumbs.db",
    ".env",
    "notebook.html",
}


def process_notebook(filepath: Path) -> Optional[str]:
    """
    Parses a Jupyter Notebook (.ipynb) file and extracts only the code and
    markdown content, ignoring all cell outputs (like images).
    """
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            notebook = json.load(f)

        content_parts = []
        for i, cell in enumerate(notebook.get("cells", [])):
            cell_type = cell.get("cell_type")
            source_list = cell.get("source", [])

            # Ensure source is a single string
            if isinstance(source_list, list):
                source = "".join(source_list)
            else:
                source = str(source_list)

            if not source.strip():
                continue

            if cell_type == "code":
                content_parts.append(f"# --- Code Cell {i+1} ---\n{source}\n")
            elif cell_type == "markdown":
                content_parts.append(f"# --- Markdown Cell {i+1} ---\n{source}\n")

        return "\n".join(content_parts)
    except Exception as e:
        print(f"    [WARN] Could not parse notebook {filepath.name}: {e}")
        return None


def is_likely_text_file(filepath: Path) -> bool:
    """
    Checks if a file is likely to be a text file.
    This check is run *after* the specific .ipynb check.
    """
    if filepath.suffix.lower() in EXCLUDE_EXTS:
        return False
    try:
        with open(filepath, "rb") as f:
            return b"\0" not in f.read(1024)
    except (IOError, PermissionError):
        return False


def combine_project_files() -> None:
    """
    Scans the project directory and combines all relevant files into a single output file.
    """
    output_filepath = PROJECT_ROOT / OUTPUT_FILENAME

    print(f"Project root identified as: {PROJECT_ROOT}")
    print(f"Output will be saved to: {output_filepath}\n")

    files_processed_count = 0
    files_skipped_count = 0

    try:
        with open(output_filepath, "w", encoding="utf-8", errors="ignore") as outfile:
            outfile.write("--- Project Source Code Archive ---\n\n")
            outfile.write(
                "This file contains the concatenated source code of the project, with each file wrapped in tags indicating its relative path.\n\n"
            )

            for dirpath, dirnames, filenames in os.walk(PROJECT_ROOT):
                # It filters a directory if:
                # 1. Its name is in the exact-match set.
                # 2. Its name ends with any of the specified patterns.
                dirnames[:] = [
                    d
                    for d in dirnames
                    if d not in EXCLUDE_DIRS_EXACT
                    and not any(d.endswith(p) for p in EXCLUDE_DIRS_PATTERNS)
                ]

                for filename in sorted(filenames):
                    if filename in EXCLUDE_FILES:
                        continue

                    filepath = Path(dirpath) / filename
                    relative_path_str = filepath.relative_to(PROJECT_ROOT).as_posix()
                    content = None

                    try:
                        # 1. First, specifically check for .ipynb files
                        if filepath.suffix.lower() == ".ipynb":
                            print(f"  + Processing Notebook: {relative_path_str}")
                            content = process_notebook(filepath)
                        # 2. If it's not a notebook, check if it's a general text file
                        elif is_likely_text_file(filepath):
                            print(f"  + Processing Text File: {relative_path_str}")
                            with open(
                                filepath, "r", encoding="utf-8", errors="ignore"
                            ) as infile:
                                content = infile.read()
                        # 3. If neither, it's a file to be skipped
                        else:
                            print(
                                f"  - Skipping binary/excluded file: {relative_path_str}"
                            )
                            files_skipped_count += 1
                            continue

                        # If content was successfully extracted, write it to the output file
                        if content and content.strip():
                            outfile.write(f"<{relative_path_str}>\n")
                            outfile.write(content.strip())
                            outfile.write(f"\n</{relative_path_str}>\n\n")
                            files_processed_count += 1
                        else:
                            print(
                                f"    [INFO] No content extracted from {relative_path_str}"
                            )
                            files_skipped_count += 1

                    except Exception as e:
                        print(
                            f"    [ERROR] Could not read file {relative_path_str}: {e}"
                        )
                        files_skipped_count += 1

        print("\n--- Summary ---")
        print(f"Successfully processed {files_processed_count} files.")
        print(f"Skipped {files_skipped_count} binary, excluded, or unreadable files.")
        print(f"Combined output saved to: {output_filepath}")

    except IOError as e:
        print(f"\n[FATAL ERROR] Could not write to output file {output_filepath}: {e}")
    except Exception as e:
        print(f"\n[FATAL ERROR] An unexpected error occurred: {e}")


if __name__ == "__main__":
    combine_project_files()
