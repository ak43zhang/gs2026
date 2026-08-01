// 测试前端传的 time 格式
const timeStr = '09:30:42';
const url = 'http://example.com/api?time=' + timeStr;
console.log('URL:', url);

// 检查是否有编码问题
console.log('encodeURIComponent:', encodeURIComponent(timeStr));
