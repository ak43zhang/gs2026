"""离线数据验证工具 v3

支持方式:
    1. 直接传参调用
    2. YAML配置文件
    3. 脚本命令行

使用示例:
    # 方式1: 直接传参
    from tools.data_validation import run_validation
    result = run_validation(start_date='20260422', end_date='20260422', validator_types=['news'])
    
    # 方式2: YAML配置
    result = run_validation(yaml_config='config/validation_tasks.yaml', task_name='daily_news_validation')
    
    # 方式3: 批量YAML任务
    results = run_yaml_tasks(task_names=['daily_news_validation', 'ztb_special_check'])
    
    # 方式4: 脚本调用
    python data_validator.py --task daily_news_validation
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Dict, List, Any, Optional, Type

# 添加项目路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import create_engine

from gs2026.utils import config_util
from gs2026.utils import mysql_util as mu

# 相对导入（当作为模块使用时）
try:
    from .models import ValidationReport
    from .params import ValidationParams, ValidationResult
    from .yaml_loader import YamlConfigLoader
    from .validators import NewsValidator, ZtbValidator, NoticeValidator, DomainValidator
    from .cleaners import DataCleaner
    from .reporters import ConsoleReporter, FileReporter
except ImportError:
    # 直接运行时
    from models import ValidationReport
    from params import ValidationParams, ValidationResult
    from yaml_loader import YamlConfigLoader
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


def load_validation_config(config_path: str = None) -> Dict:
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


def run_single_validation(validator_type: str, start_date: str, end_date: str, 
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


def run_validation(
    start_date: str = None,
    end_date: str = None,
    validator_types: List[str] = None,
    mode: str = 'check',
    output_dir: str = './reports',
    config_path: str = None,
    auto_fix: bool = False,
    interactive: bool = False,
    mysql_engine=None,
    redis_client=None,
    params: ValidationParams = None,
    yaml_config: str = None,
    task_name: str = None
) -> ValidationResult:
    """
    执行数据验证（主入口函数）
    
    参数优先级（从高到低）:
    1. yaml_config + task_name
    2. params对象
    3. 直接传参
    
    Args:
        start_date: 开始日期 (YYYYMMDD)
        end_date: 结束日期 (YYYYMMDD)
        validator_types: 验证类型列表 ['ztb', 'news', 'notice', 'domain']，None表示全部
        mode: 执行模式 'check'/'fix'/'report'/'interactive'
        output_dir: 报告输出目录
        config_path: 验证规则配置文件路径
        auto_fix: 是否自动清理（mode='fix'时生效）
        interactive: 是否交互模式
        mysql_engine: MySQL引擎（None时自动创建）
        redis_client: Redis客户端（None时自动创建）
        params: ValidationParams对象（直接传参方式）
        yaml_config: YAML配置文件路径
        task_name: YAML中定义的任务名称
    
    Returns:
        ValidationResult对象
    """
    result = ValidationResult()
    
    try:
        # 优先级1: YAML配置
        if yaml_config and task_name:
            loader = YamlConfigLoader(yaml_config)
            params_dict = loader.get_task(task_name)
            params = ValidationParams.from_dict(params_dict)
        
        # 优先级2: params对象
        if params:
            start_date = params.start_date
            end_date = params.end_date
            validator_types = params.validator_types
            mode = params.mode
            output_dir = params.output_dir
            config_path = params.config_path
            auto_fix = params.auto_fix
            interactive = params.interactive
        
        # 参数校验
        if not start_date or not end_date:
            result.success = False
            result.errors.append('start_date和end_date不能为空')
            return result
        
        # 加载验证规则配置
        validation_config = load_validation_config(config_path)
        
        # 创建MySQL引擎（如果未提供）
        if mysql_engine is None:
            mysql_engine = create_mysql_engine()
        
        # 确定验证类型
        if validator_types is None or validator_types == ['all']:
            validator_types = list(VALIDATOR_MAP.keys())
        
        print(f"验证类型: {', '.join(validator_types)}")
        print(f"日期范围: {start_date} ~ {end_date}")
        print(f"执行模式: {mode}")
        
        # 执行验证
        for vtype in validator_types:
            report = run_single_validation(vtype, start_date, end_date, validation_config, mysql_engine)
            if report:
                result.reports.append(report)
        
        # 生成报告
        console_reporter = ConsoleReporter()
        console_reporter.generate(result.reports)
        
        # 根据模式执行后续操作
        if mode == 'report':
            file_reporter = FileReporter(output_dir)
            file_reporter.generate(result.reports)
            result.output_files = [f"{output_dir}/validation_report.json", f"{output_dir}/validation_report.md"]
        
        elif mode == 'fix':
            if any(r.invalid_records for r in result.reports):
                if auto_fix:
                    cleaner = DataCleaner(mysql_engine, redis_client)
                    for report in result.reports:
                        if report.invalid_records:
                            print(f"\n清理 [{report.validator_type}] 异常数据...")
                            fix_report = cleaner.clean(report, interactive=False)
                            result.fix_report = fix_report
                            console_reporter.generate_fix_report(fix_report)
                else:
                    print("\n" + "=" * 80)
                    confirm = input("确认清理以上异常数据? [y/N]: ").strip().lower()
                    if confirm == 'y':
                        cleaner = DataCleaner(mysql_engine, redis_client)
                        for report in result.reports:
                            if report.invalid_records:
                                print(f"\n清理 [{report.validator_type}] 异常数据...")
                                fix_report = cleaner.clean(report, interactive=False)
                                result.fix_report = fix_report
                                console_reporter.generate_fix_report(fix_report)
                    else:
                        print("已取消清理操作")
            else:
                print("\n没有发现异常数据，无需清理")
        
        elif mode == 'interactive':
            if any(r.invalid_records for r in result.reports):
                cleaner = DataCleaner(mysql_engine, redis_client)
                for report in result.reports:
                    if report.invalid_records:
                        print(f"\n交互清理 [{report.validator_type}] 异常数据...")
                        fix_report = cleaner.clean(report, interactive=True)
                        result.fix_report = fix_report
                        console_reporter.generate_fix_report(fix_report)
            else:
                print("\n没有发现异常数据")
        
    except Exception as e:
        result.success = False
        result.errors.append(str(e))
        import traceback
        traceback.print_exc()
    
    return result


def batch_validate(
    date_list: List[str],
    validator_types: List[str] = None,
    mode: str = 'check',
    **kwargs
) -> Dict[str, ValidationResult]:
    """
    批量验证多个日期
    
    Args:
        date_list: 日期列表 ['20260422', '20260423', ...]
        validator_types: 验证类型列表
        mode: 执行模式
        **kwargs: 其他参数传递给run_validation
    
    Returns:
        {date: ValidationResult}
    """
    results = {}
    
    for date in date_list:
        print(f"\n{'='*80}")
        print(f"验证日期: {date}")
        print('='*80)
        
        result = run_validation(
            start_date=date,
            end_date=date,
            validator_types=validator_types,
            mode=mode,
            **kwargs
        )
        
        results[date] = result
    
    return results


def run_yaml_tasks(
    yaml_path: str = 'config/validation_tasks.yaml',
    task_names: List[str] = None,
    batch_group: str = None,
    dry_run: bool = False
) -> Dict[str, ValidationResult]:
    """
    执行YAML中定义的多个任务
    
    Args:
        yaml_path: YAML配置文件路径
        task_names: 指定任务名称列表（None表示执行所有enabled任务）
        batch_group: 批量任务组名称
        dry_run: 是否仅预览，不实际执行
    
    Returns:
        {task_name: ValidationResult}
    """
    loader = YamlConfigLoader(yaml_path)
    results = {}
    
    # 确定要执行的任务列表
    if batch_group:
        task_names = loader.get_batch_group(batch_group)
        print(f"执行批量任务组 '{batch_group}': {task_names}")
    elif not task_names:
        task_names = loader.get_enabled_tasks()
        print(f"执行所有启用的任务: {task_names}")
    
    for task_name in task_names:
        print(f"\n{'='*80}")
        print(f"执行任务: {task_name}")
        print('='*80)
        
        if dry_run:
            print("[DRY RUN] 预览模式，不实际执行")
            params = loader.get_task(task_name)
            print(f"参数: {json.dumps(params, indent=2, ensure_ascii=False)}")
            continue
        
        result = run_validation(yaml_config=yaml_path, task_name=task_name)
        results[task_name] = result
    
    return results


def time_task_do_validation(
    date_param: str,
    start_date: str,
    end_date: str,
    validator_types: List[str] = None,
    mode: str = 'check',
    polling_time: int = 60
) -> None:
    """
    按指定日期参数循环执行验证任务
    
    类似于 time_task_do_ztb 的实现方式
    
    Args:
        date_param: 日期参数字符串（格式 'YYYY-MM-DD'），用于日志显示
        start_date: 查询起始日期
        end_date: 查询截止日期
        validator_types: 验证类型列表
        mode: 执行模式
        polling_time: 每轮验证后的休眠时间（秒）
    """
    print(f"启动定时验证任务: {date_param}")
    print(f"轮询间隔: {polling_time}秒")
    print("按 Ctrl+C 停止")
    
    try:
        while True:
            result = run_validation(
                start_date=start_date,
                end_date=end_date,
                validator_types=validator_types,
                mode=mode
            )
            
            # 检查是否还有异常数据
            has_invalid = any(r.invalid_records for r in result.reports)
            
            if not has_invalid:
                print(f"\n日期 {date_param} 的所有数据验证通过，任务结束")
                break
            
            if mode == 'fix':
                print(f"\n已修复异常数据，{polling_time}秒后重新验证...")
            else:
                print(f"\n发现异常数据，{polling_time}秒后重新检查...")
            
            time.sleep(polling_time)
    
    except KeyboardInterrupt:
        print("\n用户中断，任务停止")


# 脚本入口
if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='离线数据验证工具 v3',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  # YAML任务
  %(prog)s --yaml-config config/validation_tasks.yaml --task daily_news_validation
  
  # 批量任务组
  %(prog)s --yaml-config config/validation_tasks.yaml --batch-group daily_all
  
  # 预览模式
  %(prog)s --yaml-config config/validation_tasks.yaml --batch-group daily_all --dry-run
  
  # 传统方式（保持兼容）
  %(prog)s -s 20260422 -e 20260422 -t news -m check
        """
    )
    
    # YAML配置相关
    parser.add_argument('--yaml-config', default='config/validation_tasks.yaml',
                       help='YAML配置文件路径')
    parser.add_argument('--task', help='执行指定任务')
    parser.add_argument('--batch-group', help='执行批量任务组')
    parser.add_argument('--dry-run', action='store_true', help='预览模式')
    
    # 传统参数（保持兼容）
    parser.add_argument('-s', '--start-date', help='开始日期 (YYYYMMDD)')
    parser.add_argument('-e', '--end-date', help='结束日期 (YYYYMMDD)')
    parser.add_argument('-t', '--types', help='验证类型，逗号分隔')
    parser.add_argument('-m', '--mode', default='check', 
                       choices=['check', 'fix', 'report', 'interactive'],
                       help='执行模式 (默认: check)')
    parser.add_argument('-o', '--output', default='./reports', help='输出目录')
    parser.add_argument('-c', '--config', help='验证规则配置文件路径')
    parser.add_argument('--auto-fix', action='store_true', help='自动修复')
    
    args = parser.parse_args()
    
    # 如果传了--task或--batch-group，使用YAML模式
    if args.task or args.batch_group:
        results = run_yaml_tasks(
            yaml_path=args.yaml_config,
            task_names=[args.task] if args.task else None,
            batch_group=args.batch_group,
            dry_run=args.dry_run
        )
        
        # 输出汇总
        print("\n" + "="*80)
        print("任务执行汇总")
        print("="*80)
        for task_name, result in results.items():
            status = "✓ 成功" if result.success else "✗ 失败"
            print(f"  {task_name}: {status}")
            if result.errors:
                print(f"    错误: {', '.join(result.errors)}")
    
    # 传统方式
    elif args.start_date and args.end_date:
        validator_types = args.types.split(',') if args.types else None
        result = run_validation(
            start_date=args.start_date,
            end_date=args.end_date,
            validator_types=validator_types,
            mode=args.mode,
            output_dir=args.output,
            config_path=args.config,
            auto_fix=args.auto_fix
        )
        
        if not result.success:
            print(f"\n验证失败: {result.errors}")
            sys.exit(1)
    
    else:
        parser.print_help()
        sys.exit(1)
    
    print("\n验证完成")
