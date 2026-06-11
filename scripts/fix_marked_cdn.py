"""Fix: move marked.js to local, fix CDN blocking issue"""

with open(r'F:\pyworkspace2026\gs2026\src\gs2026\dashboard2\templates\profile.html', encoding='utf-8') as f:
    content = f.read()

changes = 0

# 1. Remove CDN marked.js, add inline fallback
old_cdn = '<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>\n<script>'
new_inline = """<script>
// marked.js fallback: simple markdown renderer if CDN unavailable
if (typeof marked === 'undefined') {
    var marked = {
        parse: function(text) {
            if (!text) return '';
            return text
                .replace(/&/g, '&')
                .replace(/</g, '<')
                .replace(/>/g, '>')
                .replace(/^### (.+)$/gm, '<h3>$1</h3>')
                .replace(/^## (.+)$/gm, '<h2>$1</h2>')
                .replace(/^# (.+)$/gm, '<h1>$1</h1>')
                .replace(/\\*\\*(.+?)\\*\\*/g, '<b>$1</b>')
                .replace(/`([^`]+)`/g, '<code style="background:#f5f5f5;padding:1px 4px;border-radius:3px;">$1</code>')
                .replace(/^- (.+)$/gm, '<li>$1</li>')
                .replace(/(<li>.*<\\/li>)/gs, '<ul>$1</ul>')
                .replace(/\\n/g, '<br>');
        }
    };
}"""

# Actually let's try a simpler approach - just load marked async and define functions independently
new_inline2 = """<script>
// Load marked.js asynchronously (non-blocking)
(function(){
    var s = document.createElement('script');
    s.src = 'https://cdn.jsdelivr.net/npm/marked/marked.min.js';
    s.async = true;
    s.onerror = function() {
        // Fallback: simple markdown renderer
        window.marked = {
            parse: function(text) {
                if (!text) return '';
                return text
                    .replace(/&/g, '&').replace(/</g, '<').replace(/>/g, '>')
                    .replace(/^### (.+)$/gm, '<h3>$1</h3>')
                    .replace(/^## (.+)$/gm, '<h2>$1</h2>')
                    .replace(/^# (.+)$/gm, '<h1>$1</h1>')
                    .replace(/\\*\\*(.+?)\\*\\*/g, '<b>$1</b>')
                    .replace(/`([^`]+)`/g, '<code style="background:#f5f5f5;padding:1px 4px;border-radius:3px;">$1</code>')
                    .replace(/^- (.+)$/gm, '• $1<br>')
                    .replace(/\\n/g, '<br>');
            }
        };
    };
    document.head.appendChild(s);
})();"""

if old_cdn in content:
    content = content.replace(old_cdn, new_inline2)
    changes += 1
    print('[1] Replaced CDN with async loader + fallback')
else:
    print('[1] CDN marker not found')

with open(r'F:\pyworkspace2026\gs2026\src\gs2026\dashboard2\templates\profile.html', 'w', encoding='utf-8') as f:
    f.write(content)

print(f'Done: {changes} changes')
