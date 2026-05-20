# -*- coding: utf-8 -*-
"""
Integrated Eye Tracking + Web UI
Combines the improved backend from GitHub with your current web UI
"""
import cv2
import numpy as np
import pyautogui
import time
import threading
import webview
import os
from scipy.interpolate import RBFInterpolator

# Try to import ptgaze detector (from backend), fallback to landmarks
try:
    from modules.ptgaze_detector import PTGazeDetector
    DETECTOR_TYPE = "ptgaze"
    print("Using PTGaze detector (improved accuracy)")
except ImportError:
    from modules.landmarks import FaceLandmarkDetector
    DETECTOR_TYPE = "landmarks"
    print("Using MediaPipe landmarks detector")


# ============================================================================
# CONFIGURATION
# ============================================================================
pyautogui.FAILSAFE = False
screen_w, screen_h = pyautogui.size()
BLINK_THRESHOLD = 0.18
CALIB_EAR_MIN = 0.12
FONT = cv2.FONT_HERSHEY_SIMPLEX

# Dwell click settings (can be updated by UI)
DWELL_TIME = 1.5        # seconds - slightly longer for better accuracy
DWELL_RADIUS = 50       # pixels - larger radius for easier targeting
DWELL_COOLDOWN = 1.0    # seconds


# ============================================================================
# ONE EURO FILTER (Smoothing)
# ============================================================================
class OneEuroFilter:
    def __init__(self, min_cutoff=0.8, beta=0.3, d_cutoff=1.0):
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
            self.x_prev = x
            self.t_prev = t
            return x
        dt = max(t - self.t_prev, 1e-6)
        dx = (x - self.x_prev) / dt
        a_d = self._alpha(self.d_cutoff, dt)
        self.dx_prev = a_d * dx + (1 - a_d) * self.dx_prev
        cutoff = self.min_cutoff + self.beta * abs(self.dx_prev)
        a = self._alpha(cutoff, dt)
        x_hat = a * x + (1 - a) * self.x_prev
        self.x_prev = x_hat
        self.t_prev = t
        return x_hat


class GazeFilter:
    def __init__(self):
        # More aggressive smoothing for better stability
        self.fx = OneEuroFilter(min_cutoff=0.8, beta=0.3)
        self.fy = OneEuroFilter(min_cutoff=0.8, beta=0.3)

    def reset(self):
        self.fx.x_prev = None
        self.fy.x_prev = None

    def update(self, mx, my):
        t = cv2.getTickCount() / cv2.getTickFrequency()
        return self.fx(mx, t), self.fy(my, t)


# ============================================================================
# DWELL CLICKER
# ============================================================================
class DwellClicker:
    def __init__(self):
        self.anchor_x = None
        self.anchor_y = None
        self.dwell_start = None
        self.last_click = 0.0
        self.progress = 0.0
        self.position_buffer = []  # Buffer for position stabilization
        self.buffer_size = 5

    def update(self, gx, gy):
        """Returns True when click is fired"""
        now = time.monotonic()

        # Cooldown period
        if now - self.last_click < DWELL_COOLDOWN:
            self._reset(gx, gy)
            self.progress = 0.0
            return False

        # Stabilize position using buffer
        self.position_buffer.append((gx, gy))
        if len(self.position_buffer) > self.buffer_size:
            self.position_buffer.pop(0)
        
        # Use median position for stability
        if len(self.position_buffer) >= 3:
            stable_x = np.median([p[0] for p in self.position_buffer])
            stable_y = np.median([p[1] for p in self.position_buffer])
        else:
            stable_x, stable_y = gx, gy

        if self.anchor_x is None:
            self._reset(stable_x, stable_y)
            return False

        dist = np.hypot(stable_x - self.anchor_x, stable_y - self.anchor_y)

        if dist > DWELL_RADIUS:
            self._reset(stable_x, stable_y)
            return False

        # Accumulate dwell time
        elapsed = now - self.dwell_start
        self.progress = min(elapsed / max(DWELL_TIME, 0.1), 1.0)

        if elapsed >= DWELL_TIME:
            pyautogui.click(int(self.anchor_x), int(self.anchor_y))
            print(f"Dwell click at ({int(self.anchor_x)}, {int(self.anchor_y)})")
            self.last_click = now
            self._reset(stable_x, stable_y)
            return True

        return False

    def _reset(self, gx, gy):
        self.anchor_x = gx
        self.anchor_y = gy
        self.dwell_start = time.monotonic()
        self.progress = 0.0
        self.position_buffer = []


