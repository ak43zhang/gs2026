import hashlib
import re
import json
from typing import List, Dict, Any

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

    # 2. 确保{parent_column}是列表类型
    if not isinstance(message_collection, list):
        raise TypeError(f"'{parent_column}' 应为列表类型，实际类型为 {type(message_collection).__name__}")

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