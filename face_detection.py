from flask import Flask, Response
import cv2
import time
import os

app = Flask(__name__)

# Updated cascade_path
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

def generate_frames():
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

        # Draw rectangles around detected faces
        for (x, y, w, h) in faces:
            cv2.rectangle(frame, (x, y), (x+w, y+h), (255, 0, 0), 2)

        # Encode the frame as JPEG
        ret, buffer = cv2.imencode('.jpg', frame)
        frame = buffer.tobytes()

        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

@app.route('/')
def index():
    return """
    <html>
    <head>
        <title>Face Detection Stream</title>
    </head>
    <body>
        <h1>Face Detection Stream</h1>
        <img src="/video_feed" width="640" height="480" />
    </body>
    </html>
    """

@app.route('/video_feed')
def video_feed():
    return Response(generate_frames(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
