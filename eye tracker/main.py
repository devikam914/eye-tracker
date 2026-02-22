"""
Eye Gaze Tracker — v7
======================
landmarks.py now uses inner canthus Y as vertical reference (lid-independent).
Expected raw_gaze Y range: approximately -0.15 (looking up) to +0.15 (looking down)
centered around 0.0 when looking straight.

AxisNormalizer updated:
  Y_CENTER = 0.0   (iris sits at canthus level when looking straight ahead)
  Y_HALF   = 0.15  (±15% of eye_width covers comfortable vertical gaze range)
  These are set to match the new canthus-relative coordinate system.
"""

import cv2
import numpy as np
import pyautogui
from scipy.interpolate import RBFInterpolator
from modules.landmarks import FaceLandmarkDetector

print("Initialising...")
detector = FaceLandmarkDetector()
cap = cv2.VideoCapture(0)
if not cap.isOpened():
    print("ERROR: Camera not detected"); exit()

pyautogui.FAILSAFE = False
screen_w, screen_h = pyautogui.size()
BLINK_THRESHOLD = 0.18
FONT = cv2.FONT_HERSHEY_SIMPLEX
DEBUG_MODE = True

# ── Kalman ────────────────────────────────────────────────────────────────────
class GazeKalman:
    def __init__(self):
        self.kf = cv2.KalmanFilter(4, 2)
        dt = 1.0
        self.kf.transitionMatrix = np.array([
            [1,0,dt,0],[0,1,0,dt],[0,0,1,0],[0,0,0,1]
        ], dtype=np.float32)
        self.kf.measurementMatrix = np.array([
            [1,0,0,0],[0,1,0,0]
        ], dtype=np.float32)
        self.base_Q = 0.1   # lower = smoother when fixating
        self.kf.measurementNoiseCov = np.array(
            [[250.0,0],[0,250.0]], dtype=np.float32)  # higher = less jitter
        self._set_Q(self.base_Q)
        self.kf.errorCovPost = np.eye(4, dtype=np.float32) * 500.0
        self.initialised = False

    def _set_Q(self, q):
        self.kf.processNoiseCov = np.diag(
            [q, q*0.7, q*6, q*4]).astype(np.float32)

    def update(self, mx, my):
        meas = np.array([[np.float32(mx)],[np.float32(my)]])
        if not self.initialised:
            self.kf.statePre  = np.array([[mx],[my],[0.],[0.]], dtype=np.float32)
            self.kf.statePost = self.kf.statePre.copy()
            self.initialised  = True
        predicted = self.kf.predict()
        jump = float(np.linalg.norm(meas - predicted[:2,:]))
        self._set_Q(float(np.clip(self.base_Q + 0.6*jump, self.base_Q, 80.0)))
        c = self.kf.correct(meas)
        return float(c[0,0]), float(c[1,0])

# ── AxisNormalizer ────────────────────────────────────────────────────────────
class AxisNormalizer:
    """
    Normalizes X and Y axes based on dynamically fitted data from calibration.
    """
    def __init__(self):
        self.X_CENTER = 0.506
        self.X_HALF   = 0.160
        self.Y_CENTER = -0.111
        self.Y_HALF   = 0.073

    def fit(self, gaze_pts):
        x_min, x_max = gaze_pts[:,0].min(), gaze_pts[:,0].max()
        y_min, y_max = gaze_pts[:,1].min(), gaze_pts[:,1].max()
        
        self.X_CENTER = (x_max + x_min) / 2.0
        self.X_HALF   = (x_max - x_min) / (2.0 * 0.92) if (x_max - x_min) > 0.001 else self.X_HALF
        
        self.Y_CENTER = (y_max + y_min) / 2.0
        self.Y_HALF   = (y_max - y_min) / (2.0 * 0.92) if (y_max - y_min) > 0.001 else self.Y_HALF

        print(f"\n  Gaze X: {x_min:.4f} -> {x_max:.4f}  span={x_max-x_min:.4f}")
        print(f"  Gaze Y: {y_min:.4f} -> {y_max:.4f}  span={y_max-y_min:.4f}")
        print(f"  X normalizer: center={self.X_CENTER:.4f} half={self.X_HALF:.4f} (dynamic)")
        print(f"  Y normalizer: center={self.Y_CENTER:.4f} half={self.Y_HALF:.4f} (dynamic)")

    def transform(self, gaze_pts):
        arr = np.atleast_2d(gaze_pts).astype(np.float64).copy()
        arr[:,0] = (arr[:,0] - self.X_CENTER) / (2*self.X_HALF) + 0.5
        arr[:,1] = (arr[:,1] - self.Y_CENTER) / (2*self.Y_HALF) + 0.5
        return arr   # NO clip

