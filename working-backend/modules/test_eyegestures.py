import pyautogui
from eyeGestures.utils import VideoCapture
from eyeGestures import EyeGestures_v2

gestures = EyeGestures_v2()
cap = VideoCapture(0)
screen_w, screen_h = pyautogui.size()
calibrate = True

while True:
    ret, frame = cap.read()
    event, cevent = gestures.step(frame, calibrate, screen_w, screen_h)
    if event:
        pyautogui.moveTo(event.point[0], event.point[1])