# ============================================================================
# CALIBRATION & MAPPING
# ============================================================================
class AxisNormalizer:
    def __init__(self):
        self.X_CENTER = 0.5
        self.X_HALF = 0.15
        self.Y_CENTER = -0.1
        self.Y_HALF = 0.08

    def fit(self, gaze_pts, grid_n=7):
        x_min, x_max = gaze_pts[:, 0].min(), gaze_pts[:, 0].max()
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
    """Corrects session-based offset using a second calibration pass"""
    def __init__(self):
        self.rbf_rx = None
        self.rbf_ry = None
        self.fitted = False
        self.n_pts = 0
        self.drift_x = 0.0
        self.drift_y = 0.0

    def fit(self, pred_pts, actual_pts):
        """Fit correction field from predicted vs actual screen positions"""
        pred_arr = np.array(pred_pts, dtype=np.float64)
        actual_arr = np.array(actual_pts, dtype=np.float64)
        res_x = actual_arr[:, 0] - pred_arr[:, 0]
        res_y = actual_arr[:, 1] - pred_arr[:, 1]
        self.rbf_rx = RBFInterpolator(pred_arr, res_x,
                                      kernel='thin_plate_spline', smoothing=0.5)
        self.rbf_ry = RBFInterpolator(pred_arr, res_y,
                                      kernel='thin_plate_spline', smoothing=0.5)
        self.fitted = True
        self.n_pts = len(pred_pts)

    def correct(self, pred_x, pred_y):
        """Apply correction to predicted screen position"""
        if not self.fitted:
            return float(pred_x), float(pred_y)
        q = np.array([[pred_x, pred_y]], dtype=np.float64)
        cx = float(pred_x) + float(self.rbf_rx(q)[0]) + self.drift_x
        cy = float(pred_y) + float(self.rbf_ry(q)[0]) + self.drift_y
        return cx, cy


