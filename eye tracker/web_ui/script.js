// State
let dwellTime = 2.0;
let darkMode = false;

// Update date and time
function updateDateTime() {
    const now = new Date();
    
    // Format date
    const dateOptions = { year: 'numeric', month: 'long', day: 'numeric' };
    const dateStr = now.toLocaleDateString('en-US', dateOptions);
    document.getElementById('date').textContent = dateStr;
    
    // Format day
    const dayOptions = { weekday: 'long' };
    const dayStr = now.toLocaleDateString('en-US', dayOptions);
    document.getElementById('day').textContent = dayStr;
    
    // Format time
    const timeOptions = { hour: 'numeric', minute: '2-digit', hour12: true };
    const timeStr = now.toLocaleTimeString('en-US', timeOptions);
    document.getElementById('time').textContent = timeStr;
    
    // Full date for time widget
    document.getElementById('full-date').textContent = `${dateStr} • ${dayStr}`;
}

// Update battery
async function updateBattery() {
    try {
        // Try to get actual battery level using Battery Status API
        if ('getBattery' in navigator) {
            const battery = await navigator.getBattery();
            const batteryPercent = Math.round(battery.level * 100);
            document.getElementById('battery-percent').textContent = `${batteryPercent}%`;
            document.getElementById('battery-level').style.width = `${batteryPercent}%`;
            
            // Listen for battery changes
            battery.addEventListener('levelchange', () => {
                updateBattery();
            });
        } else {
            // Fallback: Battery API not supported, show placeholder
            document.getElementById('battery-percent').textContent = 'N/A';
            document.getElementById('battery-level').style.width = '0%';
        }
    } catch (error) {
        console.error('Error getting battery status:', error);
        // Fallback to placeholder
        document.getElementById('battery-percent').textContent = 'N/A';
        document.getElementById('battery-level').style.width = '0%';
    }
}

// Theme toggle
function toggleTheme() {
    darkMode = document.getElementById('theme-toggle').checked;
    
    if (darkMode) {
        document.body.classList.add('dark-mode');
        document.getElementById('theme-label').textContent = 'Dark';
    } else {
        document.body.classList.remove('dark-mode');
        document.getElementById('theme-label').textContent = 'Light';
    }
    
    saveSettings();
}

// Dwell time controls
function increaseDwell() {
    if (dwellTime < 5.0) {
        dwellTime += 0.5;
        document.getElementById('dwell-value').textContent = dwellTime.toFixed(1) + 's';
        saveSettings();
    }
}

function decreaseDwell() {
    if (dwellTime > 0.5) {
        dwellTime -= 0.5;
        document.getElementById('dwell-value').textContent = dwellTime.toFixed(1) + 's';
        saveSettings();
    }
}

// Load settings
function loadSettings() {
    const saved = localStorage.getItem('gazeSettings');
    if (saved) {
        const settings = JSON.parse(saved);
        dwellTime = settings.dwellTime || 2.0;
        darkMode = settings.darkMode || false;
        
        // Update UI
        document.getElementById('dwell-value').textContent = dwellTime.toFixed(1) + 's';
        document.getElementById('theme-toggle').checked = darkMode;
        
        if (darkMode) {
            document.body.classList.add('dark-mode');
            document.getElementById('theme-label').textContent = 'Dark';
        } else {
            document.getElementById('theme-label').textContent = 'Light';
        }
    }
}

// Save settings
function saveSettings() {
    const settings = {
        dwellTime,
        darkMode
    };
    localStorage.setItem('gazeSettings', JSON.stringify(settings));
}

// Tile interaction
const tiles = document.querySelectorAll('.tile');
let dwellTimer = null;
let currentTile = null;

tiles.forEach(tile => {
    // Mouse hover
    tile.addEventListener('mouseenter', () => {
        startDwell(tile);
    });
    
    tile.addEventListener('mouseleave', () => {
        stopDwell(tile);
    });
    
    // Click
    tile.addEventListener('click', () => {
        activateTile(tile);
    });
});

function startDwell(tile) {
    if (currentTile === tile) return;
    
    stopDwell(currentTile);
    currentTile = tile;
    
    tile.classList.add('dwelling');
    
    dwellTimer = setTimeout(() => {
        activateTile(tile);
    }, dwellTime * 1000);
}

function stopDwell(tile) {
    if (!tile) return;
    
    tile.classList.remove('dwelling');
    
    if (dwellTimer) {
        clearTimeout(dwellTimer);
        dwellTimer = null;
    }
    
    if (currentTile === tile) {
        currentTile = null;
    }
}

