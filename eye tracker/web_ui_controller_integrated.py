"""
Integrated Web UI Controller with Eye Tracking
Combines the improved backend with your beautiful web UI
"""
import webview
import os
import webbrowser
import threading
import time
from main_integrated import EyeTrackingEngine, DWELL_TIME


class WebUIAPI:
    """API for JavaScript to call Python functions"""
    
    def __init__(self, controller):
        self.controller = controller
        self.engine = controller.engine
    
    # ========================================================================
    # NAVIGATION
    # ========================================================================
    def handle_action(self, action):
        """Handle action from web UI"""
        print(f"Action received: {action}")
        
        if action == 'calling':
            self.controller.show_calling()
        elif action == 'browsing':
            self.controller.launch_browser()
        elif action == 'keyboard':
            self.controller.show_keyboard()
        elif action == 'settings':
            self.controller.show_settings()
        elif action == 'exit':
            self.controller.exit_system()
        
        return {'status': 'success', 'action': action}
    
    def go_back_home(self):
        """Go back to home page"""
        self.controller.go_back_home()
        return {'status': 'success'}
    
    # ========================================================================
    # EYE TRACKING CONTROLS
    # ========================================================================
    def start_calibration(self):
        """Start eye tracking calibration"""
        print("Starting calibration from UI...")
        
        # Run calibration in separate thread to avoid blocking UI
        def calibrate_thread():
            success = self.engine.calibrate(grid_size=7)
            if success:
                print("Calibration successful!")
                # Auto-start tracking after calibration
                self.engine.start_tracking()
            else:
                print("Calibration failed or cancelled")
        
        thread = threading.Thread(target=calibrate_thread, daemon=True)
        thread.start()
        
        return {'status': 'started'}
    
    def start_tracking(self):
        """Start eye tracking"""
        if not self.engine.calibrated:
            return {'status': 'error', 'message': 'Must calibrate first'}
        
        success = self.engine.start_tracking()
        return {'status': 'success' if success else 'failed'}
    
    def pause_tracking(self):
        """Pause eye tracking"""
        self.engine.paused = True
        return {'status': 'success'}
    
    def resume_tracking(self):
        """Resume eye tracking"""
        self.engine.paused = False
        return {'status': 'success'}
    
    def stop_tracking(self):
        """Stop eye tracking"""
        self.engine.running = False
        return {'status': 'success'}
    
    def get_tracking_status(self):
        """Get current tracking status"""
        return {
            'calibrated': self.engine.calibrated,
            'running': self.engine.running,
            'paused': self.engine.paused,
            'dwell_progress': self.engine.clicker.progress if self.engine.calibrated else 0.0
        }
    
    # ========================================================================
    # SETTINGS
    # ========================================================================
    def update_dwell_time(self, value):
        """Update dwell time from settings"""
        import main_integrated
        main_integrated.DWELL_TIME = float(value)
        print(f"Dwell time updated to: {value}s")
        return {'status': 'success', 'dwell_time': value}
    
    def update_settings(self, settings):
        """Update settings from web UI"""
        print(f"Settings updated: {settings}")
        
        # Update dwell time if provided
        if 'dwellTime' in settings:
            self.update_dwell_time(settings['dwellTime'])
        
        return {'status': 'success'}
    
    # ========================================================================
    # PHONE CALLS
    # ========================================================================
    def make_call(self, number):
        """Make a phone call"""
        print(f"Making call to: {number}")
        try:
            # Pause tracking during call
            if self.engine.calibrated:
                self.engine.paused = True
            
            # Use Windows Phone Link
            os.startfile(f"tel:{number}")
        except Exception as e:
            print(f"Error making call: {e}")
        return {'status': 'success', 'number': number}
    
    def cancel_call(self):
        """Cancel ongoing call"""
        print("Call cancelled")
        # Resume tracking
        if self.engine.calibrated:
            self.engine.paused = False
        return {'status': 'success'}
    
    # ========================================================================
    # SYSTEM CONTROLS
    # ========================================================================
    def toggle_bluetooth(self, enabled):
        """Toggle Bluetooth"""
        print(f"Bluetooth: {'ON' if enabled else 'OFF'}")
        return {'status': 'success'}
    
    def toggle_wifi(self, enabled):
        """Toggle Wi-Fi"""
        print(f"Wi-Fi: {'ON' if enabled else 'OFF'}")
        return {'status': 'success'}
    
    def shutdown(self):
        """Shutdown system"""
        print("Shutdown requested")
        import subprocess
        if os.name == 'nt':  # Windows
            subprocess.run(['shutdown', '/s', '/t', '0'])
        return {'status': 'success'}
    
    def restart(self):
        """Restart system"""
        print("Restart requested")
        import subprocess
        if os.name == 'nt':  # Windows
            subprocess.run(['shutdown', '/r', '/t', '0'])
        return {'status': 'success'}
    
    # ========================================================================
    # KEYBOARD & BROWSING
    # ========================================================================
    def send_keystroke(self, key):
        """Send keystroke to active window"""
        print(f"Sending keystroke: {key}")
        return {'status': 'success', 'key': key}
    
    def open_url(self, url):
        """Open URL in external browser"""
        print(f"Opening URL: {url}")
        webbrowser.open(url)
        return {'status': 'success', 'url': url}
    
    def update_family_contact(self, contact):
        """Update family contact information"""
        print(f"Family contact updated: {contact}")
        return {'status': 'success', 'contact': contact}


