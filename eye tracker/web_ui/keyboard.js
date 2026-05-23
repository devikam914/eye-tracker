// Keyboard state
let currentMode = 'abc';
let isShiftActive = false;
let isCapsLock = false;
let dwellTime = 1.2; // seconds
let dwellTimer = null;
let currentElement = null;
let isLightMode = false;

// Text composition
let composedText = '';

// Word prediction dictionary
const wordDictionary = {
    'a': ['am', 'are', 'and', 'about', 'all'],
    'b': ['be', 'but', 'by', 'been', 'back'],
    'c': ['can', 'call', 'come', 'could', 'care'],
    'd': ['do', 'doctor', 'down', 'day', "don't"],
    'e': ['eat', 'every', 'even', 'end', 'enough'],
    'f': ['for', 'from', 'feel', 'family', 'find'],
    'g': ['go', 'get', 'good', 'give', 'going'],
    'h': ['have', 'help', 'he', 'her', 'how'],
    'i': ['I', 'is', 'in', 'it', 'if'],
    'j': ['just', 'job', 'join', 'jump', 'joy'],
    'k': ['know', 'keep', 'kind', 'key', 'kick'],
    'l': ['like', 'look', 'let', 'love', 'light'],
    'm': ['me', 'my', 'more', 'make', 'may'],
    'n': ['no', 'not', 'need', 'now', 'never'],
    'o': ['of', 'on', 'or', 'out', 'okay'],
    'p': ['please', 'pain', 'put', 'people', 'place'],
    'q': ['quick', 'quiet', 'question', 'quite', 'quit'],
    'r': ['right', 'rest', 'run', 'really', 'room'],
    's': ['see', 'so', 'some', 'she', 'say'],
    't': ['the', 'to', 'that', 'this', 'thank'],
    'u': ['up', 'us', 'use', 'under', 'until'],
    'v': ['very', 'visit', 'view', 'voice', 'value'],
    'w': ['we', 'will', 'with', 'want', 'water'],
    'x': ['x-ray', 'xylophone', 'xenon', 'xerox', 'xmas'],
    'y': ['you', 'yes', 'your', 'year', 'yet'],
    'z': ['zero', 'zone', 'zoom', 'zip', 'zeal']
};

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    loadSettings();
    setupKeyboardTabs();
    setupKeys();
    setupPhrases();
    setupBottomControls();
    setupActionButtons();
    setupBackButton();
    setupThemeToggle();
    updateCharCount();
});

// Load settings
function loadSettings() {
    const saved = localStorage.getItem('gazeSettings');
    if (saved) {
        const settings = JSON.parse(saved);
        dwellTime = settings.dwellTime || 1.2;
        isLightMode = settings.lightMode || false;
        updateDwellDisplay();
        if (isLightMode) {
            document.body.classList.add('light-mode');
            document.getElementById('theme-toggle').checked = true;
        }
    }
}

function updateDwellDisplay() {
    document.getElementById('dwell-value').textContent = dwellTime.toFixed(1) + 's';
    document.documentElement.style.setProperty('--dwell-time', dwellTime + 's');
}

function increaseDwell() {
    dwellTime = Math.min(3.0, dwellTime + 0.1);
    updateDwellDisplay();
    saveDwellTime();
    playFeedback();
}

function decreaseDwell() {
    dwellTime = Math.max(0.5, dwellTime - 0.1);
    updateDwellDisplay();
    saveDwellTime();
    playFeedback();
}

function saveDwellTime() {
    const settings = JSON.parse(localStorage.getItem('gazeSettings') || '{}');
    settings.dwellTime = dwellTime;
    localStorage.setItem('gazeSettings', JSON.stringify(settings));
    if (window.pywebview && window.pywebview.api) {
        window.pywebview.api.update_dwell_time(dwellTime);
    }
}

function setupThemeToggle() {
    const toggle = document.getElementById('theme-toggle');
    toggle.addEventListener('change', (e) => {
        isLightMode = e.target.checked;
        document.body.classList.toggle('light-mode', isLightMode);
        const settings = JSON.parse(localStorage.getItem('gazeSettings') || '{}');
        settings.lightMode = isLightMode;
        localStorage.setItem('gazeSettings', JSON.stringify(settings));
        playFeedback();
    });
}

