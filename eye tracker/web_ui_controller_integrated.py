# -*- coding: utf-8 -*-
"""
Web UI Controller — integrated mode.

Calibration runs on the main thread (cv2.imshow requires it), then the
tracking loop starts in a background thread, then the webview UI opens.
All tracker state is shared in-process — no TCP socket needed.

Usage:
  python web_ui_controller_integrated.py            # full calibration + tracking
  python web_ui_controller_integrated.py --no-calib # skip calibration, UI only (mouse)
"""
import webview
import os
import sys
import json
import threading
import time
import ctypes
import ctypes.wintypes

# ---------------------------------------------------------------------------
# Win32 helpers — used for bring-to-front and snap guard
# ---------------------------------------------------------------------------
_u32 = ctypes.windll.user32

def _find_webview_hwnd():
    """Find the pywebview/WebView2 window HWND reliably.

    Strategy: enumerate all top-level windows, pick the one whose class is
    Chrome_WidgetWin_1 AND whose size covers most of the screen.  This is
    more reliable than FindWindowW(title) because frameless windows often
    have an empty Win32 title even when a title is passed to create_window().
    """
    try:
        sm_cx = _u32.GetSystemMetrics(0)   # screen width
        sm_cy = _u32.GetSystemMetrics(1)   # screen height
        threshold = 0.7                    # must cover ≥70% of screen in each dimension

        found = []

        @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
        def _cb(hwnd, _lp):
            if not _u32.IsWindowVisible(hwnd):
                return True
            cls_buf = ctypes.create_unicode_buffer(256)
            _u32.GetClassNameW(hwnd, cls_buf, 256)
            if cls_buf.value not in ('Chrome_WidgetWin_1', 'Chrome_WidgetWin_0'):
                return True
            rect = ctypes.wintypes.RECT()
            _u32.GetWindowRect(hwnd, ctypes.byref(rect))
            w = rect.right - rect.left
            h = rect.bottom - rect.top
            if w >= sm_cx * threshold and h >= sm_cy * threshold:
                found.append(hwnd)
            return True

        _u32.EnumWindows(_cb, 0)
        return found[0] if found else None
    except Exception:
        return None


def _bring_to_front(hwnd=None):
    """Bring the webview window to the foreground."""
    if hwnd is None:
        hwnd = _find_webview_hwnd()
    if not hwnd:
        return
    try:
        _u32.ShowWindow(hwnd, 9)                              # SW_RESTORE
        _u32.SetForegroundWindow(hwnd)
        _u32.BringWindowToTop(hwnd)
        _u32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 0x0003)      # HWND_TOPMOST, SWP_NOMOVE|SWP_NOSIZE
        time.sleep(0.1)
        _u32.SetWindowPos(hwnd, -2, 0, 0, 0, 0, 0x0003)      # HWND_NOTOPMOST
    except Exception:
        pass


def _is_point_in_webview(x, y):
    """Return True if screen point (x,y) is inside any WebView2 window."""
    try:
        sm_cx = _u32.GetSystemMetrics(0)
        sm_cy = _u32.GetSystemMetrics(1)
        threshold = 0.7

        result = [False]

        @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
        def _cb(hwnd, _lp):
            if not _u32.IsWindowVisible(hwnd):
                return True
            cls_buf = ctypes.create_unicode_buffer(256)
            _u32.GetClassNameW(hwnd, cls_buf, 256)
            if cls_buf.value not in ('Chrome_WidgetWin_1', 'Chrome_WidgetWin_0'):
                return True
            rect = ctypes.wintypes.RECT()
            _u32.GetWindowRect(hwnd, ctypes.byref(rect))
            w = rect.right - rect.left
            h = rect.bottom - rect.top
            if w >= sm_cx * threshold and h >= sm_cy * threshold:
                if rect.left <= x <= rect.right and rect.top <= y <= rect.bottom:
                    result[0] = True
            return True

        _u32.EnumWindows(_cb, 0)
        return result[0]
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Stub TrackerClient — replaced by in-process monkey-patch in main()
# ---------------------------------------------------------------------------
class TrackerClient:
    """Placeholder — all methods are replaced in main() to call tracker_process directly."""
    def __init__(self):
        self._status = {'status': 'idle', 'calibrated': False, 'x': 0, 'y': 0, 'dwell': 0.0}

    def get_status(self):
        return dict(self._status)

    def send(self, cmd_dict):
        return False

    def calibrate(self):  return self.send({'cmd': 'calibrate'})
    def pause(self):      return self.send({'cmd': 'pause'})
    def resume(self):     return self.send({'cmd': 'resume'})
    def set_dwell(self, v): return self.send({'cmd': 'set_dwell', 'value': v})