class WebUIController:
    """Integrated UI controller with eye tracking"""
    
    def __init__(self, demo=True):
        self.window = None
        self.running = False
        self.demo = demo  # If False, skip auto-calibration
        
        # Initialize eye tracking engine
        print("Initializing eye tracking engine...")
        self.engine = EyeTrackingEngine()
        print("Eye tracking engine ready!")
        
        # Get web UI path
        self.web_ui_path = os.path.join(os.path.dirname(__file__), 'web_ui', 'index.html')
    
    def create_window(self):
        """Create web view window"""
        api = WebUIAPI(self)
        
        # Enable DPI awareness for proper scaling on Windows
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
        except:
            try:
                ctypes.windll.user32.SetProcessDPIAware()  # Fallback for older Windows
            except:
                pass  # DPI awareness not available
        
        self.window = webview.create_window(
            'Assistive Gaze Control - Eye Tracking Enabled',
            self.web_ui_path,
            js_api=api,
            fullscreen=True,
            frameless=False,
            easy_drag=False
        )
        
        return self.window
    
    def run(self):
        """Start the web UI"""
        self.running = True
        
        # Auto-start calibration if not in demo mode
        def on_loaded():
            time.sleep(2)  # Wait for UI to fully load
            
            if self.demo:
                print("\n" + "="*60)
                print("AUTO-STARTING CALIBRATION")
                print("="*60)
                print("Calibration will begin in 3 seconds...")
                print("="*60 + "\n")
                
                time.sleep(3)
                
                # Start calibration automatically
                print("Starting automatic calibration...")
                success = self.engine.calibrate(grid_size=7)
                
                if success:
                    print("\n" + "="*60)
                    print("CALIBRATION COMPLETE - TRACKING ACTIVE")
                    print("="*60)
                    print("Eye tracking is now active!")
                    print("Look at buttons and dwell to click")
                    print("="*60 + "\n")
                    
                    # Auto-start tracking after calibration
                    self.engine.start_tracking()
                else:
                    print("\nCalibration failed or cancelled")
            else:
                print("\n" + "="*60)
                print("DEMO MODE - CALIBRATION DISABLED")
                print("="*60)
                print("Click 'Start Calibration' button in the UI to begin")
                print("="*60 + "\n")
        
        threading.Thread(target=on_loaded, daemon=True).start()
        
        webview.start(debug=False)
    
    # ========================================================================
    # NAVIGATION METHODS
    # ========================================================================
    def launch_browser(self):
        """Launch browser page with integrated keyboard"""
        print("Launching browser page with keyboard")
        if self.window:
            browsing_path = os.path.join(os.path.dirname(__file__), 'web_ui', 'browsing_new.html')
            self.window.load_url(browsing_path)
    
    def show_keyboard(self):
        """Show virtual keyboard page"""
        print("Navigating to keyboard page")
        if self.window:
            keyboard_path = os.path.join(os.path.dirname(__file__), 'web_ui', 'keyboard.html')
            self.window.load_url(keyboard_path)
    
    def show_calling(self):
        """Show calling page"""
        print("Navigating to calling page")
        if self.window:
            calling_path = os.path.join(os.path.dirname(__file__), 'web_ui', 'calling.html')
            self.window.load_url(calling_path)
    
    def show_settings(self):
        """Show settings page"""
        print("Navigating to settings page")
        if self.window:
            settings_path = os.path.join(os.path.dirname(__file__), 'web_ui', 'settings.html')
            self.window.load_url(settings_path)
    
    def go_back_home(self):
        """Go back to home page"""
        print("Returning to home")
        if self.window:
            home_path = os.path.join(os.path.dirname(__file__), 'web_ui', 'index.html')
            self.window.load_url(home_path)
    
    def exit_system(self):
        """Clean exit"""
        self.running = False
        
        # Stop eye tracking
        if self.engine:
            self.engine.stop_tracking()
        
        if self.window:
            self.window.destroy()
        
        print("System exited")


def main(demo=True):
    """
    Entry point
    
    Args:
        demo (bool): If True (default), auto-start calibration on startup.
                     If False, wait for user to click calibration button.
    """
    print("=" * 60)
    print("ASSISTIVE GAZE CONTROL - INTEGRATED VERSION")
    print("=" * 60)
    print("\nFeatures:")
    print("✓ Eye tracking with calibration")
    print("✓ Dwell-based clicking")
    print("✓ Beautiful web UI")
    print("✓ Phone calling via Windows Phone Link")
    print("✓ Virtual keyboard")
    print("✓ Web browsing")
    print("✓ System settings")
    print()
    
    if demo:
        print("Mode: AUTO-CALIBRATION (demo=True)")
        print("Calibration will start automatically after UI loads")
    else:
        print("Mode: MANUAL CALIBRATION (demo=False)")
        print("Click 'Start Calibration' button to begin")
    
    print()
    print("Starting web interface...")
    print()
    
    controller = WebUIController(demo=demo)
    window = controller.create_window()
    controller.run()


if __name__ == "__main__":
    # Default: auto-start calibration
    # To disable auto-calibration, run: python web_ui_controller_integrated.py --no-demo
    import sys
    demo_mode = '--no-demo' not in sys.argv
    main(demo=demo_mode)
