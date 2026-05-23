# -*- coding: utf-8 -*-
"""
app.py — Single entry point for Assistive Gaze Control.

Usage:
  python app.py               # full calibration (saves calibration_data.pkl)
  python app.py --quick-calib # load saved calib + correction only (~1 min)
  python app.py --no-calib    # UI only, mouse control (for setup tasks)
"""
import sys
import os
import threading
import time
import ctypes
import ctypes.wintypes
import webview

sys.path.insert(0, os.path.dirname(__file__))

# ---------------------------------------------------------------------------
# DPI awareness — set before everything else
# ---------------------------------------------------------------------------
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

# ---------------------------------------------------------------------------
# Win32 bring-to-front + terminal management
# ---------------------------------------------------------------------------
_u32 = ctypes.windll.user32

def _minimize_terminal():
    """Minimize the terminal/console window that launched this process."""
    try:
        # Get the console window for this process
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd:
            _u32.ShowWindow(hwnd, 6)  # SW_MINIMIZE
    except Exception:
        pass

def _find_webview_hwnd():
    try:
        sm_cx = _u32.GetSystemMetrics(0)
        sm_cy = _u32.GetSystemMetrics(1)
        found = []

        @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
        def _cb(hwnd, _lp):
            if not _u32.IsWindowVisible(hwnd):
                return True
            buf = ctypes.create_unicode_buffer(256)
            _u32.GetClassNameW(hwnd, buf, 256)
            if buf.value not in ('Chrome_WidgetWin_1', 'Chrome_WidgetWin_0'):
                return True
            rect = ctypes.wintypes.RECT()
            _u32.GetWindowRect(hwnd, ctypes.byref(rect))
            w = rect.right - rect.left
            h = rect.bottom - rect.top
            if w >= sm_cx * 0.7 and h >= sm_cy * 0.7:
                found.append(hwnd)
            return True

        _u32.EnumWindows(_cb, 0)
        return found[0] if found else None
    except Exception:
        return None


def _bring_to_front():
    hwnd = _find_webview_hwnd()
    if not hwnd:
        return
    try:
        # AllowSetForegroundWindow bypasses Windows' focus-steal prevention
        _u32.AllowSetForegroundWindow(0xFFFFFFFF)  # ASFW_ANY
        _u32.ShowWindow(hwnd, 9)           # SW_RESTORE
        _u32.SetForegroundWindow(hwnd)
        _u32.BringWindowToTop(hwnd)
        _u32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 0x0003)  # HWND_TOPMOST
        time.sleep(0.05)
        _u32.SetWindowPos(hwnd, -2, 0, 0, 0, 0, 0x0003)  # HWND_NOTOPMOST
    except Exception:
        pass

