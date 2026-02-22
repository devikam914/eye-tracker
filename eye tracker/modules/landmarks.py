"""
landmarks.py — v7  (root cause fix)
=====================================
ROOT CAUSE IDENTIFIED:
  iris_y relative to eyelid top/bottom is measuring EYE OPENNESS,
  not gaze direction. When eyelids open wide, top lid rises, making
  (iris_y - top_lid_y) / eyelid_height increase → cursor jumps up
  even though iris hasn't moved vertically at all.

FIX:
  Use iris Y relative to the INNER EYE CORNER (canthus), which is a
  bony landmark — it does NOT move when eyelids open/close.
  Landmark 133 (left inner canthus) and 362 (right inner canthus)
  are attached to the medial canthus tendon and are extremely stable.

  rel_y = (iris_y - inner_canthus_y) / eye_width
  
  Dividing by eye_width (horizontal) instead of eyelid_height (vertical)
  gives a stable denominator that doesn't change with blink/widening.
  The result is a value that is ONLY sensitive to actual iris vertical
  movement, not lid position.

  eye_width is ~8-12% of image width → much larger denominator than
  eyelid height (~3-4%), giving better SNR.

For X: iris relative to outer canthus / eye_width — same as before,
  this was already working correctly.
"""

import cv2
import numpy as np
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision
from collections import deque

class FaceLandmarkDetector:
    def __init__(self):
        base_options = python.BaseOptions(model_asset_path="face_landmarker.task")
        options = vision.FaceLandmarkerOptions(
            base_options=base_options,
            output_face_blendshapes=False,
            output_facial_transformation_matrixes=False,
            num_faces=1
        )
        self.detector = vision.FaceLandmarker.create_from_options(options)
        self._buf_x = deque(maxlen=3)
        self._buf_y = deque(maxlen=3)

    def process(self, frame):
        rgb    = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        result = self.detector.detect(mp_img)

        if not result.face_landmarks:
            self._buf_x.clear()
            self._buf_y.clear()
            return None, None, None

        lms    = result.face_landmarks[0]
        coords = np.array([(lm.x, lm.y, lm.z) for lm in lms])
        xy     = coords[:, :2]

        # ── Iris centers ──────────────────────────────────────────────────────
        l_iris = xy[[468, 469, 470, 471, 472]].mean(axis=0)
        r_iris = xy[[473, 474, 475, 476, 477]].mean(axis=0)

        # ── Eye corner landmarks ───────────────────────────────────────────────
        # Left eye:  outer canthus=33,  inner canthus=133
        # Right eye: inner canthus=362, outer canthus=263
        l_outer = xy[33]
        l_inner = xy[133]   # ← bony landmark, stable, does not move with lids
        r_inner = xy[362]   # ← bony landmark, stable
        r_outer = xy[263]

        # Eye widths (horizontal distance, large and stable)
        l_ew = max(abs(l_inner[0] - l_outer[0]), 1e-6)
        r_ew = max(abs(r_outer[0] - r_inner[0]), 1e-6)

        def safe_div(n, d): return n / d if abs(d) > 1e-6 else 0.0

        # ── HORIZONTAL: iris relative to outer canthus, normalised by eye width
        l_rx = safe_div(l_iris[0] - l_outer[0], l_ew)
        r_rx = safe_div(r_iris[0] - r_inner[0], r_ew)

        # ── VERTICAL: iris Y relative to INNER CANTHUS Y (lid-independent!) ──
        # Inner canthus Y is fixed to bone — unaffected by lid opening/closing.
        # Dividing by eye_width gives a consistent scale.
        # Looking down → iris_y > canthus_y → positive value increases
        # Looking up   → iris_y < canthus_y → value decreases
        l_ry = safe_div(l_iris[1] - l_inner[1], l_ew)
        r_ry = safe_div(r_iris[1] - r_inner[1], r_ew)

        # Weighted average by eye width
        total_w = max(l_ew + r_ew, 1e-6)
        rel_x   = (l_rx * l_ew + r_rx * r_ew) / total_w
        rel_y   = (l_ry * l_ew + r_ry * r_ew) / total_w

        # ── 3-frame median (spike removal only) ───────────────────────────────
        self._buf_x.append(rel_x)
        self._buf_y.append(rel_y)
        rel_x = float(np.median(self._buf_x))
        rel_y = float(np.median(self._buf_y))

        # ── EAR ───────────────────────────────────────────────────────────────
        def edist(a, b): return np.linalg.norm(xy[a] - xy[b])
        l_ear = (edist(160, 144) + edist(158, 153)) / (2.0 * edist(33, 133) + 1e-6)
        r_ear = (edist(385, 380) + edist(387, 373)) / (2.0 * edist(362, 263) + 1e-6)
        ear   = (l_ear + r_ear) / 2.0

        return float(rel_x), float(rel_y), float(ear)



