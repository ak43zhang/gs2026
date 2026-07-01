"""
批量修改文件：将 create_engine 替换为 config_util.get_engine()
"""
import os
import re

BASE_DIR = r"F:\pyworkspace2026\gs2026\src\gs2026"

# 需要修改的文件列表（相对于BASE_DIR）
FILES_TO_MODIFY = [
    # 第一优先级：DeepSeek分析
    r"analysis\worker\message\deepseek\deepseek_analysis_event_driven.py",
    r"analysis\worker\message\deepseek\deepseek_analysis_news_cls.py",
    r"analysis\worker\message\deepseek\deepseek_analysis_news_combine.py",
    r"analysis\worker\message\deepseek\deepseek_analysis_news_ztb.py",
    r"analysis\worker\message\deepseek\deepseek_analysis_notice.py",
    r"analysis\worker\message\deepseek\processor\domain.py",
    r"analysis\worker\message\deepseek\processor\news.py",
    # 分析相关
    r"analysis\worker\message\analysis_event_driven.py",
    r"analysis\worker\message\result_processor.py",
    # Volcengine
    r"analysis\worker\message\volcengine\volcengine_analysis_event_driven.py",
    r"analysis\worker\message\volcengine\volcengine_analysis_news_cls.py",
    r"analysis\worker\message\volcengine\volcengine_analysis_news_combine.py",
    r"analysis\worker\message\volcengine\volcengine_analysis_news_ztb.py",
    r"analysis\worker\message\volcengine\volcengine_analysis_notice.py",
    # 智谱
    r"analysis\worker\message\zhipuqingyan\zhipuqingyan_analysis_event_driven.py",
    # Baidu
    r"analysis\worker\message\baidu\baidu_analysis_news_combine.py",
    r"analysis\worker\message\baidu\baidu_analysis_news_financial.py",
    r"analysis\worker\message\baidu\baidu_analysis_news_ztb.py",
    r"analysis\worker\message\baidu\baidu_analysis_notice.py",
    # 采集-combine
    r"collection\combine\combine_collection.py",
    r"collection\combine\combine_ztb_area.py",
    # 采集-daily
    r"collection\daily\baostock_collection.py",
    r"collection\daily\baostock_collection_v2.py",
    r"collection\daily\base_collection.py",
    r"collection\daily\bk_gn_collection.py",
    r"collection\base\wencai_collection.py",
    r"collection\base\zt_collection.py",
    # 采集-news
    r"collection\news\cls_history.py",
    r"collection\news\collection_message.py",
    r"collection\news\dicj_yckx.py",
    r"collection\news\xhcj.py",
    r"collection\news\zqsb_rmcx.py",
    # 采集-other
    r"collection\other\akshare_collection.py",
    r"collection\other\bond_zh_cov.py",
    r"collection\other\concept_collection.py",
    r"collection\other\ods.py",
    r"collection\other\stock_update_collection.py",
    # 采集-risk
    r"collection\risk\akshare_risk_history.py",
    r"collection\risk\notice_content_fetcher.py",
    r"collection\risk\notice_risk_history.py",
    r"collection\risk\wencai_risk_history.py",
    r"collection\risk\wencai_risk_year_history.py",
    # 监控
    r"monitor\monitor_bond.py",
    r"monitor\monitor_dp_signal.py",
    r"monitor\monitor_gp_zq_rising_signal.py",
    r"monitor\monitor_industry.py",
    r"monitor\monitor_stock.py",
    # 工具
    r"tools\deepseek_ban_checker.py",
    r"tools\migrate_analysis_news.py",
    # 工具模块
    r"utils\data_recovery.py",
    r"utils\redis_util.py",
    r"utils\trading_day_util.py",
]

