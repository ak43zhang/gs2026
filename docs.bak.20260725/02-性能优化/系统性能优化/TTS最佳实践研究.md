# TTS阅读最佳实践研究

## 问题分析
当前问题：只读第一行，后面不继续

## 市面上优秀方案

### 1. 微信读书 / 喜马拉雅
**特点**:
- 预加载下一段音频（边读边缓存）
- 无缝衔接播放（当前段快结束时预加载下一段）
- 段落间有自然停顿
- 支持后台播放

**技术方案**:
```javascript
// 双音频对象交替播放
audio1.play();  // 当前段
audio2.preload(); // 预加载下一段

audio1.onended = () => {
    audio2.play();  // 无缝切换
    audio1 = audio3; // 准备下下段
};
```

### 2. Kindle / Apple Books
**特点**:
- 整章预生成（不是逐段）
- 一个音频文件包含整章内容
- 通过时间戳定位当前阅读位置
- 高亮同步跟随音频

**技术方案**:
```javascript
// 整章一个音频
audio.src = 'chapter1.mp3';
audio.currentTime = startTime; // 跳转到指定位置

// 定时器同步高亮
setInterval(() => {
    const currentTime = audio.currentTime;
    const currentSegment = findSegmentByTime(currentTime);
    highlightSegment(currentSegment);
}, 100);
```

### 3. 浏览器TTS API (Web Speech API)
**特点**:
- 使用系统TTS引擎
- 无需网络请求
- 支持SSML标记
- 逐句/逐词高亮

**技术方案**:
```javascript
const utterance = new SpeechSynthesisUtterance(text);
utterance.onboundary = (event) => {
    // 每个词/句的边界事件
    highlightWord(event.charIndex);
};
speechSynthesis.speak(utterance);
```

## 推荐方案

### 方案A: 双音频预加载（推荐）
**优点**: 无缝衔接、用户体验好
**缺点**: 实现复杂、内存占用稍高

```javascript
class TTSSequentialPlayer {
    constructor() {
        this.currentAudio = new Audio();
        this.nextAudio = new Audio();
        this.currentIndex = 0;
    }
    
    playSegment(index) {
        // 播放当前
        this.currentAudio.src = getAudioUrl(index);
        this.currentAudio.play();
        
        // 预加载下一段
        if (index + 1 < totalSegments) {
            this.nextAudio.src = getAudioUrl(index + 1);
            this.nextAudio.preload = 'auto';
        }
        
        this.currentAudio.onended = () => {
            // 无缝切换
            [this.currentAudio, this.nextAudio] = [this.nextAudio, this.currentAudio];
            this.currentIndex++;
            this.playSegment(this.currentIndex);
        };
    }
}
```

### 方案B: 单音频顺序播放（当前改进版）
**优点**: 简单可靠、易于调试
**缺点**: 段间有短暂停顿

```javascript
// 关键改进点
1. 确保audio.onended正确触发
2. 播放完成后再加载下一段
3. 添加状态机管理播放流程
4. 错误时自动重试或跳过
```

### 方案C: 整段预生成（最简单）
**优点**: 最简单、无段间停顿
**缺点**: 首次加载慢、不支持大文件

```javascript
// 一次性生成所有音频
Promise.all(segments.map((seg, i) => 
    generateAudio(seg.text, i)
)).then(() => {
    // 所有音频就绪后播放
    playSequential(0);
});
```

## 当前问题诊断

### 可能原因
1. `audio.onended` 未触发
2. `_onAudioEnded` 中条件判断错误
3. `_finishPlayback` 被过早调用
4. 队列处理逻辑有bug

### 调试建议
```javascript
// 添加详细日志
console.log('Play started:', index);
console.log('Audio src:', audio.src);
console.log('Audio duration:', audio.duration);
console.log('onended setup:', !!audio.onended);

audio.onended = function() {
    console.log('Audio ended fired:', index);
    console.log('Current segment at ended:', this.currentSegment);
    console.log('isPlaying:', this.isPlaying);
};
```

## 简化方案

鉴于当前复杂性，建议采用**简化方案B+**:

```javascript
// 核心原则
1. 一个音频对象
2. 播放完成后再加载下一段
3. 状态机控制流程
4. 详细日志便于调试

// 状态机
const State = {
    IDLE: 'idle',
    GENERATING: 'generating',
    LOADING: 'loading',
    PLAYING: 'playing',
    ENDED: 'ended'
};

// 简化流程
play(index) {
    this.state = State.GENERATING;
    generateAudio(index).then(() => {
        this.state = State.LOADING;
        return loadAudio(index);
    }).then(() => {
        this.state = State.PLAYING;
        return playAudio();
    }).then(() => {
        this.state = State.ENDED;
        if (shouldContinue) {
            this.play(index + 1);
        }
    });
}
```
