import sys
import datetime

log_file = r"F:\pyworkspace2026\gs2026\logs\analysis\import_test.log"

def log(msg):
    timestamp = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
    line = f"[{timestamp}] {msg}"
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(f"{line}\n")
    print(line)

log("=" * 60)
log("测试模块导入")

sys.path.insert(0, r"F:\pyworkspace2026\gs2026")
sys.path.insert(0, r"F:\pyworkspace2026\gs2026\src")

log("开始导入...")

try:
    log("导入 gs2026.analysis.worker.message.deepseek.deepseek_analysis_news_cls...")
    import gs2026.analysis.worker.message.deepseek.deepseek_analysis_news_cls as mod
    log(f"导入成功！模块文件: {mod.__file__}")
    log(f"time_task_do_cls: {mod.time_task_do_cls}")
except Exception as e:
    log(f"导入失败: {type(e).__name__}: {e}")
    import traceback
    log(traceback.format_exc())

log("结束")
