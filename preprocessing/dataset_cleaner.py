import os
import cv2

DATASET_DIR = "dataset"

def clean_dataset():
    for person in os.listdir(DATASET_DIR):
        person_path = os.path.join(DATASET_DIR, person)

        if not os.path.isdir(person_path):
            continue

        removed = 0

        for img_name in os.listdir(person_path):
            img_path = os.path.join(person_path, img_name)

            img = cv2.imread(img_path)

            # Remove broken or unreadable images
            if img is None:
                os.remove(img_path)
                removed += 1
                continue

            # Remove extremely small images (bad quality)
            h, w, _ = img.shape
            if h < 100 or w < 100:
                os.remove(img_path)
                removed += 1

        print(f"{person}: {removed} images removed")

    print("Dataset cleaning completed")

if __name__ == "__main__":
    clean_dataset()