# -*- coding: utf-8 -*-
"""
tracker_process.py — Eye tracking backend, runs as a SEPARATE PROCESS.

Communicates with the UI via a simple TCP socket on localhost:7007.
Commands received (newline-delimited JSON):
  {"cmd": "calibrate"}
  {"cmd": "start"}
  {"cmd": "pause"}
  {"cmd": "resume"}
  {"cmd": "stop"}
  {"cmd": "set_dwell", "value": 1.5}

Status sent back every 100ms:
  {"status": "tracking", "x": 960, "y": 540, "dwell": 0.0}
  {"status": "calibrating"}
  {"status": "idle"}
  {"status": "error", "msg": "..."}

Running as a separate process means:
  - cv2.imshow (calibration) owns the main thread with no competition
  - pyautogui.moveTo works normally (no fullscreen webview blocking it)
  - webview runs in its own process with no GIL contention
  - "Python not responding" is impossible — they can't block each other
"""
import cv2
import numpy as np
import pyautogui
import time
import socket
import json
import threading
import ctypes
import ctypes.wintypes
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from scipy.interpolate import RBFInterpolator
from modules.ptgaze_detector import PTGazeDetector

# ---------------------------------------------------------------------------
print("Tracker process starting...")

# Set DPI awareness before anything else so pyautogui.size() returns physical pixels
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    pass

pyautogui.FAILSAFE = False
screen_w, screen_h = pyautogui.size()
print(f"Screen: {screen_w}x{screen_h} (physical pixels)")

detector = PTGazeDetector()
cap = cv2.VideoCapture(0)
if not cap.isOpened():
    print("ERROR: Camera not detected"); sys.exit(1)

BLINK_THRESHOLD = 0.18
CALIB_EAR_MIN   = 0.12
FONT            = cv2.FONT_HERSHEY_SIMPLEX

DWELL_TIME     = 1.5
DWELL_RADIUS   = 45
DWELL_COOLDOWN = 1.2

# ---------------------------------------------------------------------------
# Win32 element snap (same as git version)
# ---------------------------------------------------------------------------
_u32 = ctypes.windll.user32
_u32.WindowFromPoint.restype  = ctypes.wintypes.HWND
_u32.WindowFromPoint.argtypes = [ctypes.wintypes.POINT]
_u32.GetWindowRect.restype    = ctypes.wintypes.BOOL
_u32.GetWindowRect.argtypes   = [ctypes.wintypes.HWND, ctypes.POINTER(ctypes.wintypes.RECT)]
_u32.IsWindowVisible.restype  = ctypes.wintypes.BOOL
_u32.IsWindowVisible.argtypes = [ctypes.wintypes.HWND]
SNAP_RADIUS = 40

