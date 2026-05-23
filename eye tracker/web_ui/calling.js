// Phone numbers configuration
const EMERGENCY_NUMBER = '112';
let FAMILY_NUMBER = null;
let FAMILY_NAME = 'Family';

// Dwell tracking
let dwellTimer = null;
let currentCard = null;
let _dwellLocked = false;
let dwellTime = 1.5;
let isDarkMode = false;

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    loadSettings();
    setupDwellTracking();
    setupThemeToggle();
    loadFamilyContact(); // async — calls updateFamilyDisplay when done
});

// ---- Settings --------------------------------------------------------------
function loadSettings() {
    const saved = localStorage.getItem('gazeSettings');
    if (saved) {
        const settings = JSON.parse(saved);
        dwellTime  = settings.dwellTime || 1.5;
        isDarkMode = settings.darkMode  || false;
        if (isDarkMode) {
            document.body.classList.add('dark-mode');
            document.getElementById('theme-toggle').checked = false;
        } else {
            document.body.classList.remove('dark-mode');
            document.getElementById('theme-toggle').checked = true;
        }
    }
    document.documentElement.style.setProperty('--dwell-time', dwellTime + 's');
}

function setupThemeToggle() {
    const toggle = document.getElementById('theme-toggle');
    toggle.addEventListener('change', (e) => {
        isDarkMode = !e.target.checked;
        document.body.classList.toggle('dark-mode', isDarkMode);
        const settings = JSON.parse(localStorage.getItem('gazeSettings') || '{}');
        settings.darkMode = isDarkMode;
        localStorage.setItem('gazeSettings', JSON.stringify(settings));
        playFeedback();
    });
}

// ---- Family contact — loaded from Python (disk file, persists across runs) -
function loadFamilyContact() {
    _waitForPywebview(5000, () => {
        window.pywebview.api.get_family_contact().then(contact => {
            if (contact && contact.phone) {
                FAMILY_NUMBER = contact.phone;
                FAMILY_NAME   = contact.name || 'Family';
            }
            updateFamilyDisplay();
        }).catch(() => updateFamilyDisplay());
    }, () => {
        // pywebview not available — browser testing fallback
        const saved = localStorage.getItem('familyContact');
        if (saved) {
            const c = JSON.parse(saved);
            FAMILY_NUMBER = c.phone || null;
            FAMILY_NAME   = c.name  || 'Family';
        }
        updateFamilyDisplay();
    });
}

// Wait up to maxMs for window.pywebview.api to be ready, then call onReady.
// Calls onFail if it never becomes available.
function _waitForPywebview(maxMs, onReady, onFail) {
    const start = Date.now();
    function check() {
        if (window.pywebview && window.pywebview.api) {
            onReady();
        } else if (Date.now() - start < maxMs) {
            setTimeout(check, 100);
        } else {
            onFail();
        }
    }
    check();
}

function updateFamilyDisplay() {
    const card    = document.querySelector('.family-card');
    const numEl   = document.getElementById('family-number');
    const titleEl = card.querySelector('.call-title');
    titleEl.textContent = `\u{1F46A} Call ${FAMILY_NAME}`;
    if (FAMILY_NUMBER) {
        numEl.textContent = FAMILY_NUMBER;
        numEl.style.color = '';
    } else {
        numEl.textContent = 'Set number in Settings first';
        numEl.style.color = '#ffb347';
    }
}

// ---- Dwell logic -----------------------------------------------------------
function setupDwellTracking() {
    document.querySelectorAll('.call-card, .back-btn').forEach(el => {
        el.addEventListener('mouseenter', () => startDwell(el));
        el.addEventListener('mouseleave', () => stopDwell(el));
        el.addEventListener('click', () => {
            if (_dwellLocked) return;
            _dwellLocked = true;
            stopDwell(el);
            if (el.classList.contains('call-card'))  initiateCall(el.dataset.action);
            else if (el.classList.contains('back-btn')) goBack();
            setTimeout(() => { _dwellLocked = false; }, 1200);
        });
    });
}

function startDwell(el) {
    if (currentCard === el) return;
    stopDwell(currentCard);
    currentCard = el;
    el.classList.add('dwelling');
    dwellTimer = setTimeout(() => {
        if (_dwellLocked) { stopDwell(el); return; }
        _dwellLocked = true;
        if (el.classList.contains('call-card'))     initiateCall(el.dataset.action);
        else if (el.classList.contains('back-btn')) goBack();
        stopDwell(el);
        setTimeout(() => { _dwellLocked = false; }, 1200);
    }, dwellTime * 1000);
}

function stopDwell(el) {
    if (!el) return;
    el.classList.remove('dwelling');
    if (dwellTimer) { clearTimeout(dwellTimer); dwellTimer = null; }
    if (currentCard === el) currentCard = null;
}

// ---- Call logic ------------------------------------------------------------
function initiateCall(type) {
    let number, title;
    if (type === 'emergency') {
        number = EMERGENCY_NUMBER;
        title  = '\uD83D\uDEA8 Calling Emergency...';
    } else if (type === 'family') {
        if (!FAMILY_NUMBER) {
            // Number not loaded yet or not set — show message, don't redirect
            showNotification('Loading contact... please try again in a moment');
            // Try loading again
            loadFamilyContact();
            return;
        }
        number = FAMILY_NUMBER;
        title  = `\u{1F46A} Calling ${FAMILY_NAME}...`;
    }
    showCallModal(title, number);
    makeCall(number);
    playFeedback();
}

function showCallModal(title, number) {
    document.getElementById('modal-title').textContent  = title;
    document.getElementById('modal-number').textContent = number;
    document.getElementById('call-modal').classList.remove('hidden');
}

function hideCallModal() {
    document.getElementById('call-modal').classList.add('hidden');
}

function makeCall(number) {
    console.log('Calling:', number);
    if (window.pywebview) window.pywebview.api.make_call(number);
    setTimeout(hideCallModal, 6000);
}

function cancelCall() {
    hideCallModal();
    playFeedback();
    if (window.pywebview) window.pywebview.api.cancel_call();
}

function goBack() {
    playFeedback();
    if (window.pywebview) window.pywebview.api.go_back_home();
    else window.location.href = 'index.html';
}

function playFeedback() {
    document.body.style.transform = 'scale(0.99)';
    setTimeout(() => { document.body.style.transform = 'scale(1)'; }, 100);
}

function showNotification(msg) {
    const n = document.createElement('div');
    n.style.cssText = 'position:fixed;top:50%;left:50%;transform:translate(-50%,-50%);background:rgba(79,172,254,0.95);color:white;padding:20px 40px;border-radius:15px;font-size:18px;font-weight:600;z-index:10000;box-shadow:0 10px 40px rgba(0,0,0,0.3)';
    n.textContent = msg;
    document.body.appendChild(n);
    setTimeout(() => { n.style.opacity='0'; n.style.transition='opacity 0.3s'; setTimeout(()=>n.remove(),300); }, 2500);
}

// ---- Gaze integration ------------------------------------------------------
window.updateGaze = function(x, y) {
    const els = document.querySelectorAll('.call-card, .back-btn');
    let found = null;
    for (const el of els) {
        const r = el.getBoundingClientRect();
        if (x >= r.left && x <= r.right && y >= r.top && y <= r.bottom) { found = el; break; }
    }
    if (found) startDwell(found);
    else if (currentCard) stopDwell(currentCard);
};

document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        if (!document.getElementById('call-modal').classList.contains('hidden')) cancelCall();
        else goBack();
    }
});

document.addEventListener('contextmenu', (e) => e.preventDefault());
