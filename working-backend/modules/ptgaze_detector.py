import cv2
import numpy as np
from omegaconf import OmegaConf
from ptgaze.gaze_estimator import GazeEstimator

class PTGazeDetector:
    """
    Drop-in replacement for FaceLandmarkDetector.
    Uses ETH-XGaze via ptgaze for gaze estimation.
    Returns (gx, gy, ear) — same interface as your existing detector.
    """
    def __init__(self):
        cfg = OmegaConf.create({
            "mode": "ETH-XGaze",
            "device": "cpu",
            "model": {"name": "resnet18"},
            "face_detector": {
                "mode": "mediapipe",
                "mediapipe_max_num_faces": 1,
                "mediapipe_static_image_mode": False,
                "dlib_model_path": "C:/Users/AISWARYA S/.ptgaze/dlib/shape_predictor_68_face_landmarks.dat"
            },
            "gaze_estimator": {
                "checkpoint": "C:/Users/AISWARYA S/.ptgaze/models/eth-xgaze_resnet18.pth",
                "camera_params": "C:/Users/AISWARYA S/OneDrive/Desktop/gazetrack/aisu-test/working-backend/my_camera_params.yaml",
                "use_dummy_camera_params": False,
                "normalized_camera_params": "C:/Users/AISWARYA S/eye-tracker/eye tracker/.venv/Lib/site-packages/ptgaze/data/normalized_camera_params/eth-xgaze.yaml",
                "normalized_camera_distance": 0.6,
                "image_size": [224, 224]
            },
            "demo": {
                "use_camera": True,
                "display_on_screen": False,
                "wait_time": 1,
                "image_path": None,
                "video_path": None,
                "output_dir": None,
                "output_file_extension": "avi",
                "head_pose_axis_length": 0.05,
                "gaze_visualization_length": 0.05,
                "show_bbox": False,
                "show_head_pose": False,
                "show_landmarks": False,
                "show_normalized_image": False,
                "show_template_model": False
            }
        })
        self._estimator = GazeEstimator(cfg)
        self._use_3d = True
        self._3d_available = True
        self._buffer = []
        self._buffer_size = 6
   
       

    def process(self, frame):
        try:
            faces = self._estimator.detect_faces(frame)
            if not faces:
                return None, None, None

            face = faces[0]
            self._estimator.estimate_gaze(frame, face)

            angles = face.normalized_gaze_angles
            pitch = float(angles[0])
            yaw   = float(angles[1])

            # 5-frame median buffer to reduce jitter
            self._buffer.append([yaw, pitch])
            if len(self._buffer) > self._buffer_size:
                self._buffer.pop(0)
            
            buf = np.array(self._buffer)
            gx = float(np.median(buf[:, 0]))
            gy = float(np.median(buf[:, 1]))
            ear = 0.3

            return gx, gy, ear

        except Exception as e:
            print(f"PTGaze error: {e}")
            return None, None, None