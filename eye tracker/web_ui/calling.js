// Phone numbers configuration
const EMERGENCY_NUMBER = '911';
let FAMILY_NUMBER = null; // Will be loaded from settings
let FAMILY_NAME = 'Family'; // Default name

// Dwell tracking
let dwellTimer = null;
let currentCard = null;
let dwellTime = 1.5; // seconds
let isDarkMode = false;

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    loadSettings();
    loadFamilyContact();
    setupDwellTracking();
    updateFamilyNumber();
    setupThemeToggle();
});

// Load settings
function loadSettings() {
    const saved = localStorage.getItem('gazeSettings');
    if (saved) {
        const settings = JSON.parse(saved);
        dwellTime = settings.dwellTime || 1.5;
        isDarkMode = settings.darkMode || false;
        
        if (isDarkMode) {
            document.body.classList.add('dark-mode');
            document.getElementById('theme-toggle').checked = false;
        } else {
            document.body.classList.remove('dark-mode');
            document.getElementById('theme-toggle').checked = true;
        }
    }
}

// Setup theme toggle
function setupThemeToggle() {
    const toggle = document.getElementById('theme-toggle');
    
    toggle.addEventListener('change', (e) => {
        isDarkMode = !e.target.checked;
        document.body.classList.toggle('dark-mode', isDarkMode);
        
        // Save to settings
        const settings = JSON.parse(localStorage.getItem('gazeSettings') || '{}');
        settings.darkMode = isDarkMode;
        localStorage.setItem('gazeSettings', JSON.stringify(settings));
        
        playFeedback();
    });
}

// Load family contact from settings
function loadFamilyContact() {
    const saved = localStorage.getItem('familyContact');
    if (saved) {
        const contact = JSON.parse(saved);
        FAMILY_NUMBER = contact.phone || null;
        FAMILY_NAME = contact.name || 'Family';
    }
}

// Update family number display
function updateFamilyNumber() {
    const familyCard = document.querySelector('.family-card');
    const numberElement = document.getElementById('family-number');
    const titleElement = familyCard.querySelector('.call-title');
    
    // Update title with family name
    titleElement.textContent = `👨‍👩‍👧‍👦 Call ${FAMILY_NAME}`;
    
    // Update number display
    if (FAMILY_NUMBER) {
        numberElement.textContent = formatPhoneNumber(FAMILY_NUMBER);
        familyCard.style.opacity = '1';
        familyCard.style.pointerEvents = 'auto';
    } else {
        numberElement.textContent = 'Not configured';
        numberElement.style.color = '#ff6b6b';
        // Optionally disable the card
        familyCard.style.opacity = '0.6';
        familyCard.style.cursor = 'not-allowed';
    }
}

// Format phone number for display
function formatPhoneNumber(number) {
    // Simple formatting for display
    if (number.startsWith('+91')) {
        return number.replace('+91', '+91 ') + ' (Family)';
    }
    return number;
}

// Setup dwell tracking
function setupDwellTracking() {
    const cards = document.querySelectorAll('.call-card');
    
    cards.forEach(card => {
        card.addEventListener('mouseenter', () => {
            startDwell(card);
        });
        
        card.addEventListener('mouseleave', () => {
            stopDwell(card);
        });
        
        card.addEventListener('click', () => {
            const action = card.dataset.action;
            initiateCall(action);
        });
    });
}

function startDwell(card) {
    if (currentCard === card) return;
    
    stopDwell(currentCard);
    currentCard = card;
    
    card.classList.add('dwelling');
    
    dwellTimer = setTimeout(() => {
        const action = card.dataset.action;
        initiateCall(action);
    }, dwellTime * 1000);
}

function stopDwell(card) {
    if (!card) return;
    
    card.classList.remove('dwelling');
    
    if (dwellTimer) {
        clearTimeout(dwellTimer);
        dwellTimer = null;
    }
    
    if (currentCard === card) {
        currentCard = null;
    }
}

// Initiate call
function initiateCall(type) {
    stopDwell(currentCard);
    
    let number, title;
    
    if (type === 'emergency') {
        number = EMERGENCY_NUMBER;
        title = '🚨 Calling Emergency...';
    } else if (type === 'family') {
        if (!FAMILY_NUMBER) {
            alert('Please configure family contact in Settings first');
            return;
        }
        number = FAMILY_NUMBER;
        title = `👨‍👩‍👧‍👦 Calling ${FAMILY_NAME}...`;
    }
    
    // Show modal
    showCallModal(title, number);
    
    // Make the call
    makeCall(number);
    
    // Visual feedback
    playFeedback();
}

// Show call modal
function showCallModal(title, number) {
    const modal = document.getElementById('call-modal');
    document.getElementById('modal-title').textContent = title;
    document.getElementById('modal-number').textContent = formatPhoneNumber(number);
    modal.classList.remove('hidden');
}

// Hide call modal
function hideCallModal() {
    const modal = document.getElementById('call-modal');
    modal.classList.add('hidden');
}

// Make the actual call
function makeCall(number) {
    console.log(`Initiating call to: ${number}`);
    
    // Send to Python backend (Python handles the Enter key presses automatically)
    if (window.pywebview) {
        window.pywebview.api.make_call(number);
    } else {
        // Fallback for testing in browser
        console.log(`Would call: ${number}`);
        
        // Try to use tel: protocol
        try {
            window.location.href = `tel:${number}`;
        } catch (e) {
            console.error('Cannot initiate call:', e);
        }
    }
    
    // Auto-hide modal after 5 seconds (to allow time for call initiation)
    setTimeout(() => {
        hideCallModal();
    }, 5000);
}

// Cancel call
function cancelCall() {
    hideCallModal();
    playFeedback();
    
    if (window.pywebview) {
        window.pywebview.api.cancel_call();
    }
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

// Feedback
function playFeedback() {
    document.body.style.transform = 'scale(0.99)';
    setTimeout(() => {
        document.body.style.transform = 'scale(1)';
    }, 100);
}

// Gaze tracking integration
function updateGazePosition(x, y) {
    const cards = document.querySelectorAll('.call-card');
    
    cards.forEach(card => {
        const rect = card.getBoundingClientRect();
        
        if (x >= rect.left && x <= rect.right &&
            y >= rect.top && y <= rect.bottom) {
            startDwell(card);
        } else if (currentCard === card) {
            stopDwell(card);
        }
    });
}

// Expose for Python
window.updateGaze = updateGazePosition;

// Keyboard shortcuts
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        if (!document.getElementById('call-modal').classList.contains('hidden')) {
            cancelCall();
        } else {
            goBack();
        }
    } else if (e.key === '1') {
        initiateCall('emergency');
    } else if (e.key === '2') {
        initiateCall('family');
    }
});

// Prevent context menu
document.addEventListener('contextmenu', (e) => {
    e.preventDefault();
});
