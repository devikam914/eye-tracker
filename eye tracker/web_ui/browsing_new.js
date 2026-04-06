// State
let currentMode = 'abc';
let searchText = '';
let dwellTime = 1.5;
let dwellTimer = null;
let currentElement = null;
let darkMode = false;

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    setupKeyboard();
    setupDwellTracking();
    loadSettings();
});

// Dwell time controls
function increaseDwell() {
    if (dwellTime < 5.0) {
        dwellTime += 0.5;
        document.getElementById('dwell-value').textContent = dwellTime.toFixed(1);
        saveSettings();
        playFeedback();
    }
}

function decreaseDwell() {
    if (dwellTime > 0.5) {
        dwellTime -= 0.5;
        document.getElementById('dwell-value').textContent = dwellTime.toFixed(1);
        saveSettings();
        playFeedback();
    }
}

// Load settings
function loadSettings() {
    const saved = localStorage.getItem('gazeSettings');
    if (saved) {
        const settings = JSON.parse(saved);
        dwellTime = settings.dwellTime || 1.5;
        darkMode = settings.darkMode || false;
        
        // Update UI
        document.getElementById('dwell-value').textContent = dwellTime.toFixed(1);
        document.getElementById('dark-mode-toggle').checked = darkMode;
        if (darkMode) {
            document.body.classList.add('dark-mode');
        }
    }
}

// Save settings
function saveSettings() {
    const saved = localStorage.getItem('gazeSettings');
    let settings = saved ? JSON.parse(saved) : {};
    
    settings.dwellTime = dwellTime;
    settings.darkMode = darkMode;
    
    localStorage.setItem('gazeSettings', JSON.stringify(settings));
}

// Toggle dark mode
function toggleDarkMode() {
    darkMode = document.getElementById('dark-mode-toggle').checked;
    
    if (darkMode) {
        document.body.classList.add('dark-mode');
    } else {
        document.body.classList.remove('dark-mode');
    }
    
    saveSettings();
    playFeedback();
}

// Setup keyboard
function setupKeyboard() {
    const keys = document.querySelectorAll('.key');
    
    keys.forEach(key => {
        key.addEventListener('click', (e) => {
            const keyValue = key.dataset.key;
            
            // Add pressed animation
            key.classList.add('pressed');
            setTimeout(() => {
                key.classList.remove('pressed');
            }, 200);
            
            // Create ripple effect
            createRipple(key, e);
            
            handleKeyPress(keyValue);
        });
        
        // Add hover scale effect
        key.addEventListener('mouseenter', () => {
            key.style.transition = 'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)';
        });
    });
}

// Handle key press
function handleKeyPress(key) {
    const input = document.getElementById('search-input');
    
    if (key === 'DELETE') {
        searchText = searchText.slice(0, -1);
    } else if (key === 'SPACE') {
        searchText += ' ';
    } else {
        searchText += key.toLowerCase();
    }
    
    input.value = searchText;
    playFeedback();
}

// Create ripple effect
function createRipple(element, event) {
    const ripple = document.createElement('span');
    ripple.classList.add('ripple');
    
    const rect = element.getBoundingClientRect();
    const size = Math.max(rect.width, rect.height);
    const x = event ? event.clientX - rect.left - size / 2 : rect.width / 2 - size / 2;
    const y = event ? event.clientY - rect.top - size / 2 : rect.height / 2 - size / 2;
    
    ripple.style.width = ripple.style.height = size + 'px';
    ripple.style.left = x + 'px';
    ripple.style.top = y + 'px';
    
    element.appendChild(ripple);
    
    setTimeout(() => {
        ripple.remove();
    }, 600);
}

// Switch keyboard mode
function switchMode(mode) {
    currentMode = mode;
    
    // Update tabs
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.classList.remove('active');
        if (btn.dataset.mode === mode) {
            btn.classList.add('active');
        }
    });
    
    // Update layouts
    document.querySelectorAll('.keyboard-layout').forEach(layout => {
        layout.classList.remove('active');
    });
    document.getElementById(`${mode}-layout`).classList.add('active');
    
    playFeedback();
}

// Clear search
function clearSearch() {
    searchText = '';
    document.getElementById('search-input').value = '';
    playFeedback();
}

