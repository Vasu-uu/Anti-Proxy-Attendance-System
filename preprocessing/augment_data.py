import os
import cv2
import numpy as np

INPUT_DIR = "processed_dataset"

def augment_image(img):
    augmented_images = []

    # Horizontal Flip
    flipped = cv2.flip(img, 1)
    augmented_images.append(flipped)

    # Brightness Adjustment
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    hsv[:, :, 2] = cv2.add(hsv[:, :, 2], 30)
    bright = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)
    augmented_images.append(bright)

    # Slight Rotation
    h, w, _ = img.shape
    M = cv2.getRotationMatrix2D((w/2, h/2), 10, 1)
    rotated = cv2.warpAffine(img, M, (w, h))
    augmented_images.append(rotated)

    return augmented_images


def augment_dataset():
    for person in os.listdir(INPUT_DIR):
        person_path = os.path.join(INPUT_DIR, person)

        if not os.path.isdir(person_path):
            continue

        images = os.listdir(person_path)
        count = len(images)

        for img_name in images:
            img_path = os.path.join(person_path, img_name)
            img = cv2.imread(img_path)

            if img is None:
                continue

            augmented_images = augment_image(img)

            for aug_img in augmented_images:
                save_path = os.path.join(person_path, f"{count}.jpg")
                cv2.imwrite(save_path, aug_img)
                count += 1

        print(f"{person}: Augmentation completed")

    print("Data augmentation completed")

if __name__ == "__main__":
    augment_dataset()