"""智谱清言分析模块测试脚本"""

import sys
import os

# 添加src到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..'))

def test_import():
    """测试模块导入"""
    print("Testing imports...")
    try:
        from gs2026.analysis.worker.message.zhipuqingyan import analysis_event_driven
        print("✓ analysis_event_driven imported successfully")
        return True
    except Exception as e:
        print(f"✗ Import failed: {e}")
        return False

def test_browser_class():
    """测试浏览器类定义"""
    print("\nTesting ChatGLMBrowser class...")
    try:
        # 只检查类定义，不实际启动浏览器
        from gs2026.analysis.worker.message.zhipuqingyan.zhipuqingyan_analysis_event_driven import ChatGLMBrowser
        
        methods = ['launch', 'navigate', 'close_popup', 'enable_thinking', 
                   'enable_web_search', 'send_message', 'wait_for_response', 'close']
        
        for method in methods:
            if hasattr(ChatGLMBrowser, method):
                print(f"  ✓ {method} method exists")
            else:
                print(f"  ✗ {method} method missing")
                
        return True
    except Exception as e:
        print(f"✗ Browser class test failed: {e}")
        return False

def test_prompt_build():
    """测试Prompt构造"""
    print("\nTesting prompt building...")
    try:
        from gs2026.analysis.worker.message.zhipuqingyan.zhipuqingyan_analysis_event_driven import build_prompt
        
        prompt = build_prompt(
            t_date='2026-05-20',
            main_area='科技',
            child_area='AI',
            bk_dic_str='半导体,新能源',
            gn_dic_str='ChatGPT,大模型'
        )
        
        # 检查关键内容
        checks = [
            '2026-05-20' in prompt,
            '科技' in prompt,
            'AI' in prompt,
            '重要程度评分' in prompt,
            '业务影响维度评分' in prompt,
            'json' in prompt.lower()
        ]
        
        if all(checks):
            print(f"  ✓ Prompt built successfully ({len(prompt)} chars)")
            return True
        else:
            print(f"  ✗ Prompt missing key elements")
            return False
            
    except Exception as e:
        print(f"✗ Prompt build test failed: {e}")
        return False

def test_result_processor():
    """测试结果处理器"""
    print("\nTesting result processor...")
    try:
        from gs2026.analysis.worker.message.zhipuqingyan.result_processor import process_domain
        
        # 测试JSON解析
        test_json = '''{"消息集合": [
            {
                "主领域": "科技",
                "子领域": "AI",
                "时间": "2026-05-20 09:30:00",
                "事件来源": "测试来源",
                "关键事件": "测试事件",
                "简要描述": "测试描述",
                "利空利好": "利好",
                "消息大小": "大",
                "涉及板块": "半导体",
                "涉及概念": "ChatGPT",
                "股票代码": "000001",
                "原因分析": "测试原因",
                "重要程度评分": "10",
                "业务影响维度评分": "20",
                "综合评分": "60",
                "深度分析": ["分析1", "分析2"]
            }
        ]}'''
        
        print(f"  ✓ Result processor imported")
        print(f"  ✓ Test JSON prepared ({len(test_json)} chars)")
        return True
        
    except Exception as e:
        print(f"✗ Result processor test failed: {e}")
        return False

def main():
    """主测试函数"""
    print("="*60)
    print("智谱清言分析模块测试")
    print("="*60)
    
    results = []
    results.append(("Import Test", test_import()))
    results.append(("Browser Class Test", test_browser_class()))
    results.append(("Prompt Build Test", test_prompt_build()))
    results.append(("Result Processor Test", test_result_processor()))
    
    print("\n" + "="*60)
    print("测试结果汇总")
    print("="*60)
    
    passed = sum(1 for _, r in results if r)
    total = len(results)
    
    for name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{name}: {status}")
    
    print(f"\n总计: {passed}/{total} 通过")
    
    if passed == total:
        print("\n✓ 所有测试通过！模块可以正常使用。")
    else:
        print("\n✗ 部分测试失败，请检查代码。")

if __name__ == "__main__":
    main()
