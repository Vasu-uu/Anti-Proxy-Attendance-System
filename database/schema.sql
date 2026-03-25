-- schema.sql

CREATE DATABASE IF NOT EXISTS Attandance;
USE Attandance;

CREATE TABLE students (
    student_id INT AUTO_INCREMENT PRIMARY KEY,
    roll_no VARCHAR(20) UNIQUE,
    name VARCHAR(100) NOT NULL,
    department VARCHAR(100),
    semester INT DEFAULT 6,
    batch VARCHAR(10) DEFAULT 'B',
    target_class VARCHAR(20),
    email VARCHAR(100),
    password_hash VARCHAR(255) DEFAULT 'apcas123',
    phone VARCHAR(15),
    face_encoding BLOB
);

CREATE TABLE faculty (
    faculty_id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    department VARCHAR(100),
    phone VARCHAR(15)
);

CREATE TABLE admin (
    admin_id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL
);

CREATE TABLE courses (
    course_code VARCHAR(50) PRIMARY KEY,
    course_name VARCHAR(255) NOT NULL,
    exam_slot VARCHAR(20),
    target_class VARCHAR(20),
    faculty_members TEXT,
    number_of_periods VARCHAR(20)
);

CREATE TABLE timetable (
    id INT AUTO_INCREMENT PRIMARY KEY,
    target_class VARCHAR(20),
    day_of_week VARCHAR(15) NOT NULL, 
    period_number INT NOT NULL,       
    slot VARCHAR(100)                  
);

