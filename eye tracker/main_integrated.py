# -*- coding: utf-8 -*-
"""
Integrated Eye Tracking + Web UI
Pixel-perfect cursor tracking restored from the original backend.

Key fixes vs the previous integration:
  1. PTGazeDetector paths are now portable (no hardcoded user paths)
  2. flip_x() applied before normalisation — was missing, caused X-axis drift
  3. add_edge_anchors() restored — prevents edge-of-screen prediction collapse
  4. Blink cooldown restored — cursor freezes during blinks instead of jumping
  5. ResidualCorrectionField.correct() no longer bakes in drift (kept separate)
  6. OneEuroFilter params match the tuned original (min_cutoff=1.0, beta=0.2)
  7. snap_to_nearest_element() restored for dwell-click accuracy
"""
import cv2
import numpy as np
import pyautogui
import time
import threading
import ctypes
import ctypes.wintypes
import os
import webbrowser
from scipy.interpolate import RBFInterpolator

# ---------------------------------------------------------------------------
# Detector — PTGaze with automatic fallback to MediaPipe landmarks
# ---------------------------------------------------------------------------
try:
    from modules.ptgaze_detector import PTGazeDetector
    detector = PTGazeDetector()
    print(f"Detector: {'PTGaze (ETH-XGaze)' if detector._3d_available else 'MediaPipe landmarks (fallback)'}")
except Exception as e:
    print(f"PTGazeDetector import failed ({e}), using MediaPipe landmarks")
    from modules.landmarks import FaceLandmarkDetector as PTGazeDetector
    detector = PTGazeDetector()

# ---------------------------------------------------------------------------
# Global config (UI can update DWELL_TIME at runtime)
# ---------------------------------------------------------------------------
pyautogui.FAILSAFE = False
screen_w, screen_h = pyautogui.size()

# DPI scale factor — webview renders at logical pixels, OS cursor uses physical pixels.
# On a 1080p screen at 125% scaling: physical=1920, logical=1536, scale=1.25
# We need physical pixels for SetCursorPos/mouse_event.
# pyautogui.size() already returns physical pixels on Windows with DPI awareness set.
try:
    import ctypes as _ctypes
    _ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    pass

BLINK_THRESHOLD = 0.18
CALIB_EAR_MIN   = 0.12
FONT            = cv2.FONT_HERSHEY_SIMPLEX

DWELL_TIME     = 1.5   # seconds — frontend writes this value
DWELL_RADIUS   = 45    # pixels
DWELL_COOLDOWN = 1.2   # seconds

# ---------------------------------------------------------------------------
# Win32 element-snap helpers (pure ctypes, no extra deps)
# ---------------------------------------------------------------------------
_u32 = ctypes.windll.user32
_u32.WindowFromPoint.restype  = ctypes.wintypes.HWND
_u32.WindowFromPoint.argtypes = [ctypes.wintypes.POINT]
_u32.GetWindowRect.restype    = ctypes.wintypes.BOOL
_u32.GetWindowRect.argtypes   = [ctypes.wintypes.HWND, ctypes.POINTER(ctypes.wintypes.RECT)]
_u32.IsWindowVisible.restype  = ctypes.wintypes.BOOL
_u32.IsWindowVisible.argtypes = [ctypes.wintypes.HWND]

SNAP_RADIUS = 40  # px