def modify_file(filepath):
    """修改单个文件"""
    if not os.path.exists(filepath):
        print(f"  ⚠️ 文件不存在: {filepath}")
        return False
    
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    original = content
    
    # 检查是否已经使用了 config_util.get_engine()
    if 'config_util.get_engine()' in content:
        print(f"  ✓ 已修改过，跳过")
        return False
    
    # 模式1: 删除 "from sqlalchemy import create_engine" (如果没有其他sqlalchemy导入)
    # 模式2: 从 "from sqlalchemy import create_engine, text" 中去掉 create_engine
    # 模式3: 替换 "engine = create_engine(...)" 为 "engine = config_util.get_engine()"
    # 模式4: 删除 "url = config_util.get_config("common.url")" 如果只用于engine
    
    # Step 1: 替换 engine = create_engine(...) 行
    # 匹配各种形式的 create_engine 调用
    patterns = [
        # engine = create_engine(url, pool_recycle=3600, pool_pre_ping=True, pool_size=20, max_overflow=30)
        r'engine\s*=\s*create_engine\s*\([^)]*pool_size\s*=\s*(\d+)[^)]*max_overflow\s*=\s*(\d+)[^)]*\)',
        # engine = create_engine(url, pool_recycle=3600, pool_pre_ping=True)
        r'engine\s*=\s*create_engine\s*\(url\s*,\s*pool_recycle\s*=\s*3600\s*,\s*pool_pre_ping\s*=\s*True\)',
        # engine = create_engine(url,pool_recycle=3600,pool_pre_ping=True)
        r'engine\s*=\s*create_engine\s*\(url\s*,\s*pool_recycle\s*=\s*3600\s*,\s*pool_pre_ping\s*=\s*True\)',
        # engine = create_engine(\n    url, ...)  多行形式
        r'engine\s*=\s*create_engine\s*\(\s*\n[^)]*\)',
    ]
    
    # 简单替换：所有 engine = create_engine(...) 
    # 使用更通用的正则
    engine_pattern = r'^engine\s*=\s*create_engine\s*\([^)]*\)\s*$'
    lines = content.split('\n')
    new_lines = []
    skip_next = False
    modified = False
    
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        
        # 跳过多行 create_engine 调用
        if skip_next:
            if ')' in line:
                skip_next = False
            i += 1
            continue
        
        # 匹配 engine = create_engine(...)
        if re.match(r'^engine\s*=\s*create_engine\s*\(', stripped):
            if ')' in stripped:
                # 单行形式
                # 检查是否有特殊参数需要保留
                pool_size_match = re.search(r'pool_size\s*=\s*(\d+)', stripped)
                max_overflow_match = re.search(r'max_overflow\s*=\s*(\d+)', stripped)
                
                if pool_size_match and int(pool_size_match.group(1)) != 5:
                    ps = pool_size_match.group(1)
                    mo = max_overflow_match.group(1) if max_overflow_match else "10"
                    new_lines.append(f"engine = config_util.get_engine(pool_size={ps}, max_overflow={mo})")
                else:
                    new_lines.append("engine = config_util.get_engine()")
                modified = True
            else:
                # 多行形式 - 收集所有行直到 )
                full_stmt = stripped
                j = i + 1
                while j < len(lines) and ')' not in lines[j]:
                    full_stmt += lines[j].strip()
                    j += 1
                if j < len(lines):
                    full_stmt += lines[j].strip()
                
                pool_size_match = re.search(r'pool_size\s*=\s*(\d+)', full_stmt)
                max_overflow_match = re.search(r'max_overflow\s*=\s*(\d+)', full_stmt)
                
                if pool_size_match and int(pool_size_match.group(1)) != 5:
                    ps = pool_size_match.group(1)
                    mo = max_overflow_match.group(1) if max_overflow_match else "10"
                    new_lines.append(f"engine = config_util.get_engine(pool_size={ps}, max_overflow={mo})")
                else:
                    new_lines.append("engine = config_util.get_engine()")
                modified = True
                i = j  # 跳过多行
            i += 1
            continue
        
        # 删除单独的 url = config_util.get_config("common.url") 行
        # 但只在该行仅用于engine创建时删除
        if re.match(r'^url\s*=\s*config_util\.get_config\s*\(\s*["\']common\.url["\']\s*\)\s*$', stripped):
            # 检查url是否在后续被其他地方使用（不仅仅是create_engine）
            remaining = '\n'.join(lines[i+1:])
            url_uses = len(re.findall(r'\burl\b', remaining))
            engine_uses = len(re.findall(r'create_engine\s*\(\s*url', remaining))
            if url_uses <= engine_uses + 1:  # url只被engine和可能的mysql_util使用
                # 保留该行，因为可能被mysql_util使用
                new_lines.append(line)
            else:
                new_lines.append(line)
            i += 1
            continue
        
        # 修改 from sqlalchemy import create_engine 行
        if 'from sqlalchemy import' in stripped and 'create_engine' in stripped:
            # 去掉 create_engine，保留其他导入
            new_import = re.sub(r',?\s*create_engine\s*,?', '', stripped)
            new_import = re.sub(r'import\s*,', 'import ', new_import)  # 修复 "import ," 
            new_import = re.sub(r',\s*$', '', new_import)  # 移除末尾逗号
            new_import = new_import.strip()
            
            # 如果去掉create_engine后还有其他导入
            if re.search(r'import\s+\w', new_import):
                new_lines.append(new_import)
            else:
                # 如果只剩 "from sqlalchemy import"，删除整行
                pass
            modified = True
            i += 1
            continue
        
        new_lines.append(line)
        i += 1
    
    if modified:
        content = '\n'.join(new_lines)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        return True
    else:
        print(f"  ⚠️ 未找到匹配模式")
        return False


def main():
    print("=" * 60)
    print("批量修改：create_engine → config_util.get_engine()")
    print("=" * 60)
    
    success_count = 0
    skip_count = 0
    fail_count = 0
    
    for rel_path in FILES_TO_MODIFY:
        filepath = os.path.join(BASE_DIR, rel_path)
        filename = os.path.basename(filepath)
        print(f"\n[{filename}]")
        
        try:
            result = modify_file(filepath)
            if result:
                success_count += 1
                print(f"  ✓ 修改成功")
            else:
                skip_count += 1
        except Exception as e:
            fail_count += 1
            print(f"  ✗ 失败: {e}")
    
    print("\n" + "=" * 60)
    print(f"完成！成功: {success_count}, 跳过: {skip_count}, 失败: {fail_count}")
    print("=" * 60)


if __name__ == "__main__":
    main()
