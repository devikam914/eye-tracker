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
    'd': ['do', 'doctor', 'down', 'day', 'don\'t'],
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

// Update dwell display
function updateDwellDisplay() {
    document.getElementById('dwell-value').textContent = dwellTime.toFixed(1) + 's';
    document.documentElement.style.setProperty('--dwell-time', dwellTime + 's');
}

// Increase dwell time
function increaseDwell() {
    dwellTime = Math.min(3.0, dwellTime + 0.1);
    updateDwellDisplay();
    saveDwellTime();
    playFeedback();
}

// Decrease dwell time
function decreaseDwell() {
    dwellTime = Math.max(0.5, dwellTime - 0.1);
    updateDwellDisplay();
    saveDwellTime();
    playFeedback();
}

// Save dwell time to settings
function saveDwellTime() {
    const settings = JSON.parse(localStorage.getItem('gazeSettings') || '{}');
    settings.dwellTime = dwellTime;
    localStorage.setItem('gazeSettings', JSON.stringify(settings));
}

// Setup theme toggle
function setupThemeToggle() {
    const toggle = document.getElementById('theme-toggle');
    
    toggle.addEventListener('change', (e) => {
        isLightMode = e.target.checked;
        document.body.classList.toggle('light-mode', isLightMode);
        
        // Save to settings
        const settings = JSON.parse(localStorage.getItem('gazeSettings') || '{}');
        settings.lightMode = isLightMode;
        localStorage.setItem('gazeSettings', JSON.stringify(settings));
        
        playFeedback();
    });
}

// Setup dwell slider
function setupDwellSlider() {
    const slider = document.getElementById('dwell-slider');
    const valueDisplay = document.getElementById('dwell-value');
    
    slider.addEventListener('input', (e) => {
        dwellTime = parseFloat(e.target.value);
        valueDisplay.textContent = dwellTime.toFixed(1) + 's';
        
        // Save to settings
        const settings = JSON.parse(localStorage.getItem('gazeSettings') || '{}');
        settings.dwellTime = dwellTime;
        localStorage.setItem('gazeSettings', JSON.stringify(settings));
        
        // Update CSS variable
        document.documentElement.style.setProperty('--dwell-time', dwellTime + 's');
    });
    
    // Set initial CSS variable
    document.documentElement.style.setProperty('--dwell-time', dwellTime + 's');
}

// Setup keyboard tabs
function setupKeyboardTabs() {
    const tabs = document.querySelectorAll('.tab-btn');
    
    tabs.forEach(tab => {
        tab.addEventListener('mouseenter', () => {
            startDwell(tab);
        });
        
        tab.addEventListener('mouseleave', () => {
            stopDwell(tab);
        });
        
        tab.addEventListener('click', () => {
            switchMode(tab.dataset.mode);
        });
    });
}

// Switch keyboard mode
function switchMode(mode) {
    currentMode = mode;
    
    // Update tabs
    document.querySelectorAll('.tab-btn').forEach(tab => {
        tab.classList.toggle('active', tab.dataset.mode === mode);
    });
    
    // Update layouts
    document.querySelectorAll('.keyboard-layout').forEach(layout => {
        layout.classList.toggle('active', layout.id === mode + '-layout');
    });
    
    playFeedback();
}

// Setup keys
function setupKeys() {
    const keys = document.querySelectorAll('.key');
    
    keys.forEach(key => {
        key.addEventListener('mouseenter', () => {
            startDwell(key);
        });
        
        key.addEventListener('mouseleave', () => {
            stopDwell(key);
        });
        
        key.addEventListener('click', () => {
            const char = key.dataset.key;
            addCharacter(char);
        });
    });
}

// Setup quick phrases
function setupPhrases() {
    const phrases = document.querySelectorAll('.phrase-card');
    
    phrases.forEach(phrase => {
        phrase.addEventListener('mouseenter', () => {
            startDwell(phrase);
        });
        
        phrase.addEventListener('mouseleave', () => {
            stopDwell(phrase);
        });
        
        phrase.addEventListener('click', () => {
            const text = phrase.dataset.text;
            addPhrase(text);
        });
    });
}

// Setup bottom controls
function setupBottomControls() {
    const controls = document.querySelectorAll('.control-btn');
    
    controls.forEach(control => {
        control.addEventListener('mouseenter', () => {
            startDwell(control);
        });
        
        control.addEventListener('mouseleave', () => {
            stopDwell(control);
        });
    });
}

// Dwell tracking
function startDwell(element) {
    if (currentElement === element) return;
    
    stopDwell(currentElement);
    currentElement = element;
    
    element.classList.add('dwelling');
    
    dwellTimer = setTimeout(() => {
        element.click();
        stopDwell(element);
    }, dwellTime * 1000);
}

