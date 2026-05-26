# 手动获取 Cookies 完整流程

## 最简单的方法：让我帮你创建文件

### 步骤1: 在 Edge 中获取 Cookies JSON

1. **打开 Edge 浏览器**
2. **访问**: https://chatglm.cn/main/alltoolsdetail?lang=zh
3. **完成 Access Verification 验证**（如果出现）
4. **按 F12 打开开发者工具**
5. **切换到"控制台(Console)"标签**
6. **粘贴以下代码并按回车**:

```javascript
const cookies = document.cookie.split(';').map(c => {
    const [name, ...valueParts] = c.trim().split('=');
    return {
        name: name,
        value: valueParts.join('='),
        domain: '.chatglm.cn',
        path: '/',
        expires: -1,
        httpOnly: false,
        secure: true,
        sameSite: 'Lax'
    };
});
JSON.stringify(cookies, null, 2)
```

7. **复制输出的 JSON**（从 `[` 开始到 `]` 结束）

### 步骤2: 发送给我

将复制的 JSON 粘贴到聊天中，格式如下：

```
请帮我创建 cookies 文件：

[
  {
    "name": "cookie1",
    "value": "value1",
    "domain": ".chatglm.cn",
    "path": "/",
    "expires": -1,
    "httpOnly": false,
    "secure": true,
    "sameSite": "Lax"
  },
  {
    "name": "cookie2",
    "value": "value2",
    ...
  }
]
```

### 步骤3: 我帮你创建文件

我会将 cookies 保存到：
```
F:\pyworkspace2026\gs2026\src\gs2026\analysis\worker\message\zhipuqingyan\cookies\chatglm_cookies.json
```

### 步骤4: 运行程序

配置使用 Edge：
```json
{
  "common": {
    "browser_type": "edge",
    "edge_path": "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe"
  }
}
```

运行：
```python
from gs2026.analysis.worker.message.zhipuqingyan import analysis_event_driven
analysis_event_driven(['2026-05-20'])
```

---

## 备选方法：直接编辑文件

如果你不想发送给我，可以手动创建文件：

1. 创建文件夹（如果不存在）：
   ```
   F:\pyworkspace2026\gs2026\src\gs2026\analysis\worker\message\zhipuqingyan\cookies\
   ```

2. 创建文件 `chatglm_cookies.json`

3. 粘贴从浏览器获取的 JSON

4. 保存文件

---

## 验证 Cookies 是否有效

运行验证脚本：
```bash
cd F:\pyworkspace2026\gs2026\src\gs2026\analysis\worker\message\zhipuqingyan
python verify_cookies.py
```

如果显示 "✓ Cookies 有效"，就可以正常使用了。

---

## 常见问题

### Q1: 如何找到 Edge 路径？
在 Edge 地址栏输入 `edge://version/`，查看"可执行文件路径"

### Q2: Cookies 多久会过期？
通常几天到几周，过期后需要重新获取

### Q3: 可以多个机器共用吗？
可以，复制 cookies 文件到其他机器即可
