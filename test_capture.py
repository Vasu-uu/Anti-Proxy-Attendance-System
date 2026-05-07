import cv2
import numpy as np
import torch
import gc
import time as time_module
from datetime import datetime, timedelta
import csv
import os

import main
from detection.face_detector import detect_faces
from models.embedding_model import get_face_embedding
from models.similarity import cosine_similarity

TARGET_CLASS = "S6 CSB"
CSV_FILE = "test_capture_log.csv"

# 1. Initialize CSV File
if not os.path.exists(CSV_FILE):
    with open(CSV_FILE, mode='w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(["Date", "Time", "Period", "Capture Type", "Name", "Confidence"])

def log_to_csv(period, capture_type, name, score):
    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M:%S")
    with open(CSV_FILE, mode='a', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([date_str, time_str, period, capture_type, name, f"{score:.3f}"])

# Create a dynamic test period when the script starts
SCRIPT_START_TIME = datetime.now()
TEST_PERIOD_END_TIME = SCRIPT_START_TIME + timedelta(minutes=5)

def check_activation_test():
    """
    Check if the current time matches:
    - 30 seconds AFTER the script started
    - 30 seconds BEFORE the 5-minute mark
    Returns: (period_number, capture_type) or (None, None)
    """
    now = datetime.now()

    # Trigger 30s after start
    start_trigger = SCRIPT_START_TIME + timedelta(seconds=30)
    # Trigger 30s before end (which is 4 mins 30 secs after start)
    end_trigger = TEST_PERIOD_END_TIME - timedelta(seconds=30)

    # Provide a 10-second window to catch the loop
    start_window = (start_trigger, start_trigger + timedelta(seconds=10))
    end_window = (end_trigger, end_trigger + timedelta(seconds=10))

    if start_window[0] <= now <= start_window[1]:
        return "TEST_5MIN", "start"

    if end_window[0] <= now <= end_window[1]:
        return "TEST_5MIN", "end"

    return None, None

def run_test_session(period, capture_type):
    print(f"\n[TEST MODE] Capture ({capture_type}) Triggered for Period {period}, Class {TARGET_CLASS}")
    
    known_embeddings, known_names = main.load_embeddings_from_db(target_class=TARGET_CLASS)
    if not known_embeddings:
        print("Warning: No face encodings found in the database.")
        return

    cap = main.open_irium_capture()

    start_time = time_module.time()
    captured_frames = []
    frame_count = 0

    # Capture up to 5 frames in a 10-second window
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
        print("Failed to capture images from camera.")
        return

    print("Processing images for face recognition...")
    seen_this_session = set()

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

            if best_score >= main.THRESHOLD:
                if best_name not in seen_this_session:
                    seen_this_session.add(best_name)
                    print(f"✅ {best_name} detected! Logging to CSV...")
                    log_to_csv(period, capture_type, best_name, best_score)

    print("Cleaning Memory...")
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    del captured_frames
    gc.collect()

    print("[TEST MODE] Capture Session Completed\n")

if __name__ == "__main__":
    print("=====================================================")
    print(" 🚀 Instant 5-Minute Test Capture Mode Active!")
    print(f" Target Class: {TARGET_CLASS}")
    print(f" Period Start: {SCRIPT_START_TIME.strftime('%H:%M:%S')}")
    print(f" Period End:   {TEST_PERIOD_END_TIME.strftime('%H:%M:%S')}")
    print("-----------------------------------------------------")
    print(f" [1] Start Capture will trigger at: {(SCRIPT_START_TIME + timedelta(seconds=30)).strftime('%H:%M:%S')}")
    print(f" [2] End Capture will trigger at:   {(TEST_PERIOD_END_TIME - timedelta(seconds=30)).strftime('%H:%M:%S')}")
    print(" Logs will be saved to: test_capture_log.csv")
    print("=====================================================")

    executed_captures = set()

    while True:
        now = datetime.now()
        period, capture_type = check_activation_test()

        if period and capture_type:
            capture_key = (now.date().isoformat(), period, capture_type)
            if capture_key not in executed_captures:
                run_test_session(period, capture_type)
                executed_captures.add(capture_key)

        time_module.sleep(2)