def snap_to_nearest_element(x, y):
    # Skip the Win32 accessibility tree walk entirely when the point is inside
    # any WebView2 window — walking that tree causes the .Empty.Empty... flood.
    # We check the point itself (not just the foreground window) because focus
    # can briefly shift during a dwell click.
    try:
        fg = _u32.GetForegroundWindow()
        if fg:
            cls_buf = ctypes.create_unicode_buffer(256)
            ctypes.windll.user32.GetClassNameW(fg, cls_buf, 256)
            if cls_buf.value in ('Chrome_WidgetWin_1', 'Chrome_WidgetWin_0'):
                return int(x), int(y)
            buf = ctypes.create_unicode_buffer(256)
            ctypes.windll.user32.GetWindowTextW(fg, buf, 256)
            title = buf.value
            if 'Assistive Gaze' in title or 'GazeBrowse' in title:
                return int(x), int(y)
    except Exception:
        pass
    # Also bail if the click point itself is inside a large WebView2 window
    # (handles the case where focus briefly left the webview)
    try:
        sm_cx = _u32.GetSystemMetrics(0)
        sm_cy = _u32.GetSystemMetrics(1)
        threshold = 0.7
        ix, iy = int(x), int(y)

        skip = [False]

        @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
        def _cb(hwnd, _lp):
            if skip[0]:
                return False
            if not _u32.IsWindowVisible(hwnd):
                return True
            cb2 = ctypes.create_unicode_buffer(256)
            ctypes.windll.user32.GetClassNameW(hwnd, cb2, 256)
            if cb2.value not in ('Chrome_WidgetWin_1', 'Chrome_WidgetWin_0'):
                return True
            rect = ctypes.wintypes.RECT()
            _u32.GetWindowRect(hwnd, ctypes.byref(rect))
            w = rect.right - rect.left
            h = rect.bottom - rect.top
            if w >= sm_cx * threshold and h >= sm_cy * threshold:
                if rect.left <= ix <= rect.right and rect.top <= iy <= rect.bottom:
                    skip[0] = True
            return True

        _u32.EnumWindows(_cb, 0)
        if skip[0]:
            return int(x), int(y)
    except Exception:
        pass
    try:
        best_dist = float(SNAP_RADIUS + 1)
        best_cx, best_cy = float(x), float(y)
        seen = set()
        step = max(3, SNAP_RADIUS // 5)
        for dx in range(-SNAP_RADIUS, SNAP_RADIUS + 1, step):
            for dy in range(-SNAP_RADIUS, SNAP_RADIUS + 1, step):
                px = int(x + dx); py = int(y + dy)
                hwnd = _u32.WindowFromPoint(ctypes.wintypes.POINT(px, py))
                if not hwnd or hwnd in seen: continue
                seen.add(hwnd)
                if not _u32.IsWindowVisible(hwnd): continue
                rect = ctypes.wintypes.RECT()
                if not _u32.GetWindowRect(hwnd, ctypes.byref(rect)): continue
                w = rect.right - rect.left; h = rect.bottom - rect.top
                if w < 5 or h < 5 or w > screen_w // 2 or h > screen_h // 3: continue
                ecx = (rect.left + rect.right) / 2.0
                ecy = (rect.top + rect.bottom) / 2.0
                dist = ((ecx-x)**2 + (ecy-y)**2)**0.5
                if dist < best_dist:
                    best_dist = dist; best_cx, best_cy = ecx, ecy
        return int(best_cx), int(best_cy)
    except Exception:
        return int(x), int(y)

# ---------------------------------------------------------------------------
class OneEuroFilter:
    def __init__(self, min_cutoff=1.0, beta=0.2, d_cutoff=1.0):
        self.min_cutoff = min_cutoff; self.beta = beta
        self.d_cutoff = d_cutoff; self.x_prev = None
        self.dx_prev = 0.0; self.t_prev = None

    @staticmethod
    def _alpha(cutoff, dt):
        tau = 1.0 / (2.0 * np.pi * cutoff)
        return 1.0 / (1.0 + tau / max(dt, 1e-6))

    def __call__(self, x, t):
        if self.x_prev is None:
            self.x_prev = x; self.t_prev = t; return x
        dt = max(t - self.t_prev, 1e-6)
        dx = (x - self.x_prev) / dt
        a_d = self._alpha(self.d_cutoff, dt)
        self.dx_prev = a_d * dx + (1 - a_d) * self.dx_prev
        cutoff = self.min_cutoff + self.beta * abs(self.dx_prev)
        a = self._alpha(cutoff, dt)
        x_hat = a * x + (1 - a) * self.x_prev
        self.x_prev = x_hat; self.t_prev = t
        return x_hat

class GazeFilter:
    def __init__(self):
        self.fx = OneEuroFilter(min_cutoff=1.0, beta=0.2)
        self.fy = OneEuroFilter(min_cutoff=1.0, beta=0.2)
    def reset(self): self.fx.x_prev = None; self.fy.x_prev = None
    def update(self, mx, my):
        t = cv2.getTickCount() / cv2.getTickFrequency()
        return self.fx(mx, t), self.fy(my, t)

class DwellClicker:
    def __init__(self):
        self.anchor_x = self.anchor_y = None
        self.dwell_start = None; self.last_click = 0.0; self.progress = 0.0

    def update(self, gx, gy):
        now = time.monotonic()
        # Read DWELL_TIME as global so UI changes take effect immediately
        if now - self.last_click < DWELL_COOLDOWN:
            self._reset(gx, gy); self.progress = 0.0; return False
        if self.anchor_x is None:
            self._reset(gx, gy); return False
        dist = np.hypot(gx - self.anchor_x, gy - self.anchor_y)
        if dist > DWELL_RADIUS:
            self._reset(gx, gy); return False
        elapsed = now - self.dwell_start
        self.progress = min(elapsed / max(DWELL_TIME, 0.1), 1.0)
        if elapsed >= DWELL_TIME:
            snap_x, snap_y = snap_to_nearest_element(self.anchor_x, self.anchor_y)
            snapped = (snap_x != int(self.anchor_x) or snap_y != int(self.anchor_y))
            pyautogui.click(snap_x, snap_y)
            print(f"Dwell click at ({snap_x}, {snap_y})" + (" [snapped]" if snapped else ""))
            self.last_click = now; self._reset(gx, gy); return True
        return False

    def _reset(self, gx, gy):
        self.anchor_x = gx; self.anchor_y = gy
        self.dwell_start = time.monotonic(); self.progress = 0.0

class AxisNormalizer:
    def __init__(self):
        self.X_CENTER = 0.5; self.X_HALF = 0.15
        self.Y_CENTER = -0.1; self.Y_HALF = 0.08

    def fit(self, gaze_pts, grid_n=7):
        x_min, x_max = gaze_pts[:,0].min(), gaze_pts[:,0].max()
        self.X_CENTER = (x_max + x_min) / 2.0
        if (x_max - x_min) > 0.001:
            self.X_HALF = (x_max - x_min) / (2.0 * 0.80)
        top_y = float(np.median(gaze_pts[:grid_n, 1]))
        bot_y = float(np.median(gaze_pts[(grid_n*(grid_n-1)):, 1]))
        y_span = bot_y - top_y
        if abs(y_span) > 0.01:
            self.Y_HALF = y_span / (2.0 * 0.75)
            self.Y_CENTER = top_y - (0.02 - 0.5) * 2.0 * self.Y_HALF
        else:
            y_min, y_max = gaze_pts[:,1].min(), gaze_pts[:,1].max()
            self.Y_CENTER = (y_max + y_min) / 2.0
            if (y_max - y_min) > 0.001:
                self.Y_HALF = (y_max - y_min) / (2.0 * 0.74)

    def transform(self, gaze_pts):
        arr = np.atleast_2d(gaze_pts).astype(np.float64).copy()
        arr[:,0] = (arr[:,0] - self.X_CENTER) / (2.0 * self.X_HALF) + 0.5
        arr[:,1] = (arr[:,1] - self.Y_CENTER) / (2.0 * self.Y_HALF) + 0.5
        return arr

class RBFGazeMapper:
    def __init__(self, smoothing=0.03):
        self.rbf_x = self.rbf_y = None; self.s = smoothing
    def fit(self, gaze_pts, screen_pts):
        self.rbf_x = RBFInterpolator(gaze_pts, screen_pts[:,0], kernel='thin_plate_spline', smoothing=self.s)
        self.rbf_y = RBFInterpolator(gaze_pts, screen_pts[:,1], kernel='thin_plate_spline', smoothing=self.s)
    def predict(self, gaze_pt):
        q = np.atleast_2d(gaze_pt).astype(np.float64)
        return float(self.rbf_x(q)[0]), float(self.rbf_y(q)[0])

class ResidualCorrectionField:
    def __init__(self):
        self.rbf_rx = self.rbf_ry = None; self.fitted = False
        self.n_pts = 0; self.drift_x = 0.0; self.drift_y = 0.0
    def fit(self, pred_pts, actual_pts):
        pred_arr = np.array(pred_pts, dtype=np.float64)
        actual_arr = np.array(actual_pts, dtype=np.float64)
        res_x = actual_arr[:,0] - pred_arr[:,0]
        res_y = actual_arr[:,1] - pred_arr[:,1]
        self.rbf_rx = RBFInterpolator(pred_arr, res_x, kernel='thin_plate_spline', smoothing=0.5)
        self.rbf_ry = RBFInterpolator(pred_arr, res_y, kernel='thin_plate_spline', smoothing=0.5)
        self.fitted = True; self.n_pts = len(pred_pts)
    def correct(self, pred_x, pred_y):
        if not self.fitted: return float(pred_x), float(pred_y)
        q = np.array([[pred_x, pred_y]], dtype=np.float64)
        return float(pred_x) + float(self.rbf_rx(q)[0]), float(pred_y) + float(self.rbf_ry(q)[0])

def flip_x(raw_xy):
    arr = np.atleast_2d(raw_xy).astype(np.float64).copy()
    arr[:,0] = 1.0 - arr[:,0]; return arr

def add_edge_anchors(gaze_pts, screen_pts, sw, sh, nr=7, nc=7):
    g_ex, s_ex = [], []
    for row in range(nr):
        b = row * nc
        g0, g1 = gaze_pts[b].copy(), gaze_pts[b+1].copy()
        s0, s1 = screen_pts[b].copy(), screen_pts[b+1].copy()
        dx = s1[0] - s0[0]
        if abs(dx) > 1:
            t = (0.0 - s0[0]) / dx
            g_ex.append(g0+t*(g1-g0)); s_ex.append([0.0, float(s0[1])])
        gA, gB = gaze_pts[b+nc-2].copy(), gaze_pts[b+nc-1].copy()
        sA, sB = screen_pts[b+nc-2].copy(), screen_pts[b+nc-1].copy()
        dx = sB[0] - sA[0]
        if abs(dx) > 1:
            t = (float(sw-1) - sB[0]) / dx
            g_ex.append(gB+t*(gB-gA)); s_ex.append([float(sw-1), float(sB[1])])
    for col in range(nc):
        g0, g1 = gaze_pts[col].copy(), gaze_pts[nc+col].copy()
        s0, s1 = screen_pts[col].copy(), screen_pts[nc+col].copy()
        dy = s1[1] - s0[1]
        if abs(dy) > 1:
            t = (0.0 - s0[1]) / dy
            g_ex.append(g0+t*(g1-g0)); s_ex.append([float(s0[0]), 0.0])
        gA = gaze_pts[(nr-2)*nc+col].copy(); gB = gaze_pts[(nr-1)*nc+col].copy()
        sA = screen_pts[(nr-2)*nc+col].copy(); sB = screen_pts[(nr-1)*nc+col].copy()
        dy = sB[1] - sA[1]
        if abs(dy) > 1:
            t = (float(sh-1) - sB[1]) / dy
            g_ex.append(gB+t*(gB-gA)); s_ex.append([float(sB[0]), float(sh-1)])
    if g_ex:
        return (np.vstack([gaze_pts, np.array(g_ex)]),
                np.vstack([screen_pts, np.array(s_ex, dtype=np.float64)]))
    return gaze_pts, screen_pts

# ---------------------------------------------------------------------------
# Global state
# ---------------------------------------------------------------------------
state = {
    'status': 'idle',       # idle | calibrating | tracking | paused
    'calibrated': False,
    'x': screen_w // 2,
    'y': screen_h // 2,
    'dwell': 0.0,
}
state_lock = threading.Lock()

normalizer  = AxisNormalizer()
mapper      = RBFGazeMapper(smoothing=0.03)
corrector   = ResidualCorrectionField()
gaze_filter = GazeFilter()
clicker     = DwellClicker()

CALIB_SAVE_PATH = os.path.join(os.path.dirname(__file__), 'calibration.npz')

GRID_N = 7
_cx = [0.02, 0.17, 0.33, 0.50, 0.67, 0.83, 0.98]
_cy = [0.02, 0.17, 0.33, 0.50, 0.67, 0.83, 0.98]
calibration_points = [(x, y) for y in _cy for x in _cx]
VALIDATION_PX = 120

def save_calibration(norm, normed_aug, outputs_aug):
    """Persist calibration data so quick-calib can reload it next session."""
    try:
        np.savez(CALIB_SAVE_PATH,
                 X_CENTER=np.array([norm.X_CENTER]),
                 X_HALF=np.array([norm.X_HALF]),
                 Y_CENTER=np.array([norm.Y_CENTER]),
                 Y_HALF=np.array([norm.Y_HALF]),
                 normed_aug=normed_aug,
                 outputs_aug=outputs_aug)
        print(f"Calibration saved to {CALIB_SAVE_PATH}")
    except Exception as e:
        print(f"Warning: could not save calibration: {e}")


def load_calibration():
    """Load saved calibration. Returns (normalizer, mapper) or (None, None)."""
    if not os.path.exists(CALIB_SAVE_PATH):
        return None, None
    try:
        d = np.load(CALIB_SAVE_PATH)
        _norm = AxisNormalizer()
        _norm.X_CENTER = float(d['X_CENTER'][0])
        _norm.X_HALF   = float(d['X_HALF'][0])
        _norm.Y_CENTER = float(d['Y_CENTER'][0])
        _norm.Y_HALF   = float(d['Y_HALF'][0])
        normed_aug  = d['normed_aug']
        outputs_aug = d['outputs_aug']
        _mapper = RBFGazeMapper(smoothing=0.03)
        _mapper.fit(normed_aug, outputs_aug)
        print(f"Loaded saved calibration ({len(normed_aug)} points).")
        return _norm, _mapper
    except Exception as e:
        print(f"Warning: could not load calibration: {e}")
        return None, None


def run_quick_calibration():
    """Quick-start: load saved calibration, run only the residual correction (~1 min).
    Falls back to full calibration if no saved data exists."""
    global normalizer, mapper, corrector, gaze_filter, clicker

    _norm, _mapper = load_calibration()
    if _norm is None or _mapper is None:
        print("No saved calibration found — running full calibration.")
        return run_calibration()

    with state_lock: state['status'] = 'calibrating'

    # Residual correction only — 16 points, ~1 minute
    corr_fracs = [0.02, 0.35, 0.65, 0.98]
    correction_grid = [(x, y) for y in corr_fracs for x in corr_fracs]
    cv2.namedWindow("Calibration", cv2.WND_PROP_FULLSCREEN)
    cv2.setWindowProperty("Calibration", cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)

    corr_pred_pts = []; corr_actual_pts = []
    for ci, (fx, fy) in enumerate(correction_grid):
        tx = int(fx * screen_w); ty = int(fy * screen_h)
        raw = collect_samples(30, f"Quick-cal {ci+1}/{len(correction_grid)}", tx, ty, settle=1.0)
        if raw is None:
            cv2.destroyAllWindows()
            with state_lock: state['status'] = 'idle'
            return False
        if len(raw) >= 10:
            avg = np.mean(np.array(raw), axis=0)
            proc = _norm.transform(flip_x(np.array([avg])))[0]
            px_p, py_p = _mapper.predict(proc)
            corr_pred_pts.append([px_p, py_p])
            corr_actual_pts.append([float(tx), float(ty)])
    cv2.destroyAllWindows()

    _corr = ResidualCorrectionField()
    if len(corr_pred_pts) >= 4:
        _corr.fit(corr_pred_pts, corr_actual_pts)
        print(f"Quick-cal residual correction fitted on {len(corr_pred_pts)} points.")

    # Commit
    normalizer = _norm; mapper = _mapper; corrector = _corr
    gaze_filter = GazeFilter(); clicker = DwellClicker()

    with state_lock:
        state['status'] = 'tracking'
        state['calibrated'] = True
    print("Quick calibration complete — tracking active.")
    return True

# ---------------------------------------------------------------------------
def collect_samples(n, label, tx, ty, settle=1.5):
    t0 = cv2.getTickCount()
    while (cv2.getTickCount()-t0)/cv2.getTickFrequency() < settle:
        display = np.zeros((screen_h, screen_w, 3), dtype=np.uint8)
        cv2.circle(display, (tx,ty), 20, (80,180,255), 2)
        cv2.circle(display, (tx,ty), 7,  (80,180,255), -1)
        cv2.circle(display, (tx,ty), 2,  (255,255,255), -1)
        if label:
            cv2.putText(display, label, (tx-len(label)*4, ty+45), FONT, 0.5, (150,150,150), 1)
        cv2.imshow("Calibration", display)
        if cv2.waitKey(1) & 0xFF == 27: return None
    samples = []
    while len(samples) < n:
        ret, frame = cap.read()
        if not ret: continue
        gx, gy, ear = detector.process(frame)
        if gx is not None and ear > CALIB_EAR_MIN:
            samples.append([gx, gy])
        display = np.zeros((screen_h, screen_w, 3), dtype=np.uint8)
        cv2.circle(display, (tx,ty), 8, (0,220,80), -1)
        cv2.circle(display, (tx,ty), 2, (255,255,255), -1)
        prog = int(360 * len(samples) / n)
        cv2.ellipse(display, (tx,ty), (24,24), -90, 0, prog, (0,255,120), 3)
        cv2.imshow("Calibration", display)
        if cv2.waitKey(1) & 0xFF == 27: return None
    s = np.array(samples, dtype=np.float64)
    for _ in range(2):
        for axis in [0,1]:
            q1,q3 = np.percentile(s[:,axis],[25,75]); iqr = q3-q1
            s = s[(s[:,axis] >= q1-1.2*iqr) & (s[:,axis] <= q3+1.2*iqr)]
        if len(s) < 10: s = np.array(samples, dtype=np.float64); break
    return s.tolist()


def run_calibration():
    global normalizer, mapper, corrector, gaze_filter, clicker
    with state_lock: state['status'] = 'calibrating'

    N_PTS = len(calibration_points)
    print(f"Starting {N_PTS}-point calibration.")
    cv2.namedWindow("Calibration", cv2.WND_PROP_FULLSCREEN)
    cv2.setWindowProperty("Calibration", cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)

    inputs_raw = []; outputs_px = []
    for pt_idx, (px, py) in enumerate(calibration_points):
        tx, ty = int(px*screen_w), int(py*screen_h)
        raw = collect_samples(30, f"{pt_idx+1}/{N_PTS}", tx, ty)
        if raw is None:
            cv2.destroyAllWindows()
            with state_lock: state['status'] = 'idle'
            return False
        s = np.array(raw); avg = np.mean(s, axis=0)
        inputs_raw.append(avg); outputs_px.append([tx, ty])

    cv2.destroyAllWindows()
    inputs_raw = np.array(inputs_raw); outputs_px = np.array(outputs_px)

    flipped = flip_x(inputs_raw)
    _norm = AxisNormalizer(); _norm.fit(flipped, grid_n=GRID_N)
    normed = _norm.transform(flipped)

    # Validation
    tmp_rx = RBFInterpolator(normed, outputs_px[:,0].astype(float), kernel='thin_plate_spline', smoothing=0.1)
    tmp_ry = RBFInterpolator(normed, outputs_px[:,1].astype(float), kernel='thin_plate_spline', smoothing=0.1)
    bad_pts = []
    for i in range(N_PTS):
        q = normed[i:i+1]
        err = float(np.sqrt((float(tmp_rx(q)[0])-outputs_px[i,0])**2 + (float(tmp_ry(q)[0])-outputs_px[i,1])**2))
        if err >= VALIDATION_PX: bad_pts.append(i)

    if bad_pts:
        cv2.namedWindow("Calibration", cv2.WND_PROP_FULLSCREEN)
        cv2.setWindowProperty("Calibration", cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
        for i in bad_pts:
            px, py = calibration_points[i]; tx, ty = int(px*screen_w), int(py*screen_h)
            raw = collect_samples(30, f"Recollect {i+1}", tx, ty)
            if raw: inputs_raw[i] = np.mean(np.array(raw), axis=0)
        cv2.destroyAllWindows()
        flipped = flip_x(inputs_raw)
        _norm = AxisNormalizer(); _norm.fit(flipped, grid_n=GRID_N)
        normed = _norm.transform(flipped)

    normed_aug, outputs_aug = add_edge_anchors(normed, outputs_px.astype(np.float64), screen_w, screen_h, nr=GRID_N, nc=GRID_N)
    _mapper = RBFGazeMapper(smoothing=0.03); _mapper.fit(normed_aug, outputs_aug)

    # Residual correction
    corr_fracs = [0.02, 0.35, 0.65, 0.98]
    correction_grid = [(x,y) for y in corr_fracs for x in corr_fracs]
    cv2.namedWindow("Calibration", cv2.WND_PROP_FULLSCREEN)
    cv2.setWindowProperty("Calibration", cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
    corr_pred_pts = []; corr_actual_pts = []
    for ci, (fx, fy) in enumerate(correction_grid):
        tx = int(fx*screen_w); ty = int(fy*screen_h)
        raw = collect_samples(30, f"Correction {ci+1}/{len(correction_grid)}", tx, ty, settle=1.0)
        if raw is None: cv2.destroyAllWindows(); break
        if len(raw) >= 10:
            avg = np.mean(np.array(raw), axis=0)
            proc = _norm.transform(flip_x(np.array([avg])))[0]
            px_p, py_p = _mapper.predict(proc)
            corr_pred_pts.append([px_p, py_p]); corr_actual_pts.append([float(tx), float(ty)])
    cv2.destroyAllWindows()

    _corr = ResidualCorrectionField()
    if len(corr_pred_pts) >= 4:
        _corr.fit(corr_pred_pts, corr_actual_pts)
        print(f"Residual correction fitted on {len(corr_pred_pts)} points.")

    # Save calibration data for quick-calib on next run
    save_calibration(_norm, normed_aug, outputs_aug)

    # Commit atomically
    normalizer = _norm; mapper = _mapper; corrector = _corr
    gaze_filter = GazeFilter(); clicker = DwellClicker()

    with state_lock:
        state['status'] = 'tracking'
        state['calibrated'] = True
    print("Calibration complete — tracking active.")
    return True


def tracking_loop():
    blink_cooldown = 0
    last_x = screen_w // 2; last_y = screen_h // 2

    # Corner-triggered drift correction:
    # Gaze at top-left corner (within 80px) for 2s → triggers drift correction
    CORNER_RADIUS   = 80   # px from top-left corner
    CORNER_DWELL    = 2.0  # seconds to hold gaze in corner
    corner_start    = None
    in_corner       = False
    drift_triggered = False

    while True:
        with state_lock:
            s = state['status']
        if s not in ('tracking',):
            corner_start = None; in_corner = False
            time.sleep(0.05); continue

        ret, frame = cap.read()
        if not ret: continue

        gx, gy, ear = detector.process(frame)

        if gx is not None:
            proc = normalizer.transform(flip_x(np.array([[gx, gy]])))[0]
            pred_x, pred_y = mapper.predict(proc)
            pred_x, pred_y = corrector.correct(pred_x, pred_y)
            pred_x += corrector.drift_x; pred_y += corrector.drift_y

            if ear < BLINK_THRESHOLD:
                blink_cooldown = 20; gaze_filter.reset(); clicker._reset(pred_x, pred_y)
                corner_start = None; in_corner = False
            elif blink_cooldown > 0:
                blink_cooldown -= 1
                pyautogui.moveTo(last_x, last_y)
            else:
                pred_x = float(np.clip(pred_x, 0, screen_w-1))
                pred_y = float(np.clip(pred_y, 0, screen_h-1))
                sx, sy = gaze_filter.update(pred_x, pred_y)
                last_x = int(np.clip(sx, 0, screen_w-1))
                last_y = int(np.clip(sy, 0, screen_h-1))
                pyautogui.moveTo(last_x, last_y)
                clicker.update(last_x, last_y)

                # Corner drift correction — cursor clamped to (0,0) = looking beyond top-left edge
                # This only triggers when gaze goes past the screen boundary,
                # not when looking at a button near the corner
                if last_x == 0 and last_y == 0:
                    if corner_start is None:
                        corner_start = time.monotonic()
                        in_corner = True
                    elif time.monotonic() - corner_start >= CORNER_DWELL and not drift_triggered:
                        drift_triggered = True
                        print("Corner drift correction triggered (gaze beyond top-left)...")
                        threading.Thread(
                            target=_do_drift_correction,
                            daemon=True
                        ).start()
                else:
                    corner_start = None
                    in_corner = False
                    drift_triggered = False

        with state_lock:
            state['x'] = last_x; state['y'] = last_y
            state['dwell'] = clicker.progress


def _do_drift_correction():
    """Run drift correction — pauses tracking, collects centre samples, resumes."""
    with state_lock: state['status'] = 'paused'
    gaze_filter.reset()
    cx_t = screen_w // 2; cy_t = screen_h // 2
    cv2.namedWindow("Calibration", cv2.WND_PROP_FULLSCREEN)
    cv2.setWindowProperty("Calibration", cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
    raw = collect_samples(30, "Look at centre - drift fix", cx_t, cy_t, settle=1.5)
    cv2.destroyWindow("Calibration")
    if raw and len(raw) >= 8:
        avg_d = np.mean(np.array(raw), axis=0)
        proc_d = normalizer.transform(flip_x(np.array([avg_d])))[0]
        px_d, py_d = mapper.predict(proc_d)
        px_c, py_c = corrector.correct(px_d, py_d)
        corrector.drift_x = float(cx_t - px_c)
        corrector.drift_y = float(cy_t - py_c)
        print(f"Drift correction applied: ({round(corrector.drift_x,0)},{round(corrector.drift_y,0)})px")
    with state_lock: state['status'] = 'tracking'


# ---------------------------------------------------------------------------
# Socket server — UI connects here to send commands and get status
# ---------------------------------------------------------------------------
HOST = '127.0.0.1'
PORT = 7007

def handle_client(conn):
    buf = ''
    try:
        while True:
            data = conn.recv(1024).decode('utf-8', errors='ignore')
            if not data: break
            buf += data
            while '\n' in buf:
                line, buf = buf.split('\n', 1)
                line = line.strip()
                if not line: continue
                try:
                    msg = json.loads(line)
                    cmd = msg.get('cmd', '')
                    if cmd == 'calibrate':
                        threading.Thread(target=run_calibration, daemon=True).start()
                        conn.sendall((json.dumps({'ack': 'calibrating'}) + '\n').encode())
                    elif cmd == 'pause':
                        with state_lock: state['status'] = 'paused'
                        conn.sendall((json.dumps({'ack': 'paused'}) + '\n').encode())
                    elif cmd == 'resume':
                        with state_lock:
                            if state['calibrated']: state['status'] = 'tracking'
                        conn.sendall((json.dumps({'ack': 'resumed'}) + '\n').encode())
                    elif cmd == 'set_dwell':
                        global DWELL_TIME, DWELL_RADIUS, DWELL_COOLDOWN
                        DWELL_TIME = float(msg.get('value', 1.5))
                        print(f"Dwell time set to {DWELL_TIME}s")
                        conn.sendall((json.dumps({'ack': 'dwell_set', 'value': DWELL_TIME}) + '\n').encode())
                    elif cmd == 'status':
                        with state_lock: s = dict(state)
                        conn.sendall((json.dumps(s) + '\n').encode())
                except Exception as e:
                    conn.sendall((json.dumps({'error': str(e)}) + '\n').encode())
    except Exception:
        pass
    finally:
        conn.close()


def status_broadcast(clients_lock, clients):
    """Push status to all connected clients every 200ms."""
    while True:
        time.sleep(0.2)
        with state_lock: s = dict(state)
        msg = (json.dumps(s) + '\n').encode()
        with clients_lock:
            dead = []
            for c in clients:
                try: c.sendall(msg)
                except Exception: dead.append(c)
            for c in dead: clients.remove(c)


def run_server():
    clients = []; clients_lock = threading.Lock()
    threading.Thread(target=status_broadcast, args=(clients_lock, clients), daemon=True).start()
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((HOST, PORT))
    srv.listen(5)
    print(f"Tracker socket listening on {HOST}:{PORT}")
    while True:
        conn, _ = srv.accept()
        with clients_lock: clients.append(conn)
        threading.Thread(target=handle_client, args=(conn,), daemon=True).start()


if __name__ == '__main__':
    # Start tracking loop in background thread
    threading.Thread(target=tracking_loop, daemon=True).start()
    # Start socket server in background thread
    threading.Thread(target=run_server, daemon=True).start()
    # Run calibration on main thread (cv2.imshow needs it)
    print("Starting calibration...")
    run_calibration()
    print("Tracker running.")
    print("  R key = drift correction (or look at top-left corner for 2s)")
    print("  ESC   = stop")

    # Main thread: show debug window and handle keyboard
    cv2.namedWindow("Gaze Tracker", cv2.WINDOW_NORMAL)
    while True:
        ret, frame = cap.read()
        if not ret:
            time.sleep(0.01); continue
        key = cv2.waitKey(1) & 0xFF
        if key == 27:  # ESC
            break
        if key in (ord('r'), ord('R')):
            threading.Thread(target=_do_drift_correction, daemon=True).start()

        with state_lock:
            s = state.get('status', 'idle')
            gx_disp = state.get('x', 0)
            gy_disp = state.get('y', 0)
            dwell_pct = int(state.get('dwell', 0) * 100)

        tag = "3D" if detector._3d_available else "2D"
        lbl = f"[{tag}] {s} | ({gx_disp},{gy_disp}) | dwell:{dwell_pct}% | corner/R=drift ESC=quit"
        color = (0, 220, 80) if s == 'tracking' else (0, 80, 255)
        cv2.putText(frame, lbl, (10, 28), FONT, 0.5, color, 2)
        cv2.imshow("Gaze Tracker", frame)

    cap.release()
    cv2.destroyAllWindows()
