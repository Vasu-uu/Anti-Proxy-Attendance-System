import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cv2
import numpy as np
import mysql.connector
from models.embedding_model import get_face_embedding

DATASET_DIR = "datasets"

def get_db_connection():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="",
        database="Attandance" 
    )

conn = get_db_connection()
cursor = conn.cursor()

print("Generating and saving embeddings to MySQL database...")

for class_name in os.listdir(DATASET_DIR):
    class_path = os.path.join(DATASET_DIR, class_name)
    if not os.path.isdir(class_path):
        continue

    print(f"Traversing Class Directory: {class_name}...")
    roll_counter = 1

    for student_folder in sorted(os.listdir(class_path)):
        student_path = os.path.join(class_path, student_folder)
        if not os.path.isdir(student_path):
            continue
        
        student_name = student_folder.strip().title()
        
        class_prefix = class_name.split()[-1] if ' ' in class_name else class_name
        roll_no = f"{class_prefix}-{roll_counter:02d}"

        print(f"  > Processing Student: {student_name} ({roll_no})")

        person_embs = []

        for img_name in os.listdir(student_path):
            img_path = os.path.join(student_path, img_name)
            img = cv2.imread(img_path)

            if img is None:
                continue

            embedding = get_face_embedding(img)
            if embedding is not None:
                person_embs.append(embedding)
                
            if len(person_embs) >= 3:
                break

        if person_embs:
            master_emb = np.mean(person_embs, axis=0)
            embedding_bytes = master_emb.astype(np.float32).tobytes()
            
            student_email = f"{roll_no.lower().replace('-', '')}@university.edu"
            default_pass = "cs123"
            
            cursor.execute("SELECT student_id FROM students WHERE roll_no = %s", (roll_no,))
            result = cursor.fetchone()
            
            if result:
                cursor.execute(
                    "UPDATE students SET face_encoding = %s, name = %s, target_class = %s, email = %s, password_hash = %s WHERE roll_no = %s", 
                    (embedding_bytes, student_name, class_name, student_email, default_pass, roll_no)
                )
            else:
                cursor.execute(
                    "INSERT INTO students (roll_no, name, target_class, email, password_hash, face_encoding) VALUES (%s, %s, %s, %s, %s, %s)", 
                    (roll_no, student_name, class_name, student_email, default_pass, embedding_bytes)
                )
            
            conn.commit()
            roll_counter += 1

cursor.close()
conn.close()

print("✅ Training complete — embeddings saved to database")