function setupKeyboardTabs() {
    document.querySelectorAll('.tab-btn').forEach(tab => {
        tab.addEventListener('mouseenter', () => startDwell(tab));
        tab.addEventListener('mouseleave', () => stopDwell(tab));
        tab.addEventListener('click', () => {
            if (_dwellLocked) return;
            _dwellLocked = true;
            stopDwell(tab);
            switchMode(tab.dataset.mode);
            setTimeout(() => { _dwellLocked = false; }, 1200);
        });
    });
}

function switchMode(mode) {
    currentMode = mode;
    document.querySelectorAll('.tab-btn').forEach(tab => {
        tab.classList.toggle('active', tab.dataset.mode === mode);
    });
    document.querySelectorAll('.keyboard-layout').forEach(layout => {
        layout.classList.toggle('active', layout.id === mode + '-layout');
    });
    playFeedback();
}

function setupKeys() {
    document.querySelectorAll('.key').forEach(key => {
        key.addEventListener('mouseenter', () => startDwell(key));
        key.addEventListener('mouseleave', () => stopDwell(key));
        key.addEventListener('click', () => {
            // Guard: if dwell lock is active, this click came from the JS dwell
            // timer itself (via _activateElement) — don't double-fire.
            // If lock is NOT active, this is a Python Win32 click or mouse click —
            // fire the action and engage the cooldown to block the pending JS timer.
            if (_dwellLocked) return;
            _dwellLocked = true;
            stopDwell(key);
            addCharacter(key.dataset.key);
            setTimeout(() => { _dwellLocked = false; }, 1200);
        });
    });
}

function setupPhrases() {
    document.querySelectorAll('.phrase-card').forEach(phrase => {
        phrase.addEventListener('mouseenter', () => startDwell(phrase));
        phrase.addEventListener('mouseleave', () => stopDwell(phrase));
        phrase.addEventListener('click', () => {
            if (_dwellLocked) return;
            _dwellLocked = true;
            stopDwell(phrase);
            addPhrase(phrase.dataset.text);
            setTimeout(() => { _dwellLocked = false; }, 1200);
        });
    });
}

function setupBottomControls() {
    document.querySelectorAll('.control-btn').forEach(control => {
        control.addEventListener('mouseenter', () => startDwell(control));
        control.addEventListener('mouseleave', () => stopDwell(control));
        control.addEventListener('click', () => {
            if (_dwellLocked) return;
            _dwellLocked = true;
            stopDwell(control);
            _activateElement(control);
            setTimeout(() => { _dwellLocked = false; }, 1200);
        });
    });
}

function setupActionButtons() {
    document.querySelectorAll('.action-btn').forEach(btn => {
        btn.addEventListener('mouseenter', () => startDwell(btn));
        btn.addEventListener('mouseleave', () => stopDwell(btn));
        btn.addEventListener('click', () => {
            if (_dwellLocked) return;
            _dwellLocked = true;
            stopDwell(btn);
            _activateElement(btn);
            setTimeout(() => { _dwellLocked = false; }, 1200);
        });
    });
}

function setupBackButton() {
    const back = document.querySelector('.back-btn-header');
    if (back) {
        back.addEventListener('mouseenter', () => startDwell(back));
        back.addEventListener('mouseleave', () => stopDwell(back));
        back.addEventListener('click', () => {
            if (_dwellLocked) return;
            _dwellLocked = true;
            stopDwell(back);
            goBack();
            setTimeout(() => { _dwellLocked = false; }, 1200);
        });
    }
}

// ---- Dwell logic -----------------------------------------------------------
// We call the action function directly instead of element.click() to avoid
// any double-fire from click event bubbling or Python's DwellClicker.
let _dwellLocked = false;  // prevents re-entry during cooldown

function startDwell(element) {
    if (currentElement === element) return;
    stopDwell(currentElement);
    currentElement = element;
    element.classList.add('dwelling');
    dwellTimer = setTimeout(() => {
        if (_dwellLocked) { stopDwell(element); return; }
        _dwellLocked = true;
        _activateElement(element);
        stopDwell(element);
        // Cooldown matches Python's DWELL_COOLDOWN so both sides stay in sync
        setTimeout(() => { _dwellLocked = false; }, 1200);
    }, dwellTime * 1000);
}

function stopDwell(element) {
    if (!element) return;
    element.classList.remove('dwelling');
    if (dwellTimer) { clearTimeout(dwellTimer); dwellTimer = null; }
    if (currentElement === element) currentElement = null;
}