# ============================================================================
# EYE TRACKING ENGINE
# ============================================================================
class EyeTrackingEngine:
    def __init__(self):
        print("Initializing eye tracking engine...")
        
        # Initialize detector
        if DETECTOR_TYPE == "ptgaze":
            self.detector = PTGazeDetector()
        else:
            self.detector = FaceLandmarkDetector()
        
        # Initialize camera
        self.cap = cv2.VideoCapture(0)
        if not self.cap.isOpened():
            raise RuntimeError("ERROR: Camera not detected")
        
        # Components
        self.normalizer = AxisNormalizer()
        self.mapper = RBFGazeMapper()
        self.corrector = ResidualCorrectionField()
        self.filter = GazeFilter()
        self.clicker = DwellClicker()
        
        # State
        self.calibrated = False
        self.running = False
        self.paused = False
        
        print("Eye tracking engine initialized")

    def calibrate(self, grid_size=7):
        """Run calibration sequence"""
        print(f"Starting {grid_size}x{grid_size} calibration...")
        
        # Generate calibration grid
        margin_x, margin_y = screen_w // 10, screen_h // 10
        x_coords = np.linspace(margin_x, screen_w - margin_x, grid_size)
        y_coords = np.linspace(margin_y, screen_h - margin_y, grid_size)
        
        gaze_samples = []
        screen_samples = []
        
        # PASS 1: Main calibration grid
        print("--- PASS 1: Main Calibration ---")
        for i, ty in enumerate(y_coords):
            for j, tx in enumerate(x_coords):
                tx, ty = int(tx), int(ty)
                label = f"Point {i*grid_size + j + 1}/{grid_size*grid_size}"
                
                # Collect samples for this point
                samples = self._collect_samples(30, label, tx, ty)
                if samples is None:
                    return False
                
                # Store median
                median_gaze = np.median(samples, axis=0)
                gaze_samples.append(median_gaze)
                screen_samples.append([float(tx), float(ty)])
        
        # Fit normalizer and mapper
        gaze_arr = np.array(gaze_samples, dtype=np.float64)
        screen_arr = np.array(screen_samples, dtype=np.float64)
        
        self.normalizer.fit(gaze_arr)
        normalized_gaze = self.normalizer.transform(gaze_arr)
        self.mapper.fit(normalized_gaze, screen_arr)
        
        print("Main calibration complete!")
        
        # PASS 2: Residual correction calibration
        print("\n--- PASS 2: Residual Correction ---")
        print("Look at 16 dots (4x4 grid) to correct offset")
        
        # Generate 4x4 correction grid
        corr_fracs = [0.02, 0.35, 0.65, 0.98]
        correction_grid = [(x, y) for y in corr_fracs for x in corr_fracs]
        
        corr_pred_pts = []
        corr_actual_pts = []
        
        for ci, (fx, fy) in enumerate(correction_grid):
            tx = int(fx * screen_w)
            ty = int(fy * screen_h)
            label = f"Correction {ci+1}/{len(correction_grid)}"
            
            # Collect samples
            samples = self._collect_samples(30, label, tx, ty, settle=1.0)
            if samples is None:
                return False
            
            if len(samples) >= 10:
                # Get predicted position using current calibration
                avg_gaze = np.mean(samples, axis=0)
                normalized = self.normalizer.transform([[avg_gaze[0], avg_gaze[1]]])
                px_p, py_p = self.mapper.predict(normalized[0])
                
                corr_pred_pts.append([px_p, py_p])
                corr_actual_pts.append([float(tx), float(ty)])
                
                err_x = round(px_p - tx, 0)
                err_y = round(py_p - ty, 0)
                print(f"  [{ci+1}/{len(correction_grid)}] "
                      f"actual=({tx},{ty}) pred=({round(px_p,0)},{round(py_p,0)}) "
                      f"residual=({err_x},{err_y})")
        
        # Fit residual correction
        if len(corr_pred_pts) >= 4:
            self.corrector.fit(corr_pred_pts, corr_actual_pts)
            print(f"\nResidual correction fitted on {len(corr_pred_pts)} points")
            
            # Calculate improvement
            total_before = 0.0
            total_after = 0.0
            for i in range(len(corr_pred_pts)):
                px_p, py_p = corr_pred_pts[i]
                ax, ay = corr_actual_pts[i]
                cx2, cy2 = self.corrector.correct(px_p, py_p)
                total_before += np.sqrt((px_p - ax)**2 + (py_p - ay)**2)
                total_after += np.sqrt((cx2 - ax)**2 + (cy2 - ay)**2)
            
            print(f"Mean error before correction: {round(total_before/len(corr_pred_pts), 1)}px")
            print(f"Mean error after correction: {round(total_after/len(corr_pred_pts), 1)}px")
        else:
            print("Not enough correction points - running without correction")
        
        self.calibrated = True
        print("\nCalibration complete!")
        cv2.destroyAllWindows()
        return True

    def _collect_samples(self, n, label, tx, ty, settle=1.5):
        """Collect n gaze samples at target position (tx, ty)"""
        # Settle time
        t0 = cv2.getTickCount()
        while (cv2.getTickCount() - t0) / cv2.getTickFrequency() < settle:
            display = np.zeros((screen_h, screen_w, 3), dtype=np.uint8)
            cv2.circle(display, (tx, ty), 20, (80, 180, 255), 2)
            cv2.circle(display, (tx, ty), 7, (80, 180, 255), -1)
            cv2.circle(display, (tx, ty), 2, (255, 255, 255), -1)
            if label:
                cv2.putText(display, label, (tx - len(label)*4, ty+45),
                           FONT, 0.5, (150, 150, 150), 1)
            cv2.imshow("Calibration", display)
            if cv2.waitKey(1) & 0xFF == 27:
                return None
        
        # Collect samples
        samples = []
        while len(samples) < n:
            ret, frame = self.cap.read()
            if not ret:
                continue
            
            gx, gy, ear = self.detector.process(frame)
            if gx is not None and ear > CALIB_EAR_MIN:
                samples.append([gx, gy])
            
            # Show progress
            display = np.zeros((screen_h, screen_w, 3), dtype=np.uint8)
            cv2.circle(display, (tx, ty), 8, (0, 220, 80), -1)
            cv2.circle(display, (tx, ty), 2, (255, 255, 255), -1)
            prog = int(360 * len(samples) / n)
            cv2.ellipse(display, (tx, ty), (24, 24), -90, 0, prog, (0, 255, 120), 3)
            cv2.imshow("Calibration", display)
            if cv2.waitKey(1) & 0xFF == 27:
                return None
        
        return np.array(samples, dtype=np.float64)

    def track_loop(self):
        """Main tracking loop - runs in separate thread"""
        self.running = True
        
        while self.running:
            if self.paused or not self.calibrated:
                time.sleep(0.1)
                continue
            
            ret, frame = self.cap.read()
            if not ret:
                continue
            
            # Get gaze
            gx, gy, ear = self.detector.process(frame)
            if gx is None:
                continue
            
            # Normalize and map to screen
            normalized = self.normalizer.transform([[gx, gy]])
            mx, my = self.mapper.predict(normalized[0])
            
            # Apply residual correction
            mx, my = self.corrector.correct(mx, my)
            
            # Smooth
            sx, sy = self.filter.update(mx, my)
            
            # Clamp to screen
            sx = max(0, min(screen_w - 1, sx))
            sy = max(0, min(screen_h - 1, sy))
            
            # Move cursor
            pyautogui.moveTo(int(sx), int(sy))
            
            # Dwell click
            self.clicker.update(sx, sy)
    
    def start_tracking(self):
        """Start tracking in background thread"""
        if not self.calibrated:
            print("ERROR: Must calibrate before tracking")
            return False
        
        self.paused = False
        thread = threading.Thread(target=self.track_loop, daemon=True)
        thread.start()
        return True
    
    def stop_tracking(self):
        """Stop tracking"""
        self.running = False
        self.cap.release()
        cv2.destroyAllWindows()


