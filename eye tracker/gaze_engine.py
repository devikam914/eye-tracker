# -*- coding: utf-8 -*-
"""
gaze_engine.py — Self-contained gaze tracking engine.

Built directly on the working main.py backend. All calibration, tracking,
dwell click, corner drift correction, and save/load logic lives here.
Import this module and call GazeEngine(cap).calibrate() then .start_tracking().
"""
import cv2
import numpy as np
import ctypes
import ctypes.wintypes
import time
import threading
import os
import pickle
from scipy.interpolate import RBFInterpolator

# ---------------------------------------------------------------------------
# DPI awareness — set before pyautogui so size() returns physical pixels
# ---------------------------------------------------------------------------
try:
    import ctypes as _dpi_ctypes
    _dpi_ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        import ctypes as _dpi_ctypes
        _dpi_ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

import pyautogui
pyautogui.FAILSAFE = False

# ---------------------------------------------------------------------------
# Screen dimensions (physical pixels)
# ---------------------------------------------------------------------------
screen_w, screen_h = pyautogui.size()

# ---------------------------------------------------------------------------
# Calibration persistence
# ---------------------------------------------------------------------------
_HERE      = os.path.dirname(os.path.abspath(__file__))
CALIB_FILE = os.path.join(_HERE, 'calibration_data.pkl')

def save_calibration(normalizer, mapper):
    """Silently save calibration to disk. No prompt."""
    try:
        data = {
            'X_CENTER': normalizer.X_CENTER,
            'X_HALF':   normalizer.X_HALF,
            'Y_CENTER': normalizer.Y_CENTER,
            'Y_HALF':   normalizer.Y_HALF,
            'normed_aug':  mapper._normed_aug,
            'outputs_aug': mapper._outputs_aug,
            's':           mapper.s,
        }
        tmp = CALIB_FILE + '.tmp'
        with open(tmp, 'wb') as f:
            pickle.dump(data, f)
        os.replace(tmp, CALIB_FILE)
        print(f"Calibration saved to {CALIB_FILE}")
    except Exception as e:
        print(f"Warning: could not save calibration: {e}")

def load_calibration():
    """Load saved calibration. Returns (normalizer, mapper) or (None, None)."""
    if not os.path.exists(CALIB_FILE):
        return None, None
    try:
        with open(CALIB_FILE, 'rb') as f:
            data = pickle.load(f)
        norm = AxisNormalizer()
        norm.X_CENTER = data['X_CENTER']
        norm.X_HALF   = data['X_HALF']
        norm.Y_CENTER = data['Y_CENTER']
        norm.Y_HALF   = data['Y_HALF']
        mpr = RBFGazeMapper(smoothing=data['s'])
        mpr.fit(data['normed_aug'], data['outputs_aug'])
        print(f"Loaded saved calibration ({len(data['normed_aug'])} pts).")
        return norm, mpr
    except Exception as e:
        print(f"Warning: could not load calibration ({e}). Will run full calibration.")
        return None, None

# ---------------------------------------------------------------------------
# Signal constants
# ---------------------------------------------------------------------------
BLINK_THRESHOLD = 0.18
CALIB_EAR_MIN   = 0.12
FONT            = cv2.FONT_HERSHEY_SIMPLEX

DWELL_TIME     = 1.5   # seconds — updated at runtime by UI
DWELL_RADIUS   = 60    # pixels — larger radius tolerates gaze jitter better
DWELL_COOLDOWN = 1.2   # seconds

# Corner drift trigger: hold gaze at top-left for this long
CORNER_DWELL_TIME = 4.0   # seconds
CORNER_ZONE       = 80    # px from (0,0)

# ---------------------------------------------------------------------------
# Win32 cursor movement (mouse_event — works inside webview, pyautogui does not)
# ---------------------------------------------------------------------------
_me = ctypes.windll.user32.mouse_event
MOUSEEVENTF_MOVE        = 0x0001
MOUSEEVENTF_LEFTDOWN    = 0x0002
MOUSEEVENTF_LEFTUP      = 0x0004
MOUSEEVENTF_ABSOLUTE    = 0x8000
MOUSEEVENTF_VIRTUALDESK = 0x4000

def _move_cursor(x, y):
    nx = int(x * 65535 / max(screen_w - 1, 1))
    ny = int(y * 65535 / max(screen_h - 1, 1))
    _me(MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK,
        nx, ny, 0, 0)

