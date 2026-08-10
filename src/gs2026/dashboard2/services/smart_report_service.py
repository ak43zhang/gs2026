"""
智能报告服务 - 基于AI分析结果生成重大利好日报
"""
import os
import re
from pathlib import Path
from datetime import datetime, date
from typing import List, Dict, Any, Tuple, Optional
import json

from sqlalchemy import create_engine, text as sql_text
from loguru import logger

from gs2026.utils import config_util
from gs2026.analysis.worker.message.huoshanfangzhou.trading_day_util import get_start_end
from gs2026.analysis.worker.message.huoshanfangzhou.volcengine_client import volcengine_analysis
from gs2026.analysis.worker.message.deepseek.deepseek_analysis_event_driven import deepseek_analysis
from gs2026.analysis.worker.message.deepseek.proxy import ensure_proxy_daemon
from gs2026.analysis.worker.message.prompts import GLOBAL_MARKET_ANALYSIS_PROMPT

from gs2026.analysis.worker.message.prompts import GLOBAL_MARKET_ANALYSIS_PROMPT


class SmartReportService:
    """智能报告生成服务"""

    REPORT_DIR = Path("G:/report/智能报告")
    REPORT_LIMITS = {
        'domain': 60,      # 领域分析条数
        'news': 30,        # 新闻分析条数
        'notice': 10,      # 公告分析条数
        'ztb': -1,         # 涨停分析条数（-1=全部）
    }

    def __init__(self):
        self._ensure_dir()

    def _ensure_dir(self):
        """确保报告目录存在"""
        self.REPORT_DIR.mkdir(parents=True, exist_ok=True)

    def _get_engine(self):
        """获取数据库连接"""
        url = config_util.get_config("common.url")
        return create_engine(url, pool_recycle=3600, pool_pre_ping=True)

    def generate_report(self, target_date: str = None) -> Dict[str, Any]:
        """生成智能日报

        Args:
            target_date: 目标日期 'YYYY-MM-DD'，默认当天

        Returns:
            {success, path, stats, headline_count}
        """
        if target_date is None:
            target_date = date.today().strftime('%Y-%m-%d')

        start_date, end_date = get_start_end(target_date)
        engine = self._get_engine()

        # 查询各表
        domain_data = self._query_domain(engine, start_date, end_date)
        news_data = self._query_news(engine, start_date, end_date)
        notice_data = self._query_notice(engine, start_date, end_date)
        ztb_data = self._query_ztb(engine, start_date, end_date)

        # 构建股票代码→名称映射（供渲染使用）
        self._stock_name_map = self._build_stock_name_map(engine, domain_data, news_data)

        # 合并所有数据用于头条摘要
        all_items = self._merge_for_headlines(domain_data, news_data, notice_data, ztb_data)

        # 分级
        domain_graded = self._grade(domain_data, 'composite_score')
        news_graded = self._grade(news_data, 'composite_score')
        notice_graded = self._grade(notice_data, 'overnight_score')
        ztb_graded = self._grade_ztb(ztb_data)

        # 头条摘要（取TOP 10）
        headlines = all_items[:10]

        # 板块热力图
        sector_heatmap = self._build_sector_heatmap(domain_data, news_data, ztb_data)

        # 概念热力图
        concept_heatmap = self._build_concept_heatmap(domain_data, news_data, ztb_data)

        # 盘前全球市场AI分析
        global_market_data = self._generate_global_market_analysis()

        # 生成HTML
        html = self._render_html(
            target_date=target_date,
            start_date=start_date,
            end_date=end_date,
            headlines=headlines,
            domain=domain_graded,
            news=news_graded,
            notice=notice_graded,
            ztb=ztb_graded,
            sector_heatmap=sector_heatmap,
            concept_heatmap=concept_heatmap,
            global_market=global_market_data,
            stats={
                'domain': len(domain_data),
                'news': len(news_data),
                'notice': len(notice_data),
                'ztb': len(ztb_data),
            }
        )

        # 保存文件
        file_path = self.REPORT_DIR / f"智能日报_{target_date}.html"
        file_path.write_text(html, encoding='utf-8')
        logger.info(f"[智能报告] 生成完成: {file_path}")

        return {
            'success': True,
            'path': str(file_path),
            'filename': file_path.name,
            'stats': {'domain': len(domain_data), 'news': len(news_data),
                      'notice': len(notice_data), 'ztb': len(ztb_data)},
            'headline_count': len(headlines),
            'global_market_generated': global_market_data is not None,
        }

    # ============ 数据查询 ============

    def _query_domain(self, engine, start: str, end: str) -> List[Dict]:
        """领域分析：利好+重大+超预期利好，按综合分排序
        时间范围：上一交易日收盘后(15:00) ~ 下一交易日开盘前(09:30)
        """
        limit = self.REPORT_LIMITS['domain']
        sql = f"""
            SELECT main_area, child_area, event_time, event_source, key_event,
                   brief_desc, importance_score, business_impact_score,
                   composite_score, news_size, news_type,
                   sectors, concepts, stock_codes, reason_analysis, deep_analysis,
                   expectation_type, expectation_analysis
            FROM analysis_domain_detail_2026
            WHERE news_type='利好' AND news_size='重大'
              AND expectation_type = '超预期利好'
              AND event_time >= '{start} 15:00:00' AND event_time < '{end} 09:30:00'
            ORDER BY composite_score DESC
            LIMIT {limit}
        """
        with engine.connect() as conn:
            import pandas as pd
            df = pd.read_sql(sql, conn)
        return df.to_dict('records')

    def _query_news(self, engine, start: str, end: str) -> List[Dict]:
        """新闻分析：利好+分数>=50+超预期利好，按综合分排序"""
        limit = self.REPORT_LIMITS['news']
        sql = f"""
            SELECT source_table, title, content, publish_time, source,
                   importance_score, business_impact_score, composite_score,
                   news_size, news_type, sectors, concepts, leading_stocks,
                   sector_details, deep_analysis,
                   expectation_type, expectation_analysis
            FROM analysis_news_detail_2026
            WHERE news_type='利好' AND composite_score >= 50
              AND expectation_type = '超预期利好'
              AND publish_time >= '{start}' AND publish_time <= '{end}'
            ORDER BY composite_score DESC
            LIMIT {limit}
        """
        with engine.connect() as conn:
            import pandas as pd
            df = pd.read_sql(sql, conn)
        return df.to_dict('records')

    def _query_notice(self, engine, start: str, end: str) -> List[Dict]:
        """公告分析：overnight_score>=70"""
        limit = self.REPORT_LIMITS['notice']
        sql = f"""
            SELECT content_hash, stock_code, stock_name, notice_date,
                   notice_title, notice_content, risk_level, notice_type,
                   judgment_basis, key_points, short_term_impact,
                   medium_term_impact, risk_score, type_score, overnight_score,
                   market_expectation, open_prediction, duration, overnight_strategy
            FROM analysis_notice_detail_2026
            WHERE overnight_score >= 70
              AND notice_date >= '{start}' AND notice_date <= '{end}'
            ORDER BY overnight_score DESC
            LIMIT {limit}
        """
        with engine.connect() as conn:
            import pandas as pd
            df = pd.read_sql(sql, conn)
        return df.to_dict('records')

    def _query_ztb(self, engine, start: str, end: str) -> List[Dict]:
        """涨停分析：has_expect=1，全部"""
        sql = f"""
            SELECT content_hash, stock_name, stock_code, trade_date,
                   zt_time, stock_nature, lhb_analysis, sector_msg,
                   concept_msg, leading_stock_msg, influence_msg,
                   expect_msg, deep_analysis, sectors, concepts,
                   leading_stocks, has_expect, continuity, zt_time_range
            FROM analysis_ztb_detail_2026
            WHERE has_expect = 1
              AND trade_date >= '{start}' AND trade_date <= '{end}'
            ORDER BY continuity DESC,
                     CASE zt_time_range WHEN 'early' THEN 1 WHEN 'midday' THEN 2 ELSE 3 END
        """
        with engine.connect() as conn:
            import pandas as pd
            df = pd.read_sql(sql, conn)
        return df.to_dict('records')

    def _build_stock_name_map(self, engine, *data_lists) -> Dict[str, str]:
        """从所有数据中提取股票代码，批量查询名称映射"""
        all_codes = set()
        for data_list in data_lists:
            for d in data_list:
                codes = self._parse_list(d.get('stock_codes') or d.get('leading_stocks'))
                all_codes.update(c for c in codes if c and len(c) == 6 and c.isdigit())
        if not all_codes:
            return {}
        codes_str = ','.join(f"'{c}'" for c in all_codes)
        sql = f"SELECT stock_code, short_name FROM data_agdm WHERE stock_code IN ({codes_str})"
        try:
            with engine.connect() as conn:
                import pandas as pd
                df = pd.read_sql(sql, conn)
            return dict(zip(df['stock_code'].astype(str), df['short_name']))
        except Exception as e:
            logger.warning(f"股票名称查询失败: {e}")
            return {}

    # ============ 数据处理 ============

    def _merge_for_headlines(self, domain, news, notice, ztb) -> List[Dict]:
        """合并所有数据，取TOP 10头条摘要"""
        items = []

        for d in domain:
            items.append({
                'source': 'domain',
                'source_label': f'[{d.get("main_area", "")}/{d.get("child_area", "")}]',
                'title': d.get('key_event', '')[:80],
                'score': d.get('composite_score', 0),
                'detail': d.get('reason_analysis', '')[:100],
                'time': d.get('event_time', ''),
            })
        for n in news:
            items.append({
                'source': 'news',
                'source_label': f'[新闻/{n.get("source", "")}]',
                'title': n.get('title', '')[:80],
                'score': n.get('composite_score', 0),
                'detail': (n.get('content', '') or '')[:100],
                'time': n.get('publish_time', ''),
            })
        for nt in notice:
            items.append({
                'source': 'notice',
                'source_label': f'[公告/{nt.get("stock_name", "")}]',
                'title': nt.get('notice_title', '')[:80],
                'score': nt.get('overnight_score', 0),
                'detail': ' '.join(nt.get('key_points', []) or [])[:100],
                'time': nt.get('notice_date', ''),
            })
        for z in ztb:
            items.append({
                'source': 'ztb',
                'source_label': f'[涨停/{z.get("stock_name", "")}]',
                'title': f'{z.get("stock_name", "")} {z.get("stock_code", "")} 涨停',
                'score': z.get('continuity', 0) * 50,
                'detail': ' '.join((z.get('sector_msg', '') or '')[:60] for _ in [1]),
                'time': z.get('trade_date', ''),
            })

        # 统一按score排序取TOP 10
        items.sort(key=lambda x: x['score'], reverse=True)
        return items[:10]

    def _grade(self, items: List[Dict], score_field: str) -> List[Dict]:
        """按评分排名分级：TOP 1-10, 重要 11-30, 关注 31+"""
        sorted_items = sorted(items, key=lambda x: x.get(score_field, 0), reverse=True)
        for i, item in enumerate(sorted_items):
            if i < 10:
                item['grade'] = 'top'
            elif i < 30:
                item['grade'] = 'important'
            else:
                item['grade'] = 'watch'
            item['_rank'] = i + 1
        return sorted_items

    def _grade_ztb(self, items: List[Dict]) -> List[Dict]:
        """涨停分级：全部详细展示，按连板数+封板时段排序"""
        for i, item in enumerate(items):
            item['grade'] = 'top' if i < 10 else ('important' if i < 30 else 'watch')
            item['_rank'] = i + 1
        return items

    def _build_sector_heatmap(self, domain, news, ztb) -> List[Tuple[str, int]]:
        """板块热力图：跨3张表统计板块频次"""
        from collections import Counter
        counter = Counter()

        for d in domain:
            sectors = d.get('sectors') or '[]'
            try:
                for s in json.loads(sectors) if isinstance(sectors, str) else sectors:
                    counter[s] += 3  # 领域分析权重3
            except (json.JSONDecodeError, TypeError):
                pass

        for n in news:
            sectors = n.get('sectors') or '[]'
            try:
                for s in json.loads(sectors) if isinstance(sectors, str) else sectors:
                    counter[s] += 2  # 新闻权重2
            except (json.JSONDecodeError, TypeError):
                pass

        for z in ztb:
            sectors = z.get('sectors') or '[]'
            try:
                for s in json.loads(sectors) if isinstance(sectors, str) else sectors:
                    counter[s] += 1  # 涨停权重1
            except (json.JSONDecodeError, TypeError):
                pass

        return counter.most_common(20)

    def _build_concept_heatmap(self, domain, news, ztb) -> List[Tuple[str, int]]:
        """概念热力图：跨3张表统计概念频次"""
        from collections import Counter
        counter = Counter()

        for d in domain:
            concepts = d.get('concepts') or '[]'
            try:
                for c in json.loads(concepts) if isinstance(concepts, str) else concepts:
                    counter[c] += 3
            except (json.JSONDecodeError, TypeError):
                pass

        for n in news:
            concepts = n.get('concepts') or '[]'
            try:
                for c in json.loads(concepts) if isinstance(concepts, str) else concepts:
                    counter[c] += 2
            except (json.JSONDecodeError, TypeError):
                pass

        for z in ztb:
            concepts = z.get('concepts') or '[]'
            try:
                for c in json.loads(concepts) if isinstance(concepts, str) else concepts:
                    counter[c] += 1
            except (json.JSONDecodeError, TypeError):
                pass

        return counter.most_common(20)

    # ============ HTML生成 ============

    def _render_html(self, **kwargs) -> str:
        """渲染完整HTML报告"""
        return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>GS2026 智能日报 {kwargs['target_date']}</title>
