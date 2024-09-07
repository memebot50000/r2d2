import cv2
import time
import os

# Specify the path to the Haar Cascade XML file
cascade_path = "/usr/share/opencv4/haarcascades/haarcascade_frontalface_default.xml"


# Check if the file exists
if not os.path.isfile(cascade_path):
    print(f"Error: Cascade file not found at {cascade_path}")
    print("Please install OpenCV with pre-trained cascades or specify the correct path.")
    exit()

# Load the pre-trained face detection classifier
face_cascade = cv2.CascadeClassifier(cascade_path)

# Initialize the camera
camera = cv2.VideoCapture(0)  # 0 is usually the default camera

# Check if the camera opened successfully
if not camera.isOpened():
    print("Error: Could not open camera.")
    exit()

print("Camera initialized. Press 'q' to quit.")

while True:
    # Capture frame-by-frame
    ret, frame = camera.read()

    if not ret:
        print("Error: Failed to capture frame.")
        break

    # Convert the frame to grayscale (face detection works on grayscale images)
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    # Detect faces
    faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))

    # If faces are found, print "face recognized"
    if len(faces) > 0:
        print("Face recognized")

    # Display the resulting frame (optional, remove if running headless)
    cv2.imshow('Frame', frame)

    # Break the loop if 'q' is pressed
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

    # Small delay to prevent excessive CPU usage
    time.sleep(0.1)

# Release the camera and close windows
camera.release()
cv2.destroyAllWindows()
