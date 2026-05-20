
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
            output_facial_transformation_matrixes=True,
            num_faces=1
        )
        self.detector          = vision.FaceLandmarker.create_from_options(options)
        self._buf_x            = deque(maxlen=5)
        self._buf_y            = deque(maxlen=5)
        self._use_3d           = True
        self._3d_available     = False
        self.last_transform    = None
        self._last_R           = None   # last rotation matrix for head pose delta

    def _compute_gaze(self, coords, use_3d, transform_obj=None):
        if use_3d and transform_obj is not None:
            T     = np.array(transform_obj.data, dtype=np.float32).reshape(4, 4)
            R     = T[:3, :3]
            t     = T[:3,  3]
            R_inv = R.T
            # Full 4x4 inverse: corrects both rotation AND translation.
            # After correction, take only x,y (2D projection) to avoid
            # Z-axis noise from eyelid deformation artifacts.
            def get(idx):
                if isinstance(idx, list):
                    mean_pt = coords[idx, :3].mean(axis=0)
                    return (R_inv @ (mean_pt - t))[:2]
                return (R_inv @ (coords[idx, :3] - t))[:2]
            self._last_R = R
        else:
            def get(idx):
                if isinstance(idx, list): return coords[idx, :2].mean(axis=0)
                return coords[idx, :2]
            self._last_R = None

        l_iris  = get([468, 469, 470, 471, 472])
        r_iris  = get([473, 474, 475, 476, 477])
        l_outer = get(33);  l_inner = get(133)
        r_inner = get(362); r_outer = get(263)

        l_ew = max(float(np.linalg.norm(l_outer - l_inner)), 1e-6)
        r_ew = max(float(np.linalg.norm(r_outer - r_inner)), 1e-6)

        def sdiv(n, d): return float(n) / float(d) if abs(float(d)) > 1e-6 else 0.0

        # X relative to outer canthus: maximum horizontal dynamic range
        l_rx = sdiv(l_iris[0] - l_outer[0], l_ew)
        r_rx = sdiv(r_iris[0] - r_inner[0], r_ew)

        # Y relative to inner canthus: bone-anchored, eyelid-independent
        l_ry = sdiv(l_iris[1] - l_inner[1], l_ew)
        r_ry = sdiv(r_iris[1] - r_inner[1], r_ew)

        total_w = max(l_ew + r_ew, 1e-6)
        gaze_x  = (l_rx * l_ew + r_rx * r_ew) / total_w
        gaze_y  = (l_ry * l_ew + r_ry * r_ew) / total_w
        return float(gaze_x), float(gaze_y)

    def _ear(self, xy):
        def ed(a, b): return float(np.linalg.norm(xy[a] - xy[b]))
        l = (ed(160, 144) + ed(158, 153)) / (2.0 * ed(33,  133)  + 1e-6)
        r = (ed(385, 380) + ed(387, 373)) / (2.0 * ed(362, 263) + 1e-6)
        return (l + r) / 2.0

    def process(self, frame):
        rgb    = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        result = self.detector.detect(mp_img)

        if not result.face_landmarks:
            self._buf_x.clear(); self._buf_y.clear()
            self._last_R = None
            return None, None, None

        lms    = result.face_landmarks[0]
        coords = np.array([(lm.x, lm.y, lm.z) for lm in lms])
        xy     = coords[:, :2]

        self._3d_available = False
        self.last_transform = None
        if (self._use_3d
                and result.facial_transformation_matrixes
                and len(result.facial_transformation_matrixes) > 0):
            try:
                T = np.array(
                    result.facial_transformation_matrixes[0].data,
                    dtype=np.float32).reshape(4, 4)
                self.last_transform = T
                rel_x, rel_y = self._compute_gaze(
                    coords, True, result.facial_transformation_matrixes[0])
                self._3d_available = True
            except Exception:
                rel_x, rel_y = self._compute_gaze(coords, False)
        else:
            rel_x, rel_y = self._compute_gaze(coords, False)

        self._buf_x.append(rel_x)
        self._buf_y.append(rel_y)
        rel_x = float(np.median(self._buf_x))
        rel_y = float(np.median(self._buf_y))

        return float(rel_x), float(rel_y), float(self._ear(xy))
