import logging

import cv2
import numpy as np
import pathlib
import os
import random

from src import paths


def rotate_image(image, angle):
    # Get the image dimensions (height and width)
    (h, w) = image.shape[:2]

    # Calculate the center of the image
    center = (w // 2, h // 2)

    # Perform the rotation
    M = cv2.getRotationMatrix2D(center, angle, 1.0)
    rotated = cv2.warpAffine(image, M, (w, h))

    return rotated

# def rotate_image(image, angle):
#
#     # Rotate the image by the specified angle
#     center = tuple(np.array(image.shape[1::-1]) / 2)
#     rot_mat = cv2.getRotationMatrix2D(center, angle, 1.0)
#     rotated_img = cv2.warpAffine(image, rot_mat, image.shape[1::-1], flags=cv2.INTER_LINEAR)
#
#     return rotated_img


def auto_crop(img, template_img_path, rotation_angles=[0]):
    # Load the template image
    template_image = cv2.imread(str(paths.etc_path / template_img_path))

    # Get the height and width of the template image
    template_height, template_width = template_image.shape[:2]

    # Initialize variables to keep track of the best match and angle
    best_match = None

    for angle in rotation_angles:
        rotated_img = rotate_image(img, angle)

        # Check if the rotated image is larger than the template
        if rotated_img.shape[0] >= template_height and rotated_img.shape[1] >= template_width:
            match_result = cv2.matchTemplate(rotated_img, template_image, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(match_result)

            if best_match is None or max_val > best_match[0]:
                best_match = (max_val, max_loc, angle)

    # If no valid match is found, return the original image
    if best_match is None:
        print("No valid match found. Returning the original image.")
        return img

    # Get the location of the best match
    _, max_loc, best_angle = best_match

    # Calculate the top-left and bottom-right coordinates of the ROI
    top_left = max_loc
    bottom_right = (top_left[0] + template_width, top_left[1] + template_height)

    # Ensure that the cropping coordinates are within the bounds of the image
    bottom_right = (min(bottom_right[0], img.shape[1]), min(bottom_right[1], img.shape[0]))

    # Crop the image
    cropped_img = img[top_left[1]:bottom_right[1], top_left[0]:bottom_right[0]]

    # Rotate the cropped image back to the best angle
    cropped_img = rotate_image(cropped_img, -best_angle)

    return cropped_img





def sort_circles(circles, n_cols):
    """
    Sorts an array of circles according to their positions.

    Circles are first sorted by their row position (y-coordinate), then by their column position (x-coordinate)
    within each row. Rows are divided into groups of `NUM_COLS` circles.

    Parameters
    ----------
    circles : numpy.ndarray
        Array of circles, where each circle is represented as a 1D array of 3 values [x, y, radius].
    n_cols : int
        Number of circles in each row.

    Returns
    -------
    sorted_circles : numpy.ndarray
        Sorted array of circles.

    """
    # Round the circles to integer values and sort them by their y-coordinate
    circles = np.round(circles).astype("int")
    circles = sorted(circles, key=lambda v: [v[1], v[0]])

    # Divide the sorted circles into rows of NUM_COLS circles each
    sorted_rows = []
    for k in range(0, len(circles), n_cols):
        row = circles[k:k + n_cols]
        sorted_rows.extend(sorted(row, key=lambda v: v[0]))

    # Convert the sorted rows back to a numpy array
    sorted_circles = np.array(sorted_rows)

    return sorted_circles


def plot_detected_circles(img, circles):
    # Draw detected circles
    if circles is not None:
        circles = np.uint16(np.around(circles))

        for n, i in enumerate(circles):
            # outer circle
            # cv2.circle(image, center_coordinates, radius, color, thickness)
            cv2.circle(img, (i[0], i[1]), i[2], (0, 255, 0), 2)

            # inner circle
            cv2.circle(img, (i[0], i[1]), 1, (0, 0, 255), 2)

            cv2.putText(img, "{}".format(n + 1), (i[0], i[1]), cv2.FONT_HERSHEY_PLAIN, 1.0, (255, 255, 255), 1)


def add_circles(img, circles):
    # Draw detected circles
    if circles is not None:
        circles = np.uint16(np.around(circles))

        for n, i in enumerate(circles):
            # outer circle
            # cv2.circle(image, center_coordinates, radius, color, thickness)
            cv2.circle(img, (i[0], i[1]), i[2], (0, 255, 0), 1)

            cv2.putText(img, "{}".format(n + 1), (i[0], i[1]), cv2.FONT_HERSHEY_PLAIN, 1.0, (255, 0, 0), 1)

    return img


def get_grayscales(image, circles, mask=True):
    grayscales = []
    i = 0
    
    background_greyscale = image.mean()

    for circle in circles:  # [:95]:
        x = circle[0]
        y = circle[1]
        r = circle[2] - 5

        img = image[y - r:y + r, x - r:x + r]
        i += 1

        if mask:
            # create a mask
            # https://stackoverflow.com/questions/50697179/opencv-and-python-how-croped-circle-area-only

            m = np.full((img.shape[0], img.shape[1]), 0, dtype=np.uint8)
            # create circle mask, center, radius, fill color, size of the border
            cv2.circle(m, (r, r), r, (255, 255, 255), -1)
            # get only the inside pixels
            fg = cv2.bitwise_or(img, img, mask=m)

            m = cv2.bitwise_not(m)
            background = np.full(img.shape, 255, dtype=np.uint8)
            bk = cv2.bitwise_or(background, background, mask=m)
            img = cv2.bitwise_or(fg, bk)
            
        circle_greyscale = img.mean()
        grayscales.append(circle_greyscale - (background_greyscale))

    return grayscales


def get_circles(img, min_distance=40, param1=150, param2=10, min_radius=19, max_radius=22, sort=True, plot=True):
    # https://docs.opencv.org/4.x/dd/d1a/group__imgproc__feature.html#ga47849c3be0d0406ad3ca45db65a25d2d

    # while n_circs != 96:
    circles = cv2.HoughCircles(img,
                               cv2.HOUGH_GRADIENT,
                               1,
                               minDist=min_distance,
                               param1=param1,  # + random.randint(-30, 30)
                               param2=param2,  # + random.randint(-10, 10)§
                               minRadius=min_radius,
                               maxRadius=max_radius
                               )[0]

    # n_circs = circles.shape[0]

    if sort:
        circles = sort_circles(circles, n_cols=12)

    if plot:
        plot_detected_circles(img, circles)

    return circles
