/**
 * TTS Debug Helper
 * Run this in browser console to debug TTS issues
 */

const TTSDebug = {
    /**
     * Test MD5 hash function
     */
    testMD5: function() {
        const testCases = [
            { text: "每日涨停板复盘报告", expected: "d41d8cd98f00b204e9800998ecf8427e" },
            { text: "第一部分：市场概况", expected: null }
        ];
        
        console.log('=== MD5 Test ===');
        testCases.forEach(tc => {
            const hash = ReportReader._getTextHash(tc.text);
            console.log(`Text: "${tc.text}"`);
            console.log(`Hash: ${hash}`);
            console.log(`Length: ${hash.length}`);
            if (tc.expected) {
                console.log(`Expected: ${tc.expected}`);
                console.log(`Match: ${hash === tc.expected}`);
            }
            console.log('---');
        });
    },
    
    /**
     * Check segment hashes
     */
    checkSegments: function() {
        console.log('=== Segment Hash Check ===');
        console.log(`Total segments: ${ReportReader.segments.length}`);
        console.log(`Current strategy: ${ReportReader.segmentStrategy}`);
        
        for (let i = 0; i < Math.min(5, ReportReader.segments.length); i++) {
            const seg = ReportReader.segments[i];
            const hash = ReportReader._getTextHash(seg.text);
            const hasAudio = !!seg.audio_url;
            
            console.log(`[${i}] ${hasAudio ? '✓' : '✗'} ${seg.text.substring(0, 30)}...`);
            console.log(`    Hash: ${hash}`);
            console.log(`    Has audio_url: ${hasAudio}`);
            if (seg.audio_url) {
                console.log(`    URL: ${seg.audio_url.substring(0, 50)}...`);
            }
        }
    },
    
    /**
     * Check specific segment
     */
    checkSegment: function(index) {
        if (index >= ReportReader.segments.length) {
            console.error(`Index ${index} out of range`);
            return;
        }
        
        const seg = ReportReader.segments[index];
        const hash = ReportReader._getTextHash(seg.text);
        
        console.log(`=== Segment [${index}] ===`);
        console.log(`Text: ${seg.text}`);
        console.log(`Hash: ${hash}`);
        console.log(`Has audio_url: ${!!seg.audio_url}`);
        console.log(`audio_url: ${seg.audio_url || 'N/A'}`);
        console.log(`ready: ${seg.ready}`);
        console.log(`duration: ${seg.duration || 'N/A'}`);
    },
    
    /**
     * Reset and reload
     */
    resetAndReload: function() {
        console.log('=== Resetting strategy ===');
        ReportReader.resetStrategy();
        console.log('Reloading content...');
        ReportReader.loadContent(ReportReader.currentReport.type, ReportReader.currentReport.filename);
    },
    
    /**
     * Test play sequence
     */
    testPlaySequence: function() {
        console.log('=== Testing Play Sequence ===');
        let current = 0;
        const max = Math.min(5, ReportReader.segments.length);
        
        while (current < max) {
            const seg = ReportReader.segments[current];
            const hasAudio = !!seg.audio_url;
            
            console.log(`[${current}] ${hasAudio ? 'PLAY' : 'SKIP'}: ${seg.text.substring(0, 30)}...`);
            
            if (hasAudio) {
                console.log(`    -> Will play audio`);
            } else {
                console.log(`    -> NO AUDIO, will skip!`);
            }
            
            current++;
        }
    },
    
    /**
     * Force prepare TTS
     */
    forcePrepare: function() {
        console.log('=== Force Prepare TTS ===');
        ReportReader.prepareTTS();
    }
};

// Expose to global
window.TTSDebug = TTSDebug;

console.log('TTS Debug Helper loaded. Available commands:');
console.log('  TTSDebug.testMD5() - Test MD5 hash function');
console.log('  TTSDebug.checkSegments() - Check first 5 segments');
console.log('  TTSDebug.checkSegment(n) - Check specific segment');
console.log('  TTSDebug.resetAndReload() - Reset strategy and reload');
console.log('  TTSDebug.testPlaySequence() - Test play sequence');
console.log('  TTSDebug.forcePrepare() - Force prepare TTS');
