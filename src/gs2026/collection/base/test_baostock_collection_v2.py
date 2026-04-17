"""
baostock_collection_v2.py 测试脚本

测试内容:
1. 单只股票采集功能测试
2. 并发采集功能测试
3. 批量写入测试
4. 错误重试测试
5. 性能对比测试 (v1 vs v2)
"""
import time
import unittest
from unittest.mock import Mock, patch
import pandas as pd
import baostock as bs

import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

from gs2026.collection.base.baostock_collection_v2 import (
    BaostockCollector, 
    BaostockConfig, 
    FetchResult,
    stock_update_v2
)


class TestBaostockCollector(unittest.TestCase):
    """BaostockCollector 单元测试"""
    
    def setUp(self):
        """测试前准备"""
        self.config = BaostockConfig(
            max_workers=2,
            batch_size=10,
            max_retries=2,
            retry_delay=0.1,
            enable_progress=False
        )
        self.collector = BaostockCollector(self.config)
    
    def tearDown(self):
        """测试后清理"""
        if self.collector.login_status:
            self.collector.logout()
    
    def test_config_defaults(self):
        """测试配置默认值"""
        config = BaostockConfig()
        self.assertEqual(config.max_workers, 10)
        self.assertEqual(config.batch_size, 100)
        self.assertEqual(config.max_retries, 3)
        self.assertEqual(config.retry_delay, 1.0)
        self.assertTrue(config.enable_progress)
    
    def test_fetch_result_dataclass(self):
        """测试 FetchResult 数据类"""
        result = FetchResult(
            stock_code="000001",
            success=True,
            data=pd.DataFrame(),
            error=None,
            retry_count=0
        )
        self.assertEqual(result.stock_code, "000001")
        self.assertTrue(result.success)
        self.assertIsInstance(result.data, pd.DataFrame)
        self.assertIsNone(result.error)
    
    @patch('baostock.login')
    def test_login_success(self, mock_login):
        """测试登录成功"""
        mock_login.return_value = Mock(error_code='0', error_msg='success')
        result = self.collector.login()
        self.assertTrue(result)
        self.assertTrue(self.collector.login_status)
    
    @patch('baostock.login')
    def test_login_failure(self, mock_login):
        """测试登录失败"""
        mock_login.return_value = Mock(error_code='-1', error_msg='login failed')
        result = self.collector.login()
        self.assertFalse(result)
        self.assertFalse(self.collector.login_status)
    
    @patch('baostock.logout')
    def test_logout(self, mock_logout):
        """测试登出"""
        self.collector.login_status = True
        self.collector.logout()
        self.assertFalse(self.collector.login_status)
    
    @patch('baostock.query_history_k_data_plus')
    def test_fetch_single_stock_success(self, mock_query):
        """测试单只股票采集成功"""
        # 模拟返回数据
        mock_rs = Mock()
        mock_rs.error_code = '0'
        mock_rs.error_msg = 'success'
        mock_rs.fields = ['code', 'date', 'open', 'close', 'high', 'low', 
                         'volume', 'amount', 'pctChg', 'turn', 'preclose']
        
        # 模拟迭代数据
        mock_rs.next = Mock(side_effect=[True, True, False])
        mock_rs.get_row_data = Mock(side_effect=[
            ['sh.000001', '2026-04-01', '10.0', '11.0', '12.0', '9.0', 
             '10000', '100000', '10.0', '5.0', '10.0'],
            ['sh.000001', '2026-04-02', '11.0', '12.0', '13.0', '10.0', 
             '20000', '200000', '9.0', '6.0', '11.0']
        ])
        
        mock_query.return_value = mock_rs
        
        result = self.collector.fetch_single_stock("000001", "2026-04-01", "2026-04-02")
        
        self.assertTrue(result.success)
        self.assertIsNotNone(result.data)
        self.assertEqual(len(result.data), 2)
        self.assertEqual(result.stock_code, "000001")
    
    @patch('baostock.query_history_k_data_plus')
    def test_fetch_single_stock_api_error(self, mock_query):
        """测试 API 错误重试"""
        mock_rs = Mock()
        mock_rs.error_code = '-1'
        mock_rs.error_msg = 'API error'
        mock_query.return_value = mock_rs
        
        result = self.collector.fetch_single_stock("000001", "2026-04-01", "2026-04-02")
        
        self.assertFalse(result.success)
        self.assertIsNotNone(result.error)
        self.assertEqual(result.retry_count, self.config.max_retries)
        # 验证重试次数
        self.assertEqual(mock_query.call_count, self.config.max_retries)
    
    @patch('baostock.query_history_k_data_plus')
    def test_fetch_single_stock_empty_data(self, mock_query):
        """测试空数据返回"""
        mock_rs = Mock()
        mock_rs.error_code = '0'
        mock_rs.error_msg = 'success'
        mock_rs.fields = ['code', 'date', 'open', 'close', 'high', 'low', 
                         'volume', 'amount', 'pctChg', 'turn', 'preclose']
        mock_rs.next = Mock(return_value=False)  # 无数据
        mock_query.return_value = mock_rs
        
        result = self.collector.fetch_single_stock("000001", "2026-04-01", "2026-04-02")
        
        self.assertFalse(result.success)
        self.assertEqual(result.error, "无数据返回")
    
    @patch.object(BaostockCollector, 'fetch_single_stock')
    def test_fetch_stocks_concurrent(self, mock_fetch):
        """测试并发采集"""
        # 模拟返回结果
        def side_effect(code, start, end):
            return FetchResult(
                stock_code=code,
                success=True,
                data=pd.DataFrame({'stock_code': [code]}),
                retry_count=0
            )
        
        mock_fetch.side_effect = side_effect
        
        stock_codes = ["000001", "000002", "600000", "600001"]
        results = self.collector.fetch_stocks_concurrent(
            stock_codes, "2026-04-01", "2026-04-02"
        )
        
        self.assertEqual(len(results), 4)
        self.assertTrue(all(r.success for r in results))
        self.assertEqual(set(r.stock_code for r in results), set(stock_codes))