# ── RBF Mapper ────────────────────────────────────────────────────────────────
class RBFGazeMapper:
    def __init__(self, smoothing_x=0.1, smoothing_y=0.1):
        self.rbf_x = self.rbf_y = None
        self.sx = smoothing_x
        self.sy = smoothing_y

    def fit(self, gaze_pts, screen_pts):
        self.rbf_x = RBFInterpolator(gaze_pts, screen_pts[:,0],
                                     kernel='linear', smoothing=self.sx)
        self.rbf_y = RBFInterpolator(gaze_pts, screen_pts[:,1],
                                     kernel='linear', smoothing=self.sy)

    def predict(self, gaze_pt):
        q = np.array([gaze_pt])
        return float(self.rbf_x(q)[0]), float(self.rbf_y(q)[0])

def flip_x(raw_xy):
    arr = np.atleast_2d(raw_xy).astype(np.float64).copy()
    arr[:,0] = 1.0 - arr[:,0]
    return arr

# ── Calibration ───────────────────────────────────────────────────────────────
_cx = [0.04, 0.27, 0.50, 0.73, 0.96]
_cy = [0.04, 0.27, 0.50, 0.73, 0.96]
calibration_points = [(x, y) for y in _cy for x in _cx]

SETTLE_TIME     = 1.5
COLLECT_SAMPLES = 80
OUTLIER_IQR_K   = 1.5

inputs_raw = []
outputs_px = []

print(f"Starting {len(calibration_points)}-point calibration.")
print("Keep head STILL. Move eyes only.\n")

cv2.namedWindow("Calibration", cv2.WND_PROP_FULLSCREEN)
cv2.setWindowProperty("Calibration", cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)

for pt_idx, (px, py) in enumerate(calibration_points):
    tx = int(px * screen_w)
    ty = int(py * screen_h)

    t0 = cv2.getTickCount()
    while (cv2.getTickCount() - t0) / cv2.getTickFrequency() < SETTLE_TIME:
        elapsed = (cv2.getTickCount() - t0) / cv2.getTickFrequency()
        display = np.zeros((screen_h, screen_w, 3), dtype=np.uint8)
        r = int(28*(1-elapsed/SETTLE_TIME)) + 10
        cv2.circle(display, (tx, ty), r, (80,180,255), 2)
        cv2.circle(display, (tx, ty), 7, (80,180,255), -1)
        cv2.putText(display, f"Point {pt_idx+1}/{len(calibration_points)}",
                    (tx+18, ty-16), FONT, 0.5, (150,150,150), 1)
        cv2.imshow("Calibration", display)
        cv2.waitKey(1)

    samples = []
    while len(samples) < COLLECT_SAMPLES:
        ret, frame = cap.read()
        if not ret: continue
        gx, gy, ear = detector.process(frame)
        if gx is not None and ear > BLINK_THRESHOLD:
            samples.append([gx, gy])
        display = np.zeros((screen_h, screen_w, 3), dtype=np.uint8)
        cv2.circle(display, (tx, ty), 8, (0,220,80), -1)
        prog = int(360 * len(samples) / COLLECT_SAMPLES)
        cv2.ellipse(display, (tx, ty), (24,24), -90, 0, prog, (0,255,120), 3)
        cv2.imshow("Calibration", display)
        cv2.waitKey(1)

    s = np.array(samples, dtype=np.float64)
    for axis in [0, 1]:
        q1, q3 = np.percentile(s[:,axis], [25, 75])
        iqr = q3 - q1
        s = s[(s[:,axis] >= q1 - OUTLIER_IQR_K*iqr) &
              (s[:,axis] <= q3 + OUTLIER_IQR_K*iqr)]

    avg = np.mean(s, axis=0)
    inputs_raw.append(avg)
    outputs_px.append([tx, ty])
    print(f"  [{pt_idx+1:02d}/{len(calibration_points)}] "
          f"gaze=({avg[0]:.4f},{avg[1]:.4f})  screen=({tx},{ty})")

cv2.destroyAllWindows()

