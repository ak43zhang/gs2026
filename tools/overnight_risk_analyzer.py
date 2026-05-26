#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
通达信风险数据分析工具 - 隔夜超短风险评估
基于 adata.sentiment.mine.mine_clearance_tdx
"""

import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

import pandas as pd
import adata
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class OvernightRiskAnalyzer:
    """隔夜超短风险分析器"""
    
    # 风险等级权重
    RISK_LEVEL_WEIGHTS = {
        5: 100,  # 极高风险
        4: 80,   # 高风险
        3: 50,   # 中等风险
        2: 20,   # 低风险
        1: 0     # 极低风险
    }
    
    # 风险类型加成
    RISK_TYPE_BONUS = {
        '退市': 50,
        '终止上市': 50,
        '暂停上市': 40,
        '重大违法': 40,
        '强制退市': 45,
        '*ST': 30,
        'ST': 20,
        '立案调查': 25,
        '重大诉讼': 15,
        '业绩预亏': 10,
        '业绩预减': 8,
        '股东减持': 5,
        '限售解禁': 5,
        '股权质押': 5,
        '其他风险': 10
    }
    
    def __init__(self):
        self.risk_cache = {}
    
    def get_risk_data(self, stock_code: str) -> pd.DataFrame:
        """
        获取通达信风险数据
        
        Args:
            stock_code: 股票代码
            
        Returns:
            DataFrame: 风险数据
        """
        try:
            df = adata.sentiment.mine.mine_clearance_tdx(stock_code=stock_code)
            return df
        except Exception as e:
            logger.error(f"获取 {stock_code} 风险数据失败: {e}")
            return pd.DataFrame()
    
    def calculate_risk_score(self, risk_data: Dict) -> float:
        """
        计算风险评分
        
        Args:
            risk_data: 风险数据字典
            
        Returns:
            float: 风险评分 (0-100)
        """
        base_score = 0
        
        # 基础风险等级分
        risk_level = risk_data.get('risk_level', 3)
        if isinstance(risk_level, str):
            # 尝试从字符串解析
            if '高' in risk_level or '5' in risk_level:
                risk_level = 5
            elif '中高' in risk_level or '4' in risk_level:
                risk_level = 4
            elif '中' in risk_level or '3' in risk_level:
                risk_level = 3
            elif '低' in risk_level or '2' in risk_level:
                risk_level = 2
            else:
                risk_level = 1
        
        base_score += self.RISK_LEVEL_WEIGHTS.get(risk_level, 50)
        
        # 风险类型加成
        risk_type = str(risk_data.get('risk_type', ''))
        risk_desc = str(risk_data.get('risk_desc', ''))
        combined_text = risk_type + risk_desc
        
        for keyword, bonus in self.RISK_TYPE_BONUS.items():
            if keyword in combined_text:
                base_score += bonus
                break  # 只加一次最高的
        
        # 时间因子
        notice_date = risk_data.get('notice_date')
        if notice_date:
            try:
                if isinstance(notice_date, str):
                    notice_date = datetime.strptime(notice_date, '%Y-%m-%d')
                days_since = (datetime.now() - notice_date).days
                if days_since <= 3:
                    base_score *= 1.2
                elif days_since <= 7:
                    base_score *= 1.1
            except:
                pass
        
        return min(base_score, 100)
    
    def analyze_stock(self, stock_code: str) -> Dict:
        """
        分析单只股票的隔夜超短风险
        
        Args:
            stock_code: 股票代码
            
        Returns:
            Dict: 风险分析结果
        """
        # 获取风险数据
        df_risk = self.get_risk_data(stock_code)
        
        if df_risk.empty:
            return {
                'stock_code': stock_code,
                'stock_name': '',
                'risk_score': 0,
                'risk_level': '🟢 安全',
                'risk_level_code': 1,
                'can_overnight': True,
                'max_position': 1.0,
                'position_pct': '100%',
                'risk_type': '',
                'risk_desc': '',
                'notice_date': '',
                'suggestion': '无风险数据，默认安全，可正常隔夜持仓',
                'warnings': []
            }
        
        # 取最新风险数据
        latest = df_risk.iloc[0].to_dict()
        
        # 计算风险评分
        risk_score = self.calculate_risk_score(latest)
        
        # 确定风险等级和建议
        if risk_score <= 20:
            risk_level = '🟢 安全'
            risk_level_code = 1
            can_overnight = True
            max_position = 1.0
            position_pct = '100%'
            suggestion = '风险极低，可正常隔夜持仓'
        elif risk_score <= 40:
            risk_level = '🟡 低风险'
            risk_level_code = 2
            can_overnight = True
            max_position = 0.7
            position_pct = '70%'
            suggestion = '风险较低，可隔夜持仓，建议设置止损'
        elif risk_score <= 60:
            risk_level = '🟠 中等风险'
            risk_level_code = 3
            can_overnight = True
            max_position = 0.4
            position_pct = '40%'
            suggestion = '风险中等，谨慎隔夜持仓，严格止损'
        elif risk_score <= 80:
            risk_level = '🔴 高风险'
            risk_level_code = 4
            can_overnight = False
            max_position = 0.1
            position_pct = '10%'
            suggestion = '风险较高，不建议隔夜持仓，如必须持仓请轻仓'
        else:
            risk_level = '⚫ 极高风险'
            risk_level_code = 5
            can_overnight = False
            max_position = 0.0
            position_pct = '0%'
            suggestion = '风险极高，禁止隔夜持仓，建议立即平仓'
        
        # 收集警告信息
        warnings = []
        if 'ST' in str(latest.get('risk_type', '')):
            warnings.append('ST股票')
        if '退市' in str(latest.get('risk_desc', '')):
            warnings.append('退市风险')
        if '立案' in str(latest.get('risk_desc', '')):
            warnings.append('立案调查')
        
        return {
            'stock_code': stock_code,
            'stock_name': latest.get('stock_name', ''),
            'risk_score': round(risk_score, 1),
            'risk_level': risk_level,
            'risk_level_code': risk_level_code,
            'can_overnight': can_overnight,
            'max_position': max_position,
            'position_pct': position_pct,
            'risk_type': latest.get('risk_type', ''),
            'risk_desc': latest.get('risk_desc', ''),
            'notice_date': latest.get('notice_date', ''),
            'suggestion': suggestion,
            'warnings': warnings
        }
    
    def analyze_stocks(self, stock_codes: List[str]) -> pd.DataFrame:
        """
        批量分析股票风险
        
        Args:
            stock_codes: 股票代码列表
            
        Returns:
            DataFrame: 风险分析结果
        """
        results = []
        for code in stock_codes:
            result = self.analyze_stock(code)
            results.append(result)
            logger.info(f"已分析: {code} - {result['risk_level']}")
        
        df = pd.DataFrame(results)
        return df
    
    def print_report(self, result: Dict):
        """打印单只股票风险报告"""
        print("\n" + "=" * 80)
        print(f"股票代码: {result['stock_code']}")
        print(f"股票名称: {result['stock_name']}")
        print("-" * 80)
        print(f"风险评分: {result['risk_score']}/100")
        print(f"风险等级: {result['risk_level']}")
        print(f"隔夜建议: {'✅ 可以隔夜' if result['can_overnight'] else '❌ 禁止隔夜'}")
        print(f"最大仓位: {result['position_pct']}")
        print("-" * 80)
        print(f"风险类型: {result['risk_type']}")
        print(f"风险描述: {result['risk_desc']}")
        print(f"公告日期: {result['notice_date']}")
        print("-" * 80)
        print(f"操作建议: {result['suggestion']}")
        if result['warnings']:
            print(f"⚠️  警告: {', '.join(result['warnings'])}")
        print("=" * 80)


def main():
    """主函数"""
    analyzer = OvernightRiskAnalyzer()
    
    # 示例：分析单只股票
    print("\n【单只股票分析示例】")
    stock_code = "000001"  # 可以替换为任意股票代码
    result = analyzer.analyze_stock(stock_code)
    analyzer.print_report(result)
    
    # 示例：批量分析
    print("\n【批量分析示例】")
    stock_list = ['000001', '000002', '600000', '600519']
    df_results = analyzer.analyze_stocks(stock_list)
    
    print("\n批量分析结果:")
    print(df_results[['stock_code', 'stock_name', 'risk_level', 'risk_score', 
                      'can_overnight', 'position_pct']].to_string(index=False))
    
    # 统计
    print("\n" + "=" * 80)
    print("风险统计:")
    print("=" * 80)
    risk_counts = df_results['risk_level'].value_counts()
    for level, count in risk_counts.items():
        print(f"  {level}: {count} 只")
    
    safe_count = df_results['can_overnight'].sum()
    print(f"\n可隔夜持仓: {safe_count}/{len(df_results)} 只")
    print(f"禁止隔夜: {len(df_results) - safe_count}/{len(df_results)} 只")


if __name__ == '__main__':
    main()