def _click_cursor(x, y):
    nx = int(x * 65535 / max(screen_w - 1, 1))
    ny = int(y * 65535 / max(screen_h - 1, 1))
    _me(MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK,
        nx, ny, 0, 0)
    _me(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    _me(MOUSEEVENTF_LEFTUP,   0, 0, 0, 0)

# ---------------------------------------------------------------------------
# Win32 webview detection — used to skip snap when webview is foreground
# ---------------------------------------------------------------------------
_u32 = ctypes.windll.user32

def _foreground_is_webview():
    """Return True if the foreground window is a WebView2/Chrome window."""
    try:
        fg = _u32.GetForegroundWindow()
        if not fg:
            return False
        buf = ctypes.create_unicode_buffer(256)
        _u32.GetClassNameW(fg, buf, 256)
        if buf.value in ('Chrome_WidgetWin_1', 'Chrome_WidgetWin_0'):
            return True
        _u32.GetWindowTextW(fg, buf, 256)
        return 'Assistive Gaze' in buf.value
    except Exception:
        return False

# ---------------------------------------------------------------------------
# One Euro Filter + GazeFilter (exact params from working main.py)
# ---------------------------------------------------------------------------
class OneEuroFilter:
    def __init__(self, min_cutoff=1.0, beta=0.2, d_cutoff=1.0):
        self.min_cutoff = min_cutoff
        self.beta = beta
        self.d_cutoff = d_cutoff
        self.x_prev = None
        self.dx_prev = 0.0
        self.t_prev = None

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
        # beta=0.2 — from the known-good state when offset was minimal
        self.fx = OneEuroFilter(min_cutoff=1.0, beta=0.2)
        self.fy = OneEuroFilter(min_cutoff=1.0, beta=0.2)

    def reset(self):
        self.fx.x_prev = None
        self.fy.x_prev = None

    def update(self, mx, my):
        t = cv2.getTickCount() / cv2.getTickFrequency()
        return self.fx(mx, t), self.fy(my, t)


# ---------------------------------------------------------------------------
# Dwell Clicker
# ---------------------------------------------------------------------------
class DwellClicker:
    def __init__(self):
        self.anchor_x    = None
        self.anchor_y    = None
        self.dwell_start = None
        self.last_click  = 0.0
        self.progress    = 0.0

    def update(self, gx, gy):
        global DWELL_TIME
        now = time.monotonic()
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
            # Always fire the Win32 click.
            # - When webview is NOT foreground: click brings it to front + activates element.
            # - When webview IS foreground: click activates JS mouseenter/click on the element.
            #   JS dwell also fires independently for interactive elements, but the
            #   _dwellLocked cooldown in JS prevents double-activation.
            _click_cursor(int(self.anchor_x), int(self.anchor_y))
            print(f"Dwell click at ({int(self.anchor_x)}, {int(self.anchor_y)})")
            self.last_click = now
            self._reset(gx, gy)
            return True
        return False

    def _reset(self, gx, gy):
        self.anchor_x    = gx
        self.anchor_y    = gy
        self.dwell_start = time.monotonic()
        self.progress    = 0.0

# ---------------------------------------------------------------------------
# Calibration pipeline classes (exact from working main.py)
# ---------------------------------------------------------------------------
class AxisNormalizer:
    def __init__(self):
        self.X_CENTER = 0.5;  self.X_HALF = 0.15
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
            self.Y_HALF   = y_span / (2.0 * 0.75)
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
        self.rbf_x = self.rbf_y = None
        self.s = smoothing
        self._normed_aug  = None   # stored for save/load
        self._outputs_aug = None

    def fit(self, gaze_pts, screen_pts):
        self._normed_aug  = np.array(gaze_pts,   dtype=np.float64)
        self._outputs_aug = np.array(screen_pts, dtype=np.float64)
        self.rbf_x = RBFInterpolator(self._normed_aug, self._outputs_aug[:,0],
                                     kernel='thin_plate_spline', smoothing=self.s)
        self.rbf_y = RBFInterpolator(self._normed_aug, self._outputs_aug[:,1],
                                     kernel='thin_plate_spline', smoothing=self.s)

    def predict(self, gaze_pt):
        q = np.atleast_2d(gaze_pt).astype(np.float64)
        return float(self.rbf_x(q)[0]), float(self.rbf_y(q)[0])


class ResidualCorrectionField:
    def __init__(self):
        self.rbf_rx = None
        self.rbf_ry = None
        self.fitted  = False
        self.n_pts   = 0
        self.drift_x = 0.0
        self.drift_y = 0.0

    def fit(self, pred_pts, actual_pts):
        pred_arr   = np.array(pred_pts,   dtype=np.float64)
        actual_arr = np.array(actual_pts, dtype=np.float64)
        res_x = actual_arr[:,0] - pred_arr[:,0]
        res_y = actual_arr[:,1] - pred_arr[:,1]
        # smoothing=0.5 — from the known-good state when offset was minimal
        self.rbf_rx = RBFInterpolator(pred_arr, res_x,
                                      kernel='thin_plate_spline', smoothing=0.5)
        self.rbf_ry = RBFInterpolator(pred_arr, res_y,
                                      kernel='thin_plate_spline', smoothing=0.5)
        self.fitted = True
        self.n_pts  = len(pred_pts)

    def correct(self, pred_x, pred_y):
        if not self.fitted:
            return float(pred_x), float(pred_y)
        q  = np.array([[pred_x, pred_y]], dtype=np.float64)
        cx = float(pred_x) + float(self.rbf_rx(q)[0])
        cy = float(pred_y) + float(self.rbf_ry(q)[0])
        return cx, cy


def flip_x(raw_xy):
    arr = np.atleast_2d(raw_xy).astype(np.float64).copy()
    arr[:,0] = 1.0 - arr[:,0]
    return arr


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
        gA = gaze_pts[(nr-2)*nc+col].copy()
        gB = gaze_pts[(nr-1)*nc+col].copy()
        sA = screen_pts[(nr-2)*nc+col].copy()
        sB = screen_pts[(nr-1)*nc+col].copy()
        dy = sB[1] - sA[1]
        if abs(dy) > 1:
            t = (float(sh-1) - sB[1]) / dy
            g_ex.append(gB+t*(gB-gA)); s_ex.append([float(sB[0]), float(sh-1)])
    if g_ex:
        return (np.vstack([gaze_pts, np.array(g_ex)]),
                np.vstack([screen_pts, np.array(s_ex, dtype=np.float64)]))
    return gaze_pts, screen_pts

# ---------------------------------------------------------------------------
# GazeEngine — the main class
# ---------------------------------------------------------------------------
class GazeEngine:
    """
    Wraps the working main.py backend into a class.
    Usage:
        engine = GazeEngine(cap, detector)
        engine.run_full_calibration()   # or run_quick_calibration()
        engine.start_tracking()
    """
    GRID_N      = 7
    _cx         = [0.02, 0.17, 0.33, 0.50, 0.67, 0.83, 0.98]
    _cy         = [0.02, 0.17, 0.33, 0.50, 0.67, 0.83, 0.98]
    VALIDATION_PX = 120

    def __init__(self, cap, detector):
        self.cap      = cap
        self.detector = detector

        self.normalizer = AxisNormalizer()
        self.mapper     = RBFGazeMapper(smoothing=0.03)
        self.corrector  = ResidualCorrectionField()
        self.gaze_filter = GazeFilter()
        self.clicker    = DwellClicker()

        self.calibrated = False
        self._running   = False
        self._paused    = False
        self._lock      = threading.Lock()

        self._last_x = screen_w // 2
        self._last_y = screen_h // 2

        self.calibration_points = [(x, y) for y in self._cy for x in self._cx]

        # Corner drift state
        self._corner_start    = None
        self._corner_progress = 0.0
        self._drift_running   = False

        # Bottom-left corner eye break state
        self._break_start   = None
        self._break_running = False
        self._webview_win   = None  # set by app.py after window is created

    # ------------------------------------------------------------------ props
    @property
    def paused(self):
        return self._paused

    @paused.setter
    def paused(self, v):
        self._paused = v

    @property
    def dwell_progress(self):
        return self.clicker.progress

    @property
    def corner_progress(self):
        return self._corner_progress

    # ------------------------------------------------------------------ sample
    def _collect_samples(self, n, label, tx, ty, settle=1.5):
        """Exact copy of collect_samples() from working main.py."""
        t0 = cv2.getTickCount()
        while (cv2.getTickCount() - t0) / cv2.getTickFrequency() < settle:
            display = np.zeros((screen_h, screen_w, 3), dtype=np.uint8)
            cv2.circle(display, (tx, ty), 20, (80, 180, 255), 2)
            cv2.circle(display, (tx, ty), 7,  (80, 180, 255), -1)
            cv2.circle(display, (tx, ty), 2,  (255, 255, 255), -1)
            if label:
                cv2.putText(display, label,
                            (tx - len(label)*4, ty+45), FONT, 0.5, (150, 150, 150), 1)
            cv2.imshow("Calibration", display)
            if cv2.waitKey(1) & 0xFF == 27:
                return None
        samples = []
        while len(samples) < n:
            ret, frame = self.cap.read()
            if not ret: continue
            gx, gy, ear = self.detector.process(frame)
            if gx is not None and ear > CALIB_EAR_MIN:
                samples.append([gx, gy])
            display = np.zeros((screen_h, screen_w, 3), dtype=np.uint8)
            cv2.circle(display, (tx, ty), 8, (0, 220, 80), -1)
            cv2.circle(display, (tx, ty), 2, (255, 255, 255), -1)
            prog = int(360 * len(samples) / n)
            cv2.ellipse(display, (tx, ty), (24, 24), -90, 0, prog, (0, 255, 120), 3)
            cv2.imshow("Calibration", display)
            if cv2.waitKey(1) & 0xFF == 27:
                return None
        s = np.array(samples, dtype=np.float64)
        for _ in range(2):
            for axis in [0, 1]:
                q1, q3 = np.percentile(s[:, axis], [25, 75])
                iqr = q3 - q1
                s = s[(s[:, axis] >= q1-1.2*iqr) & (s[:, axis] <= q3+1.2*iqr)]
            if len(s) < 10:
                s = np.array(samples, dtype=np.float64); break
        return s.tolist()

    # ------------------------------------------------------------------ residual
    def _run_residual_correction(self, norm, mpr):
        """
        16-point (4×4) residual correction — the known-good configuration.
        Grid at [0.1, 0.37, 0.63, 0.9] gave minimal offset in testing.
        """
        corr_fracs_x = [0.1, 0.37, 0.63, 0.9]
        corr_fracs_y = [0.1, 0.37, 0.63, 0.9]
        grid = [(x, y) for y in corr_fracs_y for x in corr_fracs_x]
        N = len(grid)
        print(f"Residual correction: {N} points. Head still.")
        cv2.namedWindow("Calibration", cv2.WND_PROP_FULLSCREEN)
        cv2.setWindowProperty("Calibration", cv2.WND_PROP_FULLSCREEN,
                              cv2.WINDOW_FULLSCREEN)
        pred_pts = []; actual_pts = []
        for ci, (fx, fy) in enumerate(grid):
            tx = int(fx * screen_w); ty = int(fy * screen_h)
            raw = self._collect_samples(30, f"Correction {ci+1}/{N}", tx, ty, settle=1.0)
            if raw is None:
                cv2.destroyAllWindows(); return None
            if len(raw) >= 10:
                avg  = np.mean(np.array(raw), axis=0)
                proc = norm.transform(flip_x(np.array([avg])))[0]
                px_p, py_p = mpr.predict(proc)
                pred_pts.append([px_p, py_p])
                actual_pts.append([float(tx), float(ty)])
                print(f"  [{ci+1}/{N}] actual=({tx},{ty})"
                      f" pred=({round(px_p,0)},{round(py_p,0)})"
                      f" residual=({round(px_p-tx,0)},{round(py_p-ty,0)})")
            else:
                print(f"  [{ci+1}/{N}] SKIPPED - no face")
        cv2.destroyAllWindows()

        corr = ResidualCorrectionField()
        if len(pred_pts) >= 4:
            corr.fit(pred_pts, actual_pts)
            total_b = total_a = 0.0
            for i in range(len(pred_pts)):
                px_p, py_p = pred_pts[i]; ax, ay = actual_pts[i]
                cx2, cy2 = corr.correct(px_p, py_p)
                total_b += np.sqrt((px_p-ax)**2 + (py_p-ay)**2)
                total_a += np.sqrt((cx2-ax)**2  + (cy2-ay)**2)
            n = len(pred_pts)
            print(f"Residual correction fitted on {n} points.")
            print(f"Mean error before: {round(total_b/n,1)}px  after: {round(total_a/n,1)}px")
        else:
            print("Not enough correction points — running without correction.")

        # --- Centre drift point -------------------------------------------
        # One final dot at screen centre to zero out any remaining global offset.
        print("Centre drift point — look at the dot.")
        cx_t = screen_w // 2; cy_t = screen_h // 2
        cv2.namedWindow("Calibration", cv2.WND_PROP_FULLSCREEN)
        cv2.setWindowProperty("Calibration", cv2.WND_PROP_FULLSCREEN,
                              cv2.WINDOW_FULLSCREEN)
        raw_c = self._collect_samples(30, "Centre drift", cx_t, cy_t, settle=1.5)
        cv2.destroyAllWindows()
        if raw_c and len(raw_c) >= 8:
            avg_c  = np.mean(np.array(raw_c), axis=0)
            proc_c = norm.transform(flip_x(np.array([avg_c])))[0]
            px_c, py_c = mpr.predict(proc_c)
            if corr.fitted:
                px_c, py_c = corr.correct(px_c, py_c)
            corr.drift_x = float(cx_t - px_c)
            corr.drift_y = float(cy_t - py_c)
            print(f"Centre drift applied: "
                  f"({round(corr.drift_x,0)}, {round(corr.drift_y,0)})px")
        return corr

    # ------------------------------------------------------------------ full calib
    def run_full_calibration(self):
        """
        Full 49-point calibration + residual correction.
        Saves calibration to disk on success.
        Must be called from the main thread (cv2.imshow requirement).
        Returns True on success, False if aborted.
        """
        N_PTS = len(self.calibration_points)
        print(f"Starting {N_PTS}-point calibration.")
        cv2.namedWindow("Calibration", cv2.WND_PROP_FULLSCREEN)
        cv2.setWindowProperty("Calibration", cv2.WND_PROP_FULLSCREEN,
                              cv2.WINDOW_FULLSCREEN)
        inputs_raw = []; outputs_px = []
        print("--- PASS 1: Collection ---")
        for pt_idx, (px, py) in enumerate(self.calibration_points):
            tx, ty = int(px * screen_w), int(py * screen_h)
            raw = self._collect_samples(30, f"{pt_idx+1}/{N_PTS}", tx, ty)
            if raw is None:
                cv2.destroyAllWindows(); return False
            avg = np.mean(np.array(raw), axis=0)
            inputs_raw.append(avg); outputs_px.append([tx, ty])
        cv2.destroyAllWindows()
        inputs_raw = np.array(inputs_raw); outputs_px = np.array(outputs_px)

        flipped = flip_x(inputs_raw)
        norm = AxisNormalizer(); norm.fit(flipped, grid_n=self.GRID_N)
        normed = norm.transform(flipped)

        print("\n--- PASS 2: Validation ---")
        tmp_rx = RBFInterpolator(normed, outputs_px[:,0].astype(float),
                                 kernel='thin_plate_spline', smoothing=0.1)
        tmp_ry = RBFInterpolator(normed, outputs_px[:,1].astype(float),
                                 kernel='thin_plate_spline', smoothing=0.1)
        bad_pts = []
        for i in range(N_PTS):
            q = normed[i:i+1]
            err = float(np.sqrt((float(tmp_rx(q)[0])-outputs_px[i,0])**2 +
                                (float(tmp_ry(q)[0])-outputs_px[i,1])**2))
            if err >= self.VALIDATION_PX: bad_pts.append(i)

        if bad_pts:
            print(f"Recollecting {len(bad_pts)} bad points.")
            cv2.namedWindow("Calibration", cv2.WND_PROP_FULLSCREEN)
            cv2.setWindowProperty("Calibration", cv2.WND_PROP_FULLSCREEN,
                                  cv2.WINDOW_FULLSCREEN)
            for i in bad_pts:
                px, py = self.calibration_points[i]
                tx, ty = int(px * screen_w), int(py * screen_h)
                raw = self._collect_samples(30, f"Recollect {i+1}", tx, ty)
                if raw: inputs_raw[i] = np.mean(np.array(raw), axis=0)
            cv2.destroyAllWindows()
            flipped = flip_x(inputs_raw)
            norm = AxisNormalizer(); norm.fit(flipped, grid_n=self.GRID_N)
            normed = norm.transform(flipped)
        else:
            print("All points passed.")

        normed_aug, outputs_aug = add_edge_anchors(
            normed, outputs_px.astype(np.float64),
            screen_w, screen_h, nr=self.GRID_N, nc=self.GRID_N)
        mpr = RBFGazeMapper(smoothing=0.03)
        mpr.fit(normed_aug, outputs_aug)

        corr = self._run_residual_correction(norm, mpr)
        if corr is None: return False

        # Commit atomically
        self.normalizer  = norm
        self.mapper      = mpr
        self.corrector   = corr
        self.gaze_filter = GazeFilter()
        self.clicker     = DwellClicker()
        self.calibrated  = True

        # Silent auto-save
        save_calibration(norm, mpr)
        print("\nCalibration complete — tracking active.")
        return True

    # ------------------------------------------------------------------ quick calib
    def run_quick_calibration(self):
        """
        Load saved calibration + run residual correction only (~1 min).
        Falls back to full calibration if no saved data exists.
        Must be called from the main thread.
        """
        norm, mpr = load_calibration()
        if norm is None or mpr is None:
            print("No saved calibration — running full calibration.")
            return self.run_full_calibration()

        corr = self._run_residual_correction(norm, mpr)
        if corr is None: return False

        self.normalizer  = norm
        self.mapper      = mpr
        self.corrector   = corr
        self.gaze_filter = GazeFilter()
        self.clicker     = DwellClicker()
        self.calibrated  = True
        print("\nQuick calibration complete — tracking active.")
        return True

    # ------------------------------------------------------------------ drift
    def _do_drift_correction(self):
        """Single-point drift correction at screen centre. Runs in a thread."""
        self._paused = True
        self.gaze_filter.reset()
        cx_t = screen_w // 2; cy_t = screen_h // 2
        cv2.namedWindow("Calibration", cv2.WND_PROP_FULLSCREEN)
        cv2.setWindowProperty("Calibration", cv2.WND_PROP_FULLSCREEN,
                              cv2.WINDOW_FULLSCREEN)
        raw = self._collect_samples(30, "Look at centre — drift fix",
                                    cx_t, cy_t, settle=1.5)
        cv2.destroyAllWindows()
        if raw and len(raw) >= 8:
            avg_d  = np.mean(np.array(raw), axis=0)
            proc_d = self.normalizer.transform(flip_x(np.array([avg_d])))[0]
            # Apply full pipeline (mapper + corrector) to get the same prediction
            # the tracking loop would produce — drift = actual - predicted
            px_d, py_d = self.mapper.predict(proc_d)
            px_d, py_d = self.corrector.correct(px_d, py_d)
            self.corrector.drift_x = float(cx_t - px_d)
            self.corrector.drift_y = float(cy_t - py_d)
            print(f"Drift correction applied: "
                  f"({round(self.corrector.drift_x,0)},{round(self.corrector.drift_y,0)})px")
        self.gaze_filter.reset()
        self.clicker._reset(self._last_x, self._last_y)
        self._drift_running = False
        self._paused = False

    # ------------------------------------------------------------------ eye break
    def _do_eye_break(self):
        """10-minute eye break with fullscreen countdown overlay in the webview."""
        BREAK_SECONDS = 10 * 60  # 10 minutes
        self._paused = True
        print("Eye break started — 10 minutes.")

        # Show break overlay in webview via evaluate_js
        def _show_overlay(seconds_left):
            if not self._webview_win:
                return
            mins = seconds_left // 60
            secs = seconds_left % 60
            countdown = f"{mins}:{secs:02d}"
            js = f"""
(function() {{
    var el = document.getElementById('__eye_break_overlay__');
    if (!el) {{
        el = document.createElement('div');
        el.id = '__eye_break_overlay__';
        el.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;'
            + 'background:rgba(10,15,25,0.97);z-index:999999;display:flex;'
            + 'flex-direction:column;align-items:center;justify-content:center;'
            + 'color:white;font-family:sans-serif;';
        el.innerHTML = '<div style="font-size:48px;margin-bottom:20px;">👁️ Eye Break</div>'
            + '<div style="font-size:28px;margin-bottom:30px;color:#aaa;">Rest your eyes — look away from the screen</div>'
            + '<div id="__break_timer__" style="font-size:96px;font-weight:bold;color:#4facfe;">{countdown}</div>'
            + '<div style="font-size:20px;margin-top:30px;color:#666;">Look at top-right corner to skip</div>';
        document.body.appendChild(el);
    }} else {{
        document.getElementById('__break_timer__').textContent = '{countdown}';
    }}
}})();
"""
            try:
                self._webview_win.evaluate_js(js)
            except Exception:
                pass

        def _hide_overlay():
            if not self._webview_win:
                return
            js = """
(function() {
    var el = document.getElementById('__eye_break_overlay__');
    if (el) el.remove();
})();
"""
            try:
                self._webview_win.evaluate_js(js)
            except Exception:
                pass

        # Show initial overlay
        _show_overlay(BREAK_SECONDS)

        # Count down, updating every second
        for remaining in range(BREAK_SECONDS, 0, -1):
            time.sleep(1.0)
            _show_overlay(remaining - 1)
            # Allow early exit if top-right corner is held (break_running set to False)
            if not self._break_running:
                break

        _hide_overlay()
        self.gaze_filter.reset()
        self.clicker._reset(self._last_x, self._last_y)
        self._break_running = False
        self._paused = False
        print("Eye break ended — tracking resumed.")

    # ------------------------------------------------------------------ tracking
    def start_tracking(self):
        """Start the tracking loop in a daemon thread."""
        if not self.calibrated:
            print("ERROR: calibrate first"); return False
        self._running = True
        self._paused  = False
        threading.Thread(target=self._track_loop, daemon=True).start()
        return True

    def stop_tracking(self):
        self._running = False

    def _track_loop(self):
        blink_cooldown = 0
        MOVE_THRESHOLD = 3  # px — keep low so screen edges are reachable

        while self._running:
            if self._paused or not self.calibrated:
                time.sleep(0.05); continue

            ret, frame = self.cap.read()
            if not ret: continue

            gx, gy, ear = self.detector.process(frame)
            if gx is None: continue

            proc = self.normalizer.transform(flip_x(np.array([[gx, gy]])))[0]
            pred_x, pred_y = self.mapper.predict(proc)
            pred_x, pred_y = self.corrector.correct(pred_x, pred_y)
            pred_x += self.corrector.drift_x
            pred_y += self.corrector.drift_y

            if ear < BLINK_THRESHOLD:
                blink_cooldown = 20
                self.gaze_filter.reset()
                self.clicker._reset(pred_x, pred_y)
                self._corner_start = None
                self._corner_progress = 0.0
            elif blink_cooldown > 0:
                blink_cooldown -= 1
                pyautogui.moveTo(self._last_x, self._last_y)
            else:
                pred_x = float(np.clip(pred_x, 0, screen_w - 1))
                pred_y = float(np.clip(pred_y, 0, screen_h - 1))
                sx, sy = self.gaze_filter.update(pred_x, pred_y)
                new_x = int(np.clip(sx, 0, screen_w - 1))
                new_y = int(np.clip(sy, 0, screen_h - 1))

                if (abs(new_x - self._last_x) > MOVE_THRESHOLD or
                        abs(new_y - self._last_y) > MOVE_THRESHOLD):
                    self._last_x = new_x
                    self._last_y = new_y
                    pyautogui.moveTo(self._last_x, self._last_y)

                self.clicker.update(self._last_x, self._last_y)

                # Top-left corner: drift correction (hold 4s)
                if self._last_x <= CORNER_ZONE and self._last_y <= CORNER_ZONE:
                    if self._corner_start is None:
                        self._corner_start = time.monotonic()
                    elapsed = time.monotonic() - self._corner_start
                    self._corner_progress = min(elapsed / CORNER_DWELL_TIME, 1.0)
                    if elapsed >= CORNER_DWELL_TIME and not self._drift_running:
                        self._drift_running = True
                        self._corner_start  = None
                        self._corner_progress = 0.0
                        print("Corner drift correction triggered...")
                        threading.Thread(target=self._do_drift_correction,
                                         daemon=True).start()
                else:
                    self._corner_start    = None
                    self._corner_progress = 0.0

                # Top-right corner: eye break trigger (hold 4s → 10-min break)
                if self._last_x >= screen_w - CORNER_ZONE and self._last_y <= CORNER_ZONE:
                    if self._break_start is None:
                        self._break_start = time.monotonic()
                    elapsed = time.monotonic() - self._break_start
                    if elapsed >= CORNER_DWELL_TIME and not self._break_running:
                        self._break_running = True
                        self._break_start   = None
                        print("Eye break triggered — pausing for 10 minutes...")
                        threading.Thread(target=self._do_eye_break,
                                         daemon=True).start()
                else:
                    self._break_start = None
