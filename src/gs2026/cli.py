"""
命令行接口

提供GS2026的命令行工具。
"""

import sys

from gs2026 import  __version__


def main():
    """主入口函数"""
    if len(sys.argv) < 2:
        print("GS2026 股票数据采集分析系统")
        print(f"版本: {__version__}")
        print("\n可用命令:")
        print("  version    显示版本")
        print("  collect    采集数据")
        print("  analyze    分析数据")
        print("  monitor    启动监控")
        return
    
    command = sys.argv[1]
    
    if command == "version":
        print(f"GS2026 版本: {__version__}")
    
    elif command == "collect":
        collector = StockCollector()
        stocks = collector.collect_all_stocks()
        print(f"采集到 {len(stocks)} 只股票")
    
    elif command == "analyze":
        analyzer = AIAnalyzer()
        print("AI分析器已初始化")
    
    elif command == "monitor":
        app = GS2026App()
        app.initialize()
        print("监控服务已启动")
    
    else:
        print(f"未知命令: {command}")


if __name__ == "__main__":
    main()
