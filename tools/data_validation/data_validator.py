"""离线数据验证工具主程序

使用示例:
    # 检测指定日期的新闻分析数据
    python data_validator.py -s 20260422 -e 20260422 -t news
    
    # 检测并自动清理
    python data_validator.py -s 20260422 -e 20260422 -t news -m fix
    
    # 检测指定日期范围的所有数据
    python data_validator.py -s 20260401 -e 20260422 -t all -m check
    
    # 交互模式
    python data_validator.py -s 20260422 -e 20260422 -t news -m interactive
"""
import argparse
import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Type

# 添加项目路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import create_engine

from gs2026.utils import config_util, log_util
from gs2026.utils import mysql_util as mu

from models import ValidationReport
from validators import NewsValidator, ZtbValidator, NoticeValidator, DomainValidator
from cleaners import DataCleaner
from reporters import ConsoleReporter, FileReporter


# 验证器映射
VALIDATOR_MAP: Dict[str, Type] = {
    'ztb': ZtbValidator,
    'news': NewsValidator,
    'notice': NoticeValidator,
    'domain': DomainValidator,
}


def load_config(config_path: str = None) -> Dict:
    """加载验证规则配置"""
    if config_path and os.path.exists(config_path):
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    # 使用默认配置
    default_config = Path(__file__).parent / 'config' / 'validation_config.json'
    if default_config.exists():
        with open(default_config, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    raise FileNotFoundError("找不到验证规则配置文件")


def create_mysql_engine():
    """创建MySQL连接引擎"""
    url = config_util.get_config('common.url')
    if not url:
        mysql_host = config_util.get_config('mysql.host', '192.168.0.101')
        mysql_port = config_util.get_config('mysql.port', 3306)
        mysql_user = config_util.get_config('mysql.user', 'root')
        mysql_password = config_util.get_config('mysql.password', '123456')
        mysql_database = config_util.get_config('mysql.database', 'gs')
        url = f"mysql+pymysql://{mysql_user}:{mysql_password}@{mysql_host}:{mysql_port}/{mysql_database}?charset=utf8mb4"
    
    return create_engine(url, pool_recycle=3600, pool_pre_ping=True)


def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description='离线数据验证工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  %(prog)s -s 20260422 -e 20260422 -t news
  %(prog)s -s 20260422 -e 20260422 -t news -m fix
  %(prog)s -s 20260401 -e 20260422 -t all -m check
  %(prog)s -s 20260422 -e 20260422 -t news -m interactive
        """
    )
    
    parser.add_argument(
        '-s', '--start-date',
        required=True,
        help='开始日期 (YYYYMMDD)'
    )
    parser.add_argument(
        '-e', '--end-date',
        required=True,
        help='结束日期 (YYYYMMDD)'
    )
    parser.add_argument(
        '-t', '--types',
        default='all',
        help='验证类型，逗号分隔: ztb,news,notice,domain,all (默认: all)'
    )
    parser.add_argument(
        '-m', '--mode',
        default='check',
        choices=['check', 'fix', 'report', 'interactive'],
        help='执行模式 (默认: check)'
    )
    parser.add_argument(
        '-o', '--output',
        default='./reports',
        help='报告输出目录 (默认: ./reports)'
    )
    parser.add_argument(
        '-c', '--config',
        default=None,
        help='验证规则配置文件路径'
    )
    
    return parser.parse_args()


def get_validator_types(types_arg: str) -> List[str]:
    """获取验证器类型列表"""
    if types_arg == 'all':
        return list(VALIDATOR_MAP.keys())
    
    types = [t.strip() for t in types_arg.split(',')]
    valid_types = []
    
    for t in types:
        if t in VALIDATOR_MAP:
            valid_types.append(t)
        else:
            print(f"警告: 未知的验证类型 '{t}'，已跳过")
    
    return valid_types


def run_validation(validator_type: str, start_date: str, end_date: str, 
                   config: Dict, engine) -> ValidationReport:
    """执行单个验证器"""
    validator_class = VALIDATOR_MAP[validator_type]
    validator_config = config['validators'].get(validator_type, {})
    
    if not validator_config:
        print(f"错误: 找不到 {validator_type} 的验证规则配置")
        return None
    
    validator = validator_class(validator_config, engine)
    print(f"\n开始验证 [{validator_type}] {start_date} ~ {end_date} ...")
    
    report = validator.validate(start_date, end_date)
    
    print(f"  总记录数: {report.total_records}")
    print(f"  异常记录数: {report.invalid_count}")
    if report.total_records > 0:
        print(f"  异常率: {report.invalid_rate:.2f}%")
    print(f"  耗时: {report.duration_seconds:.2f}秒")
    
    return report


def main():
    """主入口"""
    args = parse_args()
    
    # 加载配置
    try:
        config = load_config(args.config)
        print(f"已加载验证规则配置 (版本: {config.get('version', 'unknown')})")
    except Exception as e:
        print(f"加载配置失败: {e}")
        sys.exit(1)
    
    # 创建MySQL连接
    try:
        engine = create_mysql_engine()
        print("MySQL连接已建立")
    except Exception as e:
        print(f"创建MySQL连接失败: {e}")
        sys.exit(1)
    
    # 获取验证器类型
    validator_types = get_validator_types(args.types)
    if not validator_types:
        print("错误: 没有有效的验证类型")
        sys.exit(1)
    
    print(f"验证类型: {', '.join(validator_types)}")
    print(f"日期范围: {args.start_date} ~ {args.end_date}")
    print(f"执行模式: {args.mode}")
    
    # 执行验证
    reports = []
    for validator_type in validator_types:
        report = run_validation(validator_type, args.start_date, args.end_date, config, engine)
        if report:
            reports.append(report)
    
    # 生成报告
    console_reporter = ConsoleReporter()
    console_reporter.generate(reports)
    
    # 根据模式执行后续操作
    if args.mode == 'report':
        # 仅生成文件报告
        file_reporter = FileReporter(args.output)
        file_reporter.generate(reports)
    
    elif args.mode == 'fix':
        # 自动清理
        if any(r.invalid_records for r in reports):
            print("\n" + "=" * 80)
            confirm = input("确认清理以上异常数据? [y/N]: ").strip().lower()
            
            if confirm == 'y':
                cleaner = DataCleaner(engine)
                for report in reports:
                    if report.invalid_records:
                        print(f"\n清理 [{report.validator_type}] 异常数据...")
                        fix_report = cleaner.clean(report, interactive=False)
                        console_reporter.generate_fix_report(fix_report)
            else:
                print("已取消清理操作")
        else:
            print("\n没有发现异常数据，无需清理")
    
    elif args.mode == 'interactive':
        # 交互模式
        if any(r.invalid_records for r in reports):
            cleaner = DataCleaner(engine)
            for report in reports:
                if report.invalid_records:
                    print(f"\n交互清理 [{report.validator_type}] 异常数据...")
                    fix_report = cleaner.clean(report, interactive=True)
                    console_reporter.generate_fix_report(fix_report)
        else:
            print("\n没有发现异常数据")
    
    print("\n验证完成")


if __name__ == '__main__':
    main()
