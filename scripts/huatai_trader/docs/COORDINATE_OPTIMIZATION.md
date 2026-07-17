# 坐标定位优化方案

## 问题分析

### 当前状况

| 模块 | 定位方式 | 是否受窗口移动影响 |
|------|----------|------------------|
| `trader.py` (买入/卖出) | 键盘驱动 (F1/F2 + Tab) | ❌ 不受影响 |
| `TpSlPlacer` (止盈止损) | 相对坐标点击 | ✅ 受影响 |

### 影响场景

```
场景1: 窗口移动
  用户将华泰窗口从屏幕左侧移到右侧
  → 相对坐标偏移 → 点击位置错误

场景2: 窗口大小变化
  用户最大化/还原窗口
  → 内部控件位置变化 → 点击位置错误

场景3: 多显示器
  窗口在不同显示器之间移动
  → 坐标系统变化 → 点击位置错误

场景4: DPI缩放
  系统缩放比例不是100%
  → 坐标换算错误 → 点击位置错误
```

---

## 优化方案

### 方案A: 纯键盘驱动 (推荐)

**核心思想**: 完全使用键盘操作，不依赖任何坐标

#### 实现方式

```python
class TpSlPlacerKeyboard:
    """纯键盘驱动的止盈止损设置"""
    
    def place(self, bond_code, base_price, tp_pct, sl_pct, quantity):
        # 1. 激活窗口
        self._activate_window()
        
        # 2. 打开条件单 (假设有快捷键,如Ctrl+Shift+C)
        # 如果没有,可以通过菜单导航: Alt + 条件单菜单 + Enter
        send_keys('^+c')  # 假设的快捷键
        time.sleep(0.5)
        
        # 3. 填充表单 (纯Tab导航)
        # Tab顺序: 代码 → 类型(止盈/止损) → 触发价 → 委托价 → 数量 → 提交
        
        # 填充代码
        send_keys(bond_code)
        time.sleep(0.1)
        send_keys('{TAB}')
        
        # 选择止盈类型
        send_keys('{DOWN}')  # 或输入'T'表示止盈
        time.sleep(0.1)
        send_keys('{TAB}')
        
        # 填充触发价
        tp_price = base_price * (1 + tp_pct / 100)
        send_keys(f'{tp_price:.3f}')
        time.sleep(0.1)
        send_keys('{TAB}')
        
        # 填充委托价
        send_keys(f'{tp_price:.3f}')
        time.sleep(0.1)
        send_keys('{TAB}')
        
        # 填充数量
        send_keys(str(quantity))
        time.sleep(0.1)
        send_keys('{TAB}')
        
        # 提交 (不自动点击,留给用户确认)
        # 或 send_keys('{ENTER}') 如果确认全自动
```

#### 优点
- ✅ 完全不依赖窗口位置和大小
- ✅ 不受DPI缩放影响
- ✅ 多显示器无问题
- ✅ 实现简单，维护成本低

#### 缺点
- ⚠️ 需要知道Tab顺序和快捷键
- ⚠️ 如果界面布局变化，Tab顺序可能改变
- ⚠️ 可能需要多次尝试确定正确的按键序列

---

### 方案B: 动态坐标校准 (备选)

**核心思想**: 每次操作前重新校准坐标

#### 实现方式

```python
class TpSlPlacerDynamic:
    """动态坐标校准的止盈止损设置"""
    
    def __init__(self):
        self.positions_cache = None
        self.cache_time = 0
        self.cache_ttl = 300  # 5分钟缓存
    
    def _get_window_rect(self):
        """获取窗口当前位置和大小"""
        hwnd = find_window("网上股票交易系统5.0")
        if not hwnd:
            raise Exception("窗口未找到")
        
        rect = win32gui.GetWindowRect(hwnd)
        return {
            'left': rect[0],
            'top': rect[1],
            'width': rect[2] - rect[0],
            'height': rect[3] - rect[1],
        }
    
    def _calibrate_positions(self, window_rect):
        """
        根据窗口大小动态计算控件位置
        
        假设控件位置与窗口大小成比例:
        - 条件单按钮: 右下角固定偏移
        - 输入框: 相对中心位置
        """
        w, h = window_rect['width'], window_rect['height']
        
        # 基于窗口大小的相对位置 (需要实测确定比例)
        positions = {
            'condition_btn': (w * 0.85, h * 0.15),  # 右上角区域
            'code_input': (w * 0.3, h * 0.3),       # 中心偏左
            'price_input': (w * 0.3, h * 0.4),
            'quantity_input': (w * 0.3, h * 0.5),
            'submit_btn': (w * 0.5, h * 0.8),      # 底部中心
        }
        
        return positions
    
    def _get_positions(self):
        """获取当前坐标 (带缓存)"""
        now = time.time()
        
        if self.positions_cache and (now - self.cache_time) < self.cache_ttl:
            return self.positions_cache
        
        # 重新校准
        window_rect = self._get_window_rect()
        self.positions_cache = self._calibrate_positions(window_rect)
        self.cache_time = now
        
        return self.positions_cache
    
    def place(self, bond_code, base_price, tp_pct, sl_pct, quantity):
        # 每次操作前获取最新坐标
        positions = self._get_positions()
        
        # 使用相对坐标点击
        hwnd = find_window("网上股票交易系统5.0")
        rect = win32gui.GetWindowRect(hwnd)
        base_x, base_y = rect[0], rect[1]
        
        # 点击条件单按钮
        btn_x = base_x + positions['condition_btn'][0]
        btn_y = base_y + positions['condition_btn'][1]
        click_at(btn_x, btn_y)
```

