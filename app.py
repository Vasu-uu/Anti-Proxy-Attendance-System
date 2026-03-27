from flask import Flask, jsonify, request, redirect, session, render_template, send_from_directory, Response
import mysql.connector
import os
import uuid
import datetime
import tempfile
import cv2
import numpy as np
import time as time_module
from models.embedding_model import get_face_embedding
from models.similarity import cosine_similarity
from detection.face_detector import detect_faces
import main
from attendance_service import AttendanceService

app = Flask(__name__, template_folder='frontend')
app.secret_key = b'apcas_secure_hash_key'
app.config['SESSION_INSTANCE_ID'] = str(uuid.uuid4())
attendance_service = AttendanceService()


@app.before_request
def invalidate_session_after_restart():
    inst = app.config['SESSION_INSTANCE_ID']
    if session.get('user_id') and session.get('session_instance') != inst:
        session.clear()
live_embeddings_cache = {"ts": 0.0, "embeddings": [], "names": []}

def get_db_connection():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="",              #mysqlpasswordhere
        database="Attandance"
    )


def get_faculty_timetable_rows(cursor, faculty_name, day_name=None):
    """
    Resolve timetable rows for a faculty based on subjects assigned in courses.faculty_members.
    Uses course-name containment to support slot variants like Tutorial/Remedial text.
    """
    cursor.execute(
        """
        SELECT course_name
        FROM courses
        WHERE faculty_members LIKE %s
        """,
        ('%' + (faculty_name or '') + '%',),
    )
    assigned_courses = cursor.fetchall()
    if not assigned_courses:
        return []

    filters = []
    params = []
    for course in assigned_courses:
        cname = (course.get('course_name') or '').strip()
        if cname:
            filters.append("LOWER(t.slot) LIKE LOWER(%s)")
            params.append(f"%{cname}%")

    if not filters:
        return []

    where_sql = f"({' OR '.join(filters)})"
    if day_name:
        where_sql += " AND t.day_of_week=%s"
        params.append(day_name)

    query = f"""
        SELECT t.id, t.target_class, t.day_of_week, t.period_number, t.slot
        FROM timetable t
        WHERE {where_sql}
        ORDER BY FIELD(t.day_of_week, 'Monday','Tuesday','Wednesday','Thursday','Friday'), t.period_number
    """
    cursor.execute(query, tuple(params))
    return cursor.fetchall()


def _get_live_embeddings():
    now_ts = time_module.time()
    if now_ts - live_embeddings_cache["ts"] > 15 or not live_embeddings_cache["embeddings"]:
        embeddings, names = main.load_embeddings_from_db()
        live_embeddings_cache["embeddings"] = embeddings
        live_embeddings_cache["names"] = names
        live_embeddings_cache["ts"] = now_ts
    return live_embeddings_cache["embeddings"], live_embeddings_cache["names"]


def _match_face_name(face_crop, known_embeddings, known_names):
    embedding = get_face_embedding(face_crop)
    if embedding is None:
        return None, 0.0
    best_score = 0.0
    best_name = None
    for ref_emb, name in zip(known_embeddings, known_names):
        score = cosine_similarity(embedding, ref_emb)
        if score > best_score:
            best_score = score
            best_name = name
    if best_score >= main.THRESHOLD:
        return best_name, best_score
    return None, best_score


def _droidcam_error_frame():
    error_frame = np.zeros((480, 800, 3), dtype=np.uint8)
    cv2.putText(
        error_frame,
        "DroidCam not accessible.",
        (40, 180),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.85,
        (0, 0, 255),
        2,
        cv2.LINE_AA,
    )
    cv2.putText(
        error_frame,
        "Start DroidCam on phone; same Wi-Fi as this PC.",
        (40, 220),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.5,
        (255, 255, 255),
        2,
        cv2.LINE_AA,
    )
    cv2.putText(
        error_frame,
        f"{main.droidcam_base_url()}  (stream + /shot.jpg)",
        (40, 255),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.45,
        (200, 200, 200),
        1,
        cv2.LINE_AA,
    )
    cv2.putText(
        error_frame,
        "Open that IP in browser to verify.",
        (40, 285),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.5,
        (255, 255, 255),
        1,
        cv2.LINE_AA,
    )
    return error_frame


