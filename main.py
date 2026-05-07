import cv2
import numpy as np
import torch
import gc
import time as time_module
from datetime import datetime, time, timedelta
from detection.face_detector import detect_faces
from models.embedding_model import get_face_embedding
from models.similarity import cosine_similarity
import mysql.connector
from attendance_service import AttendanceService

# DB CONNECTION
def get_db_connection():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="",    #mysqlpasswordhere
        database="Attandance"
    )

# DB EMBEDDING LOADER

def load_embeddings_from_db(target_class=None):
    """
    Fetches student FaceNet embeddings directly from MySQL.
    If target_class is provided, only fetches for that class to speed up offline processing.
    """
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    query = "SELECT name, face_encoding FROM students WHERE face_encoding IS NOT NULL"
    params = ()
    if target_class:
        query += " AND target_class = %s"
        params = (target_class,)
        
    cursor.execute(query, params)
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    
    embeddings = []
    names = []
    for r in rows:
        names.append(r['name'])
        emb_array = np.frombuffer(r['face_encoding'], dtype=np.float32)
        embeddings.append(emb_array)
        
    return embeddings, names

THRESHOLD = 0.5

# Iriun Webcam over USB (UVC device).
# The app is called "Iriun Webcam" — device name shown in Windows is "Iriun Webcam".
# IRIUN_CAMERA_INDEX is the fallback index if auto-detection fails.
# Confirmed via snapshot test: OpenCV VideoCapture index 0 = Iriun, index 2 = ACER built-in.
IRIUN_CAMERA_INDEX = 0


def _find_iriun_device_index():
    """
    Confirm Iriun Webcam is connected and return IRIUN_CAMERA_INDEX.
    Diagnostic confirmed: OpenCV VideoCapture index 1 = Iriun (DSHOW backend).
    PnpDevice sort order does NOT match OpenCV indices, so we use the
    hardcoded IRIUN_CAMERA_INDEX rather than the PnpDevice position.
    """
    import subprocess
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command",
             "Get-PnpDevice -Class Camera -Status OK | Select-Object -ExpandProperty FriendlyName"],
            capture_output=True, text=True, timeout=6,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        names = [n.strip() for n in result.stdout.splitlines() if n.strip()]
        print(f"[Iriun] Connected camera devices: {names}")
        if any("iriun" in n.lower() for n in names):
            print(f"[Iriun] Iriun Webcam present — using VideoCapture index {IRIUN_CAMERA_INDEX}")
        else:
            print("[Iriun] WARNING: Iriun Webcam not found. Is the Iriun app running on the phone?")
    except Exception as e:
        print(f"[Iriun] Device check failed ({e})")
    return IRIUN_CAMERA_INDEX


def open_irium_capture():
    """
    Open the Iriun USB webcam.
    Diagnostic confirmed: DSHOW backend works; MSMF does not on this system.
    OpenCV VideoCapture index 1 = Iriun Webcam, index 2 = ACER built-in.
    Returns a cv2.VideoCapture on success, or None if Iriun is not accessible.
    """
    idx = _find_iriun_device_index()

    # DSHOW confirmed working; try it first. MSMF not available on this system.
    backends = [cv2.CAP_DSHOW, cv2.CAP_ANY]

    for backend in backends:
        try:
            cap = cv2.VideoCapture(idx, backend)
        except Exception as e:
            print(f"[Iriun] VideoCapture({idx}, {backend}) raised: {e}")
            continue
        if not cap.isOpened():
            cap.release()
            continue
        # Request 720p @ 30fps
        cap.set(cv2.CAP_PROP_FRAME_WIDTH,  1280)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        cap.set(cv2.CAP_PROP_FPS, 30)
        for _ in range(10):
            ret, frame = cap.read()
            if ret and frame is not None and frame.size > 0:
                w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                print(f"[Iriun] Opened Iriun Webcam at index {idx} — resolution {w}x{h} (backend {backend})")
                return cap
        cap.release()

    print(f"[Iriun] Could not open Iriun Webcam at index {idx}.")
    print("[Iriun] Ensure Iriun app is open on phone and Iriun desktop client is running on PC.")
    return None