function stopDwell(element) {
    if (!element) return;
    
    element.classList.remove('dwelling');
    
    if (dwellTimer) {
        clearTimeout(dwellTimer);
        dwellTimer = null;
    }
    
    if (currentElement === element) {
        currentElement = null;
    }
}

// Voice feedback for keys
function speakKey(char) {
    if ('speechSynthesis' in window) {
        const utterance = new SpeechSynthesisUtterance(char);
        utterance.rate = 1.2;
        utterance.pitch = 1;
        utterance.volume = 0.8;
        window.speechSynthesis.cancel();
        window.speechSynthesis.speak(utterance);
    }
}

// Text composition functions
function addCharacter(char) {
    const textArea = document.getElementById('text-area');
    
    // Apply shift/caps
    if (isShiftActive || isCapsLock) {
        char = char.toUpperCase();
    }
    
    // Speak the character
    speakKey(char);
    
    // Insert at cursor or append
    if (document.activeElement === textArea) {
        document.execCommand('insertText', false, char);
    } else {
        textArea.textContent += char;
    }
    
    // Reset shift (but not caps lock)
    if (isShiftActive && !isCapsLock) {
        isShiftActive = false;
        updateShiftButton();
    }
    
    updateCharCount();
    updatePredictions();
    playFeedback();
}

function addPhrase(text) {
    const textArea = document.getElementById('text-area');
    
    // Speak the phrase
    speakKey(text);
    
    // Add space before if there's existing text
    if (textArea.textContent.trim().length > 0) {
        text = ' ' + text;
    }
    
    if (document.activeElement === textArea) {
        document.execCommand('insertText', false, text);
    } else {
        textArea.textContent += text;
    }
    
    updateCharCount();
    updatePredictions();
    playFeedback();
}

function addPrediction(word) {
    const textArea = document.getElementById('text-area');
    const text = textArea.textContent;
    const words = text.split(/\s+/);
    
    // Speak the word
    speakKey(word);
    
    // Replace the last incomplete word with the prediction
    if (words.length > 0) {
        words[words.length - 1] = word;
        textArea.textContent = words.join(' ') + ' ';
    } else {
        textArea.textContent = word + ' ';
    }
    
    updateCharCount();
    updatePredictions();
    playFeedback();
}

function addSpace() {
    const textArea = document.getElementById('text-area');
    
    // Speak "space"
    speakKey('space');
    
    if (document.activeElement === textArea) {
        document.execCommand('insertText', false, ' ');
    } else {
        textArea.textContent += ' ';
    }
    
    updateCharCount();
    updatePredictions();
    playFeedback();
}

function deleteChar() {
    const textArea = document.getElementById('text-area');
    
    // Speak "delete"
    speakKey('delete');
    
    if (document.activeElement === textArea) {
        document.execCommand('delete');
    } else {
        textArea.textContent = textArea.textContent.slice(0, -1);
    }
    
    updateCharCount();
    updatePredictions();
    playFeedback();
}

function toggleShift() {
    if (isCapsLock) {
        // Turn off caps lock
        isCapsLock = false;
        isShiftActive = false;
    } else if (isShiftActive) {
        // Turn on caps lock
        isCapsLock = true;
    } else {
        // Turn on shift
        isShiftActive = true;
    }
    
    updateShiftButton();
    playFeedback();
}

function updateShiftButton() {
    const shiftBtn = document.querySelector('.shift-btn');
    
    if (isCapsLock || isShiftActive) {
        shiftBtn.classList.add('active');
    } else {
        shiftBtn.classList.remove('active');
    }
}

function updateCharCount() {
    const textArea = document.getElementById('text-area');
    const charCount = document.getElementById('char-count');
    const count = textArea.textContent.length;
    charCount.textContent = count + ' char' + (count !== 1 ? 's' : '');
}

// Word prediction
function updatePredictions() {
    const textArea = document.getElementById('text-area');
    const text = textArea.textContent;
    const words = text.split(/\s+/);
    const lastWord = words[words.length - 1].toLowerCase();
    
    const predictionsContainer = document.getElementById('word-predictions');
    predictionsContainer.innerHTML = '';
    
    if (lastWord.length === 0) {
        return;
    }
    
    // Get predictions based on first letter
    const firstLetter = lastWord[0];
    let predictions = wordDictionary[firstLetter] || [];
    
    // Filter predictions that start with the current word
    predictions = predictions.filter(word => 
        word.toLowerCase().startsWith(lastWord) && word.toLowerCase() !== lastWord
    ).slice(0, 5);
    
    // Create prediction buttons
    predictions.forEach(word => {
        const btn = document.createElement('button');
        btn.className = 'prediction-word';
        btn.textContent = word;
        btn.dataset.word = word;
        
        btn.addEventListener('mouseenter', () => {
            startDwell(btn);
        });
        
        btn.addEventListener('mouseleave', () => {
            stopDwell(btn);
        });
        
        btn.addEventListener('click', () => {
            addPrediction(word);
        });
        
        predictionsContainer.appendChild(btn);
    });
}