def _faculty_upload_mode_frame():
    frame = np.zeros((480, 800, 3), dtype=np.uint8)
    lines = [
        "Classroom upload mode is ON for today.",
        "DroidCam auto-capture is disabled.",
        "Faculty: use Offline Attendance with a class photo.",
        "Admin: turn this off on the dashboard to use DroidCam again.",
    ]
    y = 120
    for i, line in enumerate(lines):
        cv2.putText(
            frame,
            line,
            (40, y + i * 42),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.62,
            (40, 200, 40) if i == 0 else (230, 230, 230),
            2,
            cv2.LINE_AA,
        )
    return frame


def generate_admin_live_stream():
    if attendance_service.is_faculty_upload_day(datetime.date.today()):
        while True:
            frm = _faculty_upload_mode_frame()
            ok, buffer = cv2.imencode(".jpg", frm)
            if ok:
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n" + buffer.tobytes() + b"\r\n"
                )
            time_module.sleep(1)

    # DroidCam: try MJPEG via OpenCV (FFMPEG), then fall back to /shot.jpg every frame.
    cap = main.open_droidcam_capture()
    try:
        miss = 0
        while True:
            frame = None
            if cap is not None and cap.isOpened():
                ret, f = cap.read()
                if ret and f is not None and f.size > 0:
                    frame = f
            if frame is None:
                frame = main.read_droidcam_shot_jpeg()
            if frame is None:
                miss += 1
                if miss % 10 == 1:
                    err = _droidcam_error_frame()
                    ok, buffer = cv2.imencode(".jpg", err)
                    if ok:
                        yield (
                            b"--frame\r\n"
                            b"Content-Type: image/jpeg\r\n\r\n" + buffer.tobytes() + b"\r\n"
                        )
                time_module.sleep(0.3)
                continue
            miss = 0

            known_embeddings, known_names = _get_live_embeddings()
            if known_embeddings:
                boxes = detect_faces(frame)
                for (x1, y1, x2, y2) in boxes:
                    face = frame[y1:y2, x1:x2]
                    if face is None or face.size == 0:
                        continue
                    matched_name, score = _match_face_name(face, known_embeddings, known_names)
                    if not matched_name:
                        continue
                    cv2.rectangle(frame, (x1, y1), (x2, y2), (22, 163, 74), 2)
                    label = f"{matched_name} ({score:.2f})"
                    cv2.putText(
                        frame,
                        label,
                        (x1, max(y1 - 10, 20)),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.5,
                        (22, 163, 74),
                        2,
                        cv2.LINE_AA,
                    )

            ok, buffer = cv2.imencode(".jpg", frame)
            if not ok:
                continue
            frame_bytes = buffer.tobytes()
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n" + frame_bytes + b"\r\n"
            )
    finally:
        if cap is not None:
            cap.release()

@app.route("/")
def home():
    if 'role' in session:
        if session['role'] == 'student':
            return redirect("/studentdashboard.html")
        elif session['role'] == 'faculty':
            return redirect("/facultydashboard.html")
        elif session['role'] == 'admin':
            return redirect("/admindashboard.html")
    return redirect('/login.html')


@app.route("/logout")
def logout():
    session.clear()
    return redirect('/')

@app.route("/auth", methods=["POST"])
def auth():
    auth_type = request.form.get("auth_type", "login")
    role = request.form.get("role")
    email = request.form.get("email")
    password = request.form.get("password")
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    if auth_type == "admin_add_faculty":
        name = request.form.get("fullname")
        dept = request.form.get("department")
        cursor.execute("SELECT faculty_id FROM faculty WHERE email=%s", (email,))
        existing = cursor.fetchone()
        if existing:
            cursor.close()
            conn.close()
            return redirect("/admindashboard.html?msg=FacultyExists")

        cursor.execute("INSERT INTO faculty (name, email, password_hash, department) VALUES (%s, %s, %s, %s)",
                       (name, email, password, dept))
        conn.commit()

        # If this faculty name is already assigned in course metadata, mapping is automatic.
        cursor.execute("SELECT COUNT(*) AS c FROM courses WHERE faculty_members LIKE %s", ('%' + (name or '') + '%',))
        mapped = cursor.fetchone()["c"]
        cursor.close()
        conn.close()
        if mapped > 0:
            return redirect("/admindashboard.html?msg=FacultyAddedMapped")
        return redirect("/admindashboard.html?msg=FacultyAdded")
        
    else:
        if role == "student":
            cursor.execute("SELECT * FROM students WHERE email=%s AND password_hash=%s", (email, password))
            user = cursor.fetchone()
            if user:
                session['user_id'] = user['student_id']
                session['name'] = user['name']
                session['target_class'] = user['target_class']
                session['role'] = 'student'
                session['session_instance'] = app.config['SESSION_INSTANCE_ID']
                return redirect('/studentdashboard.html')
                
        elif role == "faculty":
            cursor.execute("SELECT * FROM faculty WHERE email=%s AND password_hash=%s", (email, password))
            user = cursor.fetchone()
            if user:
                session['user_id'] = user['faculty_id']
                session['name'] = user['name']
                session['department'] = user['department']
                session['role'] = 'faculty'
                session['session_instance'] = app.config['SESSION_INSTANCE_ID']
                return redirect('/facultydashboard.html')
                
        elif role == "admin":
            cursor.execute("SELECT * FROM admin WHERE email=%s AND password_hash=%s", (email, password))
            user = cursor.fetchone()
            if user:
                session['user_id'] = user['admin_id']
                session['name'] = user['name']
                session['role'] = 'admin'
                session['session_instance'] = app.config['SESSION_INSTANCE_ID']
                return redirect('/admindashboard.html')
                
    return redirect('/login.html?error=1')


