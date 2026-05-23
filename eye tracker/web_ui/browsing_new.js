// State
let currentMode = 'abc';
let searchText = '';
let dwellTime = 1.5;
let dwellTimer = null;
let currentElement = null;
let _dwellLocked = false;
let darkMode = false;

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    setupKeyboard();
    setupAllDwellListeners();
    loadSettings();
});

// ---- Settings --------------------------------------------------------------
function loadSettings() {
    const saved = localStorage.getItem('gazeSettings');
    if (saved) {
        const settings = JSON.parse(saved);
        dwellTime = settings.dwellTime || 1.5;
        darkMode  = settings.darkMode  || false;
        document.getElementById('dwell-value').textContent = dwellTime.toFixed(1);
        document.getElementById('dark-mode-toggle').checked = darkMode;
        if (darkMode) document.body.classList.add('dark-mode');
    }
    document.documentElement.style.setProperty('--dwell-time', dwellTime + 's');
}

function saveSettings() {
    const saved = localStorage.getItem('gazeSettings');
    let settings = saved ? JSON.parse(saved) : {};
    settings.dwellTime = dwellTime;
    settings.darkMode  = darkMode;
    localStorage.setItem('gazeSettings', JSON.stringify(settings));
    if (window.pywebview && window.pywebview.api) {
        window.pywebview.api.update_dwell_time(dwellTime);
    }
}

function toggleDarkMode() {
    darkMode = document.getElementById('dark-mode-toggle').checked;
    document.body.classList.toggle('dark-mode', darkMode);
    saveSettings();
    playFeedback();
}

function increaseDwell() {
    if (dwellTime < 5.0) {
        dwellTime += 0.5;
        document.getElementById('dwell-value').textContent = dwellTime.toFixed(1);
        document.documentElement.style.setProperty('--dwell-time', dwellTime + 's');
        saveSettings();
        playFeedback();
    }
}

function decreaseDwell() {
    if (dwellTime > 0.5) {
        dwellTime -= 0.5;
        document.getElementById('dwell-value').textContent = dwellTime.toFixed(1);
        document.documentElement.style.setProperty('--dwell-time', dwellTime + 's');
        saveSettings();
        playFeedback();
    }
}

// ---- Dwell logic -----------------------------------------------------------
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
        setTimeout(() => { _dwellLocked = false; }, 1200);
    }, dwellTime * 1000);
}

function stopDwell(element) {
    if (!element) return;
    element.classList.remove('dwelling');
    if (dwellTimer) { clearTimeout(dwellTimer); dwellTimer = null; }
    if (currentElement === element) currentElement = null;
}

function _activateElement(el) {
    if (el.classList.contains('key')) {
        el.classList.add('pressed');
        setTimeout(() => el.classList.remove('pressed'), 200);
        handleKeyPress(el.dataset.key);
        return;
    }
    if (el.classList.contains('tab-btn') && el.dataset.mode) { switchMode(el.dataset.mode); return; }
    if (el.classList.contains('search-btn'))      { performSearch();  return; }
    if (el.classList.contains('speak-btn'))        { speakText();      return; }
    if (el.classList.contains('call-btn'))         { goToCalling();    return; }
    if (el.classList.contains('back-btn'))         { goBackToHome();   return; }
    if (el.classList.contains('clear-search-btn')) { clearSearch();    return; }
    if (el.classList.contains('quick-link'))       { el.click();       return; }
    if (el.classList.contains('dwell-btn')) {
        el.textContent.trim() === '+' ? increaseDwell() : decreaseDwell();
        return;
    }
    el.click();
}

// Wire mouseenter/mouseleave + click guard on every interactive element
function setupAllDwellListeners() {
    const sel = '.key, .search-btn, .speak-btn, .call-btn, .quick-link, .back-btn, .tab-btn, .clear-search-btn, .dwell-btn';
    document.querySelectorAll(sel).forEach(el => {
        el.addEventListener('mouseenter', () => startDwell(el));
        el.addEventListener('mouseleave', () => stopDwell(el));
        // Click guard: native Win32 click or mouse click — fire action + engage cooldown
        el.addEventListener('click', () => {
            if (_dwellLocked) return;
            _dwellLocked = true;
            stopDwell(el);
            _activateElement(el);
            setTimeout(() => { _dwellLocked = false; }, 1200);
        });
    });
}

