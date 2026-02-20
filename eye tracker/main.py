import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks import python
from mediapipe.tasks.python import vision

# --------- LOAD MODEL ---------
model_path = "face_landmarker.task"

BaseOptions = python.BaseOptions
FaceLandmarker = vision.FaceLandmarker
FaceLandmarkerOptions = vision.FaceLandmarkerOptions
VisionRunningMode = vision.RunningMode

options = FaceLandmarkerOptions(
    base_options=BaseOptions(model_asset_path=model_path),
    running_mode=VisionRunningMode.VIDEO,
    num_faces=1
)

landmarker = FaceLandmarker.create_from_options(options)

# --------- NORMALIZED GAZE FUNCTION ---------
def get_normalized_gaze(landmarks):

    LEFT_EYE_LEFT = 33
    LEFT_EYE_RIGHT = 133
    LEFT_EYE_TOP = 159
    LEFT_EYE_BOTTOM = 145
    LEFT_IRIS = [474, 475, 476, 477]

    left_x = landmarks[LEFT_EYE_LEFT].x
    right_x = landmarks[LEFT_EYE_RIGHT].x
    top_y = landmarks[LEFT_EYE_TOP].y
    bottom_y = landmarks[LEFT_EYE_BOTTOM].y

    iris_x = np.mean([landmarks[i].x for i in LEFT_IRIS])
    iris_y = np.mean([landmarks[i].y for i in LEFT_IRIS])

    # Make sure width/height always positive
    eye_width = abs(right_x - left_x)
    eye_height = abs(bottom_y - top_y)

    if eye_width < 1e-6 or eye_height < 1e-6:
        return None

    # Always subtract minimum corner
    min_x = min(left_x, right_x)
    min_y = min(top_y, bottom_y)

    norm_x = (iris_x - min_x) / eye_width
    norm_y = (iris_y - min_y) / eye_height

    return norm_x, norm_y


# --------- CAMERA LOOP ---------
cap = cv2.VideoCapture(0)
frame_timestamp = 0

while True:
    ret, frame = cap.read()
    if not ret:
        break

    frame = cv2.flip(frame, 1)
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
    result = landmarker.detect_for_video(mp_image, frame_timestamp)
    frame_timestamp += 1

    if result.face_landmarks:

        landmarks = result.face_landmarks[0]

        # RAW iris center
        iris = landmarks[468]
        print("RAW:", round(iris.x,3), round(iris.y,3))

        gaze = get_normalized_gaze(landmarks)

        if gaze:
            gx, gy = gaze

            # Clamp values safely between 0–1
            gx = max(0, min(1, gx))
            gy = max(0, min(1, gy))

            print("NORM:", round(gx,3), round(gy,3))

            cv2.putText(frame, f"X: {round(gx,3)}",
                        (30, 40),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        1, (0,255,0), 2)

            cv2.putText(frame, f"Y: {round(gy,3)}",
                        (30, 80),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        1, (0,255,0), 2)

    cv2.imshow("Gaze Debug", frame)

    if cv2.waitKey(1) & 0xFF == 27:
        break

cap.release()
cv2.destroyAllWindows()
