#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""JSON引号转换工具模块

用于处理AI返回的JSON文本内容中包含英文双引号的问题。
"""

import json
from json.decoder import JSONDecodeError

# 定义引号字符
ASCII_QUOTE = '"'
CHINESE_LEFT_QUOTE = '\u201c'   # "
CHINESE_RIGHT_QUOTE = '\u201d'  # "


def convert_quotes_to_chinese(json_str: str) -> str:
    """将JSON字符串内容中的英文双引号转换为中文双引号
    
    使用状态机遍历字符，识别JSON字符串边界，将字符串内部的
    英文双引号转换为中文双引号。
    
    Args:
        json_str: 原始JSON字符串
        
    Returns:
        转换后的JSON字符串
    """
    if not json_str or not isinstance(json_str, str):
        return json_str
    
    result = []
    chars = list(json_str)
    i = 0
    n = len(chars)
    in_string = False  # 是否在字符串内部
    escape_next = False  # 下一个字符是否被转义
    quote_count = 0  # 用于交替使用左右引号
    
    while i < n:
        char = chars[i]
        
        if escape_next:
            result.append(char)
            escape_next = False
            i += 1
            continue
        
        if char == '\\':
            result.append(char)
            escape_next = True
            i += 1
            continue
        
        if char == ASCII_QUOTE:
            if not in_string:
                # 字符串开始
                in_string = True
                quote_count = 0
                result.append(char)
            else:
                # 在字符串内部，检查是否是字符串结束
                j = i + 1
                while j < n and chars[j] in ' \t\n\r':
                    j += 1
                
                next_char = chars[j] if j < n else ''
                
                # 检查是否是字符串结束
                is_string_end = (
                    next_char in ':,}]' or  # 后面是JSON分隔符
                    j >= n                  # 字符串末尾
                )
                
                if is_string_end:
                    # 字符串结束
                    in_string = False
                    result.append(char)
                else:
                    # 字符串内部的嵌套引号，转换为中文双引号
                    # 交替使用左右引号
                    if quote_count % 2 == 0:
                        result.append(CHINESE_LEFT_QUOTE)
                    else:
                        result.append(CHINESE_RIGHT_QUOTE)
                    quote_count += 1
        else:
            result.append(char)
        
        i += 1
    
    return ''.join(result)


def safe_parse_json(json_str: str) -> dict:
    """安全解析JSON字符串，自动处理嵌套引号问题
    
    先尝试直接解析，如果失败则尝试转换引号后解析。
    
    Args:
        json_str: JSON字符串
        
    Returns:
        解析后的字典
        
    Raises:
        JSONDecodeError: 如果解析失败
    """
    if not json_str:
        raise JSONDecodeError("Empty JSON string", "", 0)
    
    # 尝试直接解析
    try:
        return json.loads(json_str)
    except JSONDecodeError:
        pass
    
    # 尝试转换引号后解析
    converted = convert_quotes_to_chinese(json_str)
    try:
        return json.loads(converted)
    except JSONDecodeError as e:
        raise JSONDecodeError(f"Failed after quote conversion: {e}", json_str, 0)


# 测试
if __name__ == "__main__":
    # 测试用例
    test_cases = [
        '{"key": "value with "nested" quotes"}',
        '{"深度分析": "构建"AI服务器"双支点"}',
        '{"分析": ["构建"AI服务器PCB+高速光模块"双支点"]}',
    ]
    
    for i, test in enumerate(test_cases, 1):
        print(f"Test {i}: {test}")
        converted = convert_quotes_to_chinese(test)
        print(f"  Converted: {converted}")
        
        # 检查引号
        ascii_count = converted.count(ASCII_QUOTE)
        chinese_count = converted.count(CHINESE_LEFT_QUOTE) + converted.count(CHINESE_RIGHT_QUOTE)
        print(f"  ASCII quotes: {ascii_count}, Chinese quotes: {chinese_count}")
        
        try:
            result = json.loads(converted)
            print(f"  Result: OK")
        except json.JSONDecodeError as e:
            print(f"  Result: FAIL - {e}")
        print()