# ============================================================================
# WEB UI API
# ============================================================================
class WebUIAPI:
    def __init__(self, engine):
        self.engine = engine
    
    def start_calibration(self):
        """Start calibration from UI"""
        success = self.engine.calibrate()
        return {'status': 'success' if success else 'failed'}
    
    def start_tracking(self):
        """Start eye tracking"""
        success = self.engine.start_tracking()
        return {'status': 'success' if success else 'failed'}
    
    def pause_tracking(self):
        """Pause tracking"""
        self.engine.paused = True
        return {'status': 'success'}
    
    def resume_tracking(self):
        """Resume tracking"""
        self.engine.paused = False
        return {'status': 'success'}
    
    def update_dwell_time(self, value):
        """Update dwell time from UI"""
        global DWELL_TIME
        DWELL_TIME = float(value)
        return {'status': 'success', 'dwell_time': DWELL_TIME}
    
    def make_call(self, number):
        """Make phone call"""
        print(f"Making call to: {number}")
        try:
            os.startfile(f"tel:{number}")
        except Exception as e:
            print(f"Error making call: {e}")
        return {'status': 'success', 'number': number}
    
    def go_back_home(self):
        """Navigate to home"""
        # Implementation depends on your UI controller
        return {'status': 'success'}


# ============================================================================
# MAIN
# ============================================================================
def main():
    print("=" * 60)
    print("INTEGRATED EYE TRACKING + WEB UI")
    print("=" * 60)
    
    # Initialize engine
    engine = EyeTrackingEngine()
    
    # Run calibration
    print("\nStarting calibration...")
    if not engine.calibrate(grid_size=7):
        print("Calibration cancelled")
        return
    
    # Start tracking
    print("\nStarting eye tracking...")
    engine.start_tracking()
    
    print("\nEye tracking active!")
    print("- Look at screen to move cursor")
    print("- Dwell on buttons to click")
    print("- Press Ctrl+C to exit")
    
    try:
        while True:
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\nStopping...")
        engine.stop_tracking()


if __name__ == "__main__":
    main()
