import cv2
import numpy as np
from PyQt5.QtCore import QThread, pyqtSignal


def get_circles(img):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    img_blur = cv2.medianBlur(gray, 5)

    circles = cv2.HoughCircles(img_blur,
                               cv2.HOUGH_GRADIENT,
                               1,
                               img.shape[0] / 20,
                               param1=30,
                               param2=10,
                               minRadius=10,
                               maxRadius=15
                               )

    # Draw detected circles
    if circles is not None:
        circles = np.uint16(np.around(circles))
        for i in circles[0, :96]:
            # outer circle
            # cv2.circle(image, center_coordinates, radius, color, thickness)
            cv2.circle(img, (i[0], i[1]), i[2], (0, 0, 0), 2)

            # inner circle
            cv2.circle(img, (i[0], i[1]), 1, (0, 0, 255), 2)

    return img


class VideoThread(QThread):
    change_pixmap_signal = pyqtSignal(np.ndarray)

    bath_temp_text = '-'
    setpoint_temp_text = '-'
    ADAMCH0_temp_text = '-'
    ADAMCH1_temp_text = '-'

    detect_circles = False

    def __init__(self):
        super().__init__()
        self._run_flag = True

    def run(self):
        # capture from webcam
        cap = cv2.VideoCapture(2)

        while self._run_flag:
            ret, cv_img = cap.read()

            if ret:
                cv2.putText(cv_img, f"     Bath temp: {self.bath_temp_text}",
                            (50, 50), cv2.FONT_HERSHEY_PLAIN, 1, (0, 255, 0), 1)
                cv2.putText(cv_img, f" Setpoint temp: {self.setpoint_temp_text}",
                            (50, 70), cv2.FONT_HERSHEY_PLAIN, 1, (0, 255, 0), 1)
                cv2.putText(cv_img, f"ADAM CH1 temp: {self.ADAMCH0_temp_text}",
                            (50, 90), cv2.FONT_HERSHEY_PLAIN, 1, (0, 255, 0), 1)
                cv2.putText(cv_img, f"ADAM CH2 temp: {self.ADAMCH1_temp_text}",
                            (50, 110), cv2.FONT_HERSHEY_PLAIN, 1, (0, 255, 0), 1)

                if get_circles:
                    cv_img = get_circles(cv_img)

                self.change_pixmap_signal.emit(cv_img)

        # shut down capture system
        cap.release()

    def stop(self):
        """Sets run flag to False and waits for thread to finish"""
        self._run_flag = False
        self.wait()
