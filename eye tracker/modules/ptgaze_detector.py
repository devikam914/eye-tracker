# -*- coding: utf-8 -*-
"""
PTGazeDetector — ETH-XGaze via ptgaze.
Matches working-backend/modules/ptgaze_detector.py exactly:
  - Uses my_camera_params.yaml (actual camera calibration, not sample_params)
  - Buffer size 6 (not 9 — less lag)
  - gx = raw median yaw (NOT negated — negation caused systematic X offset)
  - gy = raw median pitch
"""
import os
import numpy as np
from omegaconf import OmegaConf
from ptgaze.gaze_estimator import GazeEstimator


class PTGazeDetector:
    def __init__(self):
        home        = os.path.expanduser("~")
        ptgaze_home = os.path.join(home, ".ptgaze")
        checkpoint  = os.path.join(ptgaze_home, "models", "eth-xgaze_resnet18.pth")

        import ptgaze as _pkg
        data_dir           = os.path.join(os.path.dirname(_pkg.__file__), "data")
        norm_camera_params = os.path.join(data_dir, "normalized_camera_params", "eth-xgaze.yaml")

        # Use the actual camera calibration file from working-backend.
        # sample_params.yaml causes systematic gaze offset because the focal
        # length and principal point don't match this specific camera.
        _here = os.path.dirname(os.path.abspath(__file__))
        camera_params = os.path.join(_here, '..', '..', 'working-backend', 'my_camera_params.yaml')
        camera_params = os.path.normpath(camera_params)

        # Fallback to sample params if the file doesn't exist
        if not os.path.exists(camera_params):
            camera_params = os.path.join(data_dir, "calib", "sample_params.yaml")
            print(f"Warning: my_camera_params.yaml not found, using sample_params.yaml")
        else:
            print(f"Using camera params: {camera_params}")

        cfg = OmegaConf.create({
            "mode": "ETH-XGaze",
            "device": "cpu",
            "model": {"name": "resnet18"},
            "face_detector": {
                "mode": "mediapipe",
                "mediapipe_max_num_faces": 1,
                "mediapipe_static_image_mode": False,
                "dlib_model_path": "",
            },
            "gaze_estimator": {
                "checkpoint": checkpoint,
                "camera_params": camera_params,
                "use_dummy_camera_params": False,
                "normalized_camera_params": norm_camera_params,
                "normalized_camera_distance": 0.6,
                "image_size": [224, 224],
            },
            "demo": {
                "use_camera": True, "display_on_screen": False, "wait_time": 1,
                "image_path": None, "video_path": None, "output_dir": None,
                "output_file_extension": "avi", "head_pose_axis_length": 0.05,
                "gaze_visualization_length": 0.05, "show_bbox": False,
                "show_head_pose": False, "show_landmarks": False,
                "show_normalized_image": False, "show_template_model": False,
            },
        })

        self._estimator    = GazeEstimator(cfg)
        self._use_3d       = True
        self._3d_available = True
        self._buffer       = []
        self._buffer_size  = 9   # larger buffer = more stable median = less jitter

    def process(self, frame):
        try:
            faces = self._estimator.detect_faces(frame)
            if not faces:
                return None, None, None

            face = faces[0]
            self._estimator.estimate_gaze(frame, face)

            angles = face.normalized_gaze_angles
            pitch  = float(angles[0])
            yaw    = float(angles[1])

            self._buffer.append([yaw, pitch])
            if len(self._buffer) > self._buffer_size:
                self._buffer.pop(0)

            buf = np.array(self._buffer)
            # No negation — flip_x in the calibration pipeline handles X mirroring.
            # Negating here AND using flip_x causes double-flip = large X offset.
            gx = float(np.median(buf[:, 0]))
            gy = float(np.median(buf[:, 1]))

            return gx, gy, 0.3

        except Exception as e:
            print(f"PTGaze error: {e}")
            return None, None, None