<style>
{self._get_css()}
</style>
</head>
<body>
{self._get_nav(**kwargs)}
<main id="report-content">
{self._get_cover(**kwargs)}
{self._get_overview(**kwargs)}
{self._get_global_market_section(**kwargs)}
{self._get_headlines(**kwargs)}
{self._get_domain_section(**kwargs)}
{self._get_news_section(**kwargs)}
{self._get_notice_section(**kwargs)}
{self._get_ztb_section(**kwargs)}
{self._get_sector_heatmap(**kwargs)}
{self._get_concept_heatmap(**kwargs)}
</main>
{self._get_search_js()}
</body>
</html>"""

    def _get_css(self) -> str:
        return """
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, "Microsoft YaHei", sans-serif; background: #f5f6fa; color: #2d3142; line-height: 1.7; padding: 30px; }
        .cover { text-align: center; padding: 40px 20px; border-bottom: 3px solid #667eea; margin-bottom: 30px; }
        .cover h1 { font-size: 32px; color: #667eea; margin-bottom: 10px; }
        .cover .subtitle { font-size: 16px; color: #666; }
        .overview { display: flex; gap: 12px; margin-bottom: 30px; flex-wrap: wrap; }
        .ov-card { flex: 1; min-width: 140px; background: #fff; border-radius: 10px; padding: 18px; text-align: center; box-shadow: 0 2px 8px rgba(0,0,0,0.06); }
        .ov-num { font-size: 28px; font-weight: 700; color: #667eea; }
        .ov-label { font-size: 13px; color: #999; margin-top: 4px; }
        .headlines { background: #fffbe6; border-radius: 10px; padding: 20px; margin-bottom: 30px; border-left: 5px solid #faad14; }
        .headlines h2 { color: #d48806; margin-bottom: 14px; font-size: 18px; }
        .hl-item { padding: 6px 0; border-bottom: 1px dashed #f0e6c8; }
        .hl-item:last-child { border-bottom: none; }
        .hl-rank { display: inline-block; width: 24px; height: 24px; background: #faad14; color: #fff; border-radius: 50%; text-align: center; line-height: 24px; font-size: 12px; font-weight: 700; margin-right: 8px; }
        .section { margin-bottom: 35px; }
        .section-title { font-size: 20px; font-weight: 700; margin-bottom: 18px; padding-bottom: 8px; border-bottom: 2px solid #667eea; }
        .grade-top { border-left: 4px solid #e74c3c; }
        .grade-important { border-left: 4px solid #f39c12; }
        .grade-watch { border-left: 4px solid #3498db; }
        .card { background: #fff; border-radius: 8px; padding: 18px; margin-bottom: 14px; box-shadow: 0 1px 4px rgba(0,0,0,0.06); }
        .card-top { background: #fff5f5; }
        .card-important { background: #fffbf0; }
        .card-watch { background: #f8faff; padding: 10px 14px; }
        .card-title { font-size: 15px; font-weight: 600; margin-bottom: 6px; }
        .card-meta { font-size: 12px; color: #999; margin-bottom: 8px; }
        .tag { display: inline-block; background: #e8ecf7; color: #667eea; padding: 2px 8px; border-radius: 4px; font-size: 12px; margin: 2px 3px; }
        .tag-red { background: #fde8e8; color: #e74c3c; }
        .tag-orange { background: #fef3e2; color: #f39c12; }
        .tag-blue { background: #e8f0fe; color: #3498db; }
        .score-badge { display: inline-block; background: #667eea; color: #fff; padding: 2px 10px; border-radius: 12px; font-size: 13px; font-weight: 600; margin-left: 8px; }
        .card-body { font-size: 14px; color: #444; margin-top: 8px; }
        .card-body strong { color: #2d3142; }
        .depth-score { margin-top: 8px; }
        .depth-item { font-size: 13px; padding: 3px 0; }
        .depth-bar { display: inline-block; width: 60px; height: 8px; background: #e8ecf7; border-radius: 4px; vertical-align: middle; margin-right: 6px; }
        .depth-fill { height: 100%; background: #667eea; border-radius: 4px; }
        .compact-table { width: 100%; font-size: 13px; border-collapse: collapse; }
        .compact-table th { background: #f0f2f8; padding: 6px 10px; text-align: left; font-weight: 600; color: #667eea; }
        .compact-table td { padding: 6px 10px; border-bottom: 1px solid #f0f0f0; }
        .compact-table tr:hover { background: #fafbff; }
        .appendix { background: #fff; border-radius: 10px; padding: 20px; }
        .sector-tag { display: inline-block; background: #e8ecf7; color: #667eea; padding: 4px 12px; border-radius: 16px; font-size: 13px; margin: 3px; }
        .footer { text-align: center; color: #bbb; font-size: 12px; margin-top: 40px; padding-top: 15px; border-top: 1px solid #eee; }
        details { margin-top: 8px; }
        details summary { cursor: pointer; color: #667eea; font-size: 13px; padding: 4px 0; user-select: none; }
        details summary:hover { text-decoration: underline; }
        .card-header { display: flex; align-items: baseline; flex-wrap: wrap; gap: 6px; }
        .card-header .rank { font-weight: 700; font-size: 14px; color: #667eea; }
        .card-header .title { font-weight: 600; font-size: 15px; color: #2d3142; }
        .card-header .meta { font-size: 12px; color: #999; }
        .card-logic { margin-top: 6px; font-size: 14px; color: #444; line-height: 1.6; padding-left: 4px; border-left: 3px solid #667eea; }
        .card-evidence { font-size:13px; color:#2e7d32; margin:4px 0 6px 0; padding:4px 8px; background:#e8f5e9; border-radius:4px; line-height:1.5; }
        .card-detail { margin-top: 10px; padding: 12px; background: #f8f9fc; border-radius: 6px; font-size: 13px; line-height: 1.8; }
        /* 导航栏 */
        #report-nav { position: fixed; left: 0; top: 0; width: 180px; height: 100vh; background: #fff; border-right: 1px solid #eee; padding: 16px 10px; overflow-y: auto; z-index: 100; box-shadow: 2px 0 8px rgba(0,0,0,0.04); }
        #report-content { margin-left: 190px; }
        .nav-title { font-size: 13px; font-weight: 700; color: #667eea; margin-bottom: 10px; padding-left: 6px; }
        .nav-item { display: block; padding: 5px 8px; font-size: 12px; color: #555; text-decoration: none; border-radius: 4px; margin-bottom: 2px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        .nav-item:hover { background: #f0f2ff; color: #667eea; }
        .nav-item.active { background: #667eea; color: #fff; }
        /* 搜索 */
        .nav-search { margin-bottom: 14px; }
        .nav-search input { width: 100%; padding: 6px 8px; border: 1px solid #ddd; border-radius: 5px; font-size: 12px; outline: none; }
        .nav-search input:focus { border-color: #667eea; }
        .search-info { display: flex; align-items: center; gap: 4px; margin-top: 4px; font-size: 11px; color: #999; }
        .search-info button { border: none; background: #f0f2ff; color: #667eea; width: 20px; height: 20px; border-radius: 3px; cursor: pointer; font-size: 12px; }
        .search-info button:hover { background: #667eea; color: #fff; }
        .search-highlight { background: #ffeb3b; padding: 0 1px; border-radius: 2px; }
        .search-current { background: #ff9800; color: #fff; border-radius: 2px; }
        """


    def _get_nav(self, **kw) -> str:
        """左侧导航栏（搜索+目录）"""
        s = kw['stats']
        return """
        <nav id="report-nav">
            <div class="nav-search">
                <input type="text" id="search-input" placeholder="🔍 搜索关键词...">
                <div class="search-info" id="search-info" style="display:none;">
                    <span id="search-count">0/0</span>
                    <button id="search-prev" title="上一个">↑</button>
                    <button id="search-next" title="下一个">↓</button>
                    <button id="search-clear" title="清除">✕</button>
                </div>
            </div>
            <div class="nav-title">📋 目录</div>
            <a href="#sec-overview" class="nav-item">📊 今日速览</a>
            <a href="#sec-global" class="nav-item">🌍 全球市场</a>
            <a href="#sec-headlines" class="nav-item">🔥 头条摘要</a>
            <a href="#sec-domain" class="nav-item">🏭 领域重大利好</a>
            <a href="#sec-news" class="nav-item">📰 重大新闻利好</a>
            <a href="#sec-notice" class="nav-item">📋 高价值公告</a>
            <a href="#sec-ztb" class="nav-item">📈 涨停分析</a>
            <a href="#sec-sector" class="nav-item">📊 板块热度</a>
            <a href="#sec-concept" class="nav-item">💡 概念热度</a>
        </nav>"""


    def _get_search_js(self) -> str:
        """搜索和导航JS"""
        return """
        <script>
        (function() {
            const input = document.getElementById('search-input');
            const info = document.getElementById('search-info');
            const countEl = document.getElementById('search-count');
            let matches = [];
            let currentIdx = -1;

            // 搜索功能
            input.addEventListener('input', function() {
                clearHighlights();
                const query = this.value.trim();
                if (!query) { info.style.display='none'; return; }
                info.style.display = 'flex';
                matches = [];
                currentIdx = -1;
                highlightText(document.getElementById('report-content'), query);
                countEl.textContent = matches.length > 0 ? `1/${matches.length}` : '0/0';
                if (matches.length > 0) jumpTo(0);
            });

            document.getElementById('search-prev').onclick = function() {
                if (matches.length === 0) return;
                jumpTo((currentIdx - 1 + matches.length) % matches.length);
            };
            document.getElementById('search-next').onclick = function() {
                if (matches.length === 0) return;
                jumpTo((currentIdx + 1) % matches.length);
            };
            document.getElementById('search-clear').onclick = function() {
                input.value = '';
                clearHighlights();
                info.style.display = 'none';
            };

            function highlightText(root, query) {
                const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, null);
                const nodesToReplace = [];
                while (walker.nextNode()) {
                    const node = walker.currentNode;
                    if (node.parentElement.closest('#report-nav')) continue;
                    if (node.textContent.includes(query)) {
                        nodesToReplace.push(node);
                    }
                }
                nodesToReplace.forEach(node => {
                    const parts = node.textContent.split(query);
                    const frag = document.createDocumentFragment();
                    parts.forEach((part, i) => {
                        frag.appendChild(document.createTextNode(part));
                        if (i < parts.length - 1) {
                            const mark = document.createElement('mark');
                            mark.className = 'search-highlight';
                            mark.textContent = query;
                            matches.push(mark);
                            frag.appendChild(mark);
                        }
                    });
                    node.parentNode.replaceChild(frag, node);
                });
            }

            function clearHighlights() {
                document.querySelectorAll('mark.search-highlight, mark.search-current').forEach(el => {
                    el.replaceWith(document.createTextNode(el.textContent));
                });
                document.getElementById('report-content').normalize();
                matches = [];
                currentIdx = -1;
            }

            function jumpTo(idx) {
                if (matches[currentIdx]) matches[currentIdx].className = 'search-highlight';
                currentIdx = idx;
                matches[currentIdx].className = 'search-current';
                matches[currentIdx].scrollIntoView({ behavior: 'smooth', block: 'center' });
                countEl.textContent = `${currentIdx + 1}/${matches.length}`;
            }

            // 导航高亮
            const sections = ['sec-overview','sec-headlines','sec-domain','sec-news','sec-notice','sec-ztb','sec-sector','sec-concept'];
            const navItems = document.querySelectorAll('.nav-item');
            window.addEventListener('scroll', function() {
                let current = '';
                sections.forEach(id => {
                    const el = document.getElementById(id);
                    if (el && el.getBoundingClientRect().top <= 100) current = id;
                });
                navItems.forEach(item => {
                    item.classList.toggle('active', item.getAttribute('href') === '#' + current);
                });
            });
        })();
        </script>"""

    def _get_cover(self, **kw) -> str:
        # 计算纯文本字数和阅读时间
        html_content = (self._get_overview(**kw) + self._get_headlines(**kw) +
                       self._get_domain_section(**kw) + self._get_news_section(**kw) +
                       self._get_notice_section(**kw) + self._get_ztb_section(**kw))
        import re as _re
        # 全文字数（含details内容）— 统计纯文本字符，去除HTML标签/实体/空白
        full_text = _re.sub(r'<[^>]+>', '', html_content)
        full_text = _re.sub(r'&\w+;', '', full_text)
        full_text = _re.sub(r'\s+', '', full_text)
        full_len = len(full_text)
        full_min = max(1, round(full_len / 420))

        # 缩略字数（移除details内容）— 统计纯文本字符
        summary_html = _re.sub(r'<details>.*?</details>', '', html_content, flags=_re.DOTALL)
        summary_text = _re.sub(r'<[^>]+>', '', summary_html)
        summary_text = _re.sub(r'&\w+;', '', summary_text)
        summary_text = _re.sub(r'\s+', '', summary_text)
        summary_len = len(summary_text)
        summary_min = max(1, round(summary_len / 420))

        return f"""
        <div class="cover">
            <h1>🧠 GS2026 智能日报</h1>
            <div class="subtitle">{kw['target_date']}（{self._weekday(kw['target_date'])}）</div>
            <div class="subtitle" style="margin-top:6px;">时间窗口：{kw['start_date']} ~ {kw['end_date']}</div>
            <div class="subtitle" style="margin-top:8px;color:#667eea;">
                📖 缩略阅读：约 {summary_len:,} 字 · 预计 {summary_min} 分钟<br>
                📚 全文阅读：约 {full_len:,} 字 · 预计 {full_min} 分钟
            </div>
        </div>"""

    def _get_overview(self, **kw) -> str:
        s = kw['stats']
        return f"""
        <div class="overview" id="sec-overview">
            <div class="ov-card"><div class="ov-num">{s['domain']}</div><div class="ov-label">🏭 领域利好</div></div>
            <div class="ov-card"><div class="ov-num">{s['news']}</div><div class="ov-label">📰 重大新闻</div></div>
            <div class="ov-card"><div class="ov-num">{s['notice']}</div><div class="ov-label">📋 高分公告</div></div>
            <div class="ov-card"><div class="ov-num">{s['ztb']}</div><div class="ov-label">📈 涨停分析</div></div>
        </div>"""

    def _get_headlines(self, **kw) -> str:
        items = kw['headlines']
        if not items:
            return ''
        rows = []
        for i, item in enumerate(items):
            rank_icon = ['①','②','③','④','⑤','⑥','⑦','⑧','⑨','⑩'][i]
            rows.append(f"""
            <div class="hl-item">
                <span class="hl-rank">{rank_icon}</span>
                <strong>{item['source_label']}</strong> {item['title']}
            </div>""")
        return f"""
        <div class="headlines" id="sec-headlines">
            <h2>🔥 头条摘要（TOP {len(items)}）</h2>
            {''.join(rows)}
        </div>"""

    def _get_domain_section(self, **kw) -> str:
        domain = kw['domain']
        if not domain:
            return ''
        top_items = [d for d in domain if d['grade'] == 'top']
        imp_items = [d for d in domain if d['grade'] == 'important']
        watch_items = [d for d in domain if d['grade'] == 'watch']

        top_cards = ''.join(self._render_domain_card(d) for d in top_items)
        imp_cards = ''.join(self._render_domain_card(d) for d in imp_items)
        watch_cards = ''.join(self._render_domain_card(d) for d in watch_items)

        return f"""
        <div class="section">
            <div class="section-title" id="sec-domain">🏭 第一章 · 领域重大利好（共{len(domain)}条）</div>
            <div style="margin-bottom:10px; color:#e74c3c; font-weight:600;">🔴 TOP级（第1-10名）</div>
            {top_cards}
            <div style="margin:18px 0 10px; color:#f39c12; font-weight:600;">🟠 重要级（第11-30名）</div>
            {imp_cards}
            <div style="margin:18px 0 10px; color:#3498db; font-weight:600;">🟡 关注级（第31名及以后）</div>
            {watch_cards}
        </div>"""

    def _render_domain_card(self, d: Dict) -> str:
        sectors = self._parse_list(d.get('sectors'))
        concepts = self._parse_list(d.get('concepts'))
        stocks = self._parse_list(d.get('stock_codes'))
        deep = d.get('deep_analysis') or '[]'
        depth_items = self._parse_depth(deep)
        # 拆分为业务影响维度(前12)和超短维度(后10)
        biz_items = depth_items[:12]
        cd_items = depth_items[12:22]
        biz_html = ''.join(f'<div class="depth-item">• {item}</div>' for item in biz_items)
        cd_html = ''.join(f'<div class="depth-item">• {item}</div>' for item in cd_items)
        depth_html = (
            f'<div><strong>📊 业务影响维度评分：</strong></div>{biz_html}'
            f'<div style="margin-top:6px;"><strong>⚡ 超短维度评分：</strong></div>{cd_html}'
        )
        # 股票展示为 名称(代码) 格式
        stock_name_map = getattr(self, '_stock_name_map', {})
        stocks_html = ''.join(
            f'<span class="tag tag-blue">{stock_name_map.get(s, "")}{("(" + s + ")") if stock_name_map.get(s) else s}</span>'
            for s in stocks[:5]
        )

        grade_class = f'card-{d["grade"]}'
        return f"""
        <div class="card {grade_class}">
            <div class="card-header">
                <span class="rank">{d['_rank']}</span>
                <span class="score-badge">{d.get('composite_score',0)}分</span>
                <span class="title">{self._trunc(d.get('key_event',''), 80)}</span>
                <span class="meta">| {d.get('event_source','')} | {self._fmt_time(d.get('event_time'))}</span>
            </div>
            <div class="card-logic">💡 {d.get('reason_analysis','') or '无'}</div>
            <div class="card-evidence">🎯 超预期利好证据：{d.get('expectation_analysis','') or '无'}</div>
            <details>
                <summary>📋 查看完整内容</summary>
                <div class="card-detail">
                    <div>📍 领域：{d.get('main_area','')} / {d.get('child_area','')}</div>
                    <div style="margin-top:6px;">
                        📌 板块：{''.join(f'<span class="tag">{s}</span>' for s in sectors[:5])}
                    </div>
                    <div>📌 概念：{''.join(f'<span class="tag tag-red">{s}</span>' for s in concepts[:5])}</div>
                    <div>📌 股票：{stocks_html}</div>
                    <div class="depth-score" style="margin-top:8px;">
                        {depth_html}
                    </div>
                </div>
            </details>
        </div>"""

    def _render_domain_row(self, d: Dict) -> str:
        sectors = ', '.join(self._parse_list(d.get('sectors'))[:3])
        stock_codes = self._parse_list(d.get('stock_codes'))[:3]
        stock_name_map = getattr(self, '_stock_name_map', {})
        stocks = ', '.join(
            f"{stock_name_map.get(s, '')}{('(' + s + ')') if stock_name_map.get(s) else s}"
            for s in stock_codes
        )
        return f"""
        <tr>
            <td>{d['_rank']}</td>
            <td>{d.get('main_area','')}/{d.get('child_area','')}</td>
            <td>{self._trunc(d.get('key_event',''), 50)}</td>
            <td><strong>{d.get('composite_score',0)}</strong></td>
            <td>{sectors}</td>
            <td>{stocks}</td>
        </tr>"""

    def _get_news_section(self, **kw) -> str:
        news = kw['news']
        if not news:
            return ''
        top_items = [n for n in news if n['grade'] == 'top']
        imp_items = [n for n in news if n['grade'] == 'important']
        watch_items = [n for n in news if n['grade'] == 'watch']

        top_cards = ''.join(self._render_news_card(n) for n in top_items)
        imp_cards = ''.join(self._render_news_card(n) for n in imp_items)
        watch_cards = ''.join(self._render_news_card(n) for n in watch_items)

        return f"""
        <div class="section">
            <div class="section-title" id="sec-news">📰 第二章 · 重大新闻利好（共{len(news)}条）</div>
            <div style="margin-bottom:10px; color:#e74c3c; font-weight:600;">🔴 TOP级（第1-10名）</div>
            {top_cards}
            <div style="margin:18px 0 10px; color:#f39c12; font-weight:600;">🟠 重要级（第11-30名）</div>
            {imp_cards}
            <div style="margin:18px 0 10px; color:#3498db; font-weight:600;">🟡 关注级（第31名及以后）</div>
            {watch_cards}
        </div>"""

    def _render_news_card(self, n: Dict) -> str:
        sectors = self._parse_list(n.get('sectors'))
        concepts = self._parse_list(n.get('concepts'))
        leading = self._parse_list(n.get('leading_stocks'))

        # 核心逻辑：从sector_details提取关联原因
        logic = ''
        sector_details = n.get('sector_details') or '[]'
        try:
            sd = json.loads(sector_details) if isinstance(sector_details, str) else sector_details
            if isinstance(sd, list) and sd:
                reasons = []
                for sec in sd[:3]:
                    details = sec.get('板块明细', [])[:2]
                    for det in details:
                        r = det.get('关联原因', '')
                        if r:
                            reasons.append(r)
                logic = '；'.join(reasons[:3])
        except (json.JSONDecodeError, TypeError):
            pass
        if not logic:
            logic = self._trunc(n.get('content', '') or '', 100)

        # 深度分析
        deep_html = ''
        deep = n.get('deep_analysis') or '[]'
        try:
            da = json.loads(deep) if isinstance(deep, str) else deep
            if isinstance(da, list) and da:
                deep_html = ''.join(f'<div class="depth-item">• {str(pt)[:80]}</div>' for pt in da[:5])
        except (json.JSONDecodeError, TypeError):
            pass

        # 板块明细
        detail_html = ''
        try:
            sd = json.loads(sector_details) if isinstance(sector_details, str) else sector_details
            if isinstance(sd, list) and sd:
                detail_html = '<div style="margin-top:6px;"><strong>📊 板块明细：</strong>'
                for sec in sd[:3]:
                    name = sec.get('板块名称', '')
                    details = sec.get('板块明细', [])[:2]
                    for det in details:
                        reason = det.get('关联原因', '')[:60]
                        detail_html += f'<div style="font-size:12px;color:#666;margin:2px 0;">• {name}: {reason}</div>'
                detail_html += '</div>'
        except (json.JSONDecodeError, TypeError):
            pass

        grade_class = f'card-{n["grade"]}'
        return f"""
        <div class="card {grade_class}">
            <div class="card-header">
                <span class="rank">{n['_rank']}</span>
                <span class="score-badge">{n.get('composite_score',0)}分</span>
                <span class="title">{self._trunc(n.get('title',''), 60)}</span>
                <span class="meta">| {n.get('source','')} | {self._fmt_time(n.get('publish_time'))}</span>
            </div>
            <div class="card-logic">💡 {logic or '无'}</div>
            <div class="card-evidence">🎯 超预期利好证据：{n.get('expectation_analysis','') or '无'}</div>
            <details>
                <summary>📋 查看完整内容</summary>
                <div class="card-detail">
                    <div style="margin-top:4px;">
                        📌 板块：{''.join(f'<span class="tag">{s}</span>' for s in sectors[:5])}
                    </div>
                    <div>📌 概念：{''.join(f'<span class="tag tag-red">{s}</span>' for s in concepts[:5])}</div>
                    <div>📌 龙头：{''.join(f'<span class="tag tag-blue">{s}</span>' for s in leading[:5])}</div>
                    {detail_html}
                    {f'<div class="depth-score" style="margin-top:8px;"><strong>📊 深度分析：</strong>{deep_html}</div>' if deep_html else ''}
                </div>
            </details>
        </div>"""

    def _render_news_row(self, n: Dict) -> str:
        sectors = ', '.join(self._parse_list(n.get('sectors'))[:3])
        return f"""
        <tr>
            <td>{n['_rank']}</td>
            <td>{self._trunc(n.get('title',''), 50)}</td>
            <td>{n.get('source','')}</td>
            <td><strong>{n.get('composite_score',0)}</strong></td>
            <td>{sectors}</td>
        </tr>"""

    def _get_notice_section(self, **kw) -> str:
        notices = kw['notice']
        if not notices:
            return ''
        cards = ''.join(self._render_notice_card(n, i+1) for i, n in enumerate(notices))
        return f"""
        <div class="section">
            <div class="section-title" id="sec-notice">📋 第三章 · 高价值公告（共{len(notices)}条）</div>
            {cards}
        </div>"""

    def _render_notice_card(self, n: Dict, idx: int) -> str:
        kp = self._parse_list(n.get('key_points'))
        kp_html = ''.join(f'<li>{str(p)[:100]}</li>' for p in kp[:5])
        judgment = self._parse_list(n.get('judgment_basis'))
        jb_html = ''.join(f'<li>{str(j)[:100]}</li>' for j in judgment[:3])
        return f"""
        <div class="card">
            <div class="card-title">{idx}. {n.get('stock_code','')} {n.get('stock_name','')}
                <span class="score-badge">隔夜{n.get('overnight_score',0)}</span>
            </div>
            <div class="card-meta">📋 {n.get('notice_title','')} | {self._fmt_time(n.get('notice_date'), 10)} | {n.get('notice_type','')} | 风险{n.get('risk_level','')}</div>
            <div class="card-body">
                <strong>📌 关键要点：</strong>
                <ul style="margin-left:18px;font-size:13px;">{kp_html}</ul>
                <strong style="margin-top:6px;display:block;">📝 判断依据：</strong>
                <ul style="margin-left:18px;font-size:13px;color:#666;">{jb_html}</ul>
            </div>
            <div style="margin-top:8px; font-size:13px;">
                📊 评分：隔夜策略分 <strong>{n.get('overnight_score',0)}</strong> | 风险分 {n.get('risk_score',0)} | 类型分 {n.get('type_score',0)}
            </div>
            <div style="margin-top:4px; font-size:13px;">
                💡 短期：{self._trunc(n.get('short_term_impact',''), 80) or '无'}
                &nbsp;|&nbsp; 中期：{self._trunc(n.get('medium_term_impact',''), 80) or '无'}
            </div>
            {f'<div style="margin-top:6px;font-size:13px;color:#d48806;">🎯 隔夜策略：{n.get("overnight_strategy","")}</div>' if n.get('overnight_strategy') else ''}
        </div>"""

    def _get_ztb_section(self, **kw) -> str:
        ztb = kw['ztb']
        if not ztb:
            return ''
        # 按封板时段分组
        groups = {'early': ('⚡ 早盘涨停', []), 'midday': ('🕐 午盘涨停', []), 'late': ('🌙 尾盘涨停', [])}
        for z in ztb:
            r = z.get('zt_time_range', 'early')
            if r in groups:
                groups[r][1].append(z)
            else:
                groups['early'][1].append(z)

        sections = []
        for rng, (label, items) in groups.items():
            if not items:
                continue
            cards = ''.join(self._render_ztb_card(z, i+1) for i, z in enumerate(items))
            sections.append(f'<div style="margin:14px 0 6px;color:#667eea;font-weight:700;">{label}（{len(items)}只）</div>{cards}')

        return f"""
        <div class="section">
            <div class="section-title" id="sec-ztb">📈 第四章 · 涨停分析（共{len(ztb)}只）</div>
            {''.join(sections)}
        </div>"""

    def _render_ztb_card(self, z: Dict, idx: int) -> str:
        sectors = self._parse_list(z.get('sectors'))
        concepts = self._parse_list(z.get('concepts'))
        leading = self._parse_list(z.get('leading_stocks'))

        # 核心逻辑：influence_msg
        logic = ''
        if z.get('influence_msg'):
            try:
                im = json.loads(z['influence_msg']) if isinstance(z['influence_msg'], str) else z['influence_msg']
                if isinstance(im, list) and im:
                    logic = str(im[0])[:120]
                elif isinstance(im, str):
                    logic = im[:120]
            except (json.JSONDecodeError, TypeError):
                logic = str(z.get('influence_msg', ''))[:120]
        if not logic:
            logic = z.get('stock_nature', '')[:80]

        # 涨停原因
        sec_msg = ''
        if z.get('sector_msg'):
            try:
                sm = json.loads(z['sector_msg']) if isinstance(z['sector_msg'], str) else z['sector_msg']
                if isinstance(sm, list) and sm:
                    sec_msg = sm[0].get('板块刺激消息', [''])[0][:80]
            except (json.JSONDecodeError, TypeError, IndexError, KeyError):
                pass
        # 预期消息
        exp_msg = ''
        if z.get('expect_msg'):
            try:
                em = json.loads(z['expect_msg']) if isinstance(z['expect_msg'], str) else z['expect_msg']
                if isinstance(em, list) and em:
                    exp_msg = em[0].get('预期消息', '')[:80]
            except (json.JSONDecodeError, TypeError, IndexError, KeyError):
                pass
        # 深度分析
        deep_html = ''
        deep = z.get('deep_analysis') or '[]'
        try:
            da = json.loads(deep) if isinstance(deep, str) else deep
            if isinstance(da, list) and da:
                deep_html = ''.join(f'<div class="depth-item">• {str(pt)[:80]}</div>' for pt in da[:5])
        except (json.JSONDecodeError, TypeError):
            pass

        grade_class = 'card-watch' if z['grade'] == 'watch' else ('card-important' if z['grade'] == 'important' else 'card-top')
        cont = z.get('continuity', 0)
        cont_label = '首板' if cont <= 1 else f'连板{cont}'
        return f"""
        <div class="card {grade_class}">
            <div class="card-header">
                <span class="rank">{idx}</span>
                <span class="score-badge">{cont_label}</span>
                <span class="title">{z.get('stock_name','')}({z.get('stock_code','')})</span>
                <span class="meta">| {self._fmt_time(z.get('trade_date'), 10)} | 封板：{self._fmt_time(z.get('zt_time'), 8)}</span>
            </div>
            <div class="card-logic">💡 {logic}</div>
            <details>
                <summary>📋 查看完整内容</summary>
                <div class="card-detail">
                    <div>{z.get('stock_nature','')[:60]}</div>
                    <div style="margin-top:4px;">
                        📌 板块：{''.join(f'<span class="tag">{s}</span>' for s in sectors[:5])}
                    </div>
                    <div>📌 概念：{''.join(f'<span class="tag tag-red">{s}</span>' for s in concepts[:5])}</div>
                    <div>📌 龙头：{''.join(f'<span class="tag tag-blue">{s}</span>' for s in leading[:5])}</div>
                    {f'<div style="margin-top:6px;font-size:13px;">🔥 涨停原因：{sec_msg}</div>' if sec_msg else ''}
                    {f'<div style="margin-top:4px;font-size:13px;">🎯 预期消息：{exp_msg}</div>' if exp_msg else ''}
                    {f'<div class="depth-score" style="margin-top:8px;"><strong>📊 深度分析：</strong>{deep_html}</div>' if deep_html else ''}
                </div>
            </details>
        </div>"""

    def _get_sector_heatmap(self, **kw) -> str:
        heatmap = kw.get('sector_heatmap', [])
        if not heatmap:
            return ''
        tags = ''.join(f'<span class="sector-tag">{name} ({cnt})</span>' for name, cnt in heatmap[:20])
        return f"""
        <div class="appendix">
            <div class="section-title" id="sec-sector">📊 附录 · 今日板块热度 TOP20</div>
            <div style="line-height:2.5;">{tags}</div>
            <div style="font-size:12px;color:#999;margin-top:8px;">权重：领域分析×3 新闻分析×2 涨停分析×1</div>
        </div>"""

    def _get_concept_heatmap(self, **kw) -> str:
        heatmap = kw.get('concept_heatmap', [])
        if not heatmap:
            return ''
        tags = ''.join(f'<span class="sector-tag" style="background:#fde8e8;color:#e74c3c;">{name} ({cnt})</span>' for name, cnt in heatmap[:20])
        return f"""
        <div class="appendix" style="margin-top:20px;">
            <div class="section-title" id="sec-concept">💡 附录 · 今日概念热度 TOP20</div>
            <div style="line-height:2.5;">{tags}</div>
            <div style="font-size:12px;color:#999;margin-top:8px;">权重：领域分析×3 新闻分析×2 涨停分析×1</div>
        </div>"""

    # ============ 工具方法 ============

    @staticmethod
    def _parse_list(val) -> List[str]:
        """安全解析JSON数组"""
        if not val:
            return []
        if isinstance(val, list):
            return val
        try:
            result = json.loads(val)
            return result if isinstance(result, list) else []
        except (json.JSONDecodeError, TypeError):
            return []

    @staticmethod
    def _parse_depth(val) -> List[str]:
        """解析深度分析数组，拆分为独立评分项"""
        items = SmartReportService._parse_list(val)
        if not items:
            return []
        # deep_analysis通常是单个长字符串（用；分隔），需要拆分
        results = []
        for item in items:
            s = str(item)
            # 按中文分号拆分
            parts = s.replace('；', ';').split(';')
            for part in parts:
                part = part.strip()
                if part and len(part) > 3:
                    results.append(part)
        return results

    @staticmethod
    def _trunc(text: str, max_len: int = 80) -> str:
        if not text:
            return ''
        return text[:max_len] + '...' if len(text) > max_len else text

    @staticmethod
    def _weekday(date_str: str) -> str:
        try:
            from datetime import datetime
            wd = ['周一','周二','周三','周四','周五','周六','周日']
            return wd[datetime.strptime(date_str, '%Y-%m-%d').weekday()]
        except Exception:
            return ''

    @staticmethod
    def _fmt_time(val, fmt: int = 16) -> str:
        """安全格式化时间字段（兼容Timestamp/str/None）"""
        if val is None:
            return ''
        s = str(val)
        return s[:fmt] if len(s) >= fmt else s

    # ============ 盘前全球市场分析 ============

    def _call_ai(self, prompt: str) -> Optional[str]:
        """统一AI调用入口，volcengine/deepseek自动切换"""
        ai_engine = config_util.get_config('common.anomaly_ai_engine') or 'volcengine'
        if ai_engine == 'volcengine':
            return volcengine_analysis(prompt)
        else:
            ensure_proxy_daemon()
            return deepseek_analysis(prompt, _headless=True, process_name="smart_report")

    def _generate_global_market_analysis(self) -> Optional[Dict]:
        """调用AI分析全球市场，返回JSON"""
        try:
            beijing_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            prompt = GLOBAL_MARKET_ANALYSIS_PROMPT.format(CURR_BEIJING_TIME=beijing_time)
            logger.info(f"[智能报告] 开始生成全球市场分析... 时间: {beijing_time}")
            result = self._call_ai(prompt)
            if result:
                # 提取JSON
                json_match = re.search(r'\{[\s\S]*\}', result)
                if json_match:
                    logger.info("[智能报告] 全球市场分析生成成功")
                    return json.loads(json_match.group())
            logger.warning("[智能报告] AI返回格式异常，无法解析JSON")
            return None
        except Exception as e:
            logger.error(f"[智能报告] 全球市场分析失败: {e}")
            return None

    def _get_global_market_section(self, **kw) -> str:
        """渲染全球市场分析section（动态解析JSON）"""
        data = kw.get('global_market')
        if not data:
            return ''
        
        html = '<section id="sec-global" class="section">'
        html += '<h2 class="section-title">🌍 盘前全球市场分析</h2>'
        
        def render_value(key: str, value: Any, depth: int = 0) -> str:
            """递归渲染JSON value"""
            if isinstance(value, dict):
                # 嵌套对象
                html = f'<div class="card" style="margin-left:{depth*20}px;">'
                html += f'<div class="card-title">{key}</div>'
                html += '<div class="card-body">'
                for sub_key, sub_val in value.items():
                    html += render_value(sub_key, sub_val, depth + 1)
                html += '</div></div>'
                return html
            else:
                # 文本值
                return f'<div class="depth-item" style="margin-left:{depth*20}px;"><strong>{key}：</strong>{value}</div>'
        
        for key, value in data.items():
            html += render_value(key, value)
        
        html += '</section>'
        return html
