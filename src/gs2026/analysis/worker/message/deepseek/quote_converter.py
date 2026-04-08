#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""JSON引号转换工具模块

用于处理AI返回的JSON文本内容中包含英文双引号的问题。
"""

import json
import re
from json.decoder import JSONDecodeError


def convert_quotes_to_chinese(json_str: str) -> str:
    """将JSON字符串内容中的英文双引号转换为中文双引号
    
    此函数通过正则表达式匹配JSON字符串值，将其中的嵌套英文双引号
    替换为中文双引号，避免JSON解析失败。
    
    Args:
        json_str: 原始JSON字符串
        
    Returns:
        转换后的JSON字符串
        
    Example:
        >>> json_str = '{"key": "value with "nested" quotes"}'
        >>> result = convert_quotes_to_chinese(json_str)
        >>> print(result)
        {"key": "value with "nested" quotes"}
    """
    if not json_str or not isinstance(json_str, str):
        return json_str
    
    # 使用正则表达式找到所有字符串值
    # 匹配模式: "..." (考虑转义)
    def replace_inner_quotes(match):
        # 获取匹配的完整字符串（包括引号）
        full_match = match.group(0)
        # 获取字符串内容（不包括外层引号）
        content = match.group(1)
        
        # 检查内容中是否有嵌套的英文双引号
        if '"' in content:
            # 将内容中的英文双引号替换为中文双引号
            # 使用 " 和 " 配对
            parts = content.split('"')
            new_content = ''
            for i, part in enumerate(parts):
                if i > 0:
                    # 交替使用左引号和右引号
                    if i % 2 == 1:
                        new_content += '"' + part
                    else:
                        new_content += '"' + part
                else:
                    new_content = part
            return '"' + new_content + '"'
        else:
            # 没有嵌套引号，保持原样
            return full_match
    
    # 正则表达式：匹配JSON字符串
    # 使用递归模式处理嵌套
    pattern = r'"((?:[^"\\]|\\.)*)"'
    
    # 由于Python的re不支持真正的递归，我们使用循环处理
    result = json_str
    max_iterations = 10  # 防止无限循环
    
    for _ in range(max_iterations):
        new_result = re.sub(pattern, replace_inner_quotes, result)
        if new_result == result:
            break
        result = new_result
    
    return result


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
        try:
            result = json.loads(converted)
            print(f"  Result: OK")
        except json.JSONDecodeError as e:
            print(f"  Result: FAIL - {e}")
        print()