// Setup keyboard click handlers (for mouse users)
function setupKeyboard() {
    document.querySelectorAll('.key').forEach(key => {
        key.addEventListener('click', () => {
            if (_dwellLocked) return;
            _dwellLocked = true;
            stopDwell(key);
            key.classList.add('pressed');
            setTimeout(() => key.classList.remove('pressed'), 200);
            handleKeyPress(key.dataset.key);
            setTimeout(() => { _dwellLocked = false; }, 1200);
        });
    });
}

// ---- Key handling ----------------------------------------------------------
function handleKeyPress(key) {
    const input = document.getElementById('search-input');
    if (key === 'DELETE')     { searchText = searchText.slice(0, -1); speakKey('delete'); }
    else if (key === 'SPACE') { searchText += ' ';                    speakKey('space');  }
    else                      { searchText += key.toLowerCase();      speakKey(key);      }
    input.value = searchText;
    playFeedback();
}

function speakKey(char) {
    if ('speechSynthesis' in window) {
        const u = new SpeechSynthesisUtterance(char);
        u.rate = 1.2; u.pitch = 1; u.volume = 0.8;
        window.speechSynthesis.cancel();
        window.speechSynthesis.speak(u);
    }
}

function switchMode(mode) {
    currentMode = mode;
    document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.toggle('active', btn.dataset.mode === mode));
    document.querySelectorAll('.keyboard-layout').forEach(l => l.classList.remove('active'));
    document.getElementById(`${mode}-layout`).classList.add('active');
    playFeedback();
}

// ---- Actions ---------------------------------------------------------------
function clearSearch() {
    searchText = '';
    document.getElementById('search-input').value = '';
    playFeedback();
}

function speakText() {
    if (!searchText.trim()) return;
    if ('speechSynthesis' in window) {
        window.speechSynthesis.cancel();
        const u = new SpeechSynthesisUtterance(searchText);
        u.rate = 0.9; u.pitch = 1; u.volume = 1;
        const btn = document.querySelector('.speak-btn');
        btn.classList.add('speaking');
        u.onend = u.onerror = () => btn.classList.remove('speaking');
        window.speechSynthesis.speak(u);
        playFeedback();
    }
}

function performSearch() {
    if (!searchText.trim()) return;
    const url = `https://www.google.com/search?q=${encodeURIComponent(searchText)}`;
    if (window.pywebview) { window.pywebview.api.open_url(url); }
    else { window.open(url, '_blank'); }
    playFeedback();
}

function quickSearch(query) {
    searchText = query;
    document.getElementById('search-input').value = query;
    const url = `https://www.google.com/search?q=${encodeURIComponent(query)}`;
    if (window.pywebview) { window.pywebview.api.open_url(url); }
    else { window.open(url, '_blank'); }
    playFeedback();
}

function goBackToHome() {
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
    document.body.style.transform = 'scale(0.995)';
    setTimeout(() => { document.body.style.transform = 'scale(1)'; }, 100);
}

// ---- Gaze integration ------------------------------------------------------
function updateGazePosition(x, y) {
    const els = document.querySelectorAll('.key, .search-btn, .speak-btn, .call-btn, .quick-link, .back-btn, .tab-btn, .clear-search-btn, .dwell-btn');
    let found = null;
    for (const el of els) {
        const r = el.getBoundingClientRect();
        if (x >= r.left && x <= r.right && y >= r.top && y <= r.bottom) { found = el; break; }
    }
    if (found) { startDwell(found); }
    else if (currentElement) { stopDwell(currentElement); }
}
window.updateGaze = updateGazePosition;

document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape')         { goBackToHome(); }
    else if (e.key === 'Enter')     { performSearch(); }
    else if (e.key === 'Backspace') { e.preventDefault(); handleKeyPress('DELETE'); }
});

document.addEventListener('contextmenu', (e) => e.preventDefault());