// Text actions
function copyText() {
    const textArea = document.getElementById('text-area');
    const text = textArea.textContent;
    
    if (text.length === 0) return;
    
    // Copy to clipboard
    navigator.clipboard.writeText(text).then(() => {
        showNotification('Text copied to clipboard!');
    }).catch(err => {
        console.error('Failed to copy:', err);
    });
    
    playFeedback();
}

function speakText() {
    const textArea = document.getElementById('text-area');
    const text = textArea.textContent;
    
    if (text.length === 0) return;
    
    // Use Web Speech API
    if ('speechSynthesis' in window) {
        const utterance = new SpeechSynthesisUtterance(text);
        utterance.rate = 0.9;
        utterance.pitch = 1;
        utterance.volume = 1;
        
        window.speechSynthesis.cancel(); // Cancel any ongoing speech
        window.speechSynthesis.speak(utterance);
        
        showNotification('Speaking...');
    } else {
        showNotification('Text-to-speech not supported');
    }
    
    playFeedback();
}

function clearText() {
    const textArea = document.getElementById('text-area');
    textArea.textContent = '';
    updateCharCount();
    playFeedback();
}

// Notification
function showNotification(message) {
    const notification = document.createElement('div');
    notification.style.cssText = `
        position: fixed;
        top: 50%;
        left: 50%;
        transform: translate(-50%, -50%);
        background: rgba(79, 172, 254, 0.95);
        color: white;
        padding: 20px 40px;
        border-radius: 15px;
        font-size: 18px;
        font-weight: 600;
        z-index: 10000;
        box-shadow: 0 10px 40px rgba(0, 0, 0, 0.3);
    `;
    notification.textContent = message;
    document.body.appendChild(notification);
    
    setTimeout(() => {
        notification.style.opacity = '0';
        notification.style.transition = 'opacity 0.3s ease';
        setTimeout(() => notification.remove(), 300);
    }, 2000);
}

// Go back to home
function goBack() {
    playFeedback();
    if (window.pywebview) {
        window.pywebview.api.go_back_home();
    } else {
        window.location.href = 'index.html';
    }
}

// Go to calling page
function goToCalling() {
    playFeedback();
    if (window.pywebview) {
        window.pywebview.api.handle_action('calling');
    } else {
        window.location.href = 'calling.html';
    }
}

// Feedback
function playFeedback() {
    document.body.style.transform = 'scale(0.998)';
    setTimeout(() => {
        document.body.style.transform = 'scale(1)';
    }, 50);
}

// Gaze tracking integration
function updateGazePosition(x, y) {
    // Check all interactive elements
    const elements = [
        ...document.querySelectorAll('.key'),
        ...document.querySelectorAll('.phrase-card'),
        ...document.querySelectorAll('.tab-btn'),
        ...document.querySelectorAll('.control-btn'),
        ...document.querySelectorAll('.action-btn'),
        ...document.querySelectorAll('.prediction-word'),
        ...document.querySelectorAll('.back-btn-header')
    ];
    
    let foundElement = null;
    
    for (const element of elements) {
        const rect = element.getBoundingClientRect();
        
        if (x >= rect.left && x <= rect.right &&
            y >= rect.top && y <= rect.bottom) {
            foundElement = element;
            break;
        }
    }
    
    if (foundElement) {
        startDwell(foundElement);
    } else if (currentElement) {
        stopDwell(currentElement);
    }
}

// Expose for Python
window.updateGaze = updateGazePosition;

// Keyboard shortcuts
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        goBack();
    } else if (e.key === 'Backspace' && document.activeElement !== document.getElementById('text-area')) {
        e.preventDefault();
        deleteChar();
    } else if (e.ctrlKey && e.key === 'c' && document.activeElement !== document.getElementById('text-area')) {
        e.preventDefault();
        copyText();
    } else if (e.ctrlKey && e.key === 's') {
        e.preventDefault();
        speakText();
    }
});

// Prevent context menu
document.addEventListener('contextmenu', (e) => {
    e.preventDefault();
});

// Auto-save text
setInterval(() => {
    const textArea = document.getElementById('text-area');
    if (textArea.textContent.length > 0) {
        localStorage.setItem('gazeKeyboardText', textArea.textContent);
    }
}, 5000);

// Restore saved text
window.addEventListener('load', () => {
    const savedText = localStorage.getItem('gazeKeyboardText');
    if (savedText) {
        const textArea = document.getElementById('text-area');
        textArea.textContent = savedText;
        updateCharCount();
    }
});