#### 优点
- ✅ 适应窗口移动和大小变化
- ✅ 比纯键盘更直观
- ✅ 可以处理复杂的自定义界面

#### 缺点
- ⚠️ 需要复杂的校准逻辑
- ⚠️ 控件位置比例需要实测
- ⚠️ 界面布局变化后需要重新校准
- ⚠️ 仍然有坐标依赖，只是动态计算

---

### 方案C: 图像识别定位 (备选)

**核心思想**: 通过图像识别找到控件位置

#### 实现方式

```python
class TpSlPlacerVision:
    """基于图像识别的止盈止损设置"""
    
    def __init__(self):
        # 预存控件模板图像
        self.templates = {
            'condition_btn': cv2.imread('templates/condition_btn.png'),
            'code_input': cv2.imread('templates/code_input.png'),
            'submit_btn': cv2.imread('templates/submit_btn.png'),
        }
    
    def _find_control(self, screenshot, template):
        """在截图中查找控件位置"""
        result = cv2.matchTemplate(screenshot, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)
        
        if max_val > 0.8:  # 相似度阈值
            return max_loc
        return None
    
    def place(self, bond_code, base_price, tp_pct, sl_pct, quantity):
        # 1. 截图
        screenshot = capture_window("网上股票交易系统5.0")
        
        # 2. 查找条件单按钮
        btn_pos = self._find_control(screenshot, self.templates['condition_btn'])
        if btn_pos:
            click_at(btn_pos[0], btn_pos[1])
        
        # 3. 等待弹窗，截图查找输入框
        time.sleep(0.5)
        screenshot = capture_window("华泰理财通")
        input_pos = self._find_control(screenshot, self.templates['code_input'])
        if input_pos:
            click_at(input_pos[0], input_pos[1])
            type_text(bond_code)
```

#### 优点
- ✅ 完全不依赖坐标
- ✅ 可以适应界面主题变化
- ✅ 定位准确

#### 缺点
- ⚠️ 需要准备模板图像
- ⚠️ 性能开销大 (截图+匹配)
- ⚠️ 界面变化后需要更新模板
- ⚠️ 实现复杂，依赖OpenCV

---

## 推荐方案

### 第一阶段: 纯键盘驱动 (立即实施)

**原因**:
1. 实现最快 (1-2小时)
2. 最稳定可靠
3. 不受任何窗口变化影响
4. 维护成本低

**实施步骤**:
1. 在华泰软件中测试Tab顺序
2. 确定每个字段的快捷键
3. 实现纯键盘版本的 `TpSlPlacer`
4. 测试验证

### 第二阶段: 动态校准 (可选增强)

**时机**: 如果键盘方案遇到不可解决的问题

**实施**:
1. 实现窗口位置检测
2. 实现控件比例计算
3. 添加校准缓存机制

---

## 具体实施建议

### 立即行动

1. **在华泰中测试键盘操作**:
   ```
   步骤:
   1. 打开华泰软件
   2. 按 F1 进入买入
   3. 按 Tab 观察焦点移动顺序
   4. 记录: Tab几次到代码框? 几次到价格框?
   5. 测试 Ctrl+A 是否能全选
   6. 测试条件单是否有快捷键 (如 Alt+某个字母)
   ```

2. **确定条件单操作方式**:
   - 方式A: 菜单导航 (Alt + 方向键 + Enter)
   - 方式B: 快捷键 (需要确认是否有)
   - 方式C: 工具栏按钮 (需要坐标)

3. **选择方案**:
   - 如果条件单有快捷键或菜单可访问 → 方案A (纯键盘)
   - 如果必须通过点击 → 方案B (动态坐标)

### 需要您确认

1. **华泰条件单如何打开?**
   - 有快捷键吗? 是什么?
   - 必须通过菜单吗?
   - 还是必须通过点击工具栏按钮?

2. **Tab顺序如何?**
   - 从代码框Tab几次到价格框?
   - 各输入框的Tab顺序是什么?

3. **是否可以接受全自动提交?**
   - 止盈止损设置后是否自动提交?
   - 还是需要您最后确认?

---

## 预期效果

实施后:
- ✅ 窗口可以任意移动
- ✅ 窗口可以最大化/最小化
- ✅ 多显示器无问题
- ✅ DPI缩放无问题
- ✅ 系统更稳定可靠

---

*文档位置: scripts/huatai_trader/docs/COORDINATE_OPTIMIZATION.md*
