import cv2
import numpy as np
from gpiozero import Motor

# Motor setup
right_motor = Motor(forward=27, backward=17, enable=12)
left_motor = Motor(forward=22, backward=23, enable=13)

# Camera setup
cap = cv2.VideoCapture(0)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

# ArUco dictionary setup (use a 4x4 dictionary for faster processing)
aruco_dict = cv2.aruco.Dictionary_get(cv2.aruco.DICT_4X4_50)
parameters = cv2.aruco.DetectorParameters_create()

# Constants
MARKER_SIZE = 10.0  # Size of the AR tag in cm
DEAD_ZONE = 0.2
MAX_SPEED = 1.0

def apply_dead_zone(value, dead_zone):
    if abs(value) < dead_zone:
        return 0
    return (value - dead_zone * (1 if value > 0 else -1)) / (1 - dead_zone)

def control_motors(throttle, steering):
    throttle = apply_dead_zone(throttle, DEAD_ZONE)
    steering = apply_dead_zone(steering, DEAD_ZONE)

    left_speed = throttle + steering
    right_speed = throttle - steering

    left_speed = max(-1, min(1, left_speed))
    right_speed = max(-1, min(1, right_speed))

    left_motor.value = left_speed
    right_motor.value = right_speed

    print(f"Left: {left_speed:.2f}, Right: {right_speed:.2f}")

def stop():
    left_motor.stop()
    right_motor.stop()

# Camera matrix and distortion coefficients (you need to calibrate your camera to get these)
camera_matrix = np.array([[fx, 0, cx],
                          [0, fy, cy],
                          [0, 0, 1]], dtype=np.float32)
dist_coeffs = np.array([k1, k2, p1, p2, k3], dtype=np.float32)

try:
    while True:
        ret, frame = cap.read()
        if not ret:
            break

        # Flip the frame vertically
        frame = cv2.flip(frame, 0)

        # Convert to grayscale for faster processing
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        # Detect ArUco markers
        corners, ids, rejected = cv2.aruco.detectMarkers(gray, aruco_dict, parameters=parameters)

        if ids is not None and 0 in ids:  # Assuming we're looking for marker with ID 0
            # Draw detected markers
            cv2.aruco.drawDetectedMarkers(frame, corners, ids)

            # Get the pose of the marker
            rvecs, tvecs, _ = cv2.aruco.estimatePoseSingleMarkers(corners, MARKER_SIZE, camera_matrix, dist_coeffs)

            # Draw axis for the marker
            cv2.aruco.drawAxis(frame, camera_matrix, dist_coeffs, rvecs[0], tvecs[0], 5)

            # Calculate steering and throttle based on marker position
            marker_center = np.mean(corners[0][0], axis=0)
            frame_center = frame.shape[1] / 2
            frame_bottom = frame.shape[0]

            steering = (marker_center[0] - frame_center) / (frame_center / 2)  # Range: -1 to 1
            distance = tvecs[0][0][2]  # Z-distance from camera to marker
            throttle = (distance - 30) / 30  # Adjust these values based on your needs

            # Normalize and apply max speed
            steering = np.clip(steering, -1, 1) * MAX_SPEED
            throttle = np.clip(throttle, -1, 1) * MAX_SPEED

            control_motors(throttle, steering)
        else:
            stop()

        cv2.imshow('Frame', frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

finally:
    cap.release()
    cv2.destroyAllWindows()
    stop()