@app.route("/signup.html")
def signup_disabled():
    return redirect("/login.html")


@app.route("/api/student/attendance", methods=["GET"])
def student_attendance():
    student_id = request.args.get("student_id")
    roll = request.args.get("roll")
    from_date = request.args.get("from")
    to_date = request.args.get("to")

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    if roll and not student_id:
        cursor.execute("SELECT student_id FROM students WHERE roll_no=%s", (roll,))
        res = cursor.fetchone()
        if res:
            student_id = res['student_id']

    query = """
        SELECT date,
               hour1, hour2, hour3, hour4,
               hour5, hour6, hour7, hour8, hour9
        FROM attendance
        WHERE student_id = %s
        AND date BETWEEN %s AND %s
    """

    cursor.execute(query, (student_id, from_date, to_date))
    records = cursor.fetchall()

    cursor.close()
    conn.close()

    return jsonify(records)

@app.route("/api/admin_update_attendance", methods=["POST"])
def admin_update_attendance():
    if session.get('role') not in ['admin', 'faculty']:
        return jsonify({"error": "Unauthorized"}), 403
        
    data = request.json
    roll = data.get('roll')
    date_val = data.get('date')
    updates = data.get('updates', {})
    
    if not roll or not date_val:
        return jsonify({"error": "Missing roll or date"}), 400
        
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute("SELECT student_id, target_class FROM students WHERE roll_no=%s", (roll,))
    student = cursor.fetchone()
    
    if not student:
        cursor.close()
        conn.close()
        return jsonify({"error": "Student not found"}), 404
        
    sid = student['student_id']
    
    # Period restriction is enforced on the frontend via URL params.
    # Faculty can only reach this endpoint with 1 period's data at a time.
    cursor.execute("SELECT attendance_id FROM attendance WHERE student_id=%s AND date=%s", (sid, date_val))
    record = cursor.fetchone()
    
    # Generate the SET parameters string
    set_clause = ", ".join([f"{col} = %s" for col in updates.keys()])
    values = list(updates.values())
    
    if record:
        query = f"UPDATE attendance SET {set_clause} WHERE attendance_id=%s"
        values.append(record['attendance_id'])
        cursor.execute(query, values)
    else:
        cols = ", ".join(updates.keys())
        placeholders = ", ".join(["%s"] * len(updates))
        query = f"INSERT INTO attendance (student_id, date, {cols}) VALUES (%s, %s, {placeholders})"
        cursor.execute(query, [sid, date_val] + values)
        
    # Also ensure that all other students in the same class have an attendance record for this date
    # so they are marked 'Absent' by default instead of 'Not Marked'.
    cursor.execute("SELECT student_id FROM students WHERE target_class=%s AND student_id != %s", (student['target_class'], sid))
    other_students = cursor.fetchall()
    
    for other in other_students:
        other_sid = other['student_id']
        cursor.execute("SELECT attendance_id FROM attendance WHERE student_id=%s AND date=%s", (other_sid, date_val))
        if not cursor.fetchone():
            # Insert default row for this student
            cursor.execute("INSERT INTO attendance (student_id, date) VALUES (%s, %s)", (other_sid, date_val))
            
    conn.commit()
    cursor.close()
    conn.close()
    
    return jsonify({"success": True})

