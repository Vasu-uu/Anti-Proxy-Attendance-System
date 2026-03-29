import numpy as np
import mysql.connector
import os

def get_db_connection():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="",          #mysqlpasswordhere
        database="Attandance"
    )

def migrate():
    npz_path = "saved_models/embeddings.npz"
    if not os.path.exists(npz_path):
        print(f"File {npz_path} not found. Skipping migration.")
        return

    try:
        data = np.load(npz_path, allow_pickle=True)
        embeddings = data["embeddings"]
        names = data["names"]
    except Exception as e:
        print(f"Error loading npz: {e}")
        return

    if len(names) == 0:
        print("No embeddings found in the .npz file.")
        return

    print(f"Found {len(names)} embeddings in local cache. Migrating to database...")

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    success_count = 0
    for name, embedding in zip(names, embeddings):
        # Convert the float numpy array directly to raw bytes
        blob_data = embedding.astype(np.float32).tobytes()
        
        # Update the student's face_encoding field
        cursor.execute("UPDATE students SET face_encoding = %s WHERE name = %s", (blob_data, name))
        if cursor.rowcount > 0:
            success_count += 1
            print(f"[OK] Migrated: {name}")
        else:
            print(f"[WARN] Student not found in DB: {name}")
            
    conn.commit()
    cursor.close()
    conn.close()
    
    print(f"\nMigration complete. Successfully loaded {success_count} out of {len(names)} encodings into the MySQL students table.")

if __name__ == "__main__":
    migrate()