// Dispatch the correct action for each element type without using .click()
function _activateElement(el) {
    if (el.classList.contains('key'))          { addCharacter(el.dataset.key); return; }
    if (el.classList.contains('phrase-card'))  { addPhrase(el.dataset.text);   return; }
    if (el.classList.contains('tab-btn'))      { switchMode(el.dataset.mode);  return; }
    if (el.classList.contains('prediction-word')) { addPrediction(el.dataset.word); return; }
    if (el.classList.contains('control-btn')) {
        if (el.classList.contains('shift-btn'))  { toggleShift(); return; }
        if (el.classList.contains('space-btn'))  { addSpace();    return; }
        if (el.classList.contains('delete-btn')) { deleteChar();  return; }
    }
    if (el.classList.contains('action-btn')) {
        if (el.classList.contains('speak-btn')) { speakText();  return; }
        if (el.classList.contains('call-btn'))  { goToCalling(); return; }
        if (el.classList.contains('clear-btn')) { clearText();  return; }
        // copy btn
        copyText(); return;
    }
    if (el.classList.contains('back-btn-header')) { goBack(); return; }
    // fallback
    el.click();
}

// ---- Text composition ------------------------------------------------------
function speakKey(char) {
    if ('speechSynthesis' in window) {
        const utterance = new SpeechSynthesisUtterance(char);
        utterance.rate = 1.2; utterance.pitch = 1; utterance.volume = 0.8;
        window.speechSynthesis.cancel();
        window.speechSynthesis.speak(utterance);
    }
}

function addCharacter(char) {
    const textArea = document.getElementById('text-area');
    if (isShiftActive || isCapsLock) char = char.toUpperCase();
    speakKey(char);
    if (document.activeElement === textArea) {
        document.execCommand('insertText', false, char);
    } else {
        textArea.textContent += char;
    }
    if (isShiftActive && !isCapsLock) { isShiftActive = false; updateShiftButton(); }
    updateCharCount(); updatePredictions(); playFeedback();
}

function addPhrase(text) {
    const textArea = document.getElementById('text-area');
    speakKey(text);

    // Special case: "Help" triggers an alarm sound 4 times
    if (text.trim().toLowerCase() === 'help') {
        _playHelpAlarm();
    }

    if (textArea.textContent.trim().length > 0) text = ' ' + text;
    if (document.activeElement === textArea) {
        document.execCommand('insertText', false, text);
    } else {
        textArea.textContent += text;
    }
    updateCharCount(); updatePredictions(); playFeedback();
}

// Play a loud alarm beep 4 times using Web Audio API
function _playHelpAlarm() {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    let count = 0;
    function beep() {
        if (count >= 4) return;
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.connect(gain);
        gain.connect(ctx.destination);
        osc.type = 'square';
        osc.frequency.value = 880;  // high-pitched alarm
        gain.gain.value = 1.0;
        osc.start();
        osc.stop(ctx.currentTime + 0.6);
        osc.onended = () => {
            count++;
            setTimeout(beep, 300);  // 300ms gap between beeps
        };
    }
    beep();
}

function addPrediction(word) {
    const textArea = document.getElementById('text-area');
    const words = textArea.textContent.split(/\s+/);
    speakKey(word);
    if (words.length > 0) { words[words.length - 1] = word; textArea.textContent = words.join(' ') + ' '; }
    else { textArea.textContent = word + ' '; }
    updateCharCount(); updatePredictions(); playFeedback();
}

function addSpace() {
    const textArea = document.getElementById('text-area');
    speakKey('space');
    if (document.activeElement === textArea) { document.execCommand('insertText', false, ' '); }
    else { textArea.textContent += ' '; }
    updateCharCount(); updatePredictions(); playFeedback();
}

function deleteChar() {
    const textArea = document.getElementById('text-area');
    speakKey('delete');
    if (document.activeElement === textArea) { document.execCommand('delete'); }
    else { textArea.textContent = textArea.textContent.slice(0, -1); }
    updateCharCount(); updatePredictions(); playFeedback();
}

function toggleShift() {
    if (isCapsLock) { isCapsLock = false; isShiftActive = false; }
    else if (isShiftActive) { isCapsLock = true; }
    else { isShiftActive = true; }
    updateShiftButton(); playFeedback();
}

function updateShiftButton() {
    const shiftBtn = document.querySelector('.shift-btn');
    shiftBtn.classList.toggle('active', isCapsLock || isShiftActive);
}

function updateCharCount() {
    const textArea = document.getElementById('text-area');
    const count = textArea.textContent.length;
    document.getElementById('char-count').textContent = count + ' char' + (count !== 1 ? 's' : '');
}