@app.route("/api/offline_attendance", methods=["POST"])
def offline_attendance():
    if 'user_id' not in session or session.get('role') != 'faculty':
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403
    
    photo = request.files.get('photo')
    target_class = request.form.get('target_class')
    period = request.form.get('period', '1')
    target_date_str = request.form.get('date')
    
    if target_date_str:
        try:
            target_date = datetime.datetime.strptime(target_date_str, '%Y-%m-%d').date()
            if (datetime.date.today() - target_date).days > 3 or (datetime.date.today() - target_date).days < 0:
                return jsonify({'success': False, 'error': 'Selected date must be within the last 3 days.'})
        except ValueError:
            return jsonify({'success': False, 'error': 'Invalid date format'})
    else:
        target_date = datetime.date.today()
    
    if not photo or not target_class:
        return jsonify({'success': False, 'error': 'Missing photo or class'})

    try:
        period_int = int(period)
    except (TypeError, ValueError):
        return jsonify({'success': False, 'error': 'Invalid period'}), 400

    # Rule:
    # - Previous dates (already restricted to last 3 days) are allowed.
    # - Current date: full-day faculty upload mode, or camera failed for this period.
    if target_date == datetime.date.today():
        allowed_today = (
            attendance_service.is_faculty_upload_day(target_date)
            or attendance_service.camera_failed_for_day_period(target_date, period_int)
        )
        if not allowed_today:
            return jsonify({
                'success': False,
                'error': 'For today, upload needs admin full-day classroom mode (dashboard) or a camera failure logged for this period.'
            }), 403
    
    # Save to temp file and read
    with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as tmp:
        photo.save(tmp.name)
        frame = cv2.imread(tmp.name)
    os.unlink(tmp.name)
    
    if frame is None:
        return jsonify({'success': False, 'error': 'Could not read image'})

    try:
        detected_names = main.process_offline_image(frame, target_class)

        summary = attendance_service.mark_class_from_detected_names(
            target_class=target_class,
            period=period_int,
            target_date=target_date,
            detected_names=detected_names,
        )

        return jsonify({
            'success': True,
            'detected': summary['present'],
            'absent': summary['absent'],
            'names': list(detected_names)
        })
    except Exception as e:
        # Ensure the frontend always receives JSON (so it doesn't crash on res.json()).
        return jsonify({
            'success': False,
            'error': f'Image processing failed: {str(e)}'
        }), 500


@app.route("/api/admin_faculty_upload_day", methods=["GET"])
def admin_faculty_upload_day_get():
    if session.get('role') != 'admin':
        return jsonify({"error": "Unauthorized"}), 403
    today = datetime.date.today()
    enabled = attendance_service.is_faculty_upload_day(today)
    return jsonify({"date": today.isoformat(), "enabled": enabled})


@app.route("/api/admin_faculty_upload_day", methods=["POST"])
def admin_faculty_upload_day_post():
    if session.get('role') != 'admin':
        return jsonify({"success": False, "error": "Unauthorized"}), 403
    data = request.get_json(silent=True) or {}
    if "enabled" not in data:
        return jsonify({"success": False, "error": "Missing enabled (true/false)"}), 400
    enabled = bool(data.get("enabled"))
    target_date = datetime.date.today()
    attendance_service.set_faculty_upload_day(target_date, enabled)
    if enabled:
        msg = "Full-day classroom photo upload is ON for today. DroidCam auto-capture is disabled."
    else:
        msg = "DroidCam auto-capture is ON for today. Faculty must use the camera for scheduled captures."
    return jsonify({"success": True, "enabled": enabled, "date": target_date.isoformat(), "message": msg})


@app.route("/api/faculty_periods", methods=["GET"])
def api_faculty_periods():
    if 'user_id' not in session or session.get('role') != 'faculty':
        return jsonify([])
        
    date_str = request.args.get('date')
    if not date_str:
        return jsonify([])
        
    try:
        import datetime
        target_date = datetime.datetime.strptime(date_str, '%Y-%m-%d').date()
        day_name = target_date.strftime('%A')
    except ValueError:
        return jsonify([])
        
    faculty_name = session.get('name', '')
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    periods = get_faculty_timetable_rows(cursor, faculty_name, day_name=day_name)
    cursor.close()
    conn.close()

    today = datetime.date.today()
    for row in periods:
        pnum = row.get("period_number")
        try:
            p_int = int(pnum)
        except (TypeError, ValueError):
            row["upload_allowed"] = False
            continue
        if target_date == today:
            row["upload_allowed"] = (
                attendance_service.is_faculty_upload_day(target_date)
                or attendance_service.camera_failed_for_day_period(target_date, p_int)
            )
        else:
            row["upload_allowed"] = True

    return jsonify(periods)


