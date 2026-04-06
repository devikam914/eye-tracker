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
        
        // Update UI
        document.getElementById('dwell-value').textContent = dwellTime.toFixed(1);
        document.getElementById('dark-mode-toggle').checked = darkMode;
        document.getElementById('bluetooth-toggle').checked = bluetoothEnabled;
        document.getElementById('wifi-toggle').checked = wifiEnabled;
        
        // Apply dark mode if enabled
        if (darkMode) {
            document.body.classList.add('dark-mode');
        }
    }
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

// Shutdown
function shutdown() {
    if (confirm('Are you sure you want to shutdown?')) {
        playFeedback();
        if (window.pywebview) {
            window.pywebview.api.shutdown();
        } else {
            alert('Shutdown command sent');
        }
    }
}

// Restart
function restart() {
    if (confirm('Are you sure you want to restart?')) {
        playFeedback();
        if (window.pywebview) {
            window.pywebview.api.restart();
        } else {
            alert('Restart command sent');
        }
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
    const saved = localStorage.getItem('familyContact');
    const savedDisplay = document.getElementById('saved-contact-display');
    const inputSection = document.getElementById('contact-input-section');
    
    if (saved) {
        const contact = JSON.parse(saved);
        
        // Show saved contact display
        document.getElementById('saved-name-display').textContent = contact.name || '-';
        document.getElementById('saved-phone-display').textContent = contact.phone || '-';
        savedDisplay.style.display = 'block';
        inputSection.style.display = 'none';
    } else {
        // Show input fields
        savedDisplay.style.display = 'none';
        inputSection.style.display = 'flex';
        document.getElementById('family-name').value = '';
        document.getElementById('family-phone').value = '';
    }
}

function saveFamilyContact() {
    const name = document.getElementById('family-name').value.trim();
    const phone = document.getElementById('family-phone').value.trim();
    
    if (!name || !phone) {
        alert('Please enter both name and phone number');
        return;
    }
    
    // Validate phone number (basic validation)
    if (phone.length < 10) {
        alert('Please enter a valid phone number');
        return;
    }
    
    const contact = { name, phone };
    localStorage.setItem('familyContact', JSON.stringify(contact));
    
    playFeedback();
    
    // Show success message
    showSuccessMessage();
    
    // Switch to display mode after a short delay
    setTimeout(() => {
        loadFamilyContact();
    }, 1500);
    
    // Send to Python backend
    if (window.pywebview) {
        window.pywebview.api.update_family_contact(contact);
    }
}

function enableEditContact() {
    const savedDisplay = document.getElementById('saved-contact-display');
    const inputSection = document.getElementById('contact-input-section');
    
    // Load current values into input fields
    const saved = localStorage.getItem('familyContact');
    if (saved) {
        const contact = JSON.parse(saved);
        document.getElementById('family-name').value = contact.name || '';
        document.getElementById('family-phone').value = contact.phone || '';
    }
    
    // Show input fields, hide display
    savedDisplay.style.display = 'none';
    inputSection.style.display = 'flex';
    
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

// Dwell tracking setup
function setupDwellTracking() {
    const interactiveElements = document.querySelectorAll(
        '.control-btn, .action-btn, .toggle-switch, .close-btn, .save-btn, .edit-contact-btn'
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
    
    // Trigger click
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
