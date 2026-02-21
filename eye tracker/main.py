import cv2
from modules.landmarks import FaceLandmarkDetector

# Initialize detector
detector = FaceLandmarkDetector()

# Open webcam
cap = cv2.VideoCapture(0)

# ---- Exponential Smoothing Setup ----
alpha = 0.2   # 0.1–0.3 recommended
smooth_x = None
smooth_y = None

while True:
    ret, frame = cap.read()
    if not ret:
        break

    x, y, ear = detector.process(frame)

    if x is not None:

        # ---- Apply Exponential Smoothing ----
        if smooth_x is None:
            smooth_x = x
            smooth_y = y
        else:
            smooth_x = alpha * x + (1 - alpha) * smooth_x
            smooth_y = alpha * y + (1 - alpha) * smooth_y

        # ---- Print Smoothed Values ----
        print(f"X: {smooth_x:.2f} | Y: {smooth_y:.2f} | EAR: {ear:.2f}")

        # ---- Display on Screen ----
        cv2.putText(frame, f"X: {smooth_x:.2f}", (30, 40),
                    cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)

        cv2.putText(frame, f"Y: {smooth_y:.2f}", (30, 80),
                    cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)

        cv2.putText(frame, f"EAR: {ear:.2f}", (30, 120),
                    cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)

    cv2.imshow("Eye Tracking", frame)

    # Press ESC to exit
    if cv2.waitKey(1) & 0xFF == 27:
        break

cap.release()
cv2.destroyAllWindows()