@app.route("/api/system_status", methods=["GET"])
def api_system_status():
    if 'user_id' not in session or session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403

    status = {
        "checked_at": datetime.datetime.now().isoformat(),
        "overall": {"label": "Unavailable", "state": "danger"},
        "database": {"label": "Unavailable", "state": "danger", "detail": "Not connected"},
        "face_embeddings": {"label": "Unavailable", "state": "danger", "detail": "No data"},
        "camera": {"label": "Unavailable", "state": "danger", "detail": "No logs"},
        "timetable": {"label": "Unavailable", "state": "danger", "detail": "No records"},
    }

    conn = None
    cursor = None
    try:
        start = datetime.datetime.now()
        conn = get_db_connection()
        latency_ms = int((datetime.datetime.now() - start).total_seconds() * 1000)
        cursor = conn.cursor(dictionary=True)

        status["database"] = {
            "label": "Active",
            "state": "success",
            "detail": f"Connected ({latency_ms} ms)"
        }

        cursor.execute("SELECT COUNT(*) AS c FROM students WHERE face_encoding IS NOT NULL")
        emb_count = cursor.fetchone()["c"]
        status["face_embeddings"] = {
            "label": "Active" if emb_count > 0 else "Warning",
            "state": "success" if emb_count > 0 else "warning",
            "detail": f"{emb_count} student embeddings available"
        }

        cursor.execute("SELECT COUNT(*) AS c FROM timetable")
        tt_count = cursor.fetchone()["c"]
        status["timetable"] = {
            "label": "Active" if tt_count > 0 else "Warning",
            "state": "success" if tt_count > 0 else "warning",
            "detail": f"{tt_count} timetable rows loaded"
        }

        try:
            cursor.execute(
                """
                SELECT log_date, period_number, status
                FROM camera_health_log
                ORDER BY created_at DESC
                LIMIT 1
                """
            )
            camera_row = cursor.fetchone()
        except mysql.connector.Error:
            camera_row = None

        if camera_row:
            cam_state = "success" if camera_row["status"] == "ok" else "danger"
            cam_label = "Active" if camera_row["status"] == "ok" else "Failed"
            status["camera"] = {
                "label": cam_label,
                "state": cam_state,
                "detail": f"Last check: {camera_row['log_date']} period {camera_row['period_number']}"
            }
        else:
            status["camera"] = {
                "label": "Unknown",
                "state": "warning",
                "detail": "No camera health log entries yet"
            }

        states = [
            status["database"]["state"],
            status["face_embeddings"]["state"],
            status["camera"]["state"],
            status["timetable"]["state"],
        ]
        if "danger" in states:
            status["overall"] = {"label": "Issues Detected", "state": "danger"}
        elif "warning" in states:
            status["overall"] = {"label": "Partially Operational", "state": "warning"}
        else:
            status["overall"] = {"label": "All Systems Operational", "state": "success"}

    except mysql.connector.Error as e:
        status["database"] = {"label": "Failed", "state": "danger", "detail": str(e)}
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

    return jsonify(status)


@app.route("/api/admin/live_feed")
def api_admin_live_feed():
    if 'user_id' not in session or session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403
    return Response(
        generate_admin_live_stream(),
        mimetype="multipart/x-mixed-replace; boundary=frame"
    )


