// Settings state
let dwellTime = 2.5;
let darkMode = false;
let bluetoothEnabled = true;
let wifiEnabled = true;

// Dwell tracking
let dwellTimer = null;
let currentElement = null;

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    loadSettings();
    loadFamilyContact();
    setupDwellTracking();
});

// Load saved settings
function loadSettings() {
    const saved = localStorage.getItem('gazeSettings');
    if (saved) {
        const settings = JSON.parse(saved);
        dwellTime = settings.dwellTime || 2.5;
        darkMode = settings.darkMode || false;
        bluetoothEnabled = settings.bluetoothEnabled !== undefined ? settings.bluetoothEnabled : true;
        wifiEnabled = settings.wifiEnabled !== undefined ? settings.wifiEnabled : true;
        
        document.getElementById('dwell-value').textContent = dwellTime.toFixed(1);
        document.getElementById('dark-mode-toggle').checked = darkMode;
        document.getElementById('bluetooth-toggle').checked = bluetoothEnabled;
        document.getElementById('wifi-toggle').checked = wifiEnabled;
        
        if (darkMode) {
            document.body.classList.add('dark-mode');
        }
    }
    document.documentElement.style.setProperty('--dwell-time', dwellTime + 's');
}

// Save settings
function saveSettings() {
    const settings = {
        dwellTime,
        darkMode,
        bluetoothEnabled,
        wifiEnabled
    };
    localStorage.setItem('gazeSettings', JSON.stringify(settings));
    
    // Send to Python backend
    if (window.pywebview) {
        window.pywebview.api.update_settings(settings);
    }
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

// Dark mode toggle
function toggleDarkMode() {
    darkMode = document.getElementById('dark-mode-toggle').checked;
    
    // Apply dark mode to body
    if (darkMode) {
        document.body.classList.add('dark-mode');
    } else {
        document.body.classList.remove('dark-mode');
    }
    
    saveSettings();
    playFeedback();
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

// Bluetooth toggle
function toggleBluetooth() {
    bluetoothEnabled = document.getElementById('bluetooth-toggle').checked;
    saveSettings();
    playFeedback();
    
    if (window.pywebview) {
        window.pywebview.api.toggle_bluetooth(bluetoothEnabled);
    }
}

// Wi-Fi toggle
function toggleWifi() {
    wifiEnabled = document.getElementById('wifi-toggle').checked;
    saveSettings();
    playFeedback();
    
    if (window.pywebview) {
        window.pywebview.api.toggle_wifi(wifiEnabled);
    }
}

// Shutdown — closes the application
function shutdown() {
    playFeedback();
    if (window.pywebview) {
        window.pywebview.api.shutdown();
    } else {
        window.close();
    }
}

// Restart — closes the application
function restart() {
    playFeedback();
    if (window.pywebview) {
        window.pywebview.api.restart();
    } else {
        window.close();
    }
}

// Close settings
function closeSettings() {
    playFeedback();
    if (window.pywebview) {
        window.pywebview.api.close_settings();
    } else {
        window.history.back();
    }
}

// Feedback sound/vibration
function playFeedback() {
    // Visual feedback
    document.body.style.transform = 'scale(0.99)';
    setTimeout(() => {
        document.body.style.transform = 'scale(1)';
    }, 100);
}

// Family Contact Functions
function loadFamilyContact() {
    const savedDisplay = document.getElementById('saved-contact-display');
    const inputSection = document.getElementById('contact-input-section');

    _waitForPywebview(5000, () => {
        window.pywebview.api.get_family_contact().then(contact => {
            _applyContactDisplay(contact, savedDisplay, inputSection);
        }).catch(() => {
            savedDisplay.style.display = 'none';
            inputSection.style.display = 'flex';
        });
    }, () => {
        const saved = localStorage.getItem('familyContact');
        _applyContactDisplay(saved ? JSON.parse(saved) : null, savedDisplay, inputSection);
    });
}

// Wait up to maxMs for window.pywebview.api, then call onReady or onFail.
function _waitForPywebview(maxMs, onReady, onFail) {
    const start = Date.now();
    function check() {
        if (window.pywebview && window.pywebview.api) { onReady(); }
        else if (Date.now() - start < maxMs) { setTimeout(check, 100); }
        else { onFail(); }
    }
    check();
}

function _applyContactDisplay(contact, savedDisplay, inputSection) {
    if (contact && contact.phone) {
        document.getElementById('saved-name-display').textContent  = contact.name  || '-';
        document.getElementById('saved-phone-display').textContent = contact.phone || '-';
        savedDisplay.style.display = 'block';
        inputSection.style.display = 'none';
    } else {
        savedDisplay.style.display = 'none';
        inputSection.style.display = 'flex';
        document.getElementById('family-name').value  = '';
        document.getElementById('family-phone').value = '';
    }
}

function saveFamilyContact() {
    const name  = document.getElementById('family-name').value.trim();
    const phone = document.getElementById('family-phone').value.trim();

    if (!name || !phone) { alert('Please enter both name and phone number'); return; }
    if (phone.length < 7) { alert('Please enter a valid phone number'); return; }

    const contact = { name, phone };

    // Save via Python to disk (persists across sessions)
    if (window.pywebview && window.pywebview.api) {
        window.pywebview.api.update_family_contact(contact).then(() => {
            showSuccessMessage();
            setTimeout(loadFamilyContact, 1500);
        });
    } else {
        localStorage.setItem('familyContact', JSON.stringify(contact));
        showSuccessMessage();
        setTimeout(loadFamilyContact, 1500);
    }

    playFeedback();
}

function enableEditContact() {
    const savedDisplay = document.getElementById('saved-contact-display');
    const inputSection = document.getElementById('contact-input-section');

    _waitForPywebview(3000, () => {
        window.pywebview.api.get_family_contact().then(contact => {
            document.getElementById('family-name').value  = contact.name  || '';
            document.getElementById('family-phone').value = contact.phone || '';
            savedDisplay.style.display = 'none';
            inputSection.style.display = 'flex';
        });
    }, () => {
        const saved = localStorage.getItem('familyContact');
        if (saved) {
            const c = JSON.parse(saved);
            document.getElementById('family-name').value  = c.name  || '';
            document.getElementById('family-phone').value = c.phone || '';
        }
        savedDisplay.style.display = 'none';
        inputSection.style.display = 'flex';
    });
    playFeedback();
}

function showSuccessMessage() {
    // Remove existing success message if any
    const existing = document.querySelector('.save-success');
    if (existing) {
        existing.remove();
    }
    
    // Create and show success message
    const message = document.createElement('div');
    message.className = 'save-success';
    message.textContent = '✓ Family contact saved successfully!';
    
    const saveBtn = document.querySelector('.save-btn');
    saveBtn.parentNode.insertBefore(message, saveBtn.nextSibling);
    
    // Remove after 3 seconds
    setTimeout(() => {
        message.style.opacity = '0';
        setTimeout(() => message.remove(), 300);
    }, 3000);
}

// ---- Dwell tracking -------------------------------------------------------
// Python's DwellClicker fires real OS mouse clicks — JS dwell would double-fire.
function setupDwellTracking() { /* no-op */ }
function startDwell(element)  { /* no-op */ }
function stopDwell(element)   { /* no-op */ }
function activateElement(element) { element.click(); }

// Dwell visual feedback — poll Python's dwell_progress
(function startDwellFeedback() {
    let _lastDwelling = null;
    function poll() {
        if (!window.pywebview || !window.pywebview.api) {
            setTimeout(poll, 200); return;
        }
        window.pywebview.api.get_tracking_status().then(s => {
            const progress = s.dwell_progress || 0;
            const hovered = document.querySelector(
                '.control-btn:hover, .action-btn:hover, .save-btn:hover, .edit-contact-btn:hover, .back-btn:hover'
            );
            const target = (hovered && progress > 0.02) ? hovered : null;
            if (target !== _lastDwelling) {
                if (_lastDwelling) _lastDwelling.classList.remove('dwelling');
                if (target) target.classList.add('dwelling');
                _lastDwelling = target;
            }
            setTimeout(poll, 80);
        }).catch(() => setTimeout(poll, 200));
    }
    setTimeout(poll, 1500);
})();

// Gaze tracking integration
function updateGazePosition(x, y) {
    const interactiveElements = document.querySelectorAll(
        '.control-btn, .action-btn, .toggle-switch, .close-btn, .save-btn, .edit-contact-btn'
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
        closeSettings();
    } else if (e.key === '+' || e.key === '=') {
        increaseDwell();
    } else if (e.key === '-' || e.key === '_') {
        decreaseDwell();
    }
});

// Prevent context menu
document.addEventListener('contextmenu', (e) => {
    e.preventDefault();
});
