"""
热搜数据采集框架 - Playwright增强版
用于修复反爬较强的平台
"""
from loguru import logger
from gs2026.utils import mysql_util, config_util
from gs2026.utils.pandas_display_config import set_pandas_display_options
from gs2026.constants import FIREFOX_1408, CHROME_1208

import hashlib
import json
import re
import time
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Dict, List, Optional

import pandas as pd


def generate_content_hash(title: str, publish_time: str) -> str:
    content = f"{title}{publish_time}"
    return hashlib.md5(content.encode('utf-8')).hexdigest()


class BaseHotSearch(ABC):
    PLATFORM = ""
    
    def __init__(self, timeout: int = 10):
        self.timeout = timeout
    
    @abstractmethod
    def fetch(self, limit: int = 100) -> pd.DataFrame:
        pass
    
    def _create_result(self, title: str, content: str, analysis: str = "") -> Dict:
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        if not content or content == title:
            content = title
        return {
            'title': title,
            'publish_time': current_time,
            'content': content,
            'source': self.PLATFORM,
            'content_hash': generate_content_hash(title, current_time),
            'analysis': analysis
        }
    
    def _empty_df(self) -> pd.DataFrame:
        return pd.DataFrame(columns=['title', 'publish_time', 'content', 'source', 'content_hash', 'analysis'])


