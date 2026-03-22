"""
热搜数据采集框架 - 稳定版
支持9个平台：抖音、新浪、百度、B站、知乎日报、掘金、CSDN、IT之家、网易新闻

使用方式：
    from exe.realtime.news_collection.hot_api import HotSearchAPI
    
    # 采集所有平台
    results = HotSearchAPI.fetch_all(100)
"""
from loguru import logger
from gs2026.utils import mysql_util, config_util
from gs2026.utils.pandas_display_config import set_pandas_display_options
from gs2026.constants import FIREFOX_1408, CHROME_1208

import hashlib
import sys
import time
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Dict

import pandas as pd
import requests
from bs4 import BeautifulSoup

# 设置UTF-8输出
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')


def generate_content_hash(content: str) -> str:
    """生成内容hash（content的MD5）"""
    return hashlib.md5(content.encode('utf-8')).hexdigest()


class BaseHotSearch(ABC):
    PLATFORM = ""
    
    def __init__(self, timeout: int = 10):
        self.timeout = timeout
        self.session = requests.Session()
        self._init_headers()
    
    def _init_headers(self):
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json, text/plain, */*',
        })
    
    @abstractmethod
    def fetch(self, limit: int = 100) -> pd.DataFrame:
        pass
    
    def _create_result(self, title: str, content: str) -> Dict:
        """
        创建标准结果
        content: 优先使用具体内容，没有则用title
        content_hash: content的MD5
        """
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        if not content:
            content = title
        content_hash = generate_content_hash(content)
        return {
            'title': title,
            'publish_time': current_time,
            'content': content,
            'source': self.PLATFORM,
            'content_hash': content_hash,
            'analysis': ""
        }
    
    def _empty_df(self) -> pd.DataFrame:
        return pd.DataFrame(columns=['title', 'publish_time', 'content', 'source', 'content_hash', 'analysis'])
    
    def close(self):
        self.session.close()


# ==================== 1. 抖音 ====================
class DouyinHotSearch(BaseHotSearch):
    PLATFORM = "抖音"
    API_URL = "https://www.douyin.com/aweme/v1/web/hot/search/list/"
    
    def _init_headers(self):
        super()._init_headers()
        self.session.headers.update({'Referer': 'https://www.douyin.com/hot'})
    
    def fetch(self, limit: int = 100) -> pd.DataFrame:
        try:
            self.session.get('https://www.douyin.com/', timeout=self.timeout)
            time.sleep(0.3)
            
            params = {
                'device_platform': 'webapp',
                'aid': '6383',
                'channel': 'channel_pc_web',
                'detail_list': '1',
                'count': min(limit, 50),
                'cursor': 0,
            }
            
            response = self.session.get(self.API_URL, params=params, timeout=self.timeout)
            
            if response.status_code != 200:
                return self._empty_df()
            
            data = response.json()
            
            if data.get('status_code') != 0:
                return self._empty_df()
            
            word_list = data.get('data', {}).get('word_list', [])
            
            results = []
            for item in word_list[:limit]:
                title = item.get('word', '').strip()
                if not title:
                    continue
                
                word_cover = item.get('word_cover', {})
                desc = word_cover.get('desc', '')
                content = desc if desc else title
                
                results.append(self._create_result(title, content))
            
            return pd.DataFrame(results)
            
        except Exception:
            return self._empty_df()


# ==================== 2. 新浪 ====================
class SinaHotSearch(BaseHotSearch):
    PLATFORM = "新浪"
    API_URL = "https://weibo.com/ajax/side/hotSearch"
    
    def _init_headers(self):
        super()._init_headers()
        self.session.headers.update({
            'Referer': 'https://weibo.com/hot/search',
            'X-Requested-With': 'XMLHttpRequest',
        })
    
    def fetch(self, limit: int = 100) -> pd.DataFrame:
        try:
            response = self.session.get(self.API_URL, timeout=self.timeout)
            
            if response.status_code != 200:
                return self._empty_df()
            
            data = response.json()
            
            realtime_list = data.get('data', {}).get('realtime', [])
            
            results = []
            for item in realtime_list[:limit]:
                title = item.get('word', '').strip() or item.get('word_scheme', '').strip()
                if not title:
                    continue
                
                note = item.get('note', '') or item.get('subject_label', '')
                content = note if note else title
                
                results.append(self._create_result(title, content))
            
            return pd.DataFrame(results)
            
        except Exception:
            return self._empty_df()


# ==================== 3. 百度 ====================
class BaiduHotSearch(BaseHotSearch):
    PLATFORM = "百度"
    API_URL = "https://top.baidu.com/api/board"
    
    def _init_headers(self):
        super()._init_headers()
        self.session.headers.update({'Referer': 'https://top.baidu.com/board'})
    
    def fetch(self, limit: int = 100) -> pd.DataFrame:
        try:
            params = {'platform': 'wise', 'tab': 'realtime'}
            
            response = self.session.get(self.API_URL, params=params, timeout=self.timeout)
            
            if response.status_code != 200:
                return self._empty_df()
            
            data = response.json()
            
            cards = data.get('data', {}).get('cards', [])
            if not cards:
                return self._empty_df()
            
            first_card = cards[0]
            card_content = first_card.get('content', [])
            if not card_content:
                return self._empty_df()
            
            content_list = card_content[0].get('content', [])
            
            results = []
            for item in content_list[:limit]:
                title = item.get('word', '').strip()
                if not title:
                    continue
                
                desc = item.get('desc', '')
                content = desc if desc else title
                
                results.append(self._create_result(title, content))
            
            return pd.DataFrame(results)
            
        except Exception:
            return self._empty_df()


# ==================== 4. B站 ====================
class BilibiliHotSearch(BaseHotSearch):
    PLATFORM = "B站"
    API_URL = "https://api.bilibili.com/x/web-interface/search/square"
    
    def _init_headers(self):
        super()._init_headers()
        self.session.headers.update({'Referer': 'https://search.bilibili.com/'})
    
    def fetch(self, limit: int = 100) -> pd.DataFrame:
        try:
            params = {'limit': limit}
            
            response = self.session.get(self.API_URL, params=params, timeout=self.timeout)
            
            if response.status_code != 200:
                return self._empty_df()
            
            data = response.json()
            
            if data.get('code') != 0:
                return self._empty_df()
            
            trending = data.get('data', {}).get('trending', {})
            items = trending.get('list', [])
            
            results = []
            for item in items[:limit]:
                title = item.get('keyword', '').strip() or item.get('show_name', '').strip()
                if not title:
                    continue
                
                results.append(self._create_result(title, title))
            
            return pd.DataFrame(results)
            
        except Exception:
            return self._empty_df()


# ==================== 5. 知乎日报 ====================
class ZhihuDailyHotSearch(BaseHotSearch):
    PLATFORM = "知乎日报"
    API_URL = "https://news-at.zhihu.com/api/4/news/latest"
    
    def _init_headers(self):
        super()._init_headers()
        self.session.headers.update({'Referer': 'https://daily.zhihu.com/'})
    
    def fetch(self, limit: int = 100) -> pd.DataFrame:
        try:
            response = self.session.get(self.API_URL, timeout=self.timeout)
            
            if response.status_code != 200:
                return self._empty_df()
            
            data = response.json()
            
            stories = data.get('stories', [])
            
            results = []
            for item in stories[:limit]:
                title = item.get('title', '').strip()
                
                if not title:
                    continue
                
                hint = item.get('hint', '')
                content = hint if hint else title
                
                results.append(self._create_result(title, content))
            
            return pd.DataFrame(results)
            
        except Exception:
            return self._empty_df()


# ==================== 6. 掘金 ====================
class JuejinHotSearch(BaseHotSearch):
    PLATFORM = "掘金"
    API_URL = "https://api.juejin.cn/content_api/v1/content/article_rank"
    
    def _init_headers(self):
        super()._init_headers()
        self.session.headers.update({'Referer': 'https://juejin.cn/'})
    
    def fetch(self, limit: int = 100) -> pd.DataFrame:
        try:
            params = {
                'category_id': '1',
                'type': 'hot',
            }
            
            response = self.session.get(self.API_URL, params=params, timeout=self.timeout)
            
            if response.status_code != 200:
                return self._empty_df()
            
            data = response.json()
            
            if data.get('err_no') != 0:
                return self._empty_df()
            
            items = data.get('data', [])
            
            results = []
            for item in items[:limit]:
                content_data = item.get('content', {})
                title = content_data.get('title', '').strip()
                
                if not title:
                    continue
                
                brief = content_data.get('brief', '')
                content = brief if brief else title
                
                results.append(self._create_result(title, content))
            
            return pd.DataFrame(results)
            
        except Exception:
            return self._empty_df()


# ==================== 7. CSDN ====================
class CSDNHotSearch(BaseHotSearch):
    PLATFORM = "CSDN"
    API_URL = "https://blog.csdn.net/phoenix/web/blog/hot-rank"
    
    def _init_headers(self):
        super()._init_headers()
        self.session.headers.update({'Referer': 'https://blog.csdn.net/'})
    
    def fetch(self, limit: int = 100) -> pd.DataFrame:
        try:
            params = {'page': '0', 'size': limit}
            
            response = self.session.get(self.API_URL, params=params, timeout=self.timeout)
            
            if response.status_code != 200:
                return self._empty_df()
            
            data = response.json()
            
            if data.get('code') != 200:
                return self._empty_df()
            
            items = data.get('data', [])
            
            results = []
            for item in items[:limit]:
                title = item.get('articleTitle', '').strip() or item.get('title', '').strip()
                
                if not title:
                    continue
                
                summary = item.get('summary', '') or item.get('description', '')
                content = summary if summary else title
                
                results.append(self._create_result(title, content))
            
            return pd.DataFrame(results)
            
        except Exception:
            return self._empty_df()


# ==================== 8. IT之家 ====================
class IthomeHotSearch(BaseHotSearch):
    PLATFORM = "IT之家"
    API_URL = "https://api.ithome.com/json/newslist/news"
    
    def _init_headers(self):
        super()._init_headers()
        self.session.headers.update({'Referer': 'https://www.ithome.com/'})
    
    def fetch(self, limit: int = 100) -> pd.DataFrame:
        try:
            params = {'r': '0'}
            
            response = self.session.get(self.API_URL, params=params, timeout=self.timeout)
            
            if response.status_code != 200:
                return self._empty_df()
            
            data = response.json()
            
            newslist = data.get('newslist', [])
            
            results = []
            for item in newslist[:limit]:
                title = item.get('title', '').strip()
                
                if not title:
                    continue
                
                description = item.get('description', '')
                content = description if description else title
                
                results.append(self._create_result(title, content))
            
            return pd.DataFrame(results)
            
        except Exception:
            return self._empty_df()


# ==================== 9. 网易新闻 ====================
class NeteaseHotSearch(BaseHotSearch):
    PLATFORM = "网易新闻"
    
    def fetch(self, limit: int = 100) -> pd.DataFrame:
        try:
            self.session.headers.update({'Referer': 'https://news.163.com/'})
            
            response = self.session.get('https://news.163.com/', timeout=self.timeout)
            
            if response.status_code != 200:
                return self._empty_df()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            selectors = [
                '.news_title a',
                '.hidden-title a',
                '.mod_top_news2 li a',
                '.news-list h3 a',
            ]
            
            results = []
            for selector in selectors:
                items = soup.select(selector)
                if items:
                    for item in items[:limit]:
                        title = item.get_text().strip()
                        if title and len(title) > 5:
                            results.append(self._create_result(title, title))
                    break
            
            return pd.DataFrame(results)
            
        except Exception:
            return self._empty_df()


# ==================== 统一入口 ====================
class HotSearchAPI:
    """热搜API统一入口"""
    
    @staticmethod
    def douyin(limit: int = 100) -> pd.DataFrame:
        crawler = DouyinHotSearch()
        try:
            return crawler.fetch(limit)
        finally:
            crawler.close()
    
    @staticmethod
    def sina(limit: int = 100) -> pd.DataFrame:
        crawler = SinaHotSearch()
        try:
            return crawler.fetch(limit)
        finally:
            crawler.close()
    
    @staticmethod
    def baidu(limit: int = 100) -> pd.DataFrame:
        crawler = BaiduHotSearch()
        try:
            return crawler.fetch(limit)
        finally:
            crawler.close()
    
    @staticmethod
    def bilibili(limit: int = 100) -> pd.DataFrame:
        crawler = BilibiliHotSearch()
        try:
            return crawler.fetch(limit)
        finally:
            crawler.close()
    
    @staticmethod
    def zhihu_daily(limit: int = 100) -> pd.DataFrame:
        crawler = ZhihuDailyHotSearch()
        try:
            return crawler.fetch(limit)
        finally:
            crawler.close()
    
    @staticmethod
    def juejin(limit: int = 100) -> pd.DataFrame:
        crawler = JuejinHotSearch()
        try:
            return crawler.fetch(limit)
        finally:
            crawler.close()
    
    @staticmethod
    def csdn(limit: int = 100) -> pd.DataFrame:
        crawler = CSDNHotSearch()
        try:
            return crawler.fetch(limit)
        finally:
            crawler.close()
    
    @staticmethod
    def ithome(limit: int = 100) -> pd.DataFrame:
        crawler = IthomeHotSearch()
        try:
            return crawler.fetch(limit)
        finally:
            crawler.close()
    
    @staticmethod
    def netease(limit: int = 100) -> pd.DataFrame:
        crawler = NeteaseHotSearch()
        try:
            return crawler.fetch(limit)
        finally:
            crawler.close()
    
    @staticmethod
    def fetch_all(limit: int = 100) -> Dict[str, pd.DataFrame]:
        return {
            '抖音': HotSearchAPI.douyin(limit),
            '新浪': HotSearchAPI.sina(limit),
            '百度': HotSearchAPI.baidu(limit),
            'B站': HotSearchAPI.bilibili(limit),
            '知乎日报': HotSearchAPI.zhihu_daily(limit),
            '掘金': HotSearchAPI.juejin(limit),
            'CSDN': HotSearchAPI.csdn(limit),
            'IT之家': HotSearchAPI.ithome(limit),
            '网易新闻': HotSearchAPI.netease(limit),
        }


if __name__ == '__main__':
    print("=" * 70)
    print("热搜数据采集 - 9个平台")
    print("=" * 70)
    
    results = HotSearchAPI.fetch_all(10)
    
    for name, df in results.items():
        print("\n" + "=" * 60)
        print(f"【{name}】{len(df)}条")
        print("=" * 60)
        if not df.empty:
            for idx, row in df.head(3).iterrows():
                print(f"\n[{idx + 1}]")
                print(f"  title: {row['title'][:50]}")
                print(f"  content: {row['content'][:50]}")
                print(f"  content_hash: {row['content_hash'][:16]}...")
                print(f"  analysis: '{row['analysis']}'")
        else:
            print("(无数据)")
    
    print("\n" + "=" * 70)