# PERIOD TIMINGS

PERIODS = {
    1: (time(9, 0), time(10, 0)),
    2: (time(10, 5), time(11, 5)),
    3: (time(11, 15), time(12, 15)),
    4: (time(13, 15), time(14, 15)),
    5: (time(14, 20), time(15, 20)),
    6: (time(15, 30), time(16, 30)),
}

# Prevent duplicate triggering
executed_captures = set()
completed_periods = set()
attendance_service = AttendanceService()

# CHECK ACTIVATION WINDOW

def get_active_period(now=None):
    now = now or datetime.now()
    current_time = now.time()
    for period, (start, end) in PERIODS.items():
        if start <= current_time <= end:
            return period
    return None


def check_activation():
    now = datetime.now()
    today = now.date()

    for period, (start, end) in PERIODS.items():

        start_dt = datetime.combine(today, start)
        end_dt = datetime.combine(today, end)

        start_trigger = start_dt + timedelta(minutes=10)
        end_trigger = end_dt - timedelta(minutes=5)

        start_window = (start_trigger, start_trigger + timedelta(seconds=30))
        end_window = (end_trigger, end_trigger + timedelta(seconds=30))

        if start_window[0] <= now <= start_window[1]:
            return period, "start"

        if end_window[0] <= now <= end_window[1]:
            return period, "end"

    return None, None