# ---------------------------------------------------------------------------
# Web UI API
# ---------------------------------------------------------------------------
class WebUIAPI:
    def __init__(self, engine, window_ref):
        self.engine   = engine
        self._win     = window_ref  # mutable list [window]

    def _load(self, filename):
        win = self._win[0]
        if win:
            p = os.path.join(os.path.dirname(__file__), 'web_ui', filename)
            win.load_url('file:///' + p.replace('\\', '/'))

    # ---- navigation --------------------------------------------------------
    def handle_action(self, action):
        print(f"Action: {action}")
        if   action == 'calling':  self._load('calling.html')
        elif action == 'browsing': self._load('browsing_new.html')
        elif action == 'keyboard': self._load('keyboard.html')
        elif action == 'settings': self._load('settings.html')
        elif action == 'exit':
            win = self._win[0]
            if win: win.destroy()
        return {'status': 'success', 'action': action}

    def go_back_home(self):
        self._load('index.html')
        return {'status': 'success'}

    # ---- tracking ----------------------------------------------------------
    def start_calibration(self):
        def _run():
            self.engine.run_full_calibration()
            self.engine.start_tracking()
        threading.Thread(target=_run, daemon=True).start()
        return {'status': 'started'}

    def pause_tracking(self):
        self.engine.paused = True
        return {'status': 'success'}

    def resume_tracking(self):
        self.engine.paused = False
        return {'status': 'success'}

    def stop_tracking(self):
        self.engine.paused = True
        return {'status': 'success'}

    def start_tracking(self):
        self.engine.paused = False
        return {'status': 'success'}

    def get_tracking_status(self):
        return {
            'calibrated':     self.engine.calibrated,
            'running':        self.engine._running,
            'paused':         self.engine.paused,
            'dwell_progress': self.engine.dwell_progress,
        }

    def update_dwell_time(self, value):
        import gaze_engine as _ge
        _ge.DWELL_TIME = float(value)
        print(f"Dwell time set to {value}s")
        return {'status': 'success', 'dwell_time': value}

    def update_settings(self, settings):
        if 'dwellTime' in settings:
            self.update_dwell_time(settings['dwellTime'])
        return {'status': 'success'}

    # ---- calling -----------------------------------------------------------
    def make_call(self, number):
        print(f"Making call to: {number}")

        # Minimize webview so Phone Link is visible
        webview_hwnd = _find_webview_hwnd()
        if webview_hwnd:
            _u32.ShowWindow(webview_hwnd, 6)  # SW_MINIMIZE

        # Open Phone Link via tel: URI
        try:
            import subprocess
            subprocess.Popen(['cmd', '/c', 'start', '', f'tel:{number}'])
        except Exception as e:
            print(f"Call error: {e}")
            try:
                os.startfile(f"tel:{number}")
            except Exception as e2:
                print(f"Fallback call error: {e2}")

        def _auto_call():
            import ctypes as _ct

            # Wait for Phone Link window — do NOT pause tracking so user can
            # manually click if auto-click fails
            phone_link_hwnd = None
            deadline = time.monotonic() + 10.0
            while time.monotonic() < deadline and not phone_link_hwnd:
                time.sleep(0.3)
                try:
                    titles = ['Phone Link', 'Your Phone', number]

                    @_ct.WINFUNCTYPE(_ct.c_bool, _ct.wintypes.HWND, _ct.wintypes.LPARAM)
                    def _cb(hwnd, _lp):
                        nonlocal phone_link_hwnd
                        if not _u32.IsWindowVisible(hwnd):
                            return True
                        buf = _ct.create_unicode_buffer(512)
                        _u32.GetWindowTextW(hwnd, buf, 512)
                        for t in titles:
                            if t.lower() in buf.value.lower():
                                phone_link_hwnd = hwnd
                                return False
                        return True

                    _u32.EnumWindows(_cb, 0)
                except Exception as e:
                    print(f"Window search: {e}")

            if not phone_link_hwnd:
                print("Phone Link window not found — restoring webview.")
                wv = _find_webview_hwnd()
                if wv:
                    _u32.ShowWindow(wv, 9)
                _bring_to_front()
                return

            # Bring Phone Link to front and wait for dialog to render
            print("Phone Link found — bringing to front...")
            _u32.AllowSetForegroundWindow(0xFFFFFFFF)
            _u32.ShowWindow(phone_link_hwnd, 9)
            _u32.SetForegroundWindow(phone_link_hwnd)
            _u32.BringWindowToTop(phone_link_hwnd)
            time.sleep(2.0)  # wait for Phone Link call dialog to fully render

            # Get window rect
            rect = _ct.wintypes.RECT()
            _u32.GetWindowRect(phone_link_hwnd, _ct.byref(rect))
            win_w = rect.right  - rect.left
            win_h = rect.bottom - rect.top

            import pyautogui as _pag
            _pag.FAILSAFE = False

            # Try UI Automation first to find the call button by name
            call_clicked = False
            try:
                import comtypes.client
                comtypes.client.GetModule('UIAutomationCore.dll')
                import comtypes.gen.UIAutomationClient as uia
                automation = comtypes.client.CreateObject(
                    '{ff48dba4-60ef-4201-aa87-54103eef594e}',
                    interface=uia.IUIAutomation)
                root = automation.ElementFromHandle(phone_link_hwnd)
                condition = automation.CreatePropertyCondition(
                    uia.UIA_ControlTypePropertyId, uia.UIA_ButtonControlTypeId)
                buttons = root.FindAll(uia.TreeScope_Descendants, condition)
                for i in range(buttons.Length):
                    btn = buttons.GetElement(i)
                    name = btn.CurrentName.lower() if btn.CurrentName else ''
                    if 'call' in name or 'dial' in name or 'phone' in name:
                        rect_btn = btn.CurrentBoundingRectangle
                        cx = (rect_btn.left + rect_btn.right) // 2
                        cy = (rect_btn.top  + rect_btn.bottom) // 2
                        print(f"Found call button via UIA: '{btn.CurrentName}' at ({cx},{cy})")
                        _pag.click(cx, cy)
                        call_clicked = True
                        break
            except Exception as e:
                print(f"UIA approach failed: {e}")

            if not call_clicked:
                # Fallback: try multiple Y positions
                print("Trying positional click fallback...")
                for y_frac in [0.65, 0.72, 0.78, 0.58]:
                    cx = rect.left + win_w // 2
                    cy = rect.top  + int(win_h * y_frac)
                    print(f"  Clicking at ({cx}, {cy}) [{y_frac*100:.0f}%]")
                    _pag.click(cx, cy)
                    time.sleep(0.4)
                    # Check if window changed (call started)
                    rect2 = _ct.wintypes.RECT()
                    _u32.GetWindowRect(phone_link_hwnd, _ct.byref(rect2))
                    if abs((rect2.bottom - rect2.top) - win_h) > 30:
                        print("  Window changed — call likely started.")
                        break
            print("Call automation done.")

            # After 15s restore webview (call should be connected by then)
            time.sleep(15.0)
            wv = _find_webview_hwnd()
            if wv:
                _u32.ShowWindow(wv, 9)
            _bring_to_front()
            print("Webview restored after call.")

        threading.Thread(target=_auto_call, daemon=True).start()
        return {'status': 'success', 'number': number}

    def trigger_drift_correction(self):
        """Trigger a manual drift correction (same as corner trigger)."""
        if not self.engine.calibrated:
            return {'status': 'error', 'message': 'Not calibrated'}
        if not self.engine._drift_running:
            self.engine._drift_running = True
            threading.Thread(target=self.engine._do_drift_correction,
                             daemon=True).start()
            return {'status': 'started'}
        return {'status': 'already_running'}

    def cancel_call(self):
        self.engine.paused = False
        return {'status': 'success'}

    # ---- browser -----------------------------------------------------------
    def open_url(self, url):
        print(f"Opening URL: {url}")
        if url.startswith('http://') or url.startswith('https://'):
            import webbrowser
            webbrowser.open(url)
            win = self._win[0]
            if win:
                def _refocus():
                    time.sleep(1.5)
                    _bring_to_front()
                    js = ("(function(){var d=document.createElement('div');"
                          "d.style.cssText='position:fixed;top:50%;left:50%;"
                          "transform:translate(-50%,-50%);"
                          "background:rgba(79,172,254,0.95);color:white;"
                          "padding:20px 40px;border-radius:15px;font-size:20px;"
                          "font-weight:bold;z-index:999999';"
                          "d.innerText='Browser opened \u2713';"
                          "document.body.appendChild(d);"
                          "setTimeout(function(){d.remove();},2000);})();")
                    try: win.evaluate_js(js)
                    except Exception: pass
                threading.Thread(target=_refocus, daemon=True).start()
        else:
            win = self._win[0]
            if win: win.load_url(url)
        return {'status': 'success', 'url': url}

    # ---- misc --------------------------------------------------------------
    def toggle_bluetooth(self, enabled): return {'status': 'success'}
    def toggle_wifi(self, enabled):      return {'status': 'success'}
    def send_keystroke(self, key):       return {'status': 'success', 'key': key}

    def update_family_contact(self, c):
        """Save family contact to disk — persists across sessions."""
        import json
        try:
            contact_file = os.path.join(os.path.dirname(__file__), 'family_contact.json')
            with open(contact_file, 'w') as f:
                json.dump(c, f)
            print(f"Family contact saved: {c}")
        except Exception as e:
            print(f"Error saving contact: {e}")
        return {'status': 'success', 'contact': c}

    def get_family_contact(self):
        """Load family contact from disk."""
        import json
        try:
            contact_file = os.path.join(os.path.dirname(__file__), 'family_contact.json')
            if os.path.exists(contact_file):
                with open(contact_file, 'r') as f:
                    return json.load(f)
        except Exception as e:
            print(f"Error loading contact: {e}")
        return {'name': '', 'phone': ''}

    def shutdown(self):
        win = self._win[0]
        if win: win.destroy()
        return {'status': 'success'}

    def restart(self):
        win = self._win[0]
        if win: win.destroy()
        return {'status': 'success'}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == '__main__':
    import argparse
    import cv2

    parser = argparse.ArgumentParser(description='Assistive Gaze Control')
    parser.add_argument('--quick-calib', action='store_true',
                        help='Load saved calibration + residual correction only (~1 min)')
    parser.add_argument('--no-calib', action='store_true',
                        help='Skip calibration — UI only / mouse mode')
    args = parser.parse_args()

    print("=" * 60)
    print("ASSISTIVE GAZE CONTROL")
    print("=" * 60)
    # Note: terminal stays visible during calibration for error visibility.
    # It gets minimized when the webview UI opens.

    # ---- Camera ------------------------------------------------------------
    print("\nInitialising camera...")
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("ERROR: Camera not detected. Check connection and try again.")
        sys.exit(1)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    cap.set(cv2.CAP_PROP_FPS, 30)

    # ---- Detector ----------------------------------------------------------
    print("Loading gaze detector...")
    try:
        from modules.ptgaze_detector import PTGazeDetector
        detector = PTGazeDetector()
        print(f"Detector: {'PTGaze (ETH-XGaze)' if detector._3d_available else 'MediaPipe landmarks (fallback)'}")
    except Exception as e:
        print(f"PTGazeDetector failed ({e}), falling back to MediaPipe landmarks")
        from modules.landmarks import FaceLandmarkDetector
        detector = FaceLandmarkDetector()

    # ---- Engine ------------------------------------------------------------
    from gaze_engine import GazeEngine
    engine = GazeEngine(cap, detector)

    # ---- Calibration (must run on main thread — cv2.imshow requirement) ----
    if args.no_calib:
        print("\n[--no-calib] Skipping calibration — UI only / mouse mode.")
    elif args.quick_calib:
        print("\n[--quick-calib] Loading saved calibration + residual correction...")
        success = engine.run_quick_calibration()
        if not success:
            print("Quick calibration cancelled.")
            cap.release()
            cv2.destroyAllWindows()
            sys.exit(0)
        print("Starting tracking thread...")
        engine.start_tracking()
    else:
        print("\nStarting full 49-point calibration...")
        success = engine.run_full_calibration()
        if not success:
            print("Calibration cancelled.")
            cap.release()
            cv2.destroyAllWindows()
            sys.exit(0)
        print("Starting tracking thread...")
        engine.start_tracking()

    # ---- Web UI ------------------------------------------------------------
    print("\nLaunching web UI...")
    web_ui_path = os.path.join(os.path.dirname(__file__), 'web_ui', 'index.html')

    # window_ref is a mutable list so WebUIAPI can reference the window
    # before it is created (webview.create_window returns before start())
    window_ref = [None]
    api = WebUIAPI(engine, window_ref)

    window = webview.create_window(
        'Assistive Gaze Control',
        web_ui_path,
        js_api=api,
        fullscreen=True,
        frameless=True,
        easy_drag=False,
    )
    window_ref[0] = window
    # Give the engine a reference to the webview window so it can
    # inject JS for the eye-break countdown overlay
    engine._webview_win = window

    def _on_shown():
        # Minimize the terminal so it doesn't cover the UI
        _minimize_terminal()
        # Retry bring-to-front several times
        for wait in [0.5, 1.0, 1.0, 1.5]:
            time.sleep(wait)
            _bring_to_front()

    threading.Thread(target=_on_shown, daemon=True).start()

    # Also hook the webview shown event for an immediate attempt
    def _webview_shown():
        time.sleep(0.2)
        _bring_to_front()

    window.events.shown += _webview_shown

    webview.start(debug=False)

    # ---- Cleanup -----------------------------------------------------------
    engine.stop_tracking()
    cap.release()
    cv2.destroyAllWindows()
    print("Exited.")