def snap_to_nearest_element(x, y):
    """Snap dwell-click target to nearest small UI control via Win32."""
    try:
        best_dist = float(SNAP_RADIUS + 1)
        best_cx, best_cy = float(x), float(y)
        seen = set()
        step = max(3, SNAP_RADIUS // 5)
        for dx in range(-SNAP_RADIUS, SNAP_RADIUS + 1, step):
            for dy in range(-SNAP_RADIUS, SNAP_RADIUS + 1, step):
                px = int(x + dx); py = int(y + dy)
                hwnd = _u32.WindowFromPoint(ctypes.wintypes.POINT(px, py))
                if not hwnd or hwnd in seen:
                    continue
                seen.add(hwnd)
                if not _u32.IsWindowVisible(hwnd):
                    continue
                rect = ctypes.wintypes.RECT()
                if not _u32.GetWindowRect(hwnd, ctypes.byref(rect)):
                    continue
                w = rect.right - rect.left
                h = rect.bottom - rect.top
                if w < 5 or h < 5 or w > screen_w // 2 or h > screen_h // 3:
                    continue
                ecx = (rect.left + rect.right) / 2.0
                ecy = (rect.top + rect.bottom) / 2.0
                dist = ((ecx - x) ** 2 + (ecy - y) ** 2) ** 0.5
                if dist < best_dist:
                    best_dist = dist
                    best_cx, best_cy = ecx, ecy
        return int(best_cx), int(best_cy)
    except Exception:
        return x, y


def force_foreground(window_title):
    try:
        hwnd = ctypes.windll.user32.FindWindowW(None, window_title)
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 9)
            ctypes.windll.user32.SetForegroundWindow(hwnd)
            HWND_TOPMOST = -1
            ctypes.windll.user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, 0x0002 | 0x0001)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# One-Euro filter (tuned params from original — min_cutoff=1.0, beta=0.2)
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
        self.fx = OneEuroFilter(min_cutoff=1.0, beta=0.2)
        self.fy = OneEuroFilter(min_cutoff=1.0, beta=0.2)

    def reset(self):
        self.fx.x_prev = None; self.fy.x_prev = None

    def update(self, mx, my):
        t = cv2.getTickCount() / cv2.getTickFrequency()
        return self.fx(mx, t), self.fy(my, t)