function activateTile(tile) {
    const action = tile.dataset.action;
    
    // Visual feedback
    tile.classList.add('active');
    setTimeout(() => {
        tile.classList.remove('active');
    }, 200);
    
    // Stop dwell
    stopDwell(tile);
    
    // Send action to Python backend
    sendAction(action);
}

function sendAction(action) {
    console.log('Action triggered:', action);
    
    // Send to Python backend via WebSocket or HTTP
    if (window.pywebview) {
        // Using pywebview API
        window.pywebview.api.handle_action(action);
    } else {
        // Fallback for testing in browser
        console.log(`Would execute: ${action}`);
        alert(`Action: ${action}`);
    }
}

// Gaze tracking integration
function updateGazePosition(x, y) {
    // Check which tile is being looked at
    tiles.forEach(tile => {
        const rect = tile.getBoundingClientRect();
        
        if (x >= rect.left && x <= rect.right &&
            y >= rect.top && y <= rect.bottom) {
            startDwell(tile);
        } else if (currentTile === tile) {
            stopDwell(tile);
        }
    });
}

// Expose function for Python to call
window.updateGaze = updateGazePosition;

// Setup theme toggle
document.getElementById('theme-toggle').addEventListener('change', toggleTheme);

// Initialize
loadSettings();
updateDateTime();
updateBattery();

// Update time every second
setInterval(updateDateTime, 1000);

// Keyboard shortcuts
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        if (window.pywebview) {
            window.pywebview.api.handle_action('exit');
        }
    }
});

// Prevent context menu
document.addEventListener('contextmenu', (e) => {
    e.preventDefault();
});

// Prevent text selection
document.addEventListener('selectstart', (e) => {
    e.preventDefault();
});


// ============================================================================
// EYE TRACKING CALIBRATION
// ============================================================================

function startCalibration() {
    const btn = document.getElementById('calibration-btn');
    const text = document.getElementById('calibration-text');
    const status = document.getElementById('tracking-status');
    const statusText = document.getElementById('status-text');
    
    // Update UI to show calibration in progress
    btn.classList.add('calibrating');
    text.textContent = 'Calibrating... Follow the dots';
    statusText.textContent = 'Calibrating...';
    
    // Call Python backend to start calibration
    if (window.pywebview && window.pywebview.api) {
        window.pywebview.api.start_calibration().then(response => {
            console.log('Calibration started:', response);
            
            // Poll for calibration status
            checkTrackingStatus();
        }).catch(error => {
            console.error('Calibration error:', error);
            btn.classList.remove('calibrating');
            text.textContent = 'Calibration Failed - Try Again';
            statusText.textContent = 'Error';
        });
    } else {
        // Fallback for testing without backend
        console.log('Calibration started (demo mode)');
        setTimeout(() => {
            btn.classList.remove('calibrating');
            btn.classList.add('calibrated');
            text.textContent = '✓ Eye Tracking Active';
            status.classList.add('calibrated', 'tracking');
            statusText.textContent = 'Tracking Active';
        }, 3000);
    }
}

function checkTrackingStatus() {
    if (window.pywebview && window.pywebview.api) {
        window.pywebview.api.get_tracking_status().then(status => {
            const btn = document.getElementById('calibration-btn');
            const text = document.getElementById('calibration-text');
            const statusDiv = document.getElementById('tracking-status');
            const statusText = document.getElementById('status-text');
            
            if (status.calibrated && status.running) {
                // Calibration complete and tracking active
                btn.classList.remove('calibrating');
                btn.classList.add('calibrated');
                text.textContent = '✓ Eye Tracking Active';
                statusDiv.classList.add('calibrated', 'tracking');
                statusText.textContent = status.paused ? 'Paused' : 'Tracking Active';
            } else if (status.calibrated) {
                // Calibrated but not tracking
                btn.classList.remove('calibrating');
                btn.classList.add('calibrated');
                text.textContent = 'Start Tracking';
                statusDiv.classList.add('calibrated');
                statusText.textContent = 'Calibrated';
            } else {
                // Still calibrating or failed
                setTimeout(checkTrackingStatus, 1000);
            }
        }).catch(error => {
            console.error('Status check error:', error);
        });
    }
}

// Check tracking status on page load
window.addEventListener('load', () => {
    setTimeout(checkTrackingStatus, 1000);
});

// Pause tracking when navigating away from home
function pauseTrackingOnNavigate() {
    if (window.pywebview && window.pywebview.api) {
        window.pywebview.api.pause_tracking();
    }
}

// Resume tracking when returning home
function resumeTrackingOnHome() {
    if (window.pywebview && window.pywebview.api) {
        window.pywebview.api.resume_tracking();
    }
}