function updatePredictions() {
    const textArea = document.getElementById('text-area');
    const words = textArea.textContent.split(/\s+/);
    const lastWord = words[words.length - 1].toLowerCase();
    const container = document.getElementById('word-predictions');
    container.innerHTML = '';
    if (!lastWord.length) return;
    let predictions = (wordDictionary[lastWord[0]] || [])
        .filter(w => w.toLowerCase().startsWith(lastWord) && w.toLowerCase() !== lastWord)
        .slice(0, 5);
    predictions.forEach(word => {
        const btn = document.createElement('button');
        btn.className = 'prediction-word';
        btn.textContent = word;
        btn.dataset.word = word;
        btn.addEventListener('mouseenter', () => startDwell(btn));
        btn.addEventListener('mouseleave', () => stopDwell(btn));
        btn.addEventListener('click',      () => addPrediction(word));
        container.appendChild(btn);
    });
}

// ---- Text actions ----------------------------------------------------------
function copyText() {
    const text = document.getElementById('text-area').textContent;
    if (!text.length) return;
    navigator.clipboard.writeText(text).then(() => showNotification('Text copied to clipboard!')).catch(console.error);
    playFeedback();
}

function speakText() {
    const text = document.getElementById('text-area').textContent;
    if (!text.length) return;
    if ('speechSynthesis' in window) {
        const u = new SpeechSynthesisUtterance(text);
        u.rate = 0.9; u.pitch = 1; u.volume = 1;
        window.speechSynthesis.cancel();
        window.speechSynthesis.speak(u);
        showNotification('Speaking...');
    } else { showNotification('Text-to-speech not supported'); }
    playFeedback();
}

function clearText() {
    document.getElementById('text-area').textContent = '';
    updateCharCount(); playFeedback();
}

function showNotification(message) {
    const n = document.createElement('div');
    n.style.cssText = 'position:fixed;top:50%;left:50%;transform:translate(-50%,-50%);background:rgba(79,172,254,0.95);color:white;padding:20px 40px;border-radius:15px;font-size:18px;font-weight:600;z-index:10000;box-shadow:0 10px 40px rgba(0,0,0,0.3)';
    n.textContent = message;
    document.body.appendChild(n);
    setTimeout(() => { n.style.opacity = '0'; n.style.transition = 'opacity 0.3s ease'; setTimeout(() => n.remove(), 300); }, 2000);
}

function goBack() {
    playFeedback();
    if (window.pywebview) { window.pywebview.api.go_back_home(); }
    else { window.location.href = 'index.html'; }
}

function goToCalling() {
    playFeedback();
    if (window.pywebview) { window.pywebview.api.handle_action('calling'); }
    else { window.location.href = 'calling.html'; }
}

function playFeedback() {
    document.body.style.transform = 'scale(0.998)';
    setTimeout(() => { document.body.style.transform = 'scale(1)'; }, 50);
}

// Gaze tracking integration
function updateGazePosition(x, y) {
    const elements = [
        ...document.querySelectorAll('.key'),
        ...document.querySelectorAll('.phrase-card'),
        ...document.querySelectorAll('.tab-btn'),
        ...document.querySelectorAll('.control-btn'),
        ...document.querySelectorAll('.action-btn'),
        ...document.querySelectorAll('.prediction-word'),
        ...document.querySelectorAll('.back-btn-header')
    ];
    let found = null;
    for (const el of elements) {
        const r = el.getBoundingClientRect();
        if (x >= r.left && x <= r.right && y >= r.top && y <= r.bottom) { found = el; break; }
    }
    if (found) { startDwell(found); }
    else if (currentElement) { stopDwell(currentElement); }
}
window.updateGaze = updateGazePosition;

// Keyboard shortcuts
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') { goBack(); }
    else if (e.key === 'Backspace' && document.activeElement !== document.getElementById('text-area')) { e.preventDefault(); deleteChar(); }
    else if (e.ctrlKey && e.key === 'c' && document.activeElement !== document.getElementById('text-area')) { e.preventDefault(); copyText(); }
    else if (e.ctrlKey && e.key === 's') { e.preventDefault(); speakText(); }
});

document.addEventListener('contextmenu', (e) => e.preventDefault());

setInterval(() => {
    const t = document.getElementById('text-area');
    if (t.textContent.length > 0) localStorage.setItem('gazeKeyboardText', t.textContent);
}, 5000);

window.addEventListener('load', () => {
    const saved = localStorage.getItem('gazeKeyboardText');
    if (saved) { document.getElementById('text-area').textContent = saved; updateCharCount(); }
});
