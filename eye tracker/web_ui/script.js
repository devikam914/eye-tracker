// State
let dwellTime = 2.0;
let darkMode = false;

// Update date and time
function updateDateTime() {
    const now = new Date();
    
    const dateOptions = { year: 'numeric', month: 'long', day: 'numeric' };
    const dateStr = now.toLocaleDateString('en-US', dateOptions);
    document.getElementById('date').textContent = dateStr;
    
    const dayOptions = { weekday: 'long' };
    const dayStr = now.toLocaleDateString('en-US', dayOptions);
    document.getElementById('day').textContent = dayStr;
    
    const timeOptions = { hour: 'numeric', minute: '2-digit', hour12: true };
    const timeStr = now.toLocaleTimeString('en-US', timeOptions);
    document.getElementById('time').textContent = timeStr;
    
    document.getElementById('full-date').textContent = `${dateStr} • ${dayStr}`;
}

// Update battery
async function updateBattery() {
    try {
        if ('getBattery' in navigator) {
            const battery = await navigator.getBattery();
            const batteryPercent = Math.round(battery.level * 100);
            document.getElementById('battery-percent').textContent = `${batteryPercent}%`;
            document.getElementById('battery-level').style.width = `${batteryPercent}%`;
            battery.addEventListener('levelchange', () => { updateBattery(); });
        } else {
            document.getElementById('battery-percent').textContent = 'N/A';
            document.getElementById('battery-level').style.width = '0%';
        }
    } catch (error) {
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
        document.documentElement.style.setProperty('--dwell-time', dwellTime + 's');
        saveSettings();
    }
}

function decreaseDwell() {
    if (dwellTime > 0.5) {
        dwellTime -= 0.5;
        document.getElementById('dwell-value').textContent = dwellTime.toFixed(1) + 's';
        document.documentElement.style.setProperty('--dwell-time', dwellTime + 's');
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
        
        document.getElementById('dwell-value').textContent = dwellTime.toFixed(1) + 's';
        document.getElementById('theme-toggle').checked = darkMode;
        
        if (darkMode) {
            document.body.classList.add('dark-mode');
            document.getElementById('theme-label').textContent = 'Dark';
        } else {
            document.getElementById('theme-label').textContent = 'Light';
        }
    }
    document.documentElement.style.setProperty('--dwell-time', dwellTime + 's');
}

// Save settings
function saveSettings() {
    const settings = { dwellTime, darkMode };
    localStorage.setItem('gazeSettings', JSON.stringify(settings));
    if (window.pywebview && window.pywebview.api) {
        window.pywebview.api.update_dwell_time(dwellTime);
    }
}

// ---- Tile dwell interaction ------------------------------------------------
const tiles = document.querySelectorAll('.tile');
let dwellTimer = null;
let currentTile = null;
let _dwellLocked = false;

tiles.forEach(tile => {
    tile.addEventListener('mouseenter', () => { startDwell(tile); });
    tile.addEventListener('mouseleave', () => { stopDwell(tile); });
    tile.addEventListener('click', () => {
        if (_dwellLocked) return;
        _dwellLocked = true;
        stopDwell(tile);
        activateTile(tile);
        setTimeout(() => { _dwellLocked = false; }, 1200);
    });
});

function startDwell(tile) {
    if (currentTile === tile) return;
    stopDwell(currentTile);
    currentTile = tile;
    tile.classList.add('dwelling');
    dwellTimer = setTimeout(() => {
        if (_dwellLocked) { stopDwell(tile); return; }
        _dwellLocked = true;
        activateTile(tile);
        setTimeout(() => { _dwellLocked = false; }, 1200);
    }, dwellTime * 1000);
}

function stopDwell(tile) {
    if (!tile) return;
    tile.classList.remove('dwelling');
    if (dwellTimer) { clearTimeout(dwellTimer); dwellTimer = null; }
    if (currentTile === tile) currentTile = null;
}

function activateTile(tile) {
    const action = tile.dataset.action;
    tile.classList.add('active');
    setTimeout(() => tile.classList.remove('active'), 200);
    stopDwell(tile);
    sendAction(action);
}

function sendAction(action) {
    console.log('Action triggered:', action);
    if (window.pywebview) {
        window.pywebview.api.handle_action(action);
    } else {
        alert(`Action: ${action}`);
    }
}

// Gaze tracking integration — called by Python via evaluate_js if needed
function updateGazePosition(x, y) {
    tiles.forEach(tile => {
        const rect = tile.getBoundingClientRect();
        if (x >= rect.left && x <= rect.right && y >= rect.top && y <= rect.bottom) {
            startDwell(tile);
        } else if (currentTile === tile) {
            stopDwell(tile);
        }
    });
}
window.updateGaze = updateGazePosition;

// Setup theme toggle
document.getElementById('theme-toggle').addEventListener('change', toggleTheme);

// Initialize
loadSettings();
updateDateTime();
updateBattery();
setInterval(updateDateTime, 1000);

// Keyboard shortcuts
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        if (window.pywebview) window.pywebview.api.handle_action('exit');
    }
});

document.addEventListener('contextmenu',  (e) => e.preventDefault());
document.addEventListener('selectstart',  (e) => e.preventDefault());

// ============================================================================
// EYE TRACKING CALIBRATION
// ============================================================================

function startCalibration() {
    const btn      = document.getElementById('calibration-btn');
    const text     = document.getElementById('calibration-text');
    const statusText = document.getElementById('status-text');
    
    btn.classList.add('calibrating');
    text.textContent = 'Calibrating... Follow the dots';
    statusText.textContent = 'Calibrating...';
    
    if (window.pywebview && window.pywebview.api) {
        window.pywebview.api.start_calibration().then(response => {
            console.log('Calibration started:', response);
            checkTrackingStatus();
        }).catch(error => {
            console.error('Calibration error:', error);
            btn.classList.remove('calibrating');
            text.textContent = 'Calibration Failed - Try Again';
            statusText.textContent = 'Error';
        });
    } else {
        setTimeout(() => {
            btn.classList.remove('calibrating');
            btn.classList.add('calibrated');
            text.textContent = '✓ Eye Tracking Active';
            document.getElementById('tracking-status').classList.add('calibrated', 'tracking');
            statusText.textContent = 'Tracking Active';
        }, 3000);
    }
}

function checkTrackingStatus() {
    if (window.pywebview && window.pywebview.api) {
        window.pywebview.api.get_tracking_status().then(status => {
            const btn        = document.getElementById('calibration-btn');
            const text       = document.getElementById('calibration-text');
            const statusDiv  = document.getElementById('tracking-status');
            const statusText = document.getElementById('status-text');
            
            if (status.calibrated && status.running) {
                btn.classList.remove('calibrating');
                btn.classList.add('calibrated');
                text.textContent = '✓ Eye Tracking Active';
                statusDiv.classList.add('calibrated', 'tracking');
                statusText.textContent = status.paused ? 'Paused' : 'Tracking Active';
            } else if (status.calibrated) {
                btn.classList.remove('calibrating');
                btn.classList.add('calibrated');
                text.textContent = 'Start Tracking';
                statusDiv.classList.add('calibrated');
                statusText.textContent = 'Calibrated';
            } else {
                setTimeout(checkTrackingStatus, 1000);
            }
        }).catch(error => { console.error('Status check error:', error); });
    }
}

window.addEventListener('load', () => { setTimeout(checkTrackingStatus, 1000); });
