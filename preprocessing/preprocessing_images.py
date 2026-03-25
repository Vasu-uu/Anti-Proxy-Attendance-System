import os
import cv2
import numpy as np
from mtcnn import MTCNN

DATASET_DIR = "dataset"
OUTPUT_DIR = "processed_dataset"

detector = MTCNN()

os.makedirs(OUTPUT_DIR, exist_ok=True)


def align_face(img, keypoints):
    # Get eye coordinates
    left_eye = keypoints.get('left_eye')
    right_eye = keypoints.get('right_eye')

    # Safety check
    if left_eye is None or right_eye is None:
        return img

    # Convert to float (IMPORTANT FIX)
    left_eye = (float(left_eye[0]), float(left_eye[1]))
    right_eye = (float(right_eye[0]), float(right_eye[1]))

    # Compute angle
    dx = right_eye[0] - left_eye[0]
    dy = right_eye[1] - left_eye[1]
    angle = np.degrees(np.arctan2(dy, dx))

    # Compute center between eyes (USE / NOT //)
    eyes_center = (
        (left_eye[0] + right_eye[0]) / 2.0,
        (left_eye[1] + right_eye[1]) / 2.0
    )

    # Rotation matrix
    M = cv2.getRotationMatrix2D(eyes_center, angle, 1.0)

    # Apply affine transform
    aligned = cv2.warpAffine(img, M, (img.shape[1], img.shape[0]))

    return aligned


def preprocess():
    for person in os.listdir(DATASET_DIR):
        person_path = os.path.join(DATASET_DIR, person)
        save_path = os.path.join(OUTPUT_DIR, person)

        if not os.path.isdir(person_path):
            continue

        os.makedirs(save_path, exist_ok=True)

        count = 0

        for img_name in os.listdir(person_path):
            if not img_name.lower().endswith(('.png', '.jpg', '.jpeg')):
                continue

            img_path = os.path.join(person_path, img_name)
            img = cv2.imread(img_path)

            if img is None:
                continue

            # Convert to RGB
            img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

            # Detect face
            results = detector.detect_faces(img_rgb)

            if len(results) == 0:
                continue

            result = results[0]
            x, y, w, h = result['box']
            keypoints = result['keypoints']

            # Align face
            aligned = align_face(img_rgb, keypoints)

            # Fix negative coordinates (IMPORTANT)
            x, y = max(0, x), max(0, y)

            face = aligned[y:y+h, x:x+w]

            if face.size == 0:
                continue

            # Resize
            face = cv2.resize(face, (112, 112))

            # Convert back to BGR for saving
            save_img = cv2.cvtColor(face, cv2.COLOR_RGB2BGR)

            save_path_img = os.path.join(save_path, f"{count}.jpg")
            cv2.imwrite(save_path_img, save_img)

            count += 1

        print(f"{person}: {count} images processed")

    print("✅ Preprocessing completed (Aligned + RGB + 112x112)")


if __name__ == "__main__":
    preprocess()