inputs_raw = np.array(inputs_raw)
outputs_px  = np.array(outputs_px)

# ── Y monotonicity check ──────────────────────────────────────────────────────
print("\n  Y per-row check (mean_gaze_y MUST increase top -> bottom):")
row_means = []
for row in range(5):
    pts = inputs_raw[row*5:(row+1)*5]
    m   = pts[:,1].mean()
    row_means.append(m)
    sy  = int(_cy[row] * screen_h)
    print(f"    screen_y={sy:4d}  mean_gaze_y={m:.5f}")

span = row_means[-1] - row_means[0]
mono = all(row_means[i+1] > row_means[i] for i in range(4))
print(f"  Span={span:.5f}  Monotonic={mono}")
if not mono:
    print("  *** Y is not monotonic — eyelid contamination may still be present")
    print("      or head moved during calibration.")

# ── Fit ───────────────────────────────────────────────────────────────────────
flipped    = flip_x(inputs_raw)
normalizer = AxisNormalizer()
normalizer.fit(flipped)
normed     = normalizer.transform(flipped)

mapper = RBFGazeMapper(smoothing_x=0.1, smoothing_y=0.1)
mapper.fit(normed, outputs_px)

errs_x, errs_y = [], []
for i in range(len(normed)):
    px_p, py_p = mapper.predict(normed[i])
    errs_x.append(abs(px_p - outputs_px[i,0]))
    errs_y.append(abs(py_p - outputs_px[i,1]))
print(f"\n  X fit: mean={np.mean(errs_x):.0f}px  max={np.max(errs_x):.0f}px")
print(f"  Y fit: mean={np.mean(errs_y):.0f}px  max={np.max(errs_y):.0f}px")
print("\nTracking — ESC to quit\n")

# ── Tracking ──────────────────────────────────────────────────────────────────
kalman = GazeKalman()
blink_cooldown = 0
frame_count = 0
last_good_x = screen_w // 2   # last valid cursor position — held during blinks
last_good_y = screen_h // 2

while True:
    ret, frame = cap.read()
    if not ret: continue

    gx, gy, ear = detector.process(frame)
    frame_count += 1

    # Press SPACE to snapshot current gaze values — hold to stream continuously
    key = cv2.waitKey(1)
    if key == 27: break
    snapshot = (key == 32)   # spacebar

    if gx is not None:
        if DEBUG_MODE and snapshot:
            proc_d = normalizer.transform(flip_x(np.array([[gx,gy]])))[0]
            px_d, py_d = mapper.predict(proc_d)
            print(f"  raw=({gx:.4f},{gy:.4f})  "
                  f"normed=({proc_d[0]:.3f},{proc_d[1]:.3f})  "
                  f"pred=({px_d:.0f},{py_d:.0f})")

        if ear < BLINK_THRESHOLD:
            # Blink detected: freeze cursor at last good position,
            # reset Kalman so blink-frame measurements don't corrupt velocity
            blink_cooldown = 20   # ~0.67s at 30fps
            kalman.initialised = False   # will re-init from last_good on resume
        elif blink_cooldown > 0:
            blink_cooldown -= 1
            # Keep cursor frozen — don't move during cooldown
            pyautogui.moveTo(last_good_x, last_good_y)
        else:
            proc = normalizer.transform(flip_x(np.array([[gx,gy]])))[0]
            pred_x, pred_y = mapper.predict(proc)
            pred_x = float(np.clip(pred_x, 0, screen_w-1))
            pred_y = float(np.clip(pred_y, 0, screen_h-1))
            sx, sy = kalman.update(pred_x, pred_y)
            last_good_x = int(np.clip(sx, 0, screen_w-1))
            last_good_y = int(np.clip(sy, 0, screen_h-1))
            pyautogui.moveTo(last_good_x, last_good_y)

    if gx is not None and ear is not None:
        blinking = ear < BLINK_THRESHOLD
        label = f"gx:{gx:.3f} gy:{gy:.3f} {'BLINK' if blinking else 'OK'}"
        color = (0,80,255) if blinking else (0,220,80)
    else:
        label, color = "No face", (0,80,255)
    cv2.putText(frame, label, (10,28), FONT, 0.55, color, 2)
    cv2.imshow("Gaze Tracker", frame)
    if key == -1:   # waitKey already called above
        pass

cap.release()
cv2.destroyAllWindows()