// Speak text
function speakText() {
    if (!searchText.trim()) {
        return;
    }
    
    // Use Web Speech API
    if ('speechSynthesis' in window) {
        // Cancel any ongoing speech
        window.speechSynthesis.cancel();
        
        const utterance = new SpeechSynthesisUtterance(searchText);
        utterance.rate = 0.9; // Slightly slower for clarity
        utterance.pitch = 1;
        utterance.volume = 1;
        
        // Visual feedback
        const speakBtn = document.querySelector('.speak-btn');
        speakBtn.classList.add('speaking');
        
        utterance.onend = () => {
            speakBtn.classList.remove('speaking');
        };
        
        utterance.onerror = () => {
            speakBtn.classList.remove('speaking');
            console.error('Speech synthesis error');
        };
        
        window.speechSynthesis.speak(utterance);
        playFeedback();
    } else {
        alert('Text-to-speech is not supported in your browser');
    }
}

// Perform search
function performSearch() {
    if (!searchText.trim()) {
        return;
    }
    
    const query = encodeURIComponent(searchText);
    const url = `https://www.google.com/search?q=${query}`;
    
    // Open in external browser via Python API
    if (window.pywebview) {
        window.pywebview.api.open_url(url).then(() => {
            console.log('Browser opened with search:', searchText);
        });
    } else {
        window.open(url, '_blank');
    }
    
    playFeedback();
}

// Quick search
function quickSearch(query) {
    searchText = query;
    document.getElementById('search-input').value = query;
    
    const encodedQuery = encodeURIComponent(query);
    const url = `https://www.google.com/search?q=${encodedQuery}`;
    
    // Open in external browser via Python API
    if (window.pywebview) {
        window.pywebview.api.open_url(url).then(() => {
            console.log('Browser opened with quick search:', query);
        });
    } else {
        window.open(url, '_blank');
    }
    
    playFeedback();
}

// Go back to home
function goBackToHome() {
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
    document.body.style.transform = 'scale(0.995)';
    setTimeout(() => {
        document.body.style.transform = 'scale(1)';
    }, 100);
}

// Dwell tracking setup
function setupDwellTracking() {
    const interactiveElements = document.querySelectorAll(
        '.key, .search-btn, .speak-btn, .call-btn, .quick-link, .back-btn, .tab-btn, .clear-search-btn, .theme-toggle, .dwell-btn'
    );
    
    interactiveElements.forEach(element => {
        element.addEventListener('mouseenter', () => {
            startDwell(element);
        });
        
        element.addEventListener('mouseleave', () => {
            stopDwell(element);
        });
    });
}

function startDwell(element) {
    if (currentElement === element) return;
    
    stopDwell(currentElement);
    currentElement = element;
    
    element.classList.add('dwelling');
    
    dwellTimer = setTimeout(() => {
        activateElement(element);
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

function activateElement(element) {
    stopDwell(element);
    
    // Add pressed animation for keys
    if (element.classList.contains('key')) {
        element.classList.add('pressed');
        setTimeout(() => {
            element.classList.remove('pressed');
        }, 200);
        
        // Create ripple effect
        createRipple(element);
    }
    
    element.click();
    
    // Visual feedback
    element.style.transform = 'scale(0.95)';
    setTimeout(() => {
        element.style.transform = '';
    }, 150);
}

// Gaze tracking integration
function updateGazePosition(x, y) {
    const interactiveElements = document.querySelectorAll(
        '.key, .search-btn, .speak-btn, .call-btn, .quick-link, .back-btn, .tab-btn, .clear-search-btn, .theme-toggle, .dwell-btn'
    );
    
    interactiveElements.forEach(element => {
        const rect = element.getBoundingClientRect();
        
        if (x >= rect.left && x <= rect.right &&
            y >= rect.top && y <= rect.bottom) {
            startDwell(element);
        } else if (currentElement === element) {
            stopDwell(element);
        }
    });
}

// Expose for Python
window.updateGaze = updateGazePosition;

// Keyboard shortcuts
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        goBackToHome();
    } else if (e.key === 'Enter') {
        performSearch();
    } else if (e.key === 'Backspace') {
        e.preventDefault();
        handleKeyPress('DELETE');
    }
});

// Prevent context menu
document.addEventListener('contextmenu', (e) => {
    e.preventDefault();
});