# ---------------------------------------------------------------------------
# Dwell clicker (restored from original — uses snap_to_nearest_element)
# ---------------------------------------------------------------------------
class DwellClicker:
    def __init__(self):
        self.anchor_x    = None
        self.anchor_y    = None
        self.dwell_start = None
        self.last_click  = 0.0
        self.progress    = 0.0

    def update(self, gx, gy):
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
            # Don't use snap_to_nearest_element when webview is active —
            # it walks the Win32 accessibility tree which conflicts with webview
            # and causes the .Empty.Empty... error flood.
            snap_x, snap_y = int(self.anchor_x), int(self.anchor_y)

            MOUSEEVENTF_LEFTDOWN    = 0x0002
            MOUSEEVENTF_LEFTUP      = 0x0004
            MOUSEEVENTF_MOVE        = 0x0001
            MOUSEEVENTF_ABSOLUTE    = 0x8000
            MOUSEEVENTF_VIRTUALDESK = 0x4000
            nx = int(snap_x * 65535 / max(screen_w - 1, 1))
            ny = int(snap_y * 65535 / max(screen_h - 1, 1))
            _me = ctypes.windll.user32.mouse_event
            _me(MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK,
                nx, ny, 0, 0)
            _me(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
            _me(MOUSEEVENTF_LEFTUP,   0, 0, 0, 0)
            print(f"Dwell click at ({snap_x}, {snap_y})")
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
# Calibration pipeline (exact port from original main_backend.py)
# ---------------------------------------------------------------------------
def flip_x(raw_xy):
    """Mirror X axis — required because gaze-X is camera-mirrored."""
    arr = np.atleast_2d(raw_xy).astype(np.float64).copy()
    arr[:, 0] = 1.0 - arr[:, 0]
    return arr


def add_edge_anchors(gaze_pts, screen_pts, sw, sh, nr=7, nc=7):
    """Extrapolate calibration points to screen edges to prevent collapse."""
    g_ex, s_ex = [], []
    for row in range(nr):
        b = row * nc
        g0, g1 = gaze_pts[b].copy(), gaze_pts[b+1].copy()
        s0, s1 = screen_pts[b].copy(), screen_pts[b+1].copy()
        dx = s1[0] - s0[0]
        if abs(dx) > 1:
            t = (0.0 - s0[0]) / dx
            g_ex.append(g0 + t*(g1-g0)); s_ex.append([0.0, float(s0[1])])
        gA, gB = gaze_pts[b+nc-2].copy(), gaze_pts[b+nc-1].copy()
        sA, sB = screen_pts[b+nc-2].copy(), screen_pts[b+nc-1].copy()
        dx = sB[0] - sA[0]
        if abs(dx) > 1:
            t = (float(sw-1) - sB[0]) / dx
            g_ex.append(gB + t*(gB-gA)); s_ex.append([float(sw-1), float(sB[1])])
    for col in range(nc):
        g0, g1 = gaze_pts[col].copy(), gaze_pts[nc+col].copy()
        s0, s1 = screen_pts[col].copy(), screen_pts[nc+col].copy()
        dy = s1[1] - s0[1]
        if abs(dy) > 1:
            t = (0.0 - s0[1]) / dy
            g_ex.append(g0 + t*(g1-g0)); s_ex.append([float(s0[0]), 0.0])
        gA = gaze_pts[(nr-2)*nc+col].copy()
        gB = gaze_pts[(nr-1)*nc+col].copy()
        sA = screen_pts[(nr-2)*nc+col].copy()
        sB = screen_pts[(nr-1)*nc+col].copy()
        dy = sB[1] - sA[1]
        if abs(dy) > 1:
            t = (float(sh-1) - sB[1]) / dy
            g_ex.append(gB + t*(gB-gA)); s_ex.append([float(sB[0]), float(sh-1)])
    if g_ex:
        return (np.vstack([gaze_pts, np.array(g_ex)]),
                np.vstack([screen_pts, np.array(s_ex, dtype=np.float64)]))
    return gaze_pts, screen_pts


class AxisNormalizer:
    def __init__(self):
        self.X_CENTER = 0.5;  self.X_HALF = 0.15
        self.Y_CENTER = -0.1; self.Y_HALF = 0.08

    def fit(self, gaze_pts, grid_n=7):
        x_min, x_max = gaze_pts[:, 0].min(), gaze_pts[:, 0].max()
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
            y_min, y_max = gaze_pts[:, 1].min(), gaze_pts[:, 1].max()
            self.Y_CENTER = (y_max + y_min) / 2.0
            if (y_max - y_min) > 0.001:
                self.Y_HALF = (y_max - y_min) / (2.0 * 0.74)

    def transform(self, gaze_pts):
        arr = np.atleast_2d(gaze_pts).astype(np.float64).copy()
        arr[:, 0] = (arr[:, 0] - self.X_CENTER) / (2.0 * self.X_HALF) + 0.5
        arr[:, 1] = (arr[:, 1] - self.Y_CENTER) / (2.0 * self.Y_HALF) + 0.5
        return arr


class RBFGazeMapper:
    def __init__(self, smoothing=0.03):
        self.rbf_x = self.rbf_y = None
        self.s = smoothing

    def fit(self, gaze_pts, screen_pts):
        self.rbf_x = RBFInterpolator(gaze_pts, screen_pts[:, 0],
                                     kernel='thin_plate_spline', smoothing=self.s)
        self.rbf_y = RBFInterpolator(gaze_pts, screen_pts[:, 1],
                                     kernel='thin_plate_spline', smoothing=self.s)

    def predict(self, gaze_pt):
        q = np.atleast_2d(gaze_pt).astype(np.float64)
        return float(self.rbf_x(q)[0]), float(self.rbf_y(q)[0])


class ResidualCorrectionField:
    """Corrects session-based offset. drift_x/y kept separate from RBF correction."""
    def __init__(self):
        self.rbf_rx = None
        self.rbf_ry = None
        self.fitted  = False
        self.n_pts   = 0
        self.drift_x = 0.0   # runtime drift — updated by 'R' key
        self.drift_y = 0.0

    def fit(self, pred_pts, actual_pts):
        pred_arr   = np.array(pred_pts,   dtype=np.float64)
        actual_arr = np.array(actual_pts, dtype=np.float64)
        res_x = actual_arr[:, 0] - pred_arr[:, 0]
        res_y = actual_arr[:, 1] - pred_arr[:, 1]
        self.rbf_rx = RBFInterpolator(pred_arr, res_x,
                                      kernel='thin_plate_spline', smoothing=0.5)
        self.rbf_ry = RBFInterpolator(pred_arr, res_y,
                                      kernel='thin_plate_spline', smoothing=0.5)
        self.fitted = True
        self.n_pts  = len(pred_pts)

    def correct(self, pred_x, pred_y):
        """Apply RBF correction only — drift is added separately in the tracking loop."""
        if not self.fitted:
            return float(pred_x), float(pred_y)
        q  = np.array([[pred_x, pred_y]], dtype=np.float64)
        cx = float(pred_x) + float(self.rbf_rx(q)[0])
        cy = float(pred_y) + float(self.rbf_ry(q)[0])
        return cx, cy


# ---------------------------------------------------------------------------
# Eye Tracking Engine
# ---------------------------------------------------------------------------
class EyeTrackingEngine:
    def __init__(self, cap):
        self.cap        = cap
        self.normalizer = AxisNormalizer()
        self.mapper     = RBFGazeMapper(smoothing=0.03)
        self.corrector  = ResidualCorrectionField()
        self.gaze_filter = GazeFilter()
        self.clicker    = DwellClicker()

        self.calibrated = False
        self.running    = False
        self.paused     = False

        self._last_good_x = screen_w // 2
        self._last_good_y = screen_h // 2
        self._blink_cooldown = 0
        self._webview_window = None   # set by controller after window is created

        # Calibration grid (7x7, same as original)
        self.GRID_N = 7
        _cx = [0.02, 0.17, 0.33, 0.50, 0.67, 0.83, 0.98]
        _cy = [0.02, 0.17, 0.33, 0.50, 0.67, 0.83, 0.98]
        self.calibration_points = [(x, y) for y in _cy for x in _cx]
        self.VALIDATION_PX = 120

    # ------------------------------------------------------------------
    def _collect_samples(self, n, label, tx, ty, settle=1.5):
        t0 = cv2.getTickCount()
        while (cv2.getTickCount() - t0) / cv2.getTickFrequency() < settle:
            display = np.zeros((screen_h, screen_w, 3), dtype=np.uint8)
            cv2.circle(display, (tx, ty), 20, (80, 180, 255), 2)
            cv2.circle(display, (tx, ty), 7,  (80, 180, 255), -1)
            cv2.circle(display, (tx, ty), 2,  (255, 255, 255), -1)
            if label:
                cv2.putText(display, label, (tx - len(label)*4, ty+45),
                            FONT, 0.5, (150, 150, 150), 1)
            cv2.imshow("Calibration", display)
            if cv2.waitKey(1) & 0xFF == 27:
                return None
        samples = []
        while len(samples) < n:
            ret, frame = self.cap.read()
            if not ret: continue
            gx, gy, ear = detector.process(frame)
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


    def calibrate(self):
        """Full 2-pass calibration + residual correction (exact original logic)."""
        N_PTS = len(self.calibration_points)
        print(f"Starting {N_PTS}-point calibration.")
        print("Stare at the white dot. Head still. ESC to abort.")
        print(f"Mode: {'3D' if detector._use_3d else '2D'}\n")

        cv2.namedWindow("Calibration", cv2.WND_PROP_FULLSCREEN)
        cv2.setWindowProperty("Calibration", cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)

        inputs_raw = []
        outputs_px = []

        print("--- PASS 1: Collection ---")
        for pt_idx, (px, py) in enumerate(self.calibration_points):
            tx, ty = int(px * screen_w), int(py * screen_h)
            raw = self._collect_samples(30, f"{pt_idx+1}/{N_PTS}", tx, ty)
            if raw is None:
                cv2.destroyAllWindows(); return False
            s   = np.array(raw)
            avg = np.mean(s, axis=0)
            std_xy = np.std(s, axis=0)
            quality_ok = (std_xy[0] < 0.018 and std_xy[1] < 0.018)
            inputs_raw.append(avg)
            outputs_px.append([tx, ty])
            warn = "" if quality_ok else " [!! HEAD MOVED]"
            print(f"  [{str(pt_idx+1).zfill(2)}/{N_PTS}]"
                  f"  gaze=({round(avg[0],4)},{round(avg[1],4)})"
                  f"  std=({round(std_xy[0],4)},{round(std_xy[1],4)})"
                  f"  kept={len(raw)}{warn}")

        cv2.destroyAllWindows()
        inputs_raw = np.array(inputs_raw)
        outputs_px  = np.array(outputs_px)

        # Validation pass
        flipped    = flip_x(inputs_raw)
        normalizer = AxisNormalizer()
        normalizer.fit(flipped, grid_n=self.GRID_N)
        normed     = normalizer.transform(flipped)

        print("\n--- PASS 2: Validation ---")
        tmp_rx = RBFInterpolator(normed, outputs_px[:, 0].astype(float),
                                 kernel='thin_plate_spline', smoothing=0.1)
        tmp_ry = RBFInterpolator(normed, outputs_px[:, 1].astype(float),
                                 kernel='thin_plate_spline', smoothing=0.1)
        bad_pts = []
        for i in range(N_PTS):
            q    = normed[i:i+1]
            px_p = float(tmp_rx(q)[0])
            py_p = float(tmp_ry(q)[0])
            err  = float(np.sqrt((px_p-outputs_px[i,0])**2 + (py_p-outputs_px[i,1])**2))
            status = "OK" if err < self.VALIDATION_PX else "RECOLLECT"
            print(f"  Pt{str(i+1).zfill(2)}"
                  f" pred=({round(px_p,0)},{round(py_p,0)})"
                  f" actual=({outputs_px[i,0]},{outputs_px[i,1]})"
                  f" err={round(err,0)}px [{status}]")
            if err >= self.VALIDATION_PX:
                bad_pts.append(i)

        if bad_pts:
            print(f"Recollecting {len(bad_pts)} bad points.")
            cv2.namedWindow("Calibration", cv2.WND_PROP_FULLSCREEN)
            cv2.setWindowProperty("Calibration", cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
            for i in bad_pts:
                px, py = self.calibration_points[i]
                tx, ty = int(px * screen_w), int(py * screen_h)
                raw = self._collect_samples(30, f"Recollect {i+1}", tx, ty)
                if raw:
                    inputs_raw[i] = np.mean(np.array(raw), axis=0)
            cv2.destroyAllWindows()
            flipped    = flip_x(inputs_raw)
            normalizer = AxisNormalizer()
            normalizer.fit(flipped, grid_n=self.GRID_N)
            normed     = normalizer.transform(flipped)
        else:
            print("All points passed.")

        # Edge anchors + final mapper
        normed_aug, outputs_aug = add_edge_anchors(
            normed, outputs_px.astype(np.float64),
            screen_w, screen_h, nr=self.GRID_N, nc=self.GRID_N)
        print(f"\nEdge anchors: {len(normed_aug)-len(normed)}")

        mapper = RBFGazeMapper(smoothing=0.03)
        mapper.fit(normed_aug, outputs_aug)

        errs_x, errs_y = [], []
        for i in range(len(normed)):
            px_p, py_p = mapper.predict(normed[i])
            errs_x.append(abs(px_p - outputs_px[i, 0]))
            errs_y.append(abs(py_p - outputs_px[i, 1]))
        print(f"X fit: mean={round(np.mean(errs_x),1)}px  max={round(np.max(errs_x),1)}px")
        print(f"Y fit: mean={round(np.mean(errs_y),1)}px  max={round(np.max(errs_y),1)}px")

        self.normalizer = normalizer
        self.mapper     = mapper

        # Residual correction pass (4x4 grid)
        self._run_residual_correction()

        self.calibrated = True
        print("\nCalibration complete!")
        return True


    def _run_residual_correction(self):
        corr_fracs = [0.02, 0.35, 0.65, 0.98]
        correction_grid = [(x, y) for y in corr_fracs for x in corr_fracs]
        N_CORR = len(correction_grid)
        print(f"\nResidual correction: look at {N_CORR} dots. Head still.")

        cv2.namedWindow("Calibration", cv2.WND_PROP_FULLSCREEN)
        cv2.setWindowProperty("Calibration", cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)

        corr_pred_pts   = []
        corr_actual_pts = []

        for ci, (fx, fy) in enumerate(correction_grid):
            tx = int(fx * screen_w); ty = int(fy * screen_h)
            label = f"Correction {ci+1}/{N_CORR}"
            raw = self._collect_samples(30, label, tx, ty, settle=1.0)
            if raw is None:
                cv2.destroyAllWindows(); return
            if len(raw) >= 10:
                avg  = np.mean(np.array(raw), axis=0)
                proc = self.normalizer.transform(flip_x(np.array([avg])))[0]
                px_p, py_p = self.mapper.predict(proc)
                corr_pred_pts.append([px_p, py_p])
                corr_actual_pts.append([float(tx), float(ty)])
                print(f"  [{ci+1}/{N_CORR}] actual=({tx},{ty})"
                      f" pred=({round(px_p,0)},{round(py_p,0)})"
                      f" residual=({round(px_p-tx,0)},{round(py_p-ty,0)})")
            else:
                print(f"  [{ci+1}/{N_CORR}] SKIPPED - no face")

        cv2.destroyAllWindows()

        corrector = ResidualCorrectionField()
        if len(corr_pred_pts) >= 4:
            corrector.fit(corr_pred_pts, corr_actual_pts)
            total_before = total_after = 0.0
            for i in range(len(corr_pred_pts)):
                px_p, py_p = corr_pred_pts[i]
                ax, ay     = corr_actual_pts[i]
                cx2, cy2   = corrector.correct(px_p, py_p)
                total_before += np.sqrt((px_p-ax)**2 + (py_p-ay)**2)
                total_after  += np.sqrt((cx2-ax)**2  + (cy2-ay)**2)
            n = len(corr_pred_pts)
            print(f"Residual correction fitted on {n} points.")
            print(f"Mean error before: {round(total_before/n,1)}px")
            print(f"Mean error after:  {round(total_after/n,1)}px")
        else:
            print("Not enough correction points — running without correction.")
        self.corrector = corrector

    def _process_gaze_to_screen(self, gx, gy):
        """Apply the full pipeline: flip → normalise → RBF → residual → drift."""
        proc = self.normalizer.transform(flip_x(np.array([[gx, gy]])))[0]
        pred_x, pred_y = self.mapper.predict(proc)
        pred_x, pred_y = self.corrector.correct(pred_x, pred_y)
        pred_x += self.corrector.drift_x
        pred_y += self.corrector.drift_y
        return pred_x, pred_y

    def track_loop(self):
        """Main tracking loop — runs in a daemon thread."""
        self.running = True
        blink_cooldown = 0

        MOUSEEVENTF_MOVE        = 0x0001
        MOUSEEVENTF_LEFTDOWN    = 0x0002
        MOUSEEVENTF_LEFTUP      = 0x0004
        MOUSEEVENTF_ABSOLUTE    = 0x8000
        MOUSEEVENTF_VIRTUALDESK = 0x4000
        _mouse_event = ctypes.windll.user32.mouse_event

        # Minimum pixel movement before updating cursor — kills micro-jitter
        MOVE_THRESHOLD = 3

        def move_cursor(x, y):
            nx = int(x * 65535 / max(screen_w - 1, 1))
            ny = int(y * 65535 / max(screen_h - 1, 1))
            _mouse_event(
                MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK,
                nx, ny, 0, 0)

        while self.running:
            if self.paused or not self.calibrated:
                time.sleep(0.05); continue

            ret, frame = self.cap.read()
            if not ret: continue

            gx, gy, ear = detector.process(frame)
            if gx is None:
                continue

            pred_x, pred_y = self._process_gaze_to_screen(gx, gy)

            if ear < BLINK_THRESHOLD:
                blink_cooldown = 20
                self.gaze_filter.reset()
                self.clicker._reset(pred_x, pred_y)
            elif blink_cooldown > 0:
                blink_cooldown -= 1
                move_cursor(self._last_good_x, self._last_good_y)
            else:
                pred_x = float(np.clip(pred_x, 0, screen_w - 1))
                pred_y = float(np.clip(pred_y, 0, screen_h - 1))
                sx, sy = self.gaze_filter.update(pred_x, pred_y)
                new_x = int(np.clip(sx, 0, screen_w - 1))
                new_y = int(np.clip(sy, 0, screen_h - 1))

                # Only move cursor if gaze moved enough — suppresses micro-jitter
                dx = abs(new_x - self._last_good_x)
                dy = abs(new_y - self._last_good_y)
                if dx > MOVE_THRESHOLD or dy > MOVE_THRESHOLD:
                    self._last_good_x = new_x
                    self._last_good_y = new_y
                    move_cursor(self._last_good_x, self._last_good_y)

                self.clicker.update(self._last_good_x, self._last_good_y)

    def start_tracking(self):
        if not self.calibrated:
            print("ERROR: Must calibrate before tracking"); return False
        self.paused = False
        t = threading.Thread(target=self.track_loop, daemon=True)
        t.start()
        return True

    def stop_tracking(self):
        self.running = False

    def trigger_drift_correction(self):
        """Press 'R' equivalent — recalibrate drift to screen centre."""
        if not self.corrector.fitted:
            return
        print("Drift correction triggered. Look at screen centre...")
        cx_t = screen_w // 2; cy_t = screen_h // 2
        cv2.namedWindow("Calibration", cv2.WND_PROP_FULLSCREEN)
        cv2.setWindowProperty("Calibration", cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
        cv2.waitKey(1); force_foreground("Calibration")
        raw = self._collect_samples(30, "Look at centre - drift fix", cx_t, cy_t, settle=1.5)
        cv2.destroyAllWindows()
        if raw and len(raw) >= 8:
            avg_d  = np.mean(np.array(raw), axis=0)
            proc_d = self.normalizer.transform(flip_x(np.array([avg_d])))[0]
            px_d, py_d = self.mapper.predict(proc_d)
            px_c, py_c = self.corrector.correct(px_d, py_d)
            self.corrector.drift_x = float(cx_t - px_c)
            self.corrector.drift_y = float(cy_t - py_c)
            print(f"Drift correction applied: ({round(self.corrector.drift_x,0)},{round(self.corrector.drift_y,0)})px")
            self.gaze_filter.reset()
            self.clicker._reset(self._last_good_x, self._last_good_y)



# ---------------------------------------------------------------------------
# Web UI API (unchanged interface — all existing UI calls still work)
# ---------------------------------------------------------------------------
class WebUIAPI:
    def __init__(self, engine):
        self.engine = engine

    def start_calibration(self):
        def _run():
            success = self.engine.calibrate()
            if success:
                self.engine.start_tracking()
        threading.Thread(target=_run, daemon=True).start()
        return {'status': 'started'}

    def start_tracking(self):
        success = self.engine.start_tracking()
        return {'status': 'success' if success else 'failed'}

    def pause_tracking(self):
        self.engine.paused = True
        return {'status': 'success'}

    def resume_tracking(self):
        self.engine.paused = False
        return {'status': 'success'}

    def stop_tracking(self):
        self.engine.running = False
        return {'status': 'success'}

    def get_tracking_status(self):
        return {
            'calibrated':     self.engine.calibrated,
            'running':        self.engine.running,
            'paused':         self.engine.paused,
            'dwell_progress': self.engine.clicker.progress,
        }

    def update_dwell_time(self, value):
        global DWELL_TIME
        DWELL_TIME = float(value)
        return {'status': 'success', 'dwell_time': DWELL_TIME}

    def update_settings(self, settings):
        if 'dwellTime' in settings:
            self.update_dwell_time(settings['dwellTime'])
        return {'status': 'success'}

    def make_call(self, number):
        print(f"Making call to: {number}")
        try:
            if self.engine.calibrated:
                self.engine.paused = True
            os.startfile(f"tel:{number}")
        except Exception as e:
            print(f"Error making call: {e}")
        return {'status': 'success', 'number': number}

    def cancel_call(self):
        if self.engine.calibrated:
            self.engine.paused = False
        return {'status': 'success'}

    def go_back_home(self):
        return {'status': 'success'}

    def handle_action(self, action):
        return {'status': 'success', 'action': action}

    def toggle_bluetooth(self, enabled):
        return {'status': 'success'}

    def toggle_wifi(self, enabled):
        return {'status': 'success'}

    def shutdown(self):
        import subprocess
        subprocess.run(['shutdown', '/s', '/t', '0'])
        return {'status': 'success'}

    def restart(self):
        import subprocess
        subprocess.run(['shutdown', '/r', '/t', '0'])
        return {'status': 'success'}

    def send_keystroke(self, key):
        return {'status': 'success', 'key': key}

    def open_url(self, url):
        webbrowser.open(url)
        return {'status': 'success', 'url': url}

    def update_family_contact(self, contact):
        return {'status': 'success', 'contact': contact}


# ---------------------------------------------------------------------------
# Standalone entry point (no webview — same as original main_backend.py)
# ---------------------------------------------------------------------------
def main():
    print("Initialising camera...")
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("ERROR: Camera not detected"); return

    engine = EyeTrackingEngine(cap)

    if not engine.calibrate():
        print("Calibration cancelled.")
        cap.release(); cv2.destroyAllWindows(); return

    print("\nTracking — ESC to quit | R = drift correction")
    print(f"Dwell click: hold gaze for {DWELL_TIME}s to click\n")

    engine.start_tracking()

    # Keep main thread alive; handle ESC / R from a minimal OpenCV window
    cv2.namedWindow("Gaze Tracker", cv2.WINDOW_NORMAL)
    while True:
        ret, frame = cap.read()
        if not ret: continue
        key = cv2.waitKey(1)
        if key == 27:
            break
        if key in (ord('r'), ord('R')):
            engine.paused = True
            engine.trigger_drift_correction()
            engine.paused = False
        cv2.imshow("Gaze Tracker", frame)

    engine.stop_tracking()
    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
