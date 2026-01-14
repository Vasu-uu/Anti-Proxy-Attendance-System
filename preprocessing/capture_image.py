import cv2
import os

# Create dataset directory
dataset_path = "dataset"
os.makedirs(dataset_path, exist_ok=True)

student_name = input("Enter Student Name: ")
student_path = os.path.join(dataset_path, student_name)
os.makedirs(student_path, exist_ok=True)

cap = cv2.VideoCapture(0)
count = 0

print("Press 'Q' to stop capturing...")

while True:
    ret, frame = cap.read()
    if not ret:
        break

    cv2.imshow("Image Capture", frame)

    img_path = os.path.join(student_path, f"{count}.jpg")
    cv2.imwrite(img_path, frame)
    count += 1

    if cv2.waitKey(1) & 0xFF == ord('q') or count == 50:
        break

cap.release()
cv2.destroyAllWindows()
print("✅ 50 Images Captured Successfully")