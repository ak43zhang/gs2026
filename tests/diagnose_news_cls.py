"""
诊断脚本：测试财联社分析服务启动问题
"""
import sys
import subprocess
import time
import os
from pathlib import Path

PROJECT_ROOT = Path(r"F:\pyworkspace2026\gs2026")
PYTHON_EXE = r"F:\python312\python.exe"

def test_news_cls():
    """测试财联社服务启动"""
    print("=" * 60)
    print("测试财联社分析服务启动")
    print("=" * 60)
    
    # 1. 检查必要文件是否存在
    print("\n[1] 检查必要文件...")
    files_to_check = [
        PROJECT_ROOT / "src" / "gs2026" / "analysis" / "worker" / "message" / "deepseek" / "deepseek_analysis_news_cls.py",
        PROJECT_ROOT / "src" / "gs2026" / "utils" / "daemon_util.py",
    ]
    for f in files_to_check:
        if f.exists():
            print(f"  ✓ {f.name}")
        else:
            print(f"  ✗ {f.name} - 不存在!")
    
    # 2. 生成包装脚本（模拟 process_manager 的行为）
    print("\n[2] 生成测试包装脚本...")
    temp_dir = PROJECT_ROOT / "temp"
    temp_dir.mkdir(exist_ok=True)
    
    wrapper_code = f'''import sys
import traceback

# 记录启动日志
with open(r"{temp_dir}\\test_news_cls.log", "w", encoding="utf-8") as f:
    f.write("[INFO] 包装脚本开始执行\\n")
    f.write(f"[INFO] sys.path = {{sys.path}}\\n")

try:
    sys.path.insert(0, r"{PROJECT_ROOT}")
    sys.path.insert(0, r"{PROJECT_ROOT}\\src")
    
    with open(r"{temp_dir}\\test_news_cls.log", "a", encoding="utf-8") as f:
        f.write("[INFO] 开始导入模块\\n")
    
    from gs2026.analysis.worker.message.deepseek.deepseek_analysis_news_cls import time_task_do_cls
    
    with open(r"{temp_dir}\\test_news_cls.log", "a", encoding="utf-8") as f:
        f.write("[INFO] time_task_do_cls 导入成功\\n")
    
    from gs2026.utils.task_runner import run_daemon_task
    
    with open(r"{temp_dir}\\test_news_cls.log", "a", encoding="utf-8") as f:
        f.write("[INFO] run_daemon_task 导入成功\\n")
        f.write("[INFO] 准备启动 run_daemon_task\\n")
    
    # 启动（使用较短的轮询时间便于测试）
    run_daemon_task(target=time_task_do_cls, args=(5, "2026"))
    
    with open(r"{temp_dir}\\test_news_cls.log", "a", encoding="utf-8") as f:
        f.write("[INFO] run_daemon_task 调用完成\\n")
        
except Exception as e:
    with open(r"{temp_dir}\\test_news_cls.log", "a", encoding="utf-8") as f:
        f.write(f"[ERROR] 异常: {{str(e)}}\\n")
        f.write(f"[ERROR] 堆栈: {{traceback.format_exc()}}\\n")
    raise
'''
    
    wrapper_path = temp_dir / "test_news_cls_wrapper.py"
    wrapper_path.write_text(wrapper_code, encoding='utf-8')
    print(f"  包装脚本: {wrapper_path}")
    
    # 3. 启动进程
    print("\n[3] 启动测试进程...")
    log_file = temp_dir / "test_news_cls.log"
    
    proc = subprocess.Popen(
        [PYTHON_EXE, str(wrapper_path)],
        cwd=str(PROJECT_ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW
    )
    
    print(f"  进程 PID: {proc.pid}")
    
    # 4. 等待并检查状态
    print("\n[4] 等待5秒观察进程状态...")
    time.sleep(5)
    
    # 检查进程是否还在运行
    try:
        import psutil
        if psutil.pid_exists(proc.pid):
            p = psutil.Process(proc.pid)
            print(f"  ✓ 进程仍在运行 (PID: {proc.pid})")
            print(f"  状态: {p.status()}")
            
            # 检查子进程
            children = p.children(recursive=True)
            print(f"  子进程数: {len(children)}")
            for child in children:
                print(f"    - PID {child.pid}: {child.name()}")
        else:
            print(f"  ✗ 进程已退出 (PID: {proc.pid})")
    except Exception as e:
        print(f"  检查进程状态失败: {e}")
    
    # 5. 读取日志
    print("\n[5] 读取启动日志...")
    if log_file.exists():
        log_content = log_file.read_text(encoding='utf-8')
        print(log_content)
    else:
        print("  日志文件未生成!")
    
    # 6. 清理
    print("\n[6] 清理测试进程...")
    try:
        if psutil.pid_exists(proc.pid):
            p = psutil.Process(proc.pid)
            for child in p.children(recursive=True):
                child.terminate()
            p.terminate()
            p.wait(timeout=3)
            print("  测试进程已终止")
    except Exception as e:
        print(f"  清理失败: {e}")
    
    print("\n" + "=" * 60)
    print("诊断完成")
    print("=" * 60)


if __name__ == "__main__":
    test_news_cls()
