// 测试 JavaScript 的 null/undefined 比较
const timeStr = undefined;  // 前端可能传 undefined
const _lastCombineTime = null;  // 上次查询无时间

const timeChanged = (timeStr || null) !== _lastCombineTime;
console.log('timeStr:', timeStr);
console.log('(timeStr || null):', timeStr || null);
console.log('_lastCombineTime:', _lastCombineTime);
console.log('timeChanged:', timeChanged);

// 另一个场景
const timeStr2 = '09:30:42';
const _lastCombineTime2 = null;
const timeChanged2 = (timeStr2 || null) !== _lastCombineTime2;
console.log('\ntimeStr2:', timeStr2);
console.log('timeChanged2:', timeChanged2);