@app.route("/<path:filename>")
def serve_frontend(filename):
    if filename.endswith(".html"):
        context = {}

        if filename != 'login.html' and ('user_id' not in session or not session.get('role')):
            return redirect('/login.html')

        if filename == 'live.html':
            if 'user_id' not in session or session.get('role') != 'admin':
                return redirect('/login.html')
        
        if filename == 'studentdashboard.html' and 'user_id' in session and session.get('role') == 'student':
            import datetime
            now = datetime.datetime.now()
            day_name = now.strftime('%A')
            current_time = now.time()
            
            period_schedule = [
                (1, datetime.time(9, 0), datetime.time(10, 0)),
                (2, datetime.time(10, 5), datetime.time(11, 5)),
                (3, datetime.time(11, 15), datetime.time(12, 15)),
                (4, datetime.time(13, 15), datetime.time(14, 15)),
                (5, datetime.time(14, 20), datetime.time(15, 20)),
                (6, datetime.time(15, 30), datetime.time(16, 30)),
            ]
            
            current_period_num = None
            for p_num, p_start, p_end in period_schedule:
                if p_start <= current_time <= p_end:
                    current_period_num = p_num
                    break
            
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            
            current_subject = 'No Active Period'
            current_period_label = 'No class right now'
            if current_period_num and day_name not in ['Saturday', 'Sunday']:
                cursor.execute(
                    "SELECT slot FROM timetable WHERE target_class=%s AND day_of_week=%s AND period_number=%s",
                    (session.get('target_class'), day_name, current_period_num)
                )
                row = cursor.fetchone()
                if row and row['slot']:
                    current_subject = row['slot']
                    current_period_label = f'Period {current_period_num} ({current_subject})'
                else:
                    current_period_label = f'Period {current_period_num} (Free Hour)'
            elif day_name in ['Saturday', 'Sunday']:
                current_period_label = 'Weekend — No Classes'
            
            today_status = 'Not Marked'
            today_badge = 'badge-neutral'
            if current_period_num:
                cursor.execute(
                    "SELECT * FROM attendance WHERE student_id=%s AND date=%s",
                    (session['user_id'], now.date())
                )
                today_rec = cursor.fetchone()
                if today_rec:
                    hour_key = f'hour{current_period_num}'
                    status = today_rec.get(hour_key, 'Absent')
                    today_status = status
                    today_badge = 'badge-present' if status == 'Present' else ('badge-partial' if status == 'Partial' else 'badge-absent')
            
            cursor.execute("SELECT * FROM attendance WHERE student_id=%s", (session['user_id'],))
            all_records = cursor.fetchall()
            
            total_classes = 0
            present_count = 0
            for rec in all_records:
                for period in range(1, 7):
                    hour_key = f'hour{period}'
                    val = rec.get(hour_key)
                    if val and val != 'Absent':
                        total_classes += 1
                        if val == 'Present':
                            present_count += 1
                    elif val == 'Absent':
                        total_classes += 1
            
            absent_count = total_classes - present_count
            overall_pct = round((present_count / total_classes * 100), 1) if total_classes > 0 else 0
            
            context['current_period'] = current_period_label
            context['today_status'] = today_status
            context['today_badge'] = today_badge
            context['overall_pct'] = overall_pct
            context['classes_attended'] = present_count
            context['classes_missed'] = absent_count
            context['total_classes'] = total_classes

            cursor.execute("SELECT * FROM students WHERE student_id=%s", (session['user_id'],))
            student_info = cursor.fetchone()
            context['student'] = student_info
            
            
            cursor.close()
            conn.close()

        if filename == 'student_timetable.html' and 'user_id' in session and session.get('role') == 'student':
            import datetime
            now = datetime.datetime.now()
            today_name = now.strftime('%A')
            current_time = now.time()
            
            period_schedule = [
                (1, datetime.time(9, 0), datetime.time(10, 0)),
                (2, datetime.time(10, 5), datetime.time(11, 5)),
                (3, datetime.time(11, 15), datetime.time(12, 15)),
                (4, datetime.time(13, 15), datetime.time(14, 15)),
                (5, datetime.time(14, 20), datetime.time(15, 20)),
                (6, datetime.time(15, 30), datetime.time(16, 30)),
            ]
            
            current_period_num = None
            for p_num, p_start, p_end in period_schedule:
                if p_start <= current_time <= p_end:
                    current_period_num = p_num
                    break
            
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM timetable WHERE target_class=%s ORDER BY FIELD(day_of_week, 'Monday','Tuesday','Wednesday','Thursday','Friday'), period_number",
                           (session.get('target_class'),))
            rows = cursor.fetchall()
            
            days_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']
            day_map = {d: [] for d in days_order}
            for r in rows:
                day = r['day_of_week']
                if day in day_map:
                    is_current = (day == today_name and r['period_number'] == current_period_num)
                    day_map[day].append({
                        'subject': r['slot'] if r['slot'] else 'Free Hour',
                        'is_current': is_current
                    })
            
            timetable_days = []
            for d in days_order:
                timetable_days.append({'name': d, 'periods': day_map[d], 'is_today': (d == today_name)})
            
            context['timetable_days'] = timetable_days
            cursor.close()
            conn.close()

        if filename == 'student.html' and 'user_id' in session and session.get('role') == 'student':
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            
            cursor.execute("SELECT * FROM attendance WHERE student_id = %s ORDER BY date DESC", (session['user_id'],))
            raw_records = cursor.fetchall()

            context['attendance_records'] = raw_records
            cursor.close()
            conn.close()

        if filename == 'admindashboard.html' and 'user_id' in session and session.get('role') == 'admin':
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT COUNT(*) as c FROM students")
            context['total_students'] = cursor.fetchone()['c']
            cursor.execute("SELECT COUNT(DISTINCT target_class) as c FROM timetable")
            context['active_classes'] = cursor.fetchone()['c']
            cursor.execute("SELECT COUNT(*) as c FROM courses")
            context['total_subjects'] = cursor.fetchone()['c']
            context['proxy_alerts'] = 0 # Placeholder if no native proxy column tracked natively
            cursor.close()
            conn.close()

        if filename == 'facultydashboard.html' and 'user_id' in session and session.get('role') == 'faculty':
            import datetime
            today = datetime.date.today()
            today_name = today.strftime('%A')
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)

            faculty_name = session.get('name', '')
            faculty_rows = get_faculty_timetable_rows(cursor, faculty_name)
            available_classes = sorted({
                r.get('target_class') for r in faculty_rows if r.get('target_class')
            })
            if not available_classes:
                # fallback: all classes
                cursor.execute("SELECT DISTINCT target_class FROM timetable ORDER BY target_class")
                available_classes = [r['target_class'] for r in cursor.fetchall()]
            context['available_classes'] = available_classes

            # Get today's periods for this faculty
            faculty_today_periods = get_faculty_timetable_rows(cursor, faculty_name, day_name=today_name)
            context['faculty_today_periods'] = faculty_today_periods

            selected_class = request.args.get('class')
            
            target_date_str = request.args.get('date')
            target_date = today
            if target_date_str:
                try:
                    target_date = datetime.datetime.strptime(target_date_str, '%Y-%m-%d').date()
                except ValueError:
                    target_date = today
            
            selected_period = request.args.get('period')
            
            context['selected_class'] = selected_class
            context['selected_date'] = target_date.strftime('%Y-%m-%d')
            context['selected_period'] = selected_period

            total_students, present_count = 0, 0
            student_rows = []
            if selected_class:
                cursor.execute("SELECT student_id, name, roll_no FROM students WHERE target_class=%s ORDER BY name", (selected_class,))
                students = cursor.fetchall()
                for s in students:
                    total_students += 1
                    cursor.execute("SELECT * FROM attendance WHERE student_id=%s AND date=%s", (s['student_id'], target_date))
                    att = cursor.fetchone()
                    present_today = False
                    if att:
                        if selected_period:
                            if att.get(f'hour{selected_period}') == 'Present':
                                present_today = True
                        else:
                            for p in range(1, 7):
                                if att.get(f'hour{p}') == 'Present':
                                    present_today = True
                                    break
                    if present_today:
                        present_count += 1
                    student_rows.append({'name': s['name'], 'roll_no': s['roll_no'], 'class': selected_class, 'present': present_today})

            context['students_list'] = student_rows
            context['total_students'] = total_students
            context['present_count'] = present_count
            context['absent_count'] = total_students - present_count
            cursor.close()
            conn.close()

        if filename == 'adminclassview.html' and 'user_id' in session and session.get('role') == 'admin':
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT DISTINCT target_class FROM timetable ORDER BY target_class")
            context['all_classes'] = [r['target_class'] for r in cursor.fetchall()]

            selected_class = request.args.get('class')
            context['selected_class'] = selected_class

            if selected_class:
                cursor.execute("SELECT * FROM students WHERE target_class=%s ORDER BY name", (selected_class,))
                context['students'] = cursor.fetchall()

                cursor.execute("SELECT * FROM timetable WHERE target_class=%s ORDER BY FIELD(day_of_week, 'Monday','Tuesday','Wednesday','Thursday','Friday'), period_number", (selected_class,))
                tt_rows = cursor.fetchall()

                days_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']
                day_map = {d: [{"period_number": i, "slot": "Free", "target_class": ""} for i in range(1, 7)] for d in days_order}
                for r in tt_rows:
                    p_idx = r['period_number'] - 1
                    if 0 <= p_idx < 6:
                        day_map[r['day_of_week']][p_idx] = r
                
                context['timetable_days'] = [{'name': d, 'periods': day_map[d]} for d in days_order]
            else:
                context['students'] = []
                context['timetable_days'] = []

            cursor.close()
            conn.close()


        if filename in ['facultytimetable.html', 'edittimetable.html'] and 'user_id' in session:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            
            if filename == 'facultytimetable.html' and session.get('role') == 'faculty':
                faculty_name = session.get('name')
                raw_rows = get_faculty_timetable_rows(cursor, faculty_name)

                # Merge duplicate day/period cells (parallel classes/slots) into one display cell.
                merged = {}
                for row in raw_rows:
                    key = (row['day_of_week'], row['period_number'])
                    if key not in merged:
                        merged[key] = {
                            'id': row['id'],
                            'target_class': row.get('target_class') or '',
                            'day_of_week': row['day_of_week'],
                            'period_number': row['period_number'],
                            'slot': row.get('slot') or 'Free',
                        }
                        continue

                    existing_classes = set(
                        [c.strip() for c in merged[key]['target_class'].split(' / ') if c.strip()]
                    )
                    new_class = (row.get('target_class') or '').strip()
                    if new_class and new_class not in existing_classes:
                        merged[key]['target_class'] = (
                            merged[key]['target_class'] + ' / ' + new_class
                            if merged[key]['target_class'] else new_class
                        )

                    existing_slots = set(
                        [s.strip() for s in merged[key]['slot'].split(' / ') if s.strip()]
                    )
                    new_slot = (row.get('slot') or '').strip()
                    if new_slot and new_slot not in existing_slots:
                        merged[key]['slot'] = merged[key]['slot'] + ' / ' + new_slot

                tt_rows = list(merged.values())
            elif filename == 'edittimetable.html' and session.get('role') == 'admin':
                cursor.execute("SELECT DISTINCT target_class FROM timetable")
                context['all_classes'] = [r['target_class'] for r in cursor.fetchall()]
                
                target_class = request.args.get('class', '')
                context['selected_class'] = target_class
                
                if target_class:
                    cursor.execute("SELECT * FROM timetable WHERE target_class=%s ORDER BY FIELD(day_of_week, 'Monday','Tuesday','Wednesday','Thursday','Friday'), period_number", (target_class,))
                    tt_rows = cursor.fetchall()
                else:
                    tt_rows = []
            else:
                tt_rows = []
                
            days_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']
            day_map = {d: [{"period_number": i, "slot": "Free", "target_class": ""} for i in range(1, 7)] for d in days_order}
            for r in tt_rows:
                p_idx = r['period_number'] - 1
                if 0 <= p_idx < 6:
                    # In a master timetable with multiple classes per period, a single array [1..6] won't hold all parallel classes.
                    # For a simple structural bypass matching the teacher view, we just take the first one or group them.
                    # To not break the UI grid, we just render the first matching class for now if it's the admin master view.
                    day_map[r['day_of_week']][p_idx] = r
                
            tt_structured = [{'name': d, 'periods': day_map[d]} for d in days_order]
            context['timetable_days'] = tt_structured
            cursor.close()
            conn.close()

        if filename in ['viewattendance.html', 'studentattendance.html'] and 'user_id' in session:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT DISTINCT target_class FROM timetable")
            context['all_classes'] = [r['target_class'] for r in cursor.fetchall()]

            target_class = request.args.get('class', 'S6 CSB')
            context['selected_class'] = target_class

            cursor.execute("SELECT * FROM students WHERE target_class=%s", (target_class,))
            context['students_list'] = cursor.fetchall()
            
            if session.get('role') == 'faculty':
                import datetime
                now = datetime.datetime.now()
                current_time = now.time()
                period_schedule = [
                    (1, datetime.time(9, 0), datetime.time(10, 0)),
                    (2, datetime.time(10, 5), datetime.time(11, 5)),
                    (3, datetime.time(11, 15), datetime.time(12, 15)),
                    (4, datetime.time(13, 15), datetime.time(14, 15)),
                    (5, datetime.time(14, 20), datetime.time(15, 20)),
                    (6, datetime.time(15, 30), datetime.time(16, 30)),
                ]
                active_hour = None
                for p_num, p_start, p_end in period_schedule:
                    if p_start <= current_time <= p_end:
                        active_hour = p_num
                        break
                context['active_hour'] = active_hour
            else:
                context['active_hour'] = -1
                
            cursor.close()
            conn.close()
        
        return render_template(filename, **context)
    return send_from_directory('frontend', filename)


if __name__ == "__main__":
    import webbrowser, threading, os
    if os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
        threading.Timer(1.2, lambda: webbrowser.open("http://127.0.0.1:5000/")).start()
    app.run(debug=True)
