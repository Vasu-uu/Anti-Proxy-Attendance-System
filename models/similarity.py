import numpy as np

def cosine_similarity(vec1, vec2):
    """
    Compute cosine similarity between two vectors
    """
    if np.linalg.norm(vec1) == 0 or np.linalg.norm(vec2) == 0:
        return 0.0

    similarity = np.dot(vec1, vec2) / (
        np.linalg.norm(vec1) * np.linalg.norm(vec2)
    )
    return similarity
