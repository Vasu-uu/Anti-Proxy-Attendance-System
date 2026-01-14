import sys
import os

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

import cv2
from detection.face_detector import detect_faces
from models.embedding_model import get_face_embedding
from models.similarity import cosine_similarity


def main():
    print("[INFO] Starting Anti-Proxy Attendance System", flush=True)

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("[ERROR] Cannot access camera")
        return

    print("[INFO] Camera started. Press 'q' to exit.", flush=True)

    while True:
        ret, frame = cap.read()
        if not ret:
            print("[ERROR] Frame not received")
            break

        faces = detect_faces(frame)

        for (x, y, w, h) in faces:
            face_img = frame[y:y+h, x:x+w]
            embedding = get_face_embedding(face_img)

            score = cosine_similarity(embedding, embedding)
            print(f"[DEBUG] Similarity Score: {score:.2f}")

            cv2.rectangle(frame, (x, y), (x+w, y+h), (0, 255, 0), 2)

        cv2.imshow("Anti-Proxy Attendance System", frame)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()
    print("[INFO] System stopped", flush=True)


if __name__ == "__main__":
    main()
