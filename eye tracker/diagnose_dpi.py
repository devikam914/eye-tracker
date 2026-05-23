"""
Run this to find the exact DPI scaling on this machine.
This tells us why there's an offset in the browser keyboard.
"""
import ctypes
import pyautogui

# Before DPI awareness
w1, h1 = pyautogui.size()
print(f"pyautogui.size() BEFORE DPI awareness: {w1}x{h1}")

# Set DPI awareness
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
    print("SetProcessDpiAwareness(2) succeeded")
except Exception as e:
    print(f"SetProcessDpiAwareness failed: {e}")

w2, h2 = pyautogui.size()
print(f"pyautogui.size() AFTER DPI awareness:  {w2}x{h2}")

# Get DPI directly
try:
    hdc = ctypes.windll.user32.GetDC(0)
    dpi_x = ctypes.windll.gdi32.GetDeviceCaps(hdc, 88)  # LOGPIXELSX
    dpi_y = ctypes.windll.gdi32.GetDeviceCaps(hdc, 90)  # LOGPIXELSY
    ctypes.windll.user32.ReleaseDC(0, hdc)
    print(f"DPI: {dpi_x}x{dpi_y}")
    print(f"Scale factor: {dpi_x/96:.2f}x ({int(dpi_x/96*100)}%)")
except Exception as e:
    print(f"DPI query failed: {e}")

# Get monitor info
try:
    import ctypes.wintypes
    class MONITORINFO(ctypes.Structure):
        _fields_ = [("cbSize", ctypes.c_ulong),
                    ("rcMonitor", ctypes.wintypes.RECT),
                    ("rcWork", ctypes.wintypes.RECT),
                    ("dwFlags", ctypes.c_ulong)]
    mi = MONITORINFO()
    mi.cbSize = ctypes.sizeof(MONITORINFO)
    hwnd = ctypes.windll.user32.GetDesktopWindow()
    hmon = ctypes.windll.user32.MonitorFromWindow(hwnd, 1)
    ctypes.windll.user32.GetMonitorInfoW(hmon, ctypes.byref(mi))
    phys_w = mi.rcMonitor.right - mi.rcMonitor.left
    phys_h = mi.rcMonitor.bottom - mi.rcMonitor.top
    print(f"Physical monitor resolution: {phys_w}x{phys_h}")
    print(f"Logical resolution (pyautogui): {w2}x{h2}")
    if phys_w != w2:
        scale = phys_w / w2
        print(f"OFFSET CAUSE: pyautogui returns logical pixels ({w2}x{h2})")
        print(f"              but screen is physically {phys_w}x{phys_h}")
        print(f"              scale = {scale:.3f}")
        print(f"              gaze coords need to be DIVIDED by {scale:.3f} for webview")
    else:
        print("No DPI scaling issue — pyautogui matches physical resolution")
except Exception as e:
    print(f"Monitor info failed: {e}")
