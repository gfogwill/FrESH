import cv2
import numpy as np
import pathlib
import os

def sort_circles(circles):
        # https://stackoverflow.com/questions/61741434/opencv-sorting-array-of-circles
        circles = np.round(circles).astype("int")
        circles = sorted(circles, key=lambda v: [v[1], v[0]])

        NUM_COLS = 5

        sorted_rows = []
        for k in range(0, len(circles), NUM_COLS):
            row = circles[k:k+NUM_COLS]
            sorted_rows.extend(sorted(row, key=lambda v: v[0]))

        return sorted_rows

        
def plot_detected_circles(img, circles):
    # Draw detected circles
    if circles is not None:
        circles = np.uint16(np.around(circles))

        for n, i in enumerate(circles):

            # outer circle
            ## cv2.circle(image, center_coordinates, radius, color, thickness)
            cv2.circle(img, (i[0], i[1]), i[2], (0, 0, 0), 1)

            # inner circle
            cv2.circle(img, (i[0], i[1]), 1, (0, 0, 255), 2)

            cv2.putText(img, "{}".format(n + 1), (i[0], i[1]), cv2.FONT_HERSHEY_PLAIN, 1.0, (255, 255, 255), 1)
    
    
    cv2.imshow('Image',img)
    cv2.waitKey(0)
    cv2.destroyAllWindows()

    
def get_grayscales(image, circles, mask=True):
    grayscales = []
    
    for circle in circles[:25]:
        x = circle[0]
        y = circle[1]
        r = circle[2]

        img = image[y-r:y+r,x-r:x+r]

        if mask:
            # create a mask
            ## https://stackoverflow.com/questions/50697179/opencv-and-python-how-croped-circle-area-only

            m = np.full((img.shape[0], img.shape[1]), 0, dtype=np.uint8) 
            # create circle mask, center, radius, fill color, size of the border
            cv2.circle(m,(r,r), r, (255,255,255),-1)
            # get only the inside pixels
            fg = cv2.bitwise_or(img, img, mask=m)

            m = cv2.bitwise_not(m)
            background = np.full(img.shape, 255, dtype=np.uint8)
            bk = cv2.bitwise_or(background, background, mask=m)
            img = cv2.bitwise_or(fg, bk)
        
        
        grayscales.append(img.mean())
        
    return grayscales

    
def get_circles(img, minDist=20, param1=60, param2=10, minRadius=10, maxRadius=13, sort=True, plot=True, mask=True):
    # gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    # img_blur = cv2.medianBlur(gray, 5)

    # https://docs.opencv.org/4.x/dd/d1a/group__imgproc__feature.html#ga47849c3be0d0406ad3ca45db65a25d2d
    circles = cv2.HoughCircles(img,
                               cv2.HOUGH_GRADIENT,
                               1,
                               minDist=minDist,
                               param1=param1,
                               param2=param2,
                               minRadius=minRadius,
                               maxRadius=maxRadius
                              )[0]

    if sort:
        circles = sort_circles(circles)


    if plot:
        plot_detected_circles(img, circles)

        
    return circles
