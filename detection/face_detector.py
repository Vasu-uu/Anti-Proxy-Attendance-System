import os
from ultralytics import YOLO

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Use either face model OR official model
MODEL_PATH = os.path.join(BASE_DIR, "saved_models", "yolov8n-face.pt")
# If you want official fallback, comment above & use:
# model = YOLO("yolov8n.pt")

model = YOLO(MODEL_PATH)

def detect_faces(frame):
    results = model(frame, conf=0.5, verbose=False)
    boxes_out = []

    for result in results:
        for box in result.boxes:
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            boxes_out.append((x1, y1, x2, y2))

    return boxes_out
