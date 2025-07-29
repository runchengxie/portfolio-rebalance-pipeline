import os
import re

def clean_and_format_text(text):
    """
    移除文本中的中文字符并规范化空行格式。
    """
    # 步骤 1: 移除所有中文字符
    text_no_chinese = re.sub(r'[\u4e00-\u9fff]+', '', text)
    
    # 步骤 2: 将 <br> 或 <br/> 标签替换为标准的换行符
    text_no_br = re.sub(r'<br\s*/?>', '\n', text_no_chinese, flags=re.IGNORECASE)
    
    # 步骤 3: 将多个连续的空行合并为一个，以保持段落间距一致
    normalized_text = re.sub(r'\n\s*\n', '\n\n', text_no_br)
    
    # 返回去除首尾空白后的最终文本
    return normalized_text.strip()


def process_files_in_script_directory():
    """
    处理与本脚本文件位于同一目录下的所有 Markdown (.md) 文件。
    """
    try:
        # 获取当前脚本的绝对路径
        # __file__ 是一个特殊变量，代表当前脚本的文件名
        script_path = os.path.abspath(__file__)
        # 从脚本的绝对路径中获取其所在的目录
        script_directory = os.path.dirname(script_path)
    except NameError:
        # 如果在某些交互式环境（如Jupyter）中运行，__file__可能未定义
        # 在这种情况下，我们退回到使用当前工作目录
        script_directory = os.getcwd()
        print("警告: 无法确定脚本路径，将使用当前工作目录。")


    print(f"开始扫描脚本所在目录: {script_directory}")
    processed_count = 0
    
    # 使用 os.listdir() 列出该目录下的所有文件和文件夹名称
    for filename in os.listdir(script_directory):
        # 构建完整的文件路径
        file_path = os.path.join(script_directory, filename)
        
        # 核心判断：确保它是一个文件 (os.path.isfile) 并且以 .md 结尾
        if filename.endswith(".md") and os.path.isfile(file_path):
            try:
                # 读取原始文件内容
                with open(file_path, 'r', encoding='utf-8') as f:
                    original_content = f.read()
                
                print(f"  - 正在处理同级文件: {filename}")
                
                # 清理和格式化文本内容
                cleaned_content = clean_and_format_text(original_content)
                
                # 只有在内容发生改变时才执行写回操作，避免不必要的修改
                if cleaned_content != original_content:
                    with open(file_path, 'w', encoding='utf-8') as f:
                        f.write(cleaned_content)
                    print(f"  ✓ 文件已更新: {filename}")
                    processed_count += 1
                else:
                    print(f"  = 文件无需更改: {filename}")
                        
            except Exception as e:
                print(f"  ✗ 处理文件 {filename} 时发生错误: {e}")
                    
    if processed_count > 0:
        print(f"\n处理完毕！总共有 {processed_count} 个同级文件被更新。")
    else:
        print("\n扫描完成，没有文件需要更新。")


# --- 程序主入口 ---
if __name__ == "__main__":
    process_files_in_script_directory()