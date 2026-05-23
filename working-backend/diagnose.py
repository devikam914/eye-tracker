# -*- coding: utf-8 -*-
"""
Quick diagnostic: check camera mirroring, resolution, and gaze behavior.
Press ESC to quit.
"""
import cv2
import numpy as np
from modules.ptgaze_detector import PTGazeDetector

print("Initialising...")
detector = PTGazeDetector()
cap = cv2.VideoCapture(0)
if not cap.isOpened():
    print("ERROR: Camera not detected"); exit()

w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
fps = cap.get(cv2.CAP_PROP_FPS)
print(f"Camera: {w}x{h} @ {fps}fps")

FONT = cv2.FONT_HERSHEY_SIMPLEX
history = []

print("\n=== DIAGNOSTIC MODE ===")
print("1. Hold up text/phone with text - check if it appears MIRRORED")
print("2. Look at corners of screen - watch gaze values")
print("3. Press SPACE to log current gaze to console")
print("4. Press ESC to exit")
print()

while True:
    ret, frame = cap.read()
    if not ret: continue

    gx, gy, ear = detector.process(frame)

    key = cv2.waitKey(1) & 0xFF
    if key == 27: break

    display = frame.copy()

    if gx is not None:
        label = f"gx={gx:+.4f}  gy={gy:+.4f}"
        cv2.putText(display, label, (10, 28), FONT, 0.6, (0, 220, 80), 2)

        # Direction indicators
        if gx > 0.05:
            cv2.putText(display, "Looking LEFT (your left)", (10, 55), FONT, 0.5, (255, 200, 0), 1)
        elif gx < -0.05:
            cv2.putText(display, "Looking RIGHT (your right)", (10, 55), FONT, 0.5, (255, 200, 0), 1)

        if gy > 0.05:
            cv2.putText(display, "Looking DOWN", (10, 75), FONT, 0.5, (255, 200, 0), 1)
        elif gy < -0.05:
            cv2.putText(display, "Looking UP", (10, 75), FONT, 0.5, (255, 200, 0), 1)

        # Track last 60 values for range
        history.append([gx, gy])
        if len(history) > 300:
            history.pop(0)

        if len(history) > 10:
            h_arr = np.array(history)
            x_range = f"gx range: [{h_arr[:,0].min():+.3f} to {h_arr[:,0].max():+.3f}]"
            y_range = f"gy range: [{h_arr[:,1].min():+.3f} to {h_arr[:,1].max():+.3f}]"
            cv2.putText(display, x_range, (10, h - 35), FONT, 0.45, (150, 150, 255), 1)
            cv2.putText(display, y_range, (10, h - 15), FONT, 0.45, (150, 150, 255), 1)

        if key == 32:  # SPACE
            print(f"  gx={gx:+.4f}  gy={gy:+.4f}")
    else:
        cv2.putText(display, "No face detected", (10, 28), FONT, 0.6, (0, 0, 255), 2)

    # Camera info
    cv2.putText(display, f"{w}x{h}", (w - 80, 20), FONT, 0.4, (100, 100, 100), 1)

    # Flip test overlay
    cv2.putText(display, "MIRROR TEST: Is this text backwards?", (10, h - 60),
                FONT, 0.5, (0, 200, 255), 1)

    cv2.imshow("Gaze Diagnostic", display)

cap.release()
cv2.destroyAllWindows()

if history:
    h_arr = np.array(history)
    print(f"\n=== Session Summary ===")
    print(f"Total frames: {len(history)}")
    print(f"gx: min={h_arr[:,0].min():+.4f}  max={h_arr[:,0].max():+.4f}  span={h_arr[:,0].max()-h_arr[:,0].min():.4f}")
    print(f"gy: min={h_arr[:,1].min():+.4f}  max={h_arr[:,1].max():+.4f}  span={h_arr[:,1].max()-h_arr[:,1].min():.4f}")
    print(f"\nKey check:")
    print(f"  When you look LEFT,  does gx go POSITIVE?  (needed for flip_x)")
    print(f"  When you look RIGHT, does gx go NEGATIVE?  (needed for flip_x)")
    print(f"  When you look DOWN,  does gy go POSITIVE?")
    print(f"  When you look UP,    does gy go NEGATIVE?")
