# -*- coding: utf-8 -*-
import cv2
import numpy as np
import pyautogui
import time
import ctypes
import ctypes.wintypes
from scipy.interpolate import RBFInterpolator
from modules.ptgaze_detector import PTGazeDetector


def force_foreground(window_title):
    """Force an OpenCV window to the very front on Windows, above all other apps."""
    try:
        hwnd = ctypes.windll.user32.FindWindowW(None, window_title)
        if hwnd:
            # SW_RESTORE=9 in case minimised, then set as topmost
            ctypes.windll.user32.ShowWindow(hwnd, 9)
            ctypes.windll.user32.SetForegroundWindow(hwnd)
            HWND_TOPMOST  = -1
            SWP_NOMOVE    = 0x0002
            SWP_NOSIZE    = 0x0001
            ctypes.windll.user32.SetWindowPos(
                hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE)
    except Exception:
        pass   # non-Windows or window not found yet — silently ignore


print("Initialising...")
detector = PTGazeDetector()
cap = cv2.VideoCapture(0)
if not cap.isOpened():
    print("ERROR: Camera not detected"); exit()

pyautogui.FAILSAFE = False
screen_w, screen_h = pyautogui.size()
BLINK_THRESHOLD    = 0.18
CALIB_EAR_MIN      = 0.12
FONT               = cv2.FONT_HERSHEY_SIMPLEX
DEBUG_MODE         = True

# -- ELEMENT SNAP --------------------------------------------------------------
# Set up Win32 argtypes once so ctypes passes POINT correctly on 64-bit Windows
_u32 = ctypes.windll.user32
_u32.WindowFromPoint.restype  = ctypes.wintypes.HWND
_u32.WindowFromPoint.argtypes = [ctypes.wintypes.POINT]
_u32.GetWindowRect.restype    = ctypes.wintypes.BOOL
_u32.GetWindowRect.argtypes   = [ctypes.wintypes.HWND,
                                  ctypes.POINTER(ctypes.wintypes.RECT)]
_u32.IsWindowVisible.restype  = ctypes.wintypes.BOOL
_u32.IsWindowVisible.argtypes = [ctypes.wintypes.HWND]

SNAP_RADIUS = 40   # px — how far to search for a nearby element