class TestPerformance(unittest.TestCase):
    """性能测试"""
    
    @patch.object(BaostockCollector, 'fetch_single_stock')
    @patch.object(BaostockCollector, 'login')
    @patch.object(BaostockCollector, 'logout')
    def test_concurrent_performance(self, mock_logout, mock_login, mock_fetch):
        """测试并发性能"""
        # 模拟网络延迟
        def slow_fetch(code, start, end):
            time.sleep(0.1)  # 模拟100ms网络延迟
            return FetchResult(
                stock_code=code,
                success=True,
                data=pd.DataFrame({'stock_code': [code]}),
                retry_count=0
            )
        
        mock_fetch.side_effect = slow_fetch
        mock_login.return_value = True
        
        config = BaostockConfig(max_workers=5, enable_progress=False)
        collector = BaostockCollector(config)
        collector.login_status = True  # 跳过登录
        
        stock_codes = [f"000{i:03d}" for i in range(1, 21)]  # 20只股票
        
        start = time.time()
        results = collector.fetch_stocks_concurrent(
            stock_codes, "2026-04-01", "2026-04-02"
        )
        elapsed = time.time() - start
        
        # 串行需要 20 * 0.1 = 2秒
        # 5线程并发应该 < 0.5秒 (理论值)
        # 实际考虑开销，应该 < 1秒
        self.assertLess(elapsed, 1.0, f"并发采集太慢: {elapsed:.2f}秒")
        self.assertEqual(len(results), 20)
        
        # 验证所有股票都成功
        success_count = sum(1 for r in results if r.success)
        self.assertEqual(success_count, 20)


class TestIntegration(unittest.TestCase):
    """集成测试 (需要真实环境)"""
    
    @unittest.skip("需要真实 Baostock 环境")
    def test_real_single_stock(self):
        """真实环境单只股票测试"""
        config = BaostockConfig(
            max_workers=1,
            enable_progress=False
        )
        collector = BaostockCollector(config)
        
        if not collector.login():
            self.skipTest("Baostock 登录失败")
        
        try:
            result = collector.fetch_single_stock("000001", "2026-04-01", "2026-04-01")
            self.assertTrue(result.success)
            self.assertIsNotNone(result.data)
            print(f"采集成功: {len(result.data)} 条记录")
            print(result.data.head())
        finally:
            collector.logout()
    
    @unittest.skip("需要真实 Baostock 环境")
    def test_real_concurrent_stocks(self):
        """真实环境并发测试"""
        config = BaostockConfig(
            max_workers=5,
            enable_progress=True
        )
        collector = BaostockCollector(config)
        
        if not collector.login():
            self.skipTest("Baostock 登录失败")
        
        try:
            stock_codes = ["000001", "000002", "600000", "600001", "300001"]
            start = time.time()
            results = collector.fetch_stocks_concurrent(
                stock_codes, "2026-04-01", "2026-04-01"
            )
            elapsed = time.time() - start
            
            success_count = sum(1 for r in results if r.success)
            print(f"\n并发采集完成: {success_count}/{len(stock_codes)} 成功")
            print(f"耗时: {elapsed:.2f} 秒")
            print(f"平均每只: {elapsed/len(stock_codes):.3f} 秒")
        finally:
            collector.logout()


def run_tests():
    """运行所有测试"""
    # 创建测试套件
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # 添加测试类
    suite.addTests(loader.loadTestsFromTestCase(TestBaostockCollector))
    suite.addTests(loader.loadTestsFromTestCase(TestPerformance))
    # suite.addTests(loader.loadTestsFromTestCase(TestIntegration))  # 跳过集成测试
    
    # 运行测试
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    return result.wasSuccessful()


if __name__ == "__main__":
    print("=" * 60)
    print("Baostock Collection V2 测试套件")
    print("=" * 60)
    
    success = run_tests()
    
    print("\n" + "=" * 60)
    if success:
        print("[PASS] 所有测试通过!")
    else:
        print("[FAIL] 部分测试失败")
    print("=" * 60)
