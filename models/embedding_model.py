import cv2
import numpy as np
from keras_facenet import FaceNet

# Load FaceNet embedder (pretrained, stable)
embedder = FaceNet()

def get_face_embedding(face_img):
    """
    Generates a 512-D FaceNet embedding
    """
    if face_img is None or face_img.size == 0:
        return None

    face_img = cv2.resize(face_img, (160, 160))
    face_img = face_img.astype("float32")

    # FaceNet expects RGB
    face_img = cv2.cvtColor(face_img, cv2.COLOR_BGR2RGB)

    embedding = embedder.embeddings([face_img])[0]
    return embedding
