import cv2
import numpy as np

def get_face_embedding(face_img):
    """
    Generate a dummy face embedding.
    (FaceNet / CNN model will replace this later)
    """

    if face_img is None or face_img.size == 0:
        return np.zeros(128)

    # Resize face image
    face_img = cv2.resize(face_img, (160, 160))
    face_img = face_img.astype("float32") / 255.0

    # Dummy embedding (placeholder for DL model)
    embedding = np.mean(face_img, axis=(0, 1))
    embedding = np.pad(embedding, (0, 128 - embedding.shape[0]), mode='constant')

    return embedding
