"""Insert effect tracking frontend code into monitor.html"""

MONITOR_HTML = r'F:\pyworkspace2026\gs2026\src\gs2026\dashboard2\templates\monitor.html'

with open(MONITOR_HTML, 'r', encoding='utf-8') as f:
    content = f.read()

changes = 0

# 1. Add effect button next to gear icon in title bar
# Find the gear span and add effect button after it
old_gear = "toggleBpEditor()\">"
if 'showEffectPanel' not in content and old_gear in content:
    # Find the full gear span pattern
    idx = content.index(old_gear)
    # Find the closing </span> after it
    end_idx = content.index('</span>', idx) + len('</span>')
    insert_pos = end_idx
    effect_btn = ' <span style="cursor:pointer;font-size:13px;margin-left:6px;color:#1565c0;" onclick="showEffectPanel()" title="效果追踪">\U0001f4ca效果</span>'
    content = content[:insert_pos] + effect_btn + content[insert_pos:]
    changes += 1
    print('OK: added effect button in title bar')

# 2. Add effect modal HTML before </body>
if 'bp-effect-overlay' not in content:
    effect_modal = '''
    <!-- 效果追踪弹窗 -->
    <div id="bp-effect-overlay" class="bp-modal-overlay" onclick="if(event.target===this)this.classList.remove('active')">
        <div class="bp-modal" style="width:600px;">
            <div class="bp-modal-header">
                <span>效果追踪</span>
                <button class="bp-modal-close" onclick="document.getElementById('bp-effect-overlay').classList.remove('active')">✕</button>
            </div>
            <div style="margin-bottom:12px;">
                <button class="effect-gen-btn" id="bp-gen-btn" onclick="generateEffects()">生成今日效果</button>
                <span class="effect-gen-info" id="bp-gen-info"></span>
            </div>
            <div class="effect-section-label">效果统计</div>
            <div id="effect-stats-body"><div style="color:#ccc;font-size:12px;">点击「生成今日效果」开始计算</div></div>
            <div class="effect-section-label">明细结果</div>
            <div class="effect-detail-wrap">
                <table class="effect-detail-table">
                    <thead><tr><th>时间</th><th>代码</th><th>名称</th><th>信号价</th><th>5m</th><th>15m</th><th>30m</th><th>收盘</th></tr></thead>
                    <tbody id="effect-detail-body"><tr><td colspan="8" style="color:#ccc;text-align:center;padding:20px;">点击「生成今日效果」开始计算</td></tr></tbody>
                </table>
            </div>
        </div>
    </div>
'''
    body_close = '</body>'
    idx = content.rindex(body_close)
    content = content[:idx] + effect_modal + '\n' + content[idx:]
    changes += 1
    print('OK: added effect modal HTML')

# 3. Add JS functions before </script>
if 'function showEffectPanel' not in content:
    effect_js = '''
        function showEffectPanel() {
            var overlay = document.getElementById('bp-effect-overlay');
            if (overlay) overlay.classList.add('active');
        }

        function generateEffects() {
            var _bpDate = getSelectedDate();
            if (!_bpDate) {
                var _now = new Date();
                _bpDate = _now.getFullYear() + String(_now.getMonth()+1).padStart(2,'0') + String(_now.getDate()).padStart(2,'0');
            }
            var btn = document.getElementById('bp-gen-btn');
            var info = document.getElementById('bp-gen-info');
            btn.textContent = '生成中...'; btn.disabled = true;
            info.textContent = '';

            fetch('/api/monitor/buy-points/generate-effects', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({date: _bpDate})
            })
            .then(function(r){ return r.json(); })
            .then(function(res){
                if (res.success) {
                    info.textContent = '已生成: ' + res.filled + '条 / 跳过: ' + res.skipped + '条';
                    renderEffectStats(res.stats || {});
                    renderEffectDetails(res.details || []);
                    btn.textContent = '✓ 完成';
                } else {
                    info.textContent = '失败: ' + (res.message || '未知错误');
                    btn.textContent = '生成失败';
                }
                setTimeout(function(){ btn.textContent = '生成今日效果'; btn.disabled = false; }, 3000);
            })
            .catch(function(e){
                console.error('[EFFECT]', e);
                info.textContent = '网络错误';
                btn.textContent = '生成今日效果'; btn.disabled = false;
            });
        }

        function renderEffectStats(stats) {
            var periods = [
                {key:'5m', label:'5分钟'},
                {key:'15m', label:'15分钟'},
                {key:'30m', label:'30分钟'},
                {key:'close', label:'收盘'}
            ];
            var html = '';
            periods.forEach(function(p) {
                var s = stats[p.key] || {};
                var avgVal = s.avg_return || 0;
                var avgCls = avgVal > 0 ? 'positive' : avgVal < 0 ? 'negative' : 'neutral';
                var rateCls = (s.success_rate || 0) >= 50 ? 'positive' : 'negative';
                html += '<div class="effect-stats-row">';
                html += '<span class="effect-period">' + p.label + '</span>';
                html += '<span class="effect-metric">总<span class="val neutral">' + (s.total||0) + '</span></span>';
                html += '<span class="effect-metric">成功<span class="val positive">' + (s.success||0) + '</span></span>';
                html += '<span class="effect-metric">胜率<span class="val ' + rateCls + '">' + (s.success_rate||0) + '%</span></span>';
                html += '<span class="effect-metric">均收<span class="val ' + avgCls + '">' + (avgVal>0?'+':'') + avgVal + '%</span></span>';
                html += '</div>';
            });
            document.getElementById('effect-stats-body').innerHTML = html;
        }

        function renderEffectDetails(details) {
            var html = '';
            details.forEach(function(d) {
                html += '<tr>';
                html += '<td>' + (d.time||'') + '</td>';
                html += '<td>' + (d.code||'') + '</td>';
                html += '<td>' + (d.name||'') + '</td>';
                html += '<td>' + (d.signal_price ? '¥'+d.signal_price : '-') + '</td>';
                var vals = [d.after_5m, d.after_15m, d.after_30m, d.after_close];
                vals.forEach(function(v) {
                    var color = v === null || v === undefined ? '#ccc' : v > 0 ? '#e53935' : v < 0 ? '#43a047' : '#333';
                    var text = v === null || v === undefined ? '-' : (v > 0 ? '+' : '') + v.toFixed(2) + '%';
                    html += '<td style="color:' + color + ';">' + text + '</td>';
                });
                html += '</tr>';
            });
            if (!details.length) {
                html = '<tr><td colspan="8" style="color:#ccc;text-align:center;padding:20px;">无数据</td></tr>';
            }
            document.getElementById('effect-detail-body').innerHTML = html;
        }
'''
    # Find last </script> and insert before it
    last_script = content.rindex('</script>')
    content = content[:last_script] + effect_js + '\n' + content[last_script:]
    changes += 1
    print('OK: added effect JS functions')

if changes > 0:
    with open(MONITOR_HTML, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f'DONE: {changes} changes written')
else:
    print('SKIP: all changes already exist')