def get_target_classes_for_period(period, at_date=None):
    at_date = at_date or datetime.now().date()
    day_name = at_date.strftime("%A")
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT DISTINCT target_class
            FROM timetable
            WHERE day_of_week=%s AND period_number=%s AND target_class IS NOT NULL
            ORDER BY target_class
            """,
            (day_name, period),
        )
        return [row["target_class"] for row in cursor.fetchall() if row.get("target_class")]
    finally:
        cursor.close()
        conn.close()

# RUN 10 SECOND ATTENDANCE SESSION

def run_attendance_session(period, capture_type, target_class):

    print(f"\nAttendance Session ({capture_type}) Started for Period {period}, Class {target_class}")
    
    # Dynamically pull latest embeddings from DB
    known_embeddings, known_names = load_embeddings_from_db(target_class=target_class)
    
    if not known_embeddings:
        print("Warning: No face encodings found in the database. Attendance cannot be verified.")
        return True

    cap = open_irium_capture()

    start_time = time_module.time()
    captured_frames = []
    frame_count = 0

    while time_module.time() - start_time <= 10:
        frame = None
        if cap is not None and cap.isOpened():
            ret, f = cap.read()
            if ret and f is not None and f.size > 0:
                frame = f

        if frame is None:
            time_module.sleep(0.2)
            continue

        if frame_count < 5:
            captured_frames.append(frame.copy())
            frame_count += 1
            print(f"Captured Frame {frame_count}")
            time_module.sleep(1.5)

    if cap is not None:
        cap.release()

    if not captured_frames:
        print("Camera not accessible: no frames from irium webcam (USB). Ensure the phone is connected and irium is active.")
        return False

    print("Processing captured images...")

    for frame in captured_frames:

        boxes = detect_faces(frame)

        for (x1, y1, x2, y2) in boxes:

            face = frame[y1:y2, x1:x2]

            if face is None or face.size == 0:
                continue

            embedding = get_face_embedding(face)

            if embedding is None:
                continue

            best_score = 0
            best_name = "UNKNOWN"

            for ref_emb, name in zip(known_embeddings, known_names):
                score = cosine_similarity(embedding, ref_emb)

                if score > best_score:
                    best_score = score
                    best_name = name

            if best_score >= THRESHOLD:
                if attendance_service.mark_present_once(best_name, period, capture_type):
                    print(f"{best_name} seen during {capture_type} capture for Period {period}")

    print("Cleaning GPU and Memory...")

    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    del captured_frames
    gc.collect()

    print(f"Attendance Session ({capture_type}) Completed\n")
    return True


def finalize_period(period):
    target_date = datetime.now().date()
    target_classes = get_target_classes_for_period(period, target_date)
    for target_class in target_classes:
        attendance_service.finalize_period_for_class(target_class, period, target_date)
    print(f"Attendance finalized for Period {period}. DB records synchronized.")


def run_camera_fallback(period):
    target_date = datetime.now().date()
    attendance_service.record_camera_status(period, target_date, "failed")
    allow_manual = attendance_service.can_use_manual_upload()
    target_classes = get_target_classes_for_period(period, target_date)
    if allow_manual:
        print("Camera failed; manual upload is enabled by 3-day failure rule.")
        return
    for target_class in target_classes:
        attendance_service.mark_class_absent(target_class, period, target_date)
    print("Camera failed and manual upload not allowed; marked all students absent.")

# OFFLINE IMAGE PROCESSING API (Called by app.py)

def process_offline_image(frame_bgr, target_class):
    """
    Called by Flask route to process a single uploaded photo. 
    Applies MTCNN alignment, generates embeddings, and compares against the DB.
    """
    print(f"Processing offline image for class {target_class}...")
    
    known_embeddings, known_names = load_embeddings_from_db(target_class=target_class)
    if not known_embeddings:
        print("No embeddings found for this class.")
        return []
        
    detected_names = set()
    
    # 1. Apply MTCNN Preprocessing/Alignment (if MTCNN is available)
    try:
        from preprocessing.align import detect_and_align_faces
        aligned_faces = detect_and_align_faces(frame_bgr)
        used_mtcnn = True
    except Exception as e:
        print(f"Fallback to YOLO due to alignment error: {e}")
        aligned_faces = []
        used_mtcnn = False
        
    if not used_mtcnn or not aligned_faces:
        # Fallback to standard YOLO if MTCNN module is missing or finds 0 faces
        boxes = detect_faces(frame_bgr)
        for (x1, y1, x2, y2) in boxes:
            face = frame_bgr[y1:y2, x1:x2]
            if face is not None and face.size > 0:
                aligned_faces.append(face)
                
    # 2. Extract Embeddings and Compare
    for face_crop in aligned_faces:
        embedding = get_face_embedding(face_crop)
        if embedding is None:
            continue
            
        best_score = 0
        best_name = None
        for ref_emb, name in zip(known_embeddings, known_names):
            score = cosine_similarity(embedding, ref_emb)
            if score > best_score:
                best_score = score
                best_name = name
                
        if best_score >= THRESHOLD and best_name:
            detected_names.add(best_name)
            print(f"Offline Match: {best_name} ({best_score:.3f})")

    return list(detected_names)

# MAIN LOOP

if __name__ == "__main__":
    print("Anti-Proxy Smart Attendance System Running")
    print("Waiting for active periods...")

    while True:
        now = datetime.now()
        if attendance_service.is_faculty_upload_day(now.date()):
            time_module.sleep(5)
            continue

        period = get_active_period(now)
        if not period:
            time_module.sleep(5)
            continue

        period_key = (now.date().isoformat(), period)
        if period_key in completed_periods:
            time_module.sleep(5)
            continue

        trigger_period, capture_type = check_activation()
        if not trigger_period or not capture_type or trigger_period != period:
            time_module.sleep(5)
            continue

        target_classes = get_target_classes_for_period(period, now.date())
        if not target_classes:
            print("No scheduled classes for this period.")
            time_module.sleep(5)
            continue

        session_ok = True
        for target_class in target_classes:
            capture_key = (now.date().isoformat(), period, capture_type, target_class)
            if capture_key in executed_captures:
                continue
            ok = run_attendance_session(period, capture_type, target_class)
            session_ok = session_ok and ok
            executed_captures.add(capture_key)

        if session_ok:
            attendance_service.record_camera_status(period, now.date(), "ok")
            if capture_type == "end":
                finalize_period(period)
                completed_periods.add(period_key)
        else:
            run_camera_fallback(period)
            completed_periods.add(period_key)

        time_module.sleep(5)
