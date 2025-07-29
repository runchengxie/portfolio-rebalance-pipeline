import os
import re

def remove_lines_with_chinese(text):
    """
    逐行检查文本，如果某一行包含任何中文字符，则删除该整行。
    最后，规范化段落间的空行。
    """
    # 步骤 1: 将<br>标签统一替换为换行符，以便按行处理
    text_with_newlines = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
    
    # 步骤 2: 将文本分割成独立的行
    lines = text_with_newlines.split('\n')
    
    # 步骤 3: 创建一个新列表，只包含不含中文字符的行
    english_only_lines = []
    # 定义一个正则表达式来匹配中文字符
    chinese_char_pattern = re.compile(r'[\u4e00-\u9fff]')
    
    for line in lines:
        # re.search() 会在字符串中查找匹配项
        # 如果没有找到中文字符 (search返回None)，则保留这一行
        if not chinese_char_pattern.search(line):
            english_only_lines.append(line)
            
    # 步骤 4: 将只包含英文的行重新组合成一个字符串
    cleaned_text = '\n'.join(english_only_lines)
    
    # 步骤 5: 整理格式，确保段落之间只有一个空行
    # 这会移除因删除行而可能产生的多个连续空行
    final_text = re.sub(r'\n\s*\n+', '\n\n', cleaned_text)
    
    # 返回处理完成的文本，并移除开头和结尾可能的多余空白
    return final_text.strip()


def process_files_in_script_directory():
    """
    处理与本脚本文件位于同一目录下的所有 Markdown (.md) 文件。
    （此函数与上一版相同）
    """
    try:
        # 获取脚本所在的目录
        script_directory = os.path.dirname(os.path.abspath(__file__))
    except NameError:
        # 兼容交互式环境
        script_directory = os.getcwd()
        print("警告: 无法自动确定脚本路径，将使用当前工作目录。")

    print(f"开始扫描脚本所在目录: {script_directory}")
    processed_count = 0
    
    for filename in os.listdir(script_directory):
        file_path = os.path.join(script_directory, filename)
        
        if filename.endswith(".md") and os.path.isfile(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    original_content = f.read()
                
                print(f"  - 正在处理文件: {filename}")
                
                # 调用新的清理函数，删除包含中文的整行
                cleaned_content = remove_lines_with_chinese(original_content)
                
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
        print(f"\n处理完毕！总共有 {processed_count} 个文件被更新。")
    else:
        print("\n扫描完成，所有文件均无需更改。")


# --- 程序主入口 ---
if __name__ == "__main__":
    # 同样，将此脚本命名为 clean_docs.py 并与您的md文件放在一起
    process_files_in_script_directory()