# 智谱清言安全认证解决方案

## 问题
- 自动浏览器无法通过 Access Verification
- Cookies 方式也被拦截
- 需要人工完成验证

## 最终解决方案：人机协作模式

### 核心思路
1. **你手动操作**：打开浏览器、完成验证
2. **程序自动操作**：发送消息、获取回复
3. **通过 CDP 连接**：复用你的已验证浏览器

### 使用步骤

#### 步骤1: 启动 Edge 并启用远程调试

**方法A: 命令行启动（推荐）**
```cmd
"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" --remote-debugging-port=9222
```

**方法B: 创建快捷方式**
1. 右键桌面 → 新建 → 快捷方式
2. 位置: `C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe`
3. 右键快捷方式 → 属性
4. 在"目标"后添加: `--remote-debugging-port=9222`
5. 使用此快捷方式启动 Edge

#### 步骤2: 完成验证

1. 在启动的 Edge 中访问: https://chatglm.cn/main/alltoolsdetail?lang=zh
2. 完成 Access Verification 验证
3. 确保能看到输入框，页面正常
4. **保持浏览器打开，不要关闭**

#### 步骤3: 运行程序

```bash
cd F:\pyworkspace2026\gs2026\src\gs2026\analysis\worker\message\zhipuqingyan

# 运行人机协作模式
python human_in_the_loop.py
```

程序会：
1. 连接到你的浏览器
2. 检查页面状态
3. 发送消息
4. 等待你确认回复完成
5. 获取并保存结果

### 文件说明

| 文件 | 用途 |
|------|------|
| `human_in_the_loop.py` | 人机协作模式（推荐） |
| `manual_chatglm.py` | 半自动模式 |
| `get_cookies_from_edge.py` | Edge 获取 cookies |
| `verify_cookies.py` | 验证 cookies |

### 推荐方案

**日常使用**: `human_in_the_loop.py`
- 最稳定可靠
- 完全复用你的已验证浏览器
- 程序只负责发送和接收

### 注意事项

1. **保持浏览器打开**：程序运行期间不要关闭 Edge
2. **窗口可见**：不要最小化浏览器窗口
3. **端口占用**：确保 9222 端口未被占用
4. **验证过期**：如果验证过期，需要重新完成验证

### 故障排查

**问题1: 连接失败**
```
请确保 Edge 已使用 --remote-debugging-port=9222 启动
```
解决：检查 Edge 启动参数

**问题2: 未找到页面**
```
未找到智谱清言页面
```
解决：确保已在 Edge 中打开 https://chatglm.cn

**问题3: 页面未就绪**
```
未找到输入框，页面可能未就绪
```
解决：等待页面完全加载，或刷新页面

### 自动化改进（未来）

如果人机协作模式稳定运行，可以考虑：
1. 使用 Windows 计划任务定时启动 Edge
2. 使用 VNC 远程保持浏览器会话
3. 购买智谱清言 API 服务（如果有）

---

## 快速开始

```bash
# 1. 启动 Edge（带远程调试）
"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" --remote-debugging-port=9222

# 2. 访问智谱清言，完成验证
# 在 Edge 中打开: https://chatglm.cn/main/alltoolsdetail?lang=zh

# 3. 运行程序
cd zhipuqingyan
python human_in_the_loop.py
```
