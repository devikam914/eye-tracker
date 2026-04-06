"""
Standalone Web UI Controller - No Eye Tracking Required
Simple web-based assistive interface that can be controlled with mouse/keyboard
"""
import webview
import os
import webbrowser


class WebUIAPI:
    """API for JavaScript to call Python functions"""
    
    def __init__(self, controller):
        self.controller = controller
    
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
    
    def make_call(self, number):
        """Make a phone call"""
        print(f"Making call to: {number}")
        try:
            # Use Windows Phone Link
            os.startfile(f"tel:{number}")
        except Exception as e:
            print(f"Error making call: {e}")
        return {'status': 'success', 'number': number}
    
    def cancel_call(self):
        """Cancel ongoing call"""
        print("Call cancelled")
        return {'status': 'success'}
    
    def update_settings(self, settings):
        """Update settings from web UI"""
        print(f"Settings updated: {settings}")
        return {'status': 'success'}
    
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
    
    def go_back_home(self):
        """Go back to home page"""
        self.controller.go_back_home()
        return {'status': 'success'}
    
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
    """Standalone UI controller without eye tracking"""
    
    def __init__(self):
        self.window = None
        self.running = False
        
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
            'Assistive Gaze Control',
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
        webview.start(debug=False)
    
    # Action handlers
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
        if self.window:
            self.window.destroy()
        print("System exited")


def main():
    """Entry point"""
    print("=" * 50)
    print("Assistive UI - Standalone Version")
    print("=" * 50)
    print("\nStarting web interface...")
    print("- Use mouse to click on tiles")
    print("- Hover over tiles to see dwell animation")
    print("- Press ESC to exit")
    print()
    
    controller = WebUIController()
    window = controller.create_window()
    controller.run()


if __name__ == "__main__":
    main()