CREATE TABLE attendance (
    attendance_id INT AUTO_INCREMENT PRIMARY KEY,
    student_id INT,
    date DATE,
    hour1 VARCHAR(20) DEFAULT 'Absent',
    hour2 VARCHAR(20) DEFAULT 'Absent',
    hour3 VARCHAR(20) DEFAULT 'Absent',
    hour4 VARCHAR(20) DEFAULT 'Absent',
    hour5 VARCHAR(20) DEFAULT 'Absent',
    hour6 VARCHAR(20) DEFAULT 'Absent',
    hour7 VARCHAR(20) DEFAULT 'Absent',
    hour8 VARCHAR(20) DEFAULT 'Absent',
    hour9 VARCHAR(20) DEFAULT 'Absent',
    verified_count INT DEFAULT 0,
    attendance_status VARCHAR(20) DEFAULT 'Absent',
    FOREIGN KEY (student_id)
        REFERENCES students(student_id)
        ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS camera_health_log (
    id INT AUTO_INCREMENT PRIMARY KEY,
    log_date DATE NOT NULL,
    period_number INT NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uniq_camera_log (log_date, period_number)
);

INSERT INTO courses (course_code, course_name, exam_slot, target_class, faculty_members, number_of_periods) VALUES
('20CST302', 'Compiler Design', 'A', 'S6 CSB', 'Dr. Pradeep Kumar P', '4'),
('20CST304', 'Computer Graphics and Image Processing', 'B', 'S6 CSB', 'Er. Soumya Sara Koshy', '4'),
('20CST306', 'Algorithm Analysis and Design', 'C', 'S6 CSB', 'Dr. Reni K Cherian', '4'),
('20CST322', 'Data Analytics', 'D1', 'S6 CSB', 'Er. Lini Ickappan', '3'),
('20CST362', 'Programming in Python', 'D2', 'S6 CSB', 'Er. Prince Abraham', '3'),
('20HUT300', 'Industrial Economics and Foreign Trade', 'E', 'S6 CSB', 'Y1', '3'),
('20CST308', 'Comprehensive Course Work', 'F', 'S6 CSB', 'Er. Justin Mathew, Er. Hari M', '1'),
('20CSL302', 'Networking Lab', 'S', 'S6 CSB', 'Er. Soumya Sara Koshy, Er. Rose V Pattani', '3'),
('20CSD302', 'Mini Project', 'T', 'S6 CSB', 'Er. Gayatri J L, Dr. Jayakrishna V / Er. Jerrin Sebastian', '3'),
('20CST398-A', 'Smart Contracts and Solidity (Self Study)', 'H1', 'S6 CSB', 'Er. Gokulnath G', '-'),
('20CST394', 'Advanced Topics in Machine Learning (Self Study)', 'H2', 'S6 CSB', 'Er. Soumya Sara Koshy', '-'),
('20MAT382', 'Computational Optimization and Applications', 'M1', 'S6 CSB', 'Mr. Siju K S', '3 + 1'),
('23ERT384', 'Advanced Machine Learning (Self Study)', 'M2', 'S6 CSB', 'Er. Prathap Pillai', '-'),
('20CST302_RA', 'Compiler Design (Remedial)', 'R(A)', 'S6 CSB', 'Dr. Pradeep Kumar P', '1'),
('20CST306_RC', 'Algorithm Analysis and Design (Remedial)', 'R(C)', 'S6 CSB', 'Dr. Reni K Cherian', '1'),
('AH', 'Advisory Hour', 'AH', 'S6 CSB', 'Er. Justin Mathew', '0 or 1'),
('PT', 'Placement Training', 'PT', 'S6 CSB', 'Mr. Boaz Praveen Kumar D', '1'),
('FH', 'Free Hour', 'FH', 'S6 CSB', '', '1');

INSERT INTO timetable (target_class, day_of_week, period_number, slot) VALUES
('S6 CSB', 'Monday', 1, 'Compiler Design'), 
('S6 CSB', 'Monday', 2, 'Algorithm Analysis and Design'), 
('S6 CSB', 'Monday', 3, 'Industrial Economics and Foreign Trade'), 
('S6 CSB', 'Monday', 4, 'Minor/Honors / Compiler Design (Remedial)'), 
('S6 CSB', 'Monday', 5, 'Compiler Design'), 
('S6 CSB', 'Monday', 6, 'Computer Graphics and Image Processing (Tutorial)'),

('S6 CSB', 'Tuesday', 1, 'Computer Graphics and Image Processing'), 
('S6 CSB', 'Tuesday', 2, 'Compiler Design (Tutorial)'), 
('S6 CSB', 'Tuesday', 3, 'Minor/Honors / Algorithm Analysis and Design (Remedial)'), 
('S6 CSB', 'Tuesday', 4, 'Algorithm Analysis and Design'), 
('S6 CSB', 'Tuesday', 5, 'Placement Training'), 
('S6 CSB', 'Tuesday', 6, 'Data Analytics / Programming in Python'),

('S6 CSB', 'Wednesday', 1, 'Compiler Design'), 
('S6 CSB', 'Wednesday', 2, 'Algorithm Analysis and Design'), 
('S6 CSB', 'Wednesday', 3, 'Industrial Economics and Foreign Trade'), 
('S6 CSB', 'Wednesday', 4, 'Networking Lab / Mini Project'), 
('S6 CSB', 'Wednesday', 5, 'Networking Lab / Mini Project'), 
('S6 CSB', 'Wednesday', 6, 'Networking Lab / Mini Project'),

('S6 CSB', 'Thursday', 1, 'Data Analytics / Programming in Python'), 
('S6 CSB', 'Thursday', 2, 'Computer Graphics and Image Processing'), 
('S6 CSB', 'Thursday', 3, 'Data Analytics / Programming in Python (Tutorial)'), 
('S6 CSB', 'Thursday', 4, 'Industrial Economics and Foreign Trade'), 
('S6 CSB', 'Thursday', 5, 'Computer Graphics and Image Processing'), 
('S6 CSB', 'Thursday', 6, 'Comprehensive Course Work'),

('S6 CSB', 'Friday', 1, 'Networking Lab / Mini Project'), 
('S6 CSB', 'Friday', 2, 'Networking Lab / Mini Project'), 
('S6 CSB', 'Friday', 3, 'Networking Lab / Mini Project'), 
('S6 CSB', 'Friday', 4, 'Free Hour'), 
('S6 CSB', 'Friday', 5, 'Algorithm Analysis and Design (Tutorial)'), 
('S6 CSB', 'Friday', 6, 'Minor/Honors / Advisory Hour');

INSERT INTO admin (name, email, password_hash) VALUES 
('System Admin', 'admin@example.com', 'admin123');

INSERT INTO faculty (name, email, password_hash, department, phone) VALUES
('Dr. Pradeep Kumar P', 'pradeep@example.com', 'faculty123', 'Computer Science', '9876500001');

SELECT * FROM students;