# ---------------------------------------------------------------------------
# Web UI API — called by JavaScript via pywebview
# ---------------------------------------------------------------------------
class WebUIAPI:
    def __init__(self, controller):
        self.controller = controller
        self.tracker = controller.tracker

    def handle_action(self, action):
        print(f"Action: {action}")
        if action == 'calling':    self.controller.show_calling()
        elif action == 'browsing': self.controller.launch_browser()
        elif action == 'keyboard': self.controller.show_keyboard()
        elif action == 'settings': self.controller.show_settings()
        elif action == 'exit':     self.controller.exit_system()
        return {'status': 'success', 'action': action}

    def go_back_home(self):
        self.controller.go_back_home()
        return {'status': 'success'}

    def start_calibration(self):
        self.tracker.calibrate()
        return {'status': 'started'}

    def start_tracking(self):
        self.tracker.resume()
        return {'status': 'success'}

    def pause_tracking(self):
        self.tracker.pause()
        return {'status': 'success'}

    def resume_tracking(self):
        self.tracker.resume()
        return {'status': 'success'}

    def stop_tracking(self):
        self.tracker.pause()
        return {'status': 'success'}

    def get_tracking_status(self):
        s = self.tracker.get_status()
        return {
            'calibrated':     s.get('calibrated', False),
            'running':        s.get('status') == 'tracking',
            'paused':         s.get('status') == 'paused',
            'dwell_progress': s.get('dwell', 0.0),
        }

    def update_dwell_time(self, value):
        self.tracker.set_dwell(float(value))
        return {'status': 'success', 'dwell_time': value}

    def update_settings(self, settings):
        if 'dwellTime' in settings:
            self.update_dwell_time(settings['dwellTime'])
        return {'status': 'success'}

    def make_call(self, number):
        print(f"Making call to: {number}")
        self.tracker.pause()
        try:
            os.startfile(f"tel:{number}")
        except Exception as e:
            print(f"Call error: {e}")
        def _resume():
            time.sleep(4.0)
            self.tracker.resume()
            _bring_to_front()
            print("Tracking resumed after call.")
        threading.Thread(target=_resume, daemon=True).start()
        return {'status': 'success', 'number': number}

    def cancel_call(self):
        self.tracker.resume()
        return {'status': 'success'}

    def toggle_bluetooth(self, enabled):
        return {'status': 'success'}

    def toggle_wifi(self, enabled):
        return {'status': 'success'}

    def shutdown(self):
        print("Closing application...")
        self.controller.exit_system()
        return {'status': 'success'}

    def restart(self):
        self.controller.exit_system()
        return {'status': 'success'}

    def send_keystroke(self, key):
        return {'status': 'success', 'key': key}

    def open_url(self, url):
        """External URLs → system browser then refocus webview.
        Local file URLs → load inside webview."""
        print(f"Opening URL: {url}")
        if url.startswith('http://') or url.startswith('https://'):
            import webbrowser
            webbrowser.open(url)
            if self.controller.window:
                def _refocus_and_notify():
                    time.sleep(1.5)
                    _bring_to_front()
                    js = (
                        "(function(){"
                        "var d=document.createElement('div');"
                        "d.style.cssText='position:fixed;top:50%;left:50%;"
                        "transform:translate(-50%,-50%);"
                        "background:rgba(79,172,254,0.95);color:white;"
                        "padding:20px 40px;border-radius:15px;font-size:20px;"
                        "font-weight:bold;z-index:999999;"
                        "box-shadow:0 10px 40px rgba(0,0,0,0.3)';"
                        "d.innerText='Browser opened \u2713';"
                        "document.body.appendChild(d);"
                        "setTimeout(function(){d.remove();},2000);"
                        "})();"
                    )
                    try:
                        self.controller.window.evaluate_js(js)
                    except Exception:
                        pass
                threading.Thread(target=_refocus_and_notify, daemon=True).start()
        else:
            if self.controller.window:
                self.controller.window.load_url(url)
        return {'status': 'success', 'url': url}

    def update_family_contact(self, contact):
        return {'status': 'success', 'contact': contact}


