import cv2

class Camera:
    def __init__(self):
        self.cap = cv2.VideoCapture(0)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

    def get_frame(self):
        ret, frame = self.cap.read()
        if not ret:
            return None
        return frame

    def release(self):
        self.cap.release()


"""import cv2

class Camera:
    def __init__(self):
        self.cap = cv2.VideoCapture(0)
        #self.cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        #self.cap.set(cv2.CAP_PROP_FRAME_WIDTH,  640)
        #self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        self.cap.set(cv2.CAP_PROP_FPS, 30)
        #self.cap.set(cv2.CAP_PROP_AUTOFOCUS,    0)
        #self.cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 1)
        #self.cap.set(cv2.CAP_PROP_EXPOSURE,     -6)
        #self.cap.set(cv2.CAP_PROP_BUFFERSIZE,   1)

    def get_frame(self):
        ret, frame = self.cap.read()
        if not ret:
            return None
        return frame

    def release(self):
        self.cap.release()
"""