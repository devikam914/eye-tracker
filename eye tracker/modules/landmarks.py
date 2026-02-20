import cv2
import numpy as np
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision


class FaceLandmarkDetector:
    def __init__(self):
        base_options = python.BaseOptions(
            model_asset_path="face_landmarker.task"
        )

        options = vision.FaceLandmarkerOptions(
            base_options=base_options,
            output_face_blendshapes=False,
            output_facial_transformation_matrixes=False,
            num_faces=1
        )

        self.detector = vision.FaceLandmarker.create_from_options(options)

    def process(self, frame):
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        mp_image = mp.Image(
            image_format=mp.ImageFormat.SRGB,
            data=rgb_frame
        )

        result = self.detector.detect(mp_image)

        if not result.face_landmarks:
            return None, None, None

        landmarks = result.face_landmarks[0]

        # Convert to numpy
        coords = np.array([(lm.x, lm.y) for lm in landmarks])

        # ---- LEFT IRIS ----
        left_iris_indices = [468, 469, 470, 471, 472]
        left_points = coords[left_iris_indices]
        left_iris_x = np.mean(left_points[:, 0])
        left_iris_y = np.mean(left_points[:, 1])

        # ---- RIGHT IRIS ----
        right_iris_indices = [473, 474, 475, 476, 477]
        right_points = coords[right_iris_indices]
        right_iris_x = np.mean(right_points[:, 0])
        right_iris_y = np.mean(right_points[:, 1])

        # ---- Eye corners ----
        left_eye_left = coords[33]
        left_eye_right = coords[133]
        left_eye_top = coords[159]
        left_eye_bottom = coords[145]

        right_eye_left = coords[362]
        right_eye_right = coords[263]
        right_eye_top = coords[386]
        right_eye_bottom = coords[374]

        # ---- Relative positions ----
        left_relative_x = (left_iris_x - left_eye_left[0]) / (left_eye_right[0] - left_eye_left[0])
        left_relative_y = (left_iris_y - left_eye_top[1]) / (left_eye_bottom[1] - left_eye_top[1])

        right_relative_x = (right_iris_x - right_eye_left[0]) / (right_eye_right[0] - right_eye_left[0])
        right_relative_y = (right_iris_y - right_eye_top[1]) / (right_eye_bottom[1] - right_eye_top[1])

        relative_x = (left_relative_x + right_relative_x) / 2
        relative_y = (left_relative_y + right_relative_y) / 2

        relative_x = max(0, min(1, relative_x))
        relative_y = max(0, min(1, relative_y))

        # ---- EAR ----
        def euclidean(p1, p2):
            return np.linalg.norm(coords[p1] - coords[p2])

        left_ear = (
            euclidean(160, 144) + euclidean(158, 153)
        ) / (2.0 * euclidean(33, 133))

        right_ear = (
            euclidean(385, 380) + euclidean(387, 373)
        ) / (2.0 * euclidean(362, 263))

        ear = (left_ear + right_ear) / 2

        return relative_x, relative_y, ear
