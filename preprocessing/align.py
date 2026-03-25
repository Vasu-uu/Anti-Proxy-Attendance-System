import cv2
import numpy as np
import warnings
warnings.filterwarnings("ignore")

try:
    from mtcnn import MTCNN
    detector = MTCNN()
except ImportError:
    detector = None
    print("WARNING: MTCNN not installed. Facial alignment will be bypassed.")

def align_face_image(img, keypoints):
    """
    Given an RGB image and MTCNN keypoints, calculates the rotation angle 
    between the left and right eye, and applies an affine transformation 
    to output an aligned, level image.
    """
    left_eye = keypoints.get('left_eye')
    right_eye = keypoints.get('right_eye')

    if left_eye is None or right_eye is None:
        return img

    left_eye = (float(left_eye[0]), float(left_eye[1]))
    right_eye = (float(right_eye[0]), float(right_eye[1]))

    dx = right_eye[0] - left_eye[0]
    dy = right_eye[1] - left_eye[1]
    angle = np.degrees(np.arctan2(dy, dx))

    eyes_center = (
        (left_eye[0] + right_eye[0]) / 2.0,
        (left_eye[1] + right_eye[1]) / 2.0
    )

    M = cv2.getRotationMatrix2D(eyes_center, angle, 1.0)
    aligned = cv2.warpAffine(img, M, (img.shape[1], img.shape[0]))

    return aligned

def detect_and_align_faces(frame_bgr):
    """
    Takes a standard OpenCV BGR frame, detects all faces using MTCNN,
    aligns them via Affine Transforms (leveling the eyes), crops the faces, 
    resizes to (112, 112), and returns a list of preprocessed BGR face crops 
    ready for embedding models.
    """
    if detector is None:
        return []
        
    img_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
    results = detector.detect_faces(img_rgb)
    
    aligned_faces = []
    
    for result in results:
        x, y, w, h = result['box']
        keypoints = result['keypoints']
        
        # Rigorous Alignment
        aligned_rgb = align_face_image(img_rgb, keypoints)
        
        # Ensure bounds
        x, y = max(0, x), max(0, y)
        face_crop = aligned_rgb[y:y+h, x:x+w]
        
        if face_crop.size == 0:
            continue
            
        # Standardize output size (FaceNet typically eats 160x160, but 112x112 is fine if model supports it)
        # We will resize to what the model expects, usually FaceNet automatically resizes interally.
        # But we resize to 160x160 to be safe for keras-facenet
        face_crop = cv2.resize(face_crop, (160, 160)) 
        
        face_bgr = cv2.cvtColor(face_crop, cv2.COLOR_RGB2BGR)
        aligned_faces.append(face_bgr)
        
    return aligned_faces