# ---------------------------------------------------------------------------
# Web UI Controller
# ---------------------------------------------------------------------------
class WebUIController:
    def __init__(self):
        self.window = None
        self.tracker = TrackerClient()
        self.web_ui_path = os.path.join(os.path.dirname(__file__), 'web_ui', 'index.html')

    def run(self):
        api = WebUIAPI(self)

        # DPI awareness — must match tracker_process so pyautogui coords == viewport coords
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                pass

        self.window = webview.create_window(
            'Assistive Gaze Control',
            self.web_ui_path,
            js_api=api,
            fullscreen=True,
            frameless=True,   # client area starts at OS pixel (0,0) — no title-bar offset
            easy_drag=False,
        )

        def _on_shown():
            # Wait for the webview to fully render, then bring it to front.
            # This fires after webview.start() returns control to the event loop,
            # which is after calibration has already finished.
            time.sleep(1.0)
            _bring_to_front()

        threading.Thread(target=_on_shown, daemon=True).start()
        webview.start(debug=False)

    # ---- Navigation --------------------------------------------------------
    def _load(self, filename):
        if self.window:
            p = os.path.join(os.path.dirname(__file__), 'web_ui', filename)
            self.window.load_url('file:///' + p.replace('\\', '/'))

    def launch_browser(self): self._load('browsing_new.html')
    def show_keyboard(self):  self._load('keyboard.html')
    def show_calling(self):   self._load('calling.html')
    def show_settings(self):  self._load('settings.html')
    def go_back_home(self):   self._load('index.html')

    def exit_system(self):
        if self.window:
            self.window.destroy()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main():
    print("=" * 60)
    print("ASSISTIVE GAZE CONTROL")
    print("=" * 60)

    skip_calib   = '--no-calib'    in sys.argv
    quick_calib  = '--quick-calib' in sys.argv

    sys.path.insert(0, os.path.dirname(__file__))
    import tracker_process as tp

    if skip_calib:
        print("\n[--no-calib] Skipping calibration — UI only / mouse mode.")
        with tp.state_lock:
            tp.state['status'] = 'idle'
            tp.state['calibrated'] = False
    elif quick_calib:
        print("\n[--quick-calib] Loading saved calibration + running residual correction only...")
        import cv2
        success = tp.run_quick_calibration()
        if not success:
            print("Quick calibration cancelled.")
            tp.cap.release()
            cv2.destroyAllWindows()
            return
        print("\nQuick calibration complete — starting tracker thread...")
        threading.Thread(target=tp.tracking_loop, daemon=True).start()
    else:
        print("\nStarting full calibration on main thread...")
        import cv2
        success = tp.run_calibration()
        if not success:
            print("Calibration cancelled.")
            tp.cap.release()
            cv2.destroyAllWindows()
            return
        print("\nCalibration complete — starting tracker thread...")
        threading.Thread(target=tp.tracking_loop, daemon=True).start()

    print("Starting web UI...\n")
    controller = WebUIController()

    # ---- Wire TrackerClient to in-process tracker_process state ------------
    def _get_status():
        with tp.state_lock:
            return dict(tp.state)

    def _send(cmd_dict):
        cmd = cmd_dict.get('cmd', '')
        if cmd == 'pause':
            with tp.state_lock:
                tp.state['status'] = 'paused'
        elif cmd == 'resume':
            with tp.state_lock:
                if tp.state['calibrated']:
                    tp.state['status'] = 'tracking'
        elif cmd == 'set_dwell':
            tp.DWELL_TIME = float(cmd_dict.get('value', 1.5))
        elif cmd == 'calibrate':
            def _do_calib():
                tp.run_calibration()
                threading.Thread(target=tp.tracking_loop, daemon=True).start()
            threading.Thread(target=_do_calib, daemon=True).start()
        return True

    controller.tracker.get_status = _get_status
    controller.tracker.send       = _send
    controller.tracker.calibrate  = lambda:   _send({'cmd': 'calibrate'})
    controller.tracker.pause      = lambda:   _send({'cmd': 'pause'})
    controller.tracker.resume     = lambda:   _send({'cmd': 'resume'})
    controller.tracker.set_dwell  = lambda v: _send({'cmd': 'set_dwell', 'value': v})

    controller.run()


if __name__ == '__main__':
    main()