def snap_to_nearest_element(x, y):
    """
    Scans a grid of points within SNAP_RADIUS around (x, y).
    For each point, asks Windows which control lives there (WindowFromPoint).
    Filters out huge windows (whole app panels) — keeps only small controls
    like buttons, title-bar icons, toolbar items.
    Returns the center of the nearest qualifying control, or (x, y) unchanged.

    Works without any extra pip installs — pure Win32 via ctypes.
    Note: DWM-rendered title-bar buttons (close/min/max) ARE found because
    WindowFromPoint walks into child HWNDs.
    """
    try:
        best_dist = float(SNAP_RADIUS + 1)
        best_cx, best_cy = float(x), float(y)
        seen = set()

        step = max(3, SNAP_RADIUS // 5)
        for dx in range(-SNAP_RADIUS, SNAP_RADIUS + 1, step):
            for dy in range(-SNAP_RADIUS, SNAP_RADIUS + 1, step):
                px = int(x + dx)
                py = int(y + dy)
                hwnd = _u32.WindowFromPoint(ctypes.wintypes.POINT(px, py))
                if not hwnd or hwnd in seen:
                    continue
                seen.add(hwnd)
                if not _u32.IsWindowVisible(hwnd):
                    continue
                rect = ctypes.wintypes.RECT()
                if not _u32.GetWindowRect(hwnd, ctypes.byref(rect)):
                    continue
                w = rect.right  - rect.left
                h = rect.bottom - rect.top
                # Skip controls that are too tiny or suspiciously large
                # (large = whole application panel, not a button)
                if w < 5 or h < 5 or w > screen_w // 2 or h > screen_h // 3:
                    continue
                ecx = (rect.left + rect.right)  / 2.0
                ecy = (rect.top  + rect.bottom) / 2.0
                dist = ((ecx - x) ** 2 + (ecy - y) ** 2) ** 0.5
                if dist < best_dist:
                    best_dist = dist
                    best_cx, best_cy = ecx, ecy

        return int(best_cx), int(best_cy)
    except Exception:
        return x, y   # silently fall back to raw position


# -- DWELL CLICK SETTINGS ------------------------------------------------------
# DWELL_TIME: seconds gaze must stay within DWELL_RADIUS pixels to trigger click
# Your frontend settings tab should update DWELL_TIME at runtime.
DWELL_TIME         = 1.5    # seconds  <-- frontend writes this value
DWELL_RADIUS       = 45     # pixels   — how much gaze can wander and still count
DWELL_COOLDOWN     = 1.2    # seconds  — min gap between consecutive clicks


class OneEuroFilter:
    def __init__(self, min_cutoff=1.0, beta=0.4, d_cutoff=1.0):
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


# -- DWELL CLICKER -------------------------------------------------------------
# Tracks how long gaze has stayed within DWELL_RADIUS of an anchor point.
# When dwell_time is reached, fires a left click and enters cooldown.
# Resets anchor whenever gaze moves outside the radius.
# Progress (0.0–1.0) exposed for optional visual feedback.
class DwellClicker:
    def __init__(self):
        self.anchor_x    = None
        self.anchor_y    = None
        self.dwell_start = None
        self.last_click  = 0.0       # timestamp of last click
        self.progress    = 0.0       # 0.0 → 1.0 for UI feedback

    def update(self, gx, gy):
        """
        Call once per frame with the smoothed screen position (gx, gy).
        Returns True on the frame a click is fired, False otherwise.
        Reads globals DWELL_TIME, DWELL_RADIUS, DWELL_COOLDOWN so the
        frontend can update them at runtime without restarting.
        """
        now = time.monotonic()

        # Still in post-click cooldown — don't accumulate dwell
        if now - self.last_click < DWELL_COOLDOWN:
            self._reset(gx, gy)
            self.progress = 0.0
            return False

        if self.anchor_x is None:
            self._reset(gx, gy)
            return False

        dist = np.hypot(gx - self.anchor_x, gy - self.anchor_y)

        if dist > DWELL_RADIUS:
            # Gaze moved — start fresh anchor at new position
            self._reset(gx, gy)
            return False

        # Gaze still inside radius — accumulate dwell time
        elapsed = now - self.dwell_start
        self.progress = min(elapsed / max(DWELL_TIME, 0.1), 1.0)

        if elapsed >= DWELL_TIME:
            snap_x, snap_y = snap_to_nearest_element(self.anchor_x, self.anchor_y)
            snapped = (snap_x != int(self.anchor_x) or snap_y != int(self.anchor_y))
            pyautogui.click(snap_x, snap_y)
            print(f"Dwell click at ({snap_x}, {snap_y})"
                  + (" [snapped]" if snapped else ""))
            self.last_click = now
            self._reset(gx, gy)
            return True

        return False

    def _reset(self, gx, gy):
        self.anchor_x    = gx
        self.anchor_y    = gy
        self.dwell_start = time.monotonic()
        self.progress    = 0.0


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
        y_min, y_max = gaze_pts[:,1].min(), gaze_pts[:,1].max()
        print("  X: " + str(round(x_min,4)) + " -> " + str(round(x_max,4))
              + "  span=" + str(round(x_max-x_min,4)))
        print("  Y: " + str(round(y_min,4)) + " -> " + str(round(y_max,4))
              + "  span=" + str(round(y_max-y_min,4)))
        print("  Y_CENTER=" + str(round(self.Y_CENTER,4))
              + "  Y_HALF=" + str(round(self.Y_HALF,4)) + " (data-driven)")

    def transform(self, gaze_pts):
        arr = np.atleast_2d(gaze_pts).astype(np.float64).copy()
        arr[:,0] = (arr[:,0] - self.X_CENTER) / (2.0 * self.X_HALF) + 0.5
        arr[:,1] = (arr[:,1] - self.Y_CENTER) / (2.0 * self.Y_HALF) + 0.5
        return arr


class RBFGazeMapper:
    def __init__(self, smoothing=0.03):
        self.rbf_x = self.rbf_y = None
        self.s = smoothing

    def fit(self, gaze_pts, screen_pts):
        self.rbf_x = RBFInterpolator(gaze_pts, screen_pts[:,0],
                                     kernel='thin_plate_spline', smoothing=self.s)
        self.rbf_y = RBFInterpolator(gaze_pts, screen_pts[:,1],
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

    def fit(self, pred_pts, actual_pts):
        pred_arr   = np.array(pred_pts,   dtype=np.float64)
        actual_arr = np.array(actual_pts, dtype=np.float64)
        res_x = actual_arr[:,0] - pred_arr[:,0]
        res_y = actual_arr[:,1] - pred_arr[:,1]
        self.rbf_rx = RBFInterpolator(pred_arr, res_x,
                                      kernel='thin_plate_spline', smoothing=0.5)
        self.rbf_ry = RBFInterpolator(pred_arr, res_y,
                                      kernel='thin_plate_spline', smoothing=0.5)
        self.fitted = True
        self.n_pts  = len(pred_pts)

    def correct(self, pred_x, pred_y):
        if not self.fitted:
            return float(pred_x), float(pred_y)
        q = np.array([[pred_x, pred_y]], dtype=np.float64)
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


def collect_samples(n, label, tx, ty, settle=1.5):
    t0 = cv2.getTickCount()
    while (cv2.getTickCount()-t0)/cv2.getTickFrequency() < settle:
        display = np.zeros((screen_h, screen_w, 3), dtype=np.uint8)
        cv2.circle(display, (tx,ty), 20, (80,180,255), 2)
        cv2.circle(display, (tx,ty), 7,  (80,180,255), -1)
        cv2.circle(display, (tx,ty), 2,  (255,255,255), -1)
        if label:
            cv2.putText(display, label,
                        (tx - len(label)*4, ty+45), FONT, 0.5, (150,150,150), 1)
        cv2.imshow("Calibration", display)
        if cv2.waitKey(1) & 0xFF == 27:
            cap.release(); cv2.destroyAllWindows(); exit()

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
        if cv2.waitKey(1) & 0xFF == 27:
            cap.release(); cv2.destroyAllWindows(); exit()

    s = np.array(samples, dtype=np.float64)
    for _ in range(2):
        for axis in [0,1]:
            q1,q3 = np.percentile(s[:,axis],[25,75])
            iqr = q3-q1
            s = s[(s[:,axis] >= q1-1.2*iqr) & (s[:,axis] <= q3+1.2*iqr)]
        if len(s) < 10:
            s = np.array(samples, dtype=np.float64); break
    return s.tolist()


# -- CALIBRATION ---------------------------------------------------------------
_cx = [0.02, 0.17, 0.33, 0.50, 0.67, 0.83, 0.98]
_cy = [0.02, 0.17, 0.33, 0.50, 0.67, 0.83, 0.98]
GRID_N             = 7
calibration_points = [(x,y) for y in _cy for x in _cx]
N_PTS              = len(calibration_points)
VALIDATION_PX      = 120

print("Starting " + str(N_PTS) + "-point calibration.")
print("Stare at the white dot. Head still. ESC to abort.")
print("Mode: " + ("3D" if detector._use_3d else "2D"))
print("")

cv2.namedWindow("Calibration", cv2.WND_PROP_FULLSCREEN)
cv2.setWindowProperty("Calibration", cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)

inputs_raw = []
outputs_px = []

print("--- PASS 1: Collection ---")
for pt_idx, (px,py) in enumerate(calibration_points):
    tx, ty = int(px*screen_w), int(py*screen_h)
    raw = collect_samples(30, str(pt_idx+1)+"/"+str(N_PTS), tx, ty)
    s   = np.array(raw)
    avg = np.mean(s, axis=0)
    std_xy = np.std(s, axis=0)
    quality_ok = (std_xy[0] < 0.018 and std_xy[1] < 0.018)
    inputs_raw.append(avg)
    outputs_px.append([tx, ty])
    warn = "" if quality_ok else " [!! HEAD MOVED]"
    print("  [" + str(pt_idx+1).zfill(2) + "/" + str(N_PTS) + "]"
          + "  gaze=(" + str(round(avg[0],4)) + "," + str(round(avg[1],4)) + ")"
          + "  std=(" + str(round(std_xy[0],4)) + "," + str(round(std_xy[1],4)) + ")"
          + "  kept=" + str(len(raw)) + warn)

cv2.destroyAllWindows()
inputs_raw = np.array(inputs_raw)
outputs_px  = np.array(outputs_px)

print("")
print("Y monotonicity check:")
row_means = []
for row in range(GRID_N):
    pts = inputs_raw[row*GRID_N:(row+1)*GRID_N]
    m   = pts[:,1].mean()
    row_means.append(m)
    print("  screen_y=" + str(int(_cy[row]*screen_h))
          + "  gaze_y=" + str(round(m,5)))
span = row_means[-1] - row_means[0]
mono = all(row_means[i+1] > row_means[i] for i in range(GRID_N-1))
print("  Span=" + str(round(span,5)) + "  Monotonic=" + str(mono))

flipped    = flip_x(inputs_raw)
normalizer = AxisNormalizer()
normalizer.fit(flipped, grid_n=GRID_N)
normed     = normalizer.transform(flipped)

print("")
print("--- PASS 2: Validation ---")
tmp_rx = RBFInterpolator(normed, outputs_px[:,0].astype(float),
                         kernel='thin_plate_spline', smoothing=0.1)
tmp_ry = RBFInterpolator(normed, outputs_px[:,1].astype(float),
                         kernel='thin_plate_spline', smoothing=0.1)
bad_pts = []
for i in range(N_PTS):
    q    = normed[i:i+1]
    px_p = float(tmp_rx(q)[0])
    py_p = float(tmp_ry(q)[0])
    err  = float(np.sqrt((px_p-outputs_px[i,0])**2 + (py_p-outputs_px[i,1])**2))
    status = "OK" if err < VALIDATION_PX else "RECOLLECT"
    print("  Pt" + str(i+1).zfill(2)
          + " pred=(" + str(round(px_p,0)) + "," + str(round(py_p,0)) + ")"
          + " actual=(" + str(outputs_px[i,0]) + "," + str(outputs_px[i,1]) + ")"
          + " err=" + str(round(err,0)) + "px [" + status + "]")
    if err >= VALIDATION_PX:
        bad_pts.append(i)

if bad_pts:
    print("Recollecting " + str(len(bad_pts)) + " bad points.")
    cv2.namedWindow("Calibration", cv2.WND_PROP_FULLSCREEN)
    cv2.setWindowProperty("Calibration", cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
    for i in bad_pts:
        px, py = calibration_points[i]
        tx, ty = int(px*screen_w), int(py*screen_h)
        raw = collect_samples(30, "Recollect "+str(i+1), tx, ty)
        if raw:
            inputs_raw[i] = np.mean(np.array(raw), axis=0)
            print("  Pt" + str(i+1) + " done: gaze=("
                  + str(round(inputs_raw[i,0],4)) + ","
                  + str(round(inputs_raw[i,1],4)) + ")")
    cv2.destroyAllWindows()
    flipped    = flip_x(inputs_raw)
    normalizer = AxisNormalizer()
    normalizer.fit(flipped, grid_n=GRID_N)
    normed     = normalizer.transform(flipped)
else:
    print("All points passed.")

normed_aug, outputs_aug = add_edge_anchors(
    normed, outputs_px.astype(np.float64),
    screen_w, screen_h, nr=GRID_N, nc=GRID_N)
print("")
print("Edge anchors: " + str(len(normed_aug)-len(normed)))

mapper = RBFGazeMapper(smoothing=0.03)
mapper.fit(normed_aug, outputs_aug)

errs_x, errs_y = [], []
for i in range(len(normed)):
    px_p, py_p = mapper.predict(normed[i])
    errs_x.append(abs(px_p - outputs_px[i,0]))
    errs_y.append(abs(py_p - outputs_px[i,1]))
print("X fit: mean=" + str(round(np.mean(errs_x),1))
      + "px  max=" + str(round(np.max(errs_x),1)) + "px")
print("Y fit: mean=" + str(round(np.mean(errs_y),1))
      + "px  max=" + str(round(np.max(errs_y),1)) + "px")
print("Mode: " + ("3D" if detector._3d_available else "2D"))
print("")

# -- RESIDUAL CORRECTION -------------------------------------------------------
corr_fracs = [0.02, 0.35, 0.65, 0.98]
correction_grid = [(x,y) for y in corr_fracs for x in corr_fracs]
N_CORR = len(correction_grid)

print("Residual correction: look at " + str(N_CORR) + " dots (3x3 grid).")
print("Take 2-3 seconds per dot. Head still.")
print("This corrects session-based offset automatically.")
print("")

cv2.namedWindow("Calibration", cv2.WND_PROP_FULLSCREEN)
cv2.setWindowProperty("Calibration", cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)

corr_pred_pts   = []
corr_actual_pts = []

for ci, (fx, fy) in enumerate(correction_grid):
    tx = int(fx * screen_w)
    ty = int(fy * screen_h)
    label = "Correction " + str(ci+1) + "/" + str(N_CORR)
    raw = collect_samples(30, label, tx, ty, settle=1.0)
    if len(raw) >= 10:
        s   = np.array(raw)
        avg = np.mean(s, axis=0)
        proc = normalizer.transform(flip_x(np.array([avg])))[0]
        px_p, py_p = mapper.predict(proc)
        corr_pred_pts.append([px_p, py_p])
        corr_actual_pts.append([float(tx), float(ty)])
        err_x = round(px_p - tx, 0)
        err_y = round(py_p - ty, 0)
        print("  [" + str(ci+1) + "/" + str(N_CORR) + "]"
              + " actual=(" + str(tx) + "," + str(ty) + ")"
              + " pred=(" + str(round(px_p,0)) + "," + str(round(py_p,0)) + ")"
              + " residual=(" + str(err_x) + "," + str(err_y) + ")")
    else:
        print("  [" + str(ci+1) + "/" + str(N_CORR) + "] SKIPPED - no face")

cv2.destroyAllWindows()

corrector = ResidualCorrectionField()
corrector.drift_x = 0.0
corrector.drift_y = 0.0
if len(corr_pred_pts) >= 4:
    corrector.fit(corr_pred_pts, corr_actual_pts)
    print("")
    print("Residual correction fitted on " + str(len(corr_pred_pts)) + " points.")
    total_before = 0.0
    total_after  = 0.0
    for i in range(len(corr_pred_pts)):
        px_p, py_p = corr_pred_pts[i]
        ax,   ay   = corr_actual_pts[i]
        cx2, cy2   = corrector.correct(px_p, py_p)
        total_before += np.sqrt((px_p-ax)**2 + (py_p-ay)**2)
        total_after  += np.sqrt((cx2-ax)**2  + (cy2-ay)**2)
    print("Mean error before correction: " + str(round(total_before/len(corr_pred_pts),1)) + "px")
    print("Mean error after  correction: " + str(round(total_after /len(corr_pred_pts),1)) + "px")
else:
    print("Not enough correction points - running without correction.")

print("")
print("Tracking - ESC to quit | SPACE debug | R = drift correction")
print("Dwell click: hold gaze for " + str(DWELL_TIME) + "s to click")
print("")


# -- TRACKING ------------------------------------------------------------------
gaze_filter    = GazeFilter()
dwell_clicker  = DwellClicker()
blink_cooldown = 0
last_good_x    = screen_w // 2
last_good_y    = screen_h // 2

while True:
    ret, frame = cap.read()
    if not ret: continue

    gx, gy, ear = detector.process(frame)
    key = cv2.waitKey(1)
    if key == 27: break
    snapshot  = (key == 32)
    do_recorr = (key == ord('r') or key == ord('R'))

    if do_recorr and corrector.fitted:
        print("Drift correction triggered. Look at screen center...")
        cx_t = screen_w // 2
        cy_t = screen_h // 2
        cv2.namedWindow("Calibration", cv2.WND_PROP_FULLSCREEN)
        cv2.setWindowProperty("Calibration", cv2.WND_PROP_FULLSCREEN,
                              cv2.WINDOW_FULLSCREEN)
        # Give OpenCV one frame to actually create the window, then force it front
        cv2.waitKey(1)
        force_foreground("Calibration")
        raw_drift = collect_samples(30, "Look at center - drift fix", cx_t, cy_t,
                                    settle=1.5)
        cv2.destroyAllWindows()
        if len(raw_drift) >= 8:
            avg_d  = np.mean(np.array(raw_drift), axis=0)
            proc_d = normalizer.transform(flip_x(np.array([avg_d])))[0]
            px_d, py_d = mapper.predict(proc_d)
            px_c, py_c = corrector.correct(px_d, py_d)
            drift_x = float(cx_t - px_c)
            drift_y = float(cy_t - py_c)
            corrector.drift_x = drift_x
            corrector.drift_y = drift_y
            print("Drift correction applied: ("
                  + str(round(drift_x,0)) + ","
                  + str(round(drift_y,0)) + ")px")
            gaze_filter.reset()
            dwell_clicker._reset(last_good_x, last_good_y)

    if gx is not None:
        proc = normalizer.transform(flip_x(np.array([[gx,gy]])))[0]
        pred_x, pred_y = mapper.predict(proc)
        pred_x, pred_y = corrector.correct(pred_x, pred_y)
        pred_x += corrector.drift_x
        pred_y += corrector.drift_y

        if DEBUG_MODE and snapshot:
            print("  raw=(" + str(round(gx,4)) + "," + str(round(gy,4)) + ")"
                  + "  normed=(" + str(round(proc[0],3)) + ","
                  + str(round(proc[1],3)) + ")"
                  + "  pred=(" + str(round(pred_x,0)) + ","
                  + str(round(pred_y,0)) + ")")

        if ear < BLINK_THRESHOLD:
            blink_cooldown = 20
            gaze_filter.reset()
            dwell_clicker._reset(pred_x, pred_y)   # reset dwell on blink
        elif blink_cooldown > 0:
            blink_cooldown -= 1
            pyautogui.moveTo(last_good_x, last_good_y)
        else:
            pred_x = float(np.clip(pred_x, 0, screen_w-1))
            pred_y = float(np.clip(pred_y, 0, screen_h-1))
            sx, sy = gaze_filter.update(pred_x, pred_y)
            last_good_x = int(np.clip(sx, 0, screen_w-1))
            last_good_y = int(np.clip(sy, 0, screen_h-1))
            pyautogui.moveTo(last_good_x, last_good_y)

            # Dwell click — runs on smoothed cursor position
            dwell_clicker.update(last_good_x, last_good_y)

    if gx is not None and ear is not None:
        blinking = ear < BLINK_THRESHOLD
        tag   = "3D" if detector._3d_available else "2D"
        # Show dwell progress as a percentage in the debug overlay
        dwell_pct = int(dwell_clicker.progress * 100)
        label = ("gx:" + str(round(gx,3))
                 + " gy:" + str(round(gy,3))
                 + " [" + tag + "]"
                 + " dwell:" + str(dwell_pct) + "%"
                 + " " + ("BLINK" if blinking else "OK"))
        color = (0,80,255) if blinking else (0,220,80)
    else:
        label = "No face"; color = (0,80,255)

    cv2.putText(frame, label, (10,28), FONT, 0.55, color, 2)
    cv2.imshow("Gaze Tracker", frame)

cap.release()
cv2.destroyAllWindows()