class PlaywrightBaseHotSearch(BaseHotSearch):
    """使用Playwright的基类"""
    
    def __init__(self, timeout: int = 10, headless: bool = True):
        super().__init__(timeout)
        self.headless = headless
        self.browser = None
        self.context = None
        self.page = None
    
    def _init_browser(self):
        try:
            from playwright.sync_api import sync_playwright
            
            self.playwright = sync_playwright().start()
            self.browser = self.playwright.chromium.launch(
                headless=self.headless,
                args=['--disable-blink-features=AutomationControlled']
            )
            self.context = self.browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            )
            self.context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            """)
            self.page = self.context.new_page()
        except ImportError:
            raise ImportError("请先安装playwright: pip install playwright && playwright install chromium")
    
    def close(self):
        try:
            if self.context:
                self.context.close()
            if self.browser:
                self.browser.close()
            if hasattr(self, 'playwright'):
                self.playwright.stop()
        except:
            pass


# ==================== 什么值得买 (Playwright) ====================
class SmzdmHotSearch(PlaywrightBaseHotSearch):
    """什么值得买 - Playwright版"""
    PLATFORM = "什么值得买"
    
    def fetch(self, limit: int = 100) -> pd.DataFrame:
        try:
            self._init_browser()
            
            # 访问排行榜页面
            self.page.goto('https://www.smzdm.com/top/', wait_until='networkidle')
            time.sleep(2)
            
            # 提取数据
            items = self.page.query_selector_all('.feed-row-wide .feed-title a, .z-feed-title a')
            
            results = []
            for idx, item in enumerate(items[:limit], 1):
                title = item.inner_text().strip()
                if title:
                    analysis = f"排名:{idx}"
                    results.append(self._create_result(title, title, analysis))
            
            return pd.DataFrame(results)
            
        except Exception as e:
            print(f"什么值得买错误: {e}")
            return self._empty_df()
        finally:
            self.close()


# ==================== 腾讯新闻 (Playwright) ====================
class QQNewsHotSearch(PlaywrightBaseHotSearch):
    """腾讯新闻 - Playwright版"""
    PLATFORM = "腾讯新闻"
    
    def fetch(self, limit: int = 100) -> pd.DataFrame:
        try:
            self._init_browser()
            
            # 访问新闻页面
            self.page.goto('https://news.qq.com/', wait_until='networkidle')
            time.sleep(2)
            
            # 提取热门新闻
            items = self.page.query_selector_all('.list .title a, .news-list h3 a, [class*="hot"] a')
            
            results = []
            for idx, item in enumerate(items[:limit], 1):
                title = item.inner_text().strip()
                if title and len(title) > 5:
                    analysis = f"排名:{idx}"
                    results.append(self._create_result(title, title, analysis))
            
            return pd.DataFrame(results)
            
        except Exception as e:
            print(f"腾讯新闻错误: {e}")
            return self._empty_df()
        finally:
            self.close()


# ==================== 今日头条 (Playwright) ====================
class ToutiaoHotSearch(PlaywrightBaseHotSearch):
    """今日头条 - Playwright版"""
    PLATFORM = "今日头条"
    
    def fetch(self, limit: int = 100) -> pd.DataFrame:
        try:
            self._init_browser()
            
            # 访问热榜页面
            self.page.goto('https://www.toutiao.com/hot/', wait_until='networkidle')
            time.sleep(3)
            
            # 提取热榜数据
            items = self.page.query_selector_all('.hot-list-item .title, [class*="hot"] h3, [class*="hot"] .title')
            
            results = []
            for idx, item in enumerate(items[:limit], 1):
                title = item.inner_text().strip()
                if title:
                    analysis = f"排名:{idx}"
                    results.append(self._create_result(title, title, analysis))
            
            # 如果上面没获取到，尝试从页面数据提取
            if not results:
                data = self.page.evaluate("""() => {
                    if (window._SSR_HYDRATED_DATA) {
                        return window._SSR_HYDRATED_DATA;
                    }
                    return null;
                }""")
                
                if data:
                    # 递归查找热榜
                    def find_hot(obj, depth=0):
                        if depth > 5:
                            return None
                        if isinstance(obj, dict):
                            for k, v in obj.items():
                                if k in ['hotList', 'hot_list', 'list'] and isinstance(v, list):
                                    return v
                                result = find_hot(v, depth+1)
                                if result:
                                    return result
                        return None
                    
                    hot_list = find_hot(data)
                    if hot_list:
                        for idx, item in enumerate(hot_list[:limit], 1):
                            title = item.get('Title', '') or item.get('title', '') or item.get('word', '')
                            if title:
                                analysis = f"排名:{idx}"
                                results.append(self._create_result(title, title, analysis))
            
            return pd.DataFrame(results)
            
        except Exception as e:
            print(f"今日头条错误: {e}")
            return self._empty_df()
        finally:
            self.close()


# ==================== 快手 (Playwright) ====================
class KuaishouHotSearch(PlaywrightBaseHotSearch):
    """快手 - Playwright版"""
    PLATFORM = "快手"
    
    def fetch(self, limit: int = 100) -> pd.DataFrame:
        try:
            self._init_browser()
            
            # 访问主页
            self.page.goto('https://www.kuaishou.com/', wait_until='networkidle')
            time.sleep(3)
            
            # 提取热搜
            items = self.page.query_selector_all('.hot-search-item, [class*="hot"] a, [class*="search"] a')
            
            results = []
            for idx, item in enumerate(items[:limit], 1):
                title = item.inner_text().strip()
                if title:
                    analysis = f"排名:{idx}"
                    results.append(self._create_result(title, title, analysis))
            
            # 尝试从页面数据提取
            if not results:
                data = self.page.evaluate("""() => {
                    if (window.__INITIAL_STATE__) {
                        return window.__INITIAL_STATE__;
                    }
                    return null;
                }""")
                
                if data:
                    def find_hot(obj, depth=0):
                        if depth > 5:
                            return None
                        if isinstance(obj, dict):
                            for k, v in obj.items():
                                if k in ['hotSearch', 'hot_search', 'searchHots'] and isinstance(v, list):
                                    return v
                                result = find_hot(v, depth+1)
                                if result:
                                    return result
                        return None
                    
                    hot_list = find_hot(data)
                    if hot_list:
                        for idx, item in enumerate(hot_list[:limit], 1):
                            keyword = item.get('keyword', '') or item.get('name', '')
                            if keyword:
                                analysis = f"排名:{idx}"
                                results.append(self._create_result(keyword, keyword, analysis))
            
            return pd.DataFrame(results)
            
        except Exception as e:
            print(f"快手错误: {e}")
            return self._empty_df()
        finally:
            self.close()


# ==================== 搜狐 (Playwright) ====================
class SohuHotSearch(PlaywrightBaseHotSearch):
    """搜狐 - Playwright版"""
    PLATFORM = "搜狐"
    
    def fetch(self, limit: int = 100) -> pd.DataFrame:
        try:
            self._init_browser()
            
            # 访问主页
            self.page.goto('https://www.sohu.com/', wait_until='networkidle')
            time.sleep(2)
            
            # 提取热门新闻
            items = self.page.query_selector_all('.news-list .title a, .feed-list .title a, .hot-news a')
            
            results = []
            for idx, item in enumerate(items[:limit], 1):
                title = item.inner_text().strip()
                if title and len(title) > 5:
                    analysis = f"排名:{idx}"
                    results.append(self._create_result(title, title, analysis))
            
            return pd.DataFrame(results)
            
        except Exception as e:
            print(f"搜狐错误: {e}")
            return self._empty_df()
        finally:
            self.close()


# ==================== 统一入口 ====================
class HotSearchAPI:
    """热搜API统一入口"""
    
    @staticmethod
    def smzdm(limit: int = 100, headless: bool = True) -> pd.DataFrame:
        crawler = SmzdmHotSearch(headless=headless)
        try:
            return crawler.fetch(limit)
        finally:
            crawler.close()
    
    @staticmethod
    def qq_news(limit: int = 100, headless: bool = True) -> pd.DataFrame:
        crawler = QQNewsHotSearch(headless=headless)
        try:
            return crawler.fetch(limit)
        finally:
            crawler.close()
    
    @staticmethod
    def toutiao(limit: int = 100, headless: bool = True) -> pd.DataFrame:
        crawler = ToutiaoHotSearch(headless=headless)
        try:
            return crawler.fetch(limit)
        finally:
            crawler.close()
    
    @staticmethod
    def kuaishou(limit: int = 100, headless: bool = True) -> pd.DataFrame:
        crawler = KuaishouHotSearch(headless=headless)
        try:
            return crawler.fetch(limit)
        finally:
            crawler.close()
    
    @staticmethod
    def sohu(limit: int = 100, headless: bool = True) -> pd.DataFrame:
        crawler = SohuHotSearch(headless=headless)
        try:
            return crawler.fetch(limit)
        finally:
            crawler.close()


if __name__ == '__main__':
    import sys
    
    platform = sys.argv[1] if len(sys.argv) > 1 else 'all'
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    
    platforms = {
        'smzdm': ('什么值得买', HotSearchAPI.smzdm),
        'qq_news': ('腾讯新闻', HotSearchAPI.qq_news),
        'toutiao': ('今日头条', HotSearchAPI.toutiao),
        'kuaishou': ('快手', HotSearchAPI.kuaishou),
        'sohu': ('搜狐', HotSearchAPI.sohu),
    }
    
    if platform == 'all':
        print("=" * 60)
        print("Playwright修复平台测试")
        print("=" * 60)
        
        for key, (name, func) in platforms.items():
            print("\n[测试] %s..." % name)
            try:
                df = func(limit, headless=True)
                print("获取到 %d 条" % len(df))
                if not df.empty:
                    print(df.head(3).to_string(index=False))
            except Exception as e:
                print("错误: %s" % str(e)[:50])
    else:
        if platform in platforms:
            name, func = platforms[platform]
            df = func(limit, headless=False)  # 显示浏览器便于调试
            print("获取到 %d 条" % len(df))
            print(df.to_string(index=False))
        else:
            print("未知平台: %s" % platform)
            print("可用: %s" % ', '.join(platforms.keys()))
