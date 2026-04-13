import hashlib
import re
from typing import List, Dict, Any

import json
from json.decoder import JSONDecodeError

# !/usr/bin/env python3
# -*- coding: utf-8 -*-
"""JSON引号转换工具模块

用于处理AI返回的JSON文本内容中包含英文双引号的问题。
"""


# 定义引号字符
ASCII_QUOTE = '"'
CHINESE_LEFT_QUOTE = '\u201c'  # "
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
                        j >= n  # 字符串末尾
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


def generate_md5(text: str, encoding: str = 'utf-8') -> str:
    """
    生成字符串的MD5哈希值
    :param text: 要加密的原始字符串
    :param encoding: 编码格式，默认utf-8
    :return: 32位十六进制小写哈希字符串
    """
    md5 = hashlib.md5()
    md5.update(text.encode(encoding))
    return md5.hexdigest()

def highlight_red_keywords(text, color, keywords):
    """
    将文本中的关键词标记为红色（HTML格式）
    :param keywords:
    :param color:
    :param text: 原始文本
    :return: 处理后的HTML文本
    """
    # 转义特殊字符并创建正则表达式模式
    escaped_official = [re.escape(keyword) for keyword in keywords]

    # 构建正则表达式模式
    pattern = r'(?:{})'.format('|'.join(map(re.escape, escaped_official)))

    # 替换为红色HTML标签
    highlighted = re.sub(
        pattern,
        lambda x: f"<font color='{color}'><b>{x.group()}</b></font>",
        text,
        flags=re.IGNORECASE  # 如需区分大小写可删除此参数
    )
    return highlighted

def remove_citation(text):
    """
    移除文本中的:ml-citation{ref="x,y" data="citationList"}格式内容
    参数：
        text: 待处理字符串
    返回：
        处理后的字符串
    """
    pattern = r':ml-citation\{ref="[^"]+" data="citationList"\}'
    return re.sub(pattern, '', text)

# json校验
def is_valid_json(json_str):
    if not json_str or json_str.strip() == "":
        return False
    try:
        json.loads(json_str)
        return True
    except (ValueError, json.JSONDecodeError):
        return False


def extract_message_ids(json_data: Dict[str, Any],parent_column:str,get_column:str) -> List[str]:
    """
    从给定的 JSON 结构中提取所有消息 ID

    参数:
        json_data: 包含{parent_column}的 JSON 数据结构

    返回:
        包含所有消息 ID 的列表

    异常:
        如果数据结构不符合预期会抛出 KeyError 或 TypeError
    """
    message_ids = []

    if str(json_data)=='{}':
        return message_ids
    # 1. 验证数据结构完整性
    if parent_column not in json_data:
        print(json_data)
        raise KeyError(f"JSON 数据中缺少 '{parent_column}' 键")

    message_collection = json_data[parent_column]

    # 2. 确保{parent_column}是列表类型（支持单个对象自动包装）
    if isinstance(message_collection, dict):
        # AI 返回单个对象，包装成列表
        message_collection = [message_collection]
    elif not isinstance(message_collection, list):
        raise TypeError(f"'{parent_column}' 应为列表或字典类型，实际类型为 {type(message_collection).__name__}")

    # 3. 收集消息 ID
    for idx, message in enumerate(message_collection):
        try:
            # 3.1 检查消息对象是否为字典
            if not isinstance(message, dict):
                raise TypeError(f"{parent_column}中的第 {idx} 项应为字典类型")

            # 3.2 检查消息 ID 是否存在
            if get_column not in message:
                print(json_data)
                raise KeyError(f"{parent_column}中的第 {idx} 项缺少 '{parent_column}' 键")

            # 3.3 获取并验证消息 ID
            msg_id = message[get_column]
            if not isinstance(msg_id, str):
                # 尝试将非字符串 ID 转换为字符串
                if msg_id is None:
                    # 处理 None 值
                    msg_id = ""
                else:
                    msg_id = str(msg_id)

            # 3.4 添加到结果列表
            message_ids.append(msg_id)

        except (KeyError, TypeError) as e:
            # 4. 异常处理：记录错误并继续处理其他消息
            print(f"处理{parent_column}中的第 {idx} 项时出错: {str(e)}")
            # 可以选择跳过或添加占位符
            message_ids.append("")  # 添加空字符串作为占位符
    cleaned_list = [x for x in message_ids if x not in [None, ""] and str(x).strip()]
    return cleaned_list


# 用于解析json对象
def remove_json_prefix(text,head_text):
    """
    判断字符串是否以某个字符串开头，如果是则删除开头的此字符串
    返回处理后的字符串
    """
    text = text.lstrip()
    if text.startswith(head_text):
        return text[len(head_text):]
    return text

def extract_json_from_string(s):
    """
    从字符串中提取开头的JSON对象
    返回 (JSON对象, 剩余字符串)
    """
    decoder = json.JSONDecoder()
    try:
        # 解析字符串开头的JSON
        obj, end_index = decoder.raw_decode(s)
        # 返回JSON对象和剩余文本
        return json.dumps(obj, ensure_ascii=False, indent=2), s[end_index:].strip()
    except json.JSONDecodeError:
        # 如果解析失败返回None
        return '', s

def remove_json_comments(json_str):
    """
    移除JSON字符串中的所有//注释，返回干净的JSON字符串

    参数:
        json_str: 包含注释的JSON字符串

    返回:
        移除所有注释后的JSON字符串
    """
    # 分两步处理注释：
    # 1. 移除行内注释（在行尾的注释）
    # 2. 移除整行注释（单独一行的注释）

    # 处理行内注释（在行尾的//注释）
    # 匹配模式：任意空白 + // + 非换行字符 + 换行或字符串结尾
    inline_pattern = r'\s*//[^\n]*(?:\n|$)'
    cleaned = re.sub(inline_pattern, '\n', json_str)

    # 处理整行注释（单独一行的//注释）
    # 匹配模式：行首 + 任意空白 + // + 任意字符 + 换行或字符串结尾
    full_line_pattern = r'^\s*//[^\n]*(?:\n|$)'
    cleaned = re.sub(full_line_pattern, '', cleaned, flags=re.MULTILINE)

    return cleaned


# 敏感词替换函数
def sensitive_word_replacement(words):
    words = words.replace('习近平','中国国家主席') \
             .replace('金正恩', '朝鲜最高领导人') \
             .replace('李在明', '韩国总统') \
             .replace('普京', '俄罗斯总统') \
             .replace('金与正','朝鲜劳动党中央委员会副部长')
    return words


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