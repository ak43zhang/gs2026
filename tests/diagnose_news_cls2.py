"""
深度诊断：检查财联社服务启动后的实际运行情况
"""
import sys
import subprocess
import time
from pathlib import Path

PROJECT_ROOT = Path(r"F:\pyworkspace2026\gs2026")
PYTHON_EXE = r"F:\python312\python.exe"

def test_with_visible_console():
    """使用可见控制台启动，查看输出"""
    print("=" * 60)
    print("深度诊断：启动财联社分析（保留控制台查看输出）")
    print("=" * 60)
    
    temp_dir = PROJECT_ROOT / "temp"
    temp_dir.mkdir(exist_ok=True)
    
    # 生成带详细日志的包装脚本
    wrapper_code = f'''import sys
import traceback
import os

log_file = r"{temp_dir}\\news_cls_debug.log"

def log(msg):
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(f"[{{msg}}]\\n")
    print(msg)

log("[INIT] 包装脚本开始")
log(f"[INIT] Python: {{sys.executable}}")
log(f"[INIT] sys.path: {{sys.path}}")

try:
    sys.path.insert(0, r"{PROJECT_ROOT}")
    sys.path.insert(0, r"{PROJECT_ROOT}\\src")
    
    log("[IMPORT] 开始导入 time_task_do_cls")
    from gs2026.analysis.worker.message.deepseek.deepseek_analysis_news_cls import time_task_do_cls
    log("[IMPORT] time_task_do_cls 导入成功")
    
    log("[IMPORT] 开始导入 run_daemon_task")
    from gs2026.utils.task_runner import run_daemon_task
    log("[IMPORT] run_daemon_task 导入成功")
    
    log("[RUN] 准备调用 run_daemon_task")
    log("[RUN] 参数: polling_time=5, year=2026")
    
    # 直接调用，不包装，看具体错误
    run_daemon_task(target=time_task_do_cls, args=(5, "2026"))
    
    log("[RUN] run_daemon_task 调用完成（不应该到这里）")
    
except Exception as e:
    log(f"[ERROR] 异常: {{str(e)}}")
    log(f"[ERROR] 堆栈:")
    log(traceback.format_exc())
    raise
'''
    
    wrapper_path = temp_dir / "news_cls_debug.py"
    wrapper_path.write_text(wrapper_code, encoding='utf-8')
    
    print(f"\n启动脚本: {wrapper_path}")
    print("等待10秒观察...")
    
    # 使用可见控制台启动
    proc = subprocess.Popen(
        [PYTHON_EXE, str(wrapper_path)],
        cwd=str(PROJECT_ROOT),
        creationflags=subprocess.CREATE_NEW_CONSOLE  # 可见控制台
    )
    
    print(f"进程 PID: {proc.pid}")
    
    # 等待
    time.sleep(10)
    
    # 检查进程状态
    try:
        import psutil
        if psutil.pid_exists(proc.pid):
            p = psutil.Process(proc.pid)
            print(f"\n✓ 进程仍在运行 (PID: {proc.pid})")
            print(f"  状态: {p.status()}")
        else:
            print(f"\n✗ 进程已退出 (PID: {proc.pid})")
    except:
        print(f"\n? 无法检查进程状态")
    
    # 读取日志
    log_file = temp_dir / "news_cls_debug.log"
    if log_file.exists():
        print(f"\n日志内容:")
        print("-" * 40)
        print(log_file.read_text(encoding='utf-8'))
        print("-" * 40)
    else:
        print(f"\n日志文件未生成: {log_file}")
    
    # 尝试停止
    try:
        proc.terminate()
        proc.wait(timeout=3)
        print("\n测试进程已终止")
    except:
        print("\n测试进程终止失败或已退出")

if __name__ == "__main__":
    test_with_visible_console()
