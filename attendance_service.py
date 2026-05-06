import datetime
import mysql.connector


def get_db_connection():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="",
        database="Attandance"
    )


class AttendanceService:
    def __init__(self):
        self._seen_cache = {}

    def _ensure_camera_log_table(self, cursor):
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS camera_health_log (
                id INT AUTO_INCREMENT PRIMARY KEY,
                log_date DATE NOT NULL,
                period_number INT NOT NULL,
                status VARCHAR(20) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE KEY uniq_camera_log (log_date, period_number)
            )
            """
        )

    def ensure_attendance_row(self, cursor, student_id, target_date):
        cursor.execute(
            "SELECT attendance_id FROM attendance WHERE student_id=%s AND date=%s",
            (student_id, target_date),
        )
        record = cursor.fetchone()
        if record:
            return record["attendance_id"]

        cursor.execute(
            "INSERT INTO attendance (student_id, date) VALUES (%s, %s)",
            (student_id, target_date),
        )
        return cursor.lastrowid

    def mark_student_period_status(self, cursor, student_id, target_date, period, status):
        hour_col = f"hour{period}"
        attendance_id = self.ensure_attendance_row(cursor, student_id, target_date)
        cursor.execute(
            f"UPDATE attendance SET {hour_col}=%s WHERE attendance_id=%s",
            (status, attendance_id),
        )

    def mark_class_from_detected_names(self, target_class, period, target_date, detected_names):
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute(
                "SELECT student_id, name FROM students WHERE target_class=%s",
                (target_class,),
            )
            class_roster = cursor.fetchall()
            detected = set(detected_names or [])

            for student in class_roster:
                status = "Present" if student["name"] in detected else "Absent"
                self.mark_student_period_status(
                    cursor, student["student_id"], target_date, period, status
                )

            conn.commit()
            return {
                "total": len(class_roster),
                "present": len([s for s in class_roster if s["name"] in detected]),
                "absent": len(class_roster) - len([s for s in class_roster if s["name"] in detected]),
            }
        finally:
            cursor.close()
            conn.close()

    def mark_class_absent(self, target_class, period, target_date):
        return self.mark_class_from_detected_names(target_class, period, target_date, set())

    def mark_present_once(self, name, period, capture_type):
        if capture_type not in ("start", "end"):
            return False
        if period not in self._seen_cache:
            self._seen_cache[period] = {}
        if name not in self._seen_cache[period]:
            self._seen_cache[period][name] = {"start": False, "end": False}
        if self._seen_cache[period][name][capture_type]:
            return False
        self._seen_cache[period][name][capture_type] = True
        return True

    def get_seen_status(self, period):
        return self._seen_cache.get(period, {})

    def clear_seen_period(self, period):
        if period in self._seen_cache:
            del self._seen_cache[period]

    def finalize_period_for_class(self, target_class, period, target_date):
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute(
                "SELECT student_id, name FROM students WHERE target_class=%s",
                (target_class,),
            )
            students = cursor.fetchall()
            seen = self.get_seen_status(period)
            for student in students:
                status = seen.get(student["name"], {"start": False, "end": False})
                if status["start"] and status["end"]:
                    final_status = "Present"
                elif status["start"] or status["end"]:
                    final_status = "Partial"
                else:
                    final_status = "Absent"
                self.mark_student_period_status(
                    cursor, student["student_id"], target_date, period, final_status
                )
            conn.commit()
        finally:
            cursor.close()
            conn.close()
        self.clear_seen_period(period)

    def record_camera_status(self, period, target_date, status):
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        try:
            self._ensure_camera_log_table(cursor)
            cursor.execute(
                """
                INSERT INTO camera_health_log (log_date, period_number, status)
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE status=VALUES(status), created_at=CURRENT_TIMESTAMP
                """,
                (target_date, period, status),
            )
            conn.commit()
        finally:
            cursor.close()
            conn.close()

    def camera_failed_last_n_days(self, n_days=3):
        today = datetime.date.today()
        days = [today - datetime.timedelta(days=idx) for idx in range(n_days)]
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        try:
            self._ensure_camera_log_table(cursor)
            for d in days:
                cursor.execute(
                    """
                    SELECT 1
                    FROM camera_health_log
                    WHERE log_date=%s AND status='failed'
                    LIMIT 1
                    """,
                    (d,),
                )
                if not cursor.fetchone():
                    return False
            return True
        finally:
            cursor.close()
            conn.close()

    def can_use_manual_upload(self):
        return self.camera_failed_last_n_days(3)

    def camera_failed_for_day_period(self, target_date, period):
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        try:
            self._ensure_camera_log_table(cursor)
            cursor.execute(
                """
                SELECT 1
                FROM camera_health_log
                WHERE log_date=%s AND period_number=%s AND status='failed'
                LIMIT 1
                """,
                (target_date, period),
            )
            return cursor.fetchone() is not None
        finally:
            cursor.close()
            conn.close()

    def _ensure_faculty_upload_day_table(self, cursor):
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS faculty_upload_day (
                for_date DATE NOT NULL PRIMARY KEY,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

    def set_faculty_upload_day(self, target_date, enabled):
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        try:
            self._ensure_faculty_upload_day_table(cursor)
            if enabled:
                cursor.execute(
                    """
                    INSERT INTO faculty_upload_day (for_date)
                    VALUES (%s)
                    ON DUPLICATE KEY UPDATE created_at=CURRENT_TIMESTAMP
                    """,
                    (target_date,),
                )
            else:
                cursor.execute(
                    "DELETE FROM faculty_upload_day WHERE for_date=%s",
                    (target_date,),
                )
            conn.commit()
        finally:
            cursor.close()
            conn.close()

    def is_faculty_upload_day(self, target_date):
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        try:
            self._ensure_faculty_upload_day_table(cursor)
            cursor.execute(
                "SELECT 1 FROM faculty_upload_day WHERE for_date=%s LIMIT 1",
                (target_date,),
            )
            return cursor.fetchone() is not None
        finally:
            cursor.close()
            conn.close()
