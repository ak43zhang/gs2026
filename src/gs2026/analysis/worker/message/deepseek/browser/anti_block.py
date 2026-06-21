"""DeepSeek 反封禁辅助模块

通过模拟人工行为特征降低被 DeepSeek 反爬系统识别的概率。
所有行为模拟均为"做样子"——不操作实际内容，只为打破机器化操作模式。

使用方式：
    from gs2026.analysis.worker.message.deepseek.browser.anti_block import (
        FingerprintRandomizer, BehaviorMime, HumanTypist, DelayBox
    )
"""

import random
import time


class HumanTypist:
    """模拟人工逐字输入，仅用于短文本字段（账号、密码）。

    Prompt 等长文本不动，保持原有 .fill() 逻辑。
    """

    @staticmethod
    def type_short(page, selector: str, text: str) -> None:
        """逐字输入短文本，带随机延迟和偶发停顿。

        Args:
            page: Playwright 页面对象
            selector: 输入框 CSS 选择器
            text: 要输入的文本
        """
        page.click(selector)
        for char in text:
            page.type(selector, char)
            time.sleep(random.uniform(0.05, 0.25))
            # 5% 概率出现"思考停顿"
            if random.random() < 0.05:
                time.sleep(random.uniform(0.3, 0.8))


class BehaviorMime:
    """模拟人工浏览行为，只做样子不操作实际内容。

    所有方法仅产生鼠标移动、页面滚动等视觉行为，
    不改变表单值、不提交、不点击功能按钮。
    """

    @staticmethod
    def idle_look(page) -> None:
        """模拟"看页面"：鼠标移到随机位置 + 随机停顿。"""
        page.mouse.move(
            random.randint(100, 1200),
            random.randint(100, 700),
            steps=random.randint(3, 8),
        )
        time.sleep(random.uniform(0.5, 1.5))

    @staticmethod
    def casual_scroll(page) -> None:
        """模拟"随便翻翻"：随机滚动 + 可选回滚。"""
        dist = random.randint(100, 400)
        page.mouse.wheel(0, dist)
        time.sleep(random.uniform(0.5, 2.0))
        # 20% 概率回滚一下
        if random.random() < 0.2:
            page.mouse.wheel(0, -random.randint(50, 150))
            time.sleep(random.uniform(0.3, 0.8))

    @staticmethod
    def think_pause() -> None:
        """模拟"想一下"：纯随机停顿。"""
        time.sleep(random.uniform(0.5, 2.0))


class DelayBox:
    """统一风格的随机延迟，范围 0.5-3 秒。

    替代原来固定 sleep 和长短不一的随机区间，
    所有场景统一 ∈ [0.5, 3.0]。
    """

    @staticmethod
    def wait(seconds: float = None) -> None:
        """随机等待，默认 0.5-3 秒。可指定上限。"""
        hi = min(seconds, 3.0) if seconds else 3.0
        time.sleep(random.uniform(0.5, hi))

    @staticmethod
    def short() -> None:
        """短停顿 0.5-1.5 秒（字段间过渡）。"""
        time.sleep(random.uniform(0.5, 1.5))

    @staticmethod
    def think() -> None:
        """思考停顿 1-2 秒（操作转折点）。"""
        time.sleep(random.uniform(1.0, 2.0))


class FingerprintRandomizer:
    """每次生成不同的浏览器指纹配置。"""

    USER_AGENTS = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
    ]

    VIEWPORTS = [
        (1920, 1080), (1366, 768), (1440, 900), (1536, 864),
        (1600, 900), (1280, 720), (1680, 1050),
    ]

    @classmethod
    def randomize(cls, context) -> None:
        """为浏览器上下文应用随机指纹（随机 UA）。"""
        import random as _r
        ua = _r.choice(cls.USER_AGENTS)
        context.set_extra_http_headers({'User-Agent': ua})
