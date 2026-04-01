"""
集成性能优化功能
从 0c0ffd4 之后的提交中选择性集成性能优化
"""
import subprocess
import sys

# 定义要集成的提交（按依赖顺序）
COMMITS_TO_CHERRY_PICK = [
    # 1. 基础修复
    '12c1516',  # fix: pass enabled param to DBProfiler
    
    # 2. 股票映射批量查询优化
    '84e4a94',  # perf: batch stock mapping query optimization
    
    # 3. 涨跌幅向量化处理
    'bc27fb6',  # perf: vectorize _enrich_change_pct for 10x speedup
    
    # 4. 批量获取涨跌幅优化
    '8333519',  # perf: batch fetch change_pct from monitor_gp_sssj
    
    # 5. combine ranking 优化
    '93900de',  # perf: optimize get_combine_ranking with Redis pipeline
    '52bad31',  # perf: reduce combine ranking timestamps from 50 to 18
    
    # 6. 日期逻辑修复
    '3c0c16f',  # fix: simplify date logic
    '3ae1473',  # fix: use yesterday's data when today's data not available
]

# 排除的提交（不集成）
EXCLUDED_COMMITS = [
    'aa0783d',  # feat: add auction period UI indicator - 集合竞价UI
]

def run_command(cmd, cwd=None):
    """运行命令并返回结果"""
    result = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True)
    return result.returncode, result.stdout, result.stderr

def main():
    project_dir = r'F:\pyworkspace2026\gs2026'
    
    print("=" * 60)
    print("开始集成性能优化功能")
    print("=" * 60)
    
    failed_commits = []
    
    for commit in COMMITS_TO_CHERRY_PICK:
        print(f"\n尝试集成: {commit}")
        print("-" * 40)
        
        # 获取提交信息
        code, stdout, stderr = run_command(f'git log -1 --oneline {commit}', cwd=project_dir)
        if code != 0:
            print(f"❌ 无法找到提交 {commit}")
            failed_commits.append(commit)
            continue
        
        print(f"提交信息: {stdout.strip()}")
        
        # 尝试cherry-pick
        code, stdout, stderr = run_command(f'git cherry-pick {commit} --no-commit', cwd=project_dir)
        
        if code == 0:
            print(f"✅ 成功集成 {commit}")
            # 查看变更的文件
            code2, stdout2, stderr2 = run_command('git diff --cached --name-only', cwd=project_dir)
            if stdout2.strip():
                print(f"   变更文件:\n{stdout2}")
        else:
            print(f"⚠️  集成失败: {stderr}")
            # 回退变更
            run_command('git reset --hard HEAD', cwd=project_dir)
            failed_commits.append(commit)
            continue
    
    print("\n" + "=" * 60)
    print("集成结果汇总")
    print("=" * 60)
    
    if failed_commits:
        print(f"❌ 失败的提交: {failed_commits}")
        print("\n这些提交可能与其他提交有冲突，需要手动处理。")
    else:
        print("✅ 所有性能优化功能已集成！")
    
    # 查看当前状态
    code, stdout, stderr = run_command('git status --short', cwd=project_dir)
    if stdout.strip():
        print(f"\n当前工作区状态:\n{stdout}")
    
    return 0 if not failed_commits else 1

if __name__ == '__main__':
    sys.exit(main())
