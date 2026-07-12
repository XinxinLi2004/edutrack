"""
database.py - SQLite 数据库层
使用 Python 内置 sqlite3，无需外部依赖
"""

import sqlite3
import os
import json
import csv
import io
from datetime import datetime, timedelta
import random


def smart_csv_read(text):
    """智能读取 CSV：自动识别分隔符（逗号/Tab/空格），返回 csv.reader"""
    if not text or not text.strip():
        return csv.reader(io.StringIO(''))
    # 取前几行作为嗅探样本
    sample = '\n'.join(text.strip().split('\n')[:5])
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=',\t ')
        return csv.reader(io.StringIO(text.strip()), dialect)
    except csv.Error:
        # 嗅探失败，回退到逗号 + 也尝试 Tab
        return csv.reader(io.StringIO(text.strip()))

DATA_DIR = os.environ.get('STUDENT_SYSTEM_DATA_DIR', os.path.dirname(os.path.abspath(__file__)))
DATABASE_PATH = os.path.join(DATA_DIR, 'data', 'database.sqlite')

# 当前年级到入学级次的映射（按当前年份推算）
GRADE_TO_COHORT_OFFSET = {
    '初三': 1,
    '高一': 0,
    '高二': -1,
    '高三': -2,
}


def _add_column(cursor, table, column, definition):
    """安全地添加列（忽略已存在）"""
    try:
        cursor.execute(f'ALTER TABLE {table} ADD COLUMN {column} {definition}')
    except sqlite3.OperationalError:
        pass


def migrate_db():
    """数据库迁移：补充新字段并填充默认值"""
    conn = get_db()
    cursor = conn.cursor()

    # 新增字段
    _add_column(cursor, 'students', 'cohort', 'TEXT')
    _add_column(cursor, 'students', 'graduation_year', 'TEXT')
    _add_column(cursor, 'classes', 'cohort', 'TEXT')
    _add_column(cursor, 'courses', 'mode', 'TEXT DEFAULT "offline"')
    _add_column(cursor, 'course_attendances', 'mode', 'TEXT')

    # 为已有数据推算级次和毕业届
    current_year = datetime.now().year
    cursor.execute('SELECT id, grade, cohort FROM students')
    for row in cursor.fetchall():
        if not row['cohort'] and row['grade'] in GRADE_TO_COHORT_OFFSET:
            cohort = (current_year + GRADE_TO_COHORT_OFFSET[row['grade']]) % 100
            cohort_str = f'{cohort:02d}'
            graduation_str = compute_graduation_year(cohort)
            cursor.execute(
                'UPDATE students SET cohort = ?, graduation_year = ? WHERE id = ?',
                (cohort_str, graduation_str, row['id'])
            )

    cursor.execute('SELECT id, grade, cohort FROM classes')
    for row in cursor.fetchall():
        if not row['cohort'] and row['grade'] in GRADE_TO_COHORT_OFFSET:
            cohort = (current_year + GRADE_TO_COHORT_OFFSET[row['grade']]) % 100
            cursor.execute('UPDATE classes SET cohort = ? WHERE id = ?', (f'{cohort:02d}', row['id']))

    # 为已有课程的出勤记录补充默认参与方式
    cursor.execute('''
        UPDATE course_attendances SET mode = 'offline'
        WHERE mode IS NULL OR mode = ''
    ''')

    conn.commit()
    conn.close()


def compute_graduation_year(cohort):
    """由级次计算毕业届次：26级（2026年入学） -> 29届（2029年毕业）"""
    if cohort is None:
        return None
    try:
        c = int(cohort)
        return f'{(c + 3) % 100:02d}'
    except (ValueError, TypeError):
        return None


def _to_int(value, default=None):
    """将表单值转为整数"""
    if value is None or value == '':
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def _to_float(value, default=None):
    """将表单值转为浮点数"""
    if value is None or value == '':
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def get_db():
    """获取数据库连接"""
    conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    """初始化数据库表结构"""
    os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)
    
    conn = get_db()
    cursor = conn.cursor()
    
    # 学员表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT,
            wechat TEXT,
            school TEXT,
            grade TEXT,
            cohort TEXT,
            graduation_year TEXT,
            parent_name TEXT,
            parent_phone TEXT,
            address TEXT,
            status TEXT DEFAULT 'active',
            note TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # 班级表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS classes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            grade TEXT,
            cohort TEXT,
            subject TEXT,
            max_students INTEGER DEFAULT 20,
            teacher_name TEXT,
            status TEXT DEFAULT 'active',
            description TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # 班级学员关系表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS class_students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            class_id INTEGER NOT NULL,
            student_id INTEGER NOT NULL,
            join_date TEXT,
            status TEXT DEFAULT 'active',
            FOREIGN KEY (class_id) REFERENCES classes(id) ON DELETE CASCADE,
            FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE,
            UNIQUE(class_id, student_id)
        )
    ''')
    
    # 课程表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS courses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            class_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            scheduled_at TEXT,
            duration INTEGER DEFAULT 120,
            location TEXT,
            mode TEXT DEFAULT 'offline',
            status TEXT DEFAULT 'planned',
            description TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (class_id) REFERENCES classes(id) ON DELETE CASCADE
        )
    ''')

    # 出勤表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS course_attendances (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            course_id INTEGER NOT NULL,
            student_id INTEGER NOT NULL,
            status TEXT DEFAULT 'present',
            mode TEXT,
            note TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE CASCADE,
            FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE,
            UNIQUE(course_id, student_id)
        )
    ''')
    
    # 成绩表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS grades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            class_id INTEGER,
            exam_name TEXT NOT NULL,
            subject TEXT,
            score REAL NOT NULL,
            max_score REAL DEFAULT 100,
            exam_date TEXT,
            note TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE,
            FOREIGN KEY (class_id) REFERENCES classes(id) ON DELETE SET NULL
        )
    ''')
    
    # 作业表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS assignments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            class_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            content TEXT,
            deadline TEXT,
            status TEXT DEFAULT 'active',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (class_id) REFERENCES classes(id) ON DELETE CASCADE
        )
    ''')
    
    # 作业提交表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS assignment_submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            assignment_id INTEGER NOT NULL,
            student_id INTEGER NOT NULL,
            status TEXT DEFAULT 'pending',
            score REAL,
            submitted_at TEXT,
            note TEXT,
            FOREIGN KEY (assignment_id) REFERENCES assignments(id) ON DELETE CASCADE,
            FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE,
            UNIQUE(assignment_id, student_id)
        )
    ''')
    
    # 缴费表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            class_id INTEGER,
            amount REAL NOT NULL,
            type TEXT DEFAULT 'tuition',
            status TEXT DEFAULT 'paid',
            paid_at TEXT,
            due_date TEXT,
            note TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE,
            FOREIGN KEY (class_id) REFERENCES classes(id) ON DELETE SET NULL
        )
    ''')
    
    # 用户表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT DEFAULT 'teacher',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # 创建索引优化查询
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_students_name ON students(name)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_students_grade ON students(grade)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_students_cohort ON students(cohort)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_class_students_class ON class_students(class_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_class_students_student ON class_students(student_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_courses_class ON courses(class_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_courses_date ON courses(scheduled_at)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_grades_student ON grades(student_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_payments_student ON payments(student_id)')
    
    conn.commit()
    conn.close()

    # 执行迁移（新增字段、填充默认值）
    migrate_db()


def row_to_dict(row):
    """将 sqlite3.Row 转换为字典"""
    if row is None:
        return None
    return dict(row)


# ===== 学员相关操作 =====

def create_student(data):
    conn = get_db()
    cursor = conn.cursor()
    cohort = data.get('cohort')
    graduation_year = compute_graduation_year(cohort)
    cursor.execute('''
        INSERT INTO students (name, phone, wechat, school, grade, cohort, graduation_year,
                              parent_name, parent_phone, address, status, note)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        data.get('name') or None, data.get('phone'), data.get('wechat'), data.get('school'),
        data.get('grade'), cohort, graduation_year,
        data.get('parent_name'), data.get('parent_phone'),
        data.get('address'), data.get('status', 'active'), data.get('note')
    ))
    conn.commit()
    student_id = cursor.lastrowid
    conn.close()
    return student_id


def update_student(student_id, data):
    conn = get_db()
    cursor = conn.cursor()
    cohort = data.get('cohort')
    graduation_year = compute_graduation_year(cohort)
    cursor.execute('''
        UPDATE students SET
            name = ?, phone = ?, wechat = ?, school = ?, grade = ?, cohort = ?,
            graduation_year = ?, parent_name = ?, parent_phone = ?, address = ?,
            status = ?, note = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
    ''', (
        data.get('name') or None, data.get('phone'), data.get('wechat'), data.get('school'),
        data.get('grade'), cohort, graduation_year,
        data.get('parent_name'), data.get('parent_phone'),
        data.get('address'), data.get('status', 'active'), data.get('note'), student_id
    ))
    conn.commit()
    conn.close()


def get_student(student_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM students WHERE id = ?', (student_id,))
    row = cursor.fetchone()
    conn.close()
    return row_to_dict(row)


def find_student_by_name(name):
    """按姓名查找学员"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM students WHERE name = ? ORDER BY cohort DESC LIMIT 1', (name,))
    row = cursor.fetchone()
    conn.close()
    return row_to_dict(row)


def get_students(search=None, grade=None, cohort=None, status=None, limit=50, offset=0):
    conn = get_db()
    cursor = conn.cursor()
    
    query = 'SELECT * FROM students WHERE 1=1'
    params = []
    
    if search:
        query += ' AND (name LIKE ? OR phone LIKE ? OR school LIKE ?)'
        params.extend([f'%{search}%', f'%{search}%', f'%{search}%'])
    
    if grade:
        query += ' AND grade = ?'
        params.append(grade)
    
    if cohort:
        query += ' AND cohort = ?'
        params.append(cohort)
    
    if status:
        query += ' AND status = ?'
        params.append(status)
    
    query += ' ORDER BY cohort DESC, created_at DESC LIMIT ? OFFSET ?'
    params.extend([limit, offset])
    
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return [row_to_dict(row) for row in rows]


def count_students(search=None, grade=None, cohort=None, status=None):
    conn = get_db()
    cursor = conn.cursor()
    
    query = 'SELECT COUNT(*) as count FROM students WHERE 1=1'
    params = []
    
    if search:
        query += ' AND (name LIKE ? OR phone LIKE ? OR school LIKE ?)'
        params.extend([f'%{search}%', f'%{search}%', f'%{search}%'])
    
    if grade:
        query += ' AND grade = ?'
        params.append(grade)
    
    if cohort:
        query += ' AND cohort = ?'
        params.append(cohort)
    
    if status:
        query += ' AND status = ?'
        params.append(status)
    
    cursor.execute(query, params)
    row = cursor.fetchone()
    conn.close()
    return row['count']


def batch_update_students(student_ids, fields):
    """批量更新学员字段，fields 为字典"""
    if not student_ids or not fields:
        return 0

    allowed_fields = {'grade', 'cohort', 'status', 'school', 'note'}
    updates = {k: v for k, v in fields.items() if k in allowed_fields and v is not None}
    if not updates:
        return 0

    if 'cohort' in updates:
        updates['graduation_year'] = compute_graduation_year(updates['cohort'])

    conn = get_db()
    cursor = conn.cursor()
    placeholders = ','.join('?' * len(student_ids))
    set_clause = ', '.join(f'{k} = ?' for k in updates.keys())
    params = list(updates.values()) + [int(sid) for sid in student_ids]
    sql = f'UPDATE students SET {set_clause}, updated_at = CURRENT_TIMESTAMP WHERE id IN ({placeholders})'
    cursor.execute(sql, params)
    conn.commit()
    affected = cursor.rowcount
    conn.close()
    return affected


def batch_add_students_to_class(student_ids, class_id):
    """批量将学员加入班级"""
    if not student_ids or not class_id:
        return 0
    conn = get_db()
    cursor = conn.cursor()
    today = datetime.now().strftime('%Y-%m-%d')
    count = 0
    for sid in student_ids:
        try:
            cursor.execute('''
                INSERT INTO class_students (class_id, student_id, join_date, status)
                VALUES (?, ?, ?, ?)
            ''', (int(class_id), int(sid), today, 'active'))
            count += 1
        except sqlite3.IntegrityError:
            pass
    conn.commit()
    conn.close()
    return count


def batch_import_students(rows):
    """批量导入学员，rows 为字典列表；返回 (成功数, 错误列表)"""
    errors = []
    success = 0
    conn = get_db()
    cursor = conn.cursor()
    for idx, row in enumerate(rows, 1):
        name = row.get('name', '').strip()
        if not name:
            errors.append(f'第 {idx} 行：姓名不能为空')
            continue
        cohort = row.get('cohort', '').strip()
        graduation_year = compute_graduation_year(cohort)
        try:
            cursor.execute('''
                INSERT INTO students (name, phone, wechat, school, grade, cohort, graduation_year,
                                      parent_name, parent_phone, address, status, note)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                name, row.get('phone'), row.get('wechat'), row.get('school'),
                row.get('grade'), cohort, graduation_year,
                row.get('parent_name'), row.get('parent_phone'),
                row.get('address'), row.get('status', 'active'), row.get('note')
            ))
            success += 1
        except sqlite3.Error as e:
            errors.append(f'第 {idx} 行：{e}')
    conn.commit()
    conn.close()
    return success, errors


def get_distinct_cohorts():
    """获取所有不重复的级次"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT DISTINCT cohort FROM students WHERE cohort IS NOT NULL AND cohort != "" ORDER BY cohort DESC')
    rows = cursor.fetchall()
    conn.close()
    return [row['cohort'] for row in rows]


def delete_student(student_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM students WHERE id = ?', (student_id,))
    conn.commit()
    conn.close()


def get_student_classes(student_id):
    """获取学员所在班级"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT c.*, cs.join_date, cs.status as enrollment_status
        FROM classes c
        JOIN class_students cs ON c.id = cs.class_id
        WHERE cs.student_id = ?
        ORDER BY cs.join_date DESC
    ''', (student_id,))
    rows = cursor.fetchall()
    conn.close()
    return [row_to_dict(row) for row in rows]


def get_student_grades(student_id):
    """获取学员成绩"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT g.*, c.name as class_name,
               CASE
                   WHEN g.score >= 90 THEN 'excellent'
                   WHEN g.score >= 60 THEN 'pass'
                   ELSE 'fail'
               END as level
        FROM grades g
        LEFT JOIN classes c ON g.class_id = c.id
        WHERE g.student_id = ?
        ORDER BY g.exam_date DESC, g.created_at DESC
    ''', (student_id,))
    rows = cursor.fetchall()
    conn.close()
    return [row_to_dict(row) for row in rows]


# ===== 班级相关操作 =====

def create_class(data):
    conn = get_db()
    cursor = conn.cursor()
    max_students = _to_int(data.get('max_students'), 20)
    cursor.execute('''
        INSERT INTO classes (name, grade, cohort, subject, max_students, teacher_name, status, description)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        data.get('name') or None, data.get('grade'), data.get('cohort'), data.get('subject'),
        max_students, data.get('teacher_name'),
        data.get('status', 'active'), data.get('description')
    ))
    conn.commit()
    class_id = cursor.lastrowid
    conn.close()
    return class_id


def update_class(class_id, data):
    conn = get_db()
    cursor = conn.cursor()
    max_students = _to_int(data.get('max_students'), 20)
    cursor.execute('''
        UPDATE classes SET
            name = ?, grade = ?, cohort = ?, subject = ?, max_students = ?,
            teacher_name = ?, status = ?, description = ?
        WHERE id = ?
    ''', (
        data.get('name') or None, data.get('grade'), data.get('cohort'), data.get('subject'),
        max_students, data.get('teacher_name'),
        data.get('status', 'active'), data.get('description'), class_id
    ))
    conn.commit()
    conn.close()


def get_class(class_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM classes WHERE id = ?', (class_id,))
    row = cursor.fetchone()
    conn.close()
    return row_to_dict(row)


def get_classes(status=None):
    conn = get_db()
    cursor = conn.cursor()
    query = 'SELECT * FROM classes WHERE 1=1'
    params = []
    if status:
        query += ' AND status = ?'
        params.append(status)
    query += ' ORDER BY created_at DESC'
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return [row_to_dict(row) for row in rows]


def delete_class(class_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM classes WHERE id = ?', (class_id,))
    conn.commit()
    conn.close()


def get_class_students(class_id):
    """获取班级学员"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT s.*, cs.join_date, cs.status as enrollment_status
        FROM students s
        JOIN class_students cs ON s.id = cs.student_id
        WHERE cs.class_id = ?
        ORDER BY cs.join_date DESC
    ''', (class_id,))
    rows = cursor.fetchall()
    conn.close()
    return [row_to_dict(row) for row in rows]


def add_student_to_class(class_id, student_id):
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO class_students (class_id, student_id, join_date, status)
            VALUES (?, ?, ?, ?)
        ''', (class_id, student_id, datetime.now().strftime('%Y-%m-%d'), 'active'))
        conn.commit()
    except sqlite3.IntegrityError:
        pass
    conn.close()


def remove_student_from_class(class_id, student_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM class_students WHERE class_id = ? AND student_id = ?', (class_id, student_id))
    conn.commit()
    conn.close()


# ===== 课程相关操作 =====

def create_course(data):
    conn = get_db()
    cursor = conn.cursor()
    class_id = _to_int(data.get('class_id'))
    duration = _to_int(data.get('duration'), 120)
    mode = data.get('mode', 'offline') or 'offline'
    cursor.execute('''
        INSERT INTO courses (class_id, title, scheduled_at, duration, location, mode, status, description)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        class_id, data.get('title') or None, data.get('scheduled_at'),
        duration, data.get('location'), mode,
        data.get('status', 'planned'), data.get('description')
    ))
    conn.commit()
    course_id = cursor.lastrowid
    conn.close()
    return course_id


def update_course(course_id, data):
    conn = get_db()
    cursor = conn.cursor()
    class_id = _to_int(data.get('class_id'))
    duration = _to_int(data.get('duration'), 120)
    mode = data.get('mode', 'offline') or 'offline'
    cursor.execute('''
        UPDATE courses SET
            class_id = ?, title = ?, scheduled_at = ?, duration = ?,
            location = ?, mode = ?, status = ?, description = ?
        WHERE id = ?
    ''', (
        class_id, data.get('title') or None, data.get('scheduled_at'),
        duration, data.get('location'), mode,
        data.get('status', 'planned'), data.get('description'), course_id
    ))
    conn.commit()
    conn.close()


def get_course(course_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT c.*, cls.name as class_name, cls.grade
        FROM courses c
        LEFT JOIN classes cls ON c.class_id = cls.id
        WHERE c.id = ?
    ''', (course_id,))
    row = cursor.fetchone()
    conn.close()
    return row_to_dict(row)


def get_courses(class_id=None, start_date=None, end_date=None, limit=100):
    conn = get_db()
    cursor = conn.cursor()
    query = '''
        SELECT c.*, cls.name as class_name, cls.grade
        FROM courses c
        LEFT JOIN classes cls ON c.class_id = cls.id
        WHERE 1=1
    '''
    params = []
    if class_id:
        query += ' AND c.class_id = ?'
        params.append(class_id)
    if start_date:
        query += ' AND c.scheduled_at >= ?'
        params.append(start_date)
    if end_date:
        query += ' AND c.scheduled_at <= ?'
        params.append(end_date)
    query += ' ORDER BY c.scheduled_at DESC LIMIT ?'
    params.append(limit)
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return [row_to_dict(row) for row in rows]


def delete_course(course_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM courses WHERE id = ?', (course_id,))
    conn.commit()
    conn.close()


# ===== 出勤相关操作 =====

def set_attendance(course_id, student_id, status, note=None, mode=None):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO course_attendances (course_id, student_id, status, note, mode)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(course_id, student_id) DO UPDATE SET
            status = excluded.status,
            note = excluded.note,
            mode = excluded.mode
    ''', (course_id, student_id, status, note, mode))
    conn.commit()
    conn.close()


def get_course_attendances(course_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT a.*, s.name as student_name
        FROM course_attendances a
        JOIN students s ON a.student_id = s.id
        WHERE a.course_id = ?
    ''', (course_id,))
    rows = cursor.fetchall()
    conn.close()
    return [row_to_dict(row) for row in rows]


# ===== 成绩相关操作 =====

def create_grade(data):
    conn = get_db()
    cursor = conn.cursor()
    student_id = _to_int(data.get('student_id'))
    class_id = _to_int(data.get('class_id'))
    score = _to_float(data.get('score'))
    max_score = _to_float(data.get('max_score'), 100)
    cursor.execute('''
        INSERT INTO grades (student_id, class_id, exam_name, subject, score, max_score, exam_date, note)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        student_id, class_id, data.get('exam_name') or None,
        data.get('subject'), score, max_score,
        data.get('exam_date'), data.get('note')
    ))
    conn.commit()
    grade_id = cursor.lastrowid
    conn.close()
    return grade_id


def update_grade(grade_id, data):
    conn = get_db()
    cursor = conn.cursor()
    student_id = _to_int(data.get('student_id'))
    class_id = _to_int(data.get('class_id'))
    score = _to_float(data.get('score'))
    max_score = _to_float(data.get('max_score'), 100)
    cursor.execute('''
        UPDATE grades SET
            student_id = ?, class_id = ?, exam_name = ?, subject = ?,
            score = ?, max_score = ?, exam_date = ?, note = ?
        WHERE id = ?
    ''', (
        student_id, class_id, data.get('exam_name') or None,
        data.get('subject'), score, max_score,
        data.get('exam_date'), data.get('note'), grade_id
    ))
    conn.commit()
    conn.close()


def get_grade(grade_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM grades WHERE id = ?', (grade_id,))
    row = cursor.fetchone()
    conn.close()
    return row_to_dict(row)


def get_grades(student_id=None, class_id=None, exam_name=None, limit=100):
    conn = get_db()
    cursor = conn.cursor()
    query = '''
        SELECT g.*, s.name as student_name, c.name as class_name,
               CASE
                   WHEN g.score >= 90 THEN 'excellent'
                   WHEN g.score >= 60 THEN 'pass'
                   ELSE 'fail'
               END as level
        FROM grades g
        JOIN students s ON g.student_id = s.id
        LEFT JOIN classes c ON g.class_id = c.id
        WHERE 1=1
    '''
    params = []
    if student_id:
        query += ' AND g.student_id = ?'
        params.append(student_id)
    if class_id:
        query += ' AND g.class_id = ?'
        params.append(class_id)
    if exam_name:
        query += ' AND g.exam_name LIKE ?'
        params.append(f'%{exam_name}%')
    query += ' ORDER BY g.exam_date DESC, g.created_at DESC LIMIT ?'
    params.append(limit)
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return [row_to_dict(row) for row in rows]


def delete_grade(grade_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM grades WHERE id = ?', (grade_id,))
    conn.commit()
    conn.close()


def export_grades_to_csv(class_id=None, exam_name=None):
    """导出成绩为 CSV（UTF-8 BOM，Excel 可直接打开）"""
    grades = get_grades(class_id=class_id, exam_name=exam_name, limit=10000)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['学员姓名', '班级', '考试名称', '科目', '得分', '满分', '考试日期', '备注'])
    for g in grades:
        writer.writerow([
            g['student_name'], g['class_name'] or '', g['exam_name'],
            g['subject'] or '', g['score'], g['max_score'],
            g['exam_date'] or '', g['note'] or ''
        ])
    return '\ufeff' + output.getvalue()


def import_grades_from_csv(csv_content, default_class_id=None):
    """从 CSV 导入成绩；返回 (成功数, 错误列表)。支持按表头自动映射列。"""
    reader = smart_csv_read(csv_content)
    rows = list(reader)
    if not rows:
        return 0, ['文件为空']

    header = [h.strip() for h in rows[0]]
    # 列名映射
    name_cols = ['学员姓名', '姓名', 'name', '学生姓名']
    class_cols = ['班级', 'class', '班级名称']
    exam_cols = ['考试名称', 'exam', '考试']
    subject_cols = ['科目', 'subject']
    score_cols = ['得分', '分数', '成绩', 'score']
    max_cols = ['满分', 'max_score']
    date_cols = ['考试日期', '日期', 'exam_date']
    note_cols = ['备注', 'note']

    def find_col(candidates):
        for c in candidates:
            if c in header:
                return header.index(c)
        return None

    name_idx = find_col(name_cols)
    if name_idx is None:
        # 无表头，按固定顺序
        name_idx, class_idx, exam_idx, subject_idx = 0, 1, 2, 3
        score_idx, max_idx, date_idx, note_idx = 4, 5, 6, 7
        start = 0
    else:
        class_idx = find_col(class_cols)
        exam_idx = find_col(exam_cols)
        subject_idx = find_col(subject_cols)
        score_idx = find_col(score_cols)
        max_idx = find_col(max_cols)
        date_idx = find_col(date_cols)
        note_idx = find_col(note_cols)
        start = 1

    errors = []
    success = 0
    conn = get_db()
    cursor = conn.cursor()

    def get_value(row, idx, default=''):
        if idx is None or idx >= len(row):
            return default
        return row[idx].strip()

    for idx, row in enumerate(rows[start:], 1):
        if not row or not row[0].strip():
            continue
        try:
            student_name = get_value(row, name_idx)
            class_name = get_value(row, class_idx)
            exam_name = get_value(row, exam_idx)
            subject = get_value(row, subject_idx)
            score = _to_float(get_value(row, score_idx))
            max_score = _to_float(get_value(row, max_idx), 100)
            exam_date = get_value(row, date_idx)
            note = get_value(row, note_idx)

            if not student_name:
                errors.append(f'第 {idx} 行：学员姓名不能为空')
                continue
            if score is None:
                errors.append(f'第 {idx} 行：分数格式错误')
                continue
            if not exam_name:
                errors.append(f'第 {idx} 行：考试名称不能为空')
                continue

            # 查找学员
            cursor.execute('SELECT id FROM students WHERE name = ? LIMIT 1', (student_name,))
            student_row = cursor.fetchone()
            if not student_row:
                errors.append(f'第 {idx} 行：找不到学员 "{student_name}"')
                continue
            student_id = student_row['id']

            # 查找班级
            class_id = default_class_id
            if class_name:
                cursor.execute('SELECT id FROM classes WHERE name = ? LIMIT 1', (class_name,))
                class_row = cursor.fetchone()
                if class_row:
                    class_id = class_row['id']

            cursor.execute('''
                INSERT INTO grades (student_id, class_id, exam_name, subject, score, max_score, exam_date, note)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (student_id, class_id, exam_name, subject or None, score, max_score, exam_date or None, note or None))
            success += 1
        except Exception as e:
            errors.append(f'第 {idx} 行：{e}')

    conn.commit()
    conn.close()
    return success, errors


def get_grade_statistics(class_id=None, exam_name=None):
    """获取成绩统计"""
    conn = get_db()
    cursor = conn.cursor()
    query = '''
        SELECT 
            COUNT(*) as count,
            AVG(score) as avg_score,
            MAX(score) as max_score,
            MIN(score) as min_score
        FROM grades g
        WHERE 1=1
    '''
    params = []
    if class_id:
        query += ' AND g.class_id = ?'
        params.append(class_id)
    if exam_name:
        query += ' AND g.exam_name = ?'
        params.append(exam_name)
    cursor.execute(query, params)
    row = cursor.fetchone()
    conn.close()
    return row_to_dict(row)


def get_grade_ranking(class_id=None, exam_name=None):
    """获取成绩排名"""
    conn = get_db()
    cursor = conn.cursor()
    query = '''
        SELECT g.*, s.name as student_name,
               RANK() OVER (ORDER BY g.score DESC) as rank
        FROM grades g
        JOIN students s ON g.student_id = s.id
        WHERE 1=1
    '''
    params = []
    if class_id:
        query += ' AND g.class_id = ?'
        params.append(class_id)
    if exam_name:
        query += ' AND g.exam_name = ?'
        params.append(exam_name)
    query += ' ORDER BY g.score DESC'
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return [row_to_dict(row) for row in rows]


# ===== 作业相关操作 =====

def create_assignment(data):
    conn = get_db()
    cursor = conn.cursor()
    class_id = _to_int(data.get('class_id'))
    cursor.execute('''
        INSERT INTO assignments (class_id, title, content, deadline, status)
        VALUES (?, ?, ?, ?, ?)
    ''', (
        class_id, data.get('title') or None, data.get('content'),
        data.get('deadline'), data.get('status', 'active')
    ))
    conn.commit()
    assignment_id = cursor.lastrowid
    conn.close()
    return assignment_id


def update_assignment(assignment_id, data):
    conn = get_db()
    cursor = conn.cursor()
    class_id = _to_int(data.get('class_id'))
    cursor.execute('''
        UPDATE assignments SET
            class_id = ?, title = ?, content = ?, deadline = ?, status = ?
        WHERE id = ?
    ''', (
        class_id, data.get('title') or None, data.get('content'),
        data.get('deadline'), data.get('status', 'active'), assignment_id
    ))
    conn.commit()
    conn.close()


def get_assignment(assignment_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM assignments WHERE id = ?', (assignment_id,))
    row = cursor.fetchone()
    conn.close()
    return row_to_dict(row)


def get_assignments(class_id=None, status=None):
    conn = get_db()
    cursor = conn.cursor()
    query = '''
        SELECT a.*, c.name as class_name
        FROM assignments a
        LEFT JOIN classes c ON a.class_id = c.id
        WHERE 1=1
    '''
    params = []
    if class_id:
        query += ' AND a.class_id = ?'
        params.append(class_id)
    if status:
        query += ' AND a.status = ?'
        params.append(status)
    query += ' ORDER BY a.created_at DESC'
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return [row_to_dict(row) for row in rows]


def delete_assignment(assignment_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM assignments WHERE id = ?', (assignment_id,))
    conn.commit()
    conn.close()


# ===== 作业提交相关操作 =====

def create_assignment_submission(data):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO assignment_submissions (assignment_id, student_id, status, score, submitted_at, note)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (
        data.get('assignment_id'), data.get('student_id'), data.get('status', 'pending'),
        data.get('score'), data.get('submitted_at'), data.get('note')
    ))
    conn.commit()
    submission_id = cursor.lastrowid
    conn.close()
    return submission_id


def update_assignment_submission(assignment_id, student_id, data):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO assignment_submissions (assignment_id, student_id, status, score, submitted_at, note)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(assignment_id, student_id) DO UPDATE SET
            status = excluded.status,
            score = excluded.score,
            submitted_at = excluded.submitted_at,
            note = excluded.note
    ''', (
        assignment_id, student_id, data.get('status', 'pending'),
        data.get('score'), data.get('submitted_at'), data.get('note')
    ))
    conn.commit()
    conn.close()


def get_assignment_submissions(assignment_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT s.*, st.name as student_name
        FROM assignment_submissions s
        JOIN students st ON s.student_id = st.id
        WHERE s.assignment_id = ?
    ''', (assignment_id,))
    rows = cursor.fetchall()
    conn.close()
    return [row_to_dict(row) for row in rows]


def get_assignment_stats(assignment_id):
    """获取作业提交统计"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN status = 'submitted' THEN 1 ELSE 0 END) as submitted,
            SUM(CASE WHEN status = 'late' THEN 1 ELSE 0 END) as late,
            SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as pending
        FROM assignment_submissions
        WHERE assignment_id = ?
    ''', (assignment_id,))
    row = cursor.fetchone()
    conn.close()
    return row_to_dict(row)


def get_class_assignment_stats(class_id):
    """获取班级下所有作业的提交统计"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT 
            a.id, a.title, a.deadline,
            COUNT(s.id) as total,
            SUM(CASE WHEN s.status = 'submitted' THEN 1 ELSE 0 END) as submitted,
            SUM(CASE WHEN s.status = 'late' THEN 1 ELSE 0 END) as late,
            SUM(CASE WHEN s.status = 'pending' THEN 1 ELSE 0 END) as pending
        FROM assignments a
        LEFT JOIN assignment_submissions s ON a.id = s.assignment_id
        WHERE a.class_id = ?
        GROUP BY a.id
        ORDER BY a.created_at DESC
    ''', (class_id,))
    rows = cursor.fetchall()
    conn.close()
    return [row_to_dict(row) for row in rows]


def set_assignment_submission(assignment_id, student_id, status='submitted', score=None, note=None):
    """设置/更新单个学员的作业提交状态和成绩"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO assignment_submissions (assignment_id, student_id, status, score, submitted_at, note)
        VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, ?)
        ON CONFLICT(assignment_id, student_id) DO UPDATE SET
            status = excluded.status,
            score = excluded.score,
            note = excluded.note
    ''', (assignment_id, student_id, status, _to_float(score) if score else None, note))
    conn.commit()
    conn.close()


def import_assignment_scores(assignment_id, csv_content):
    """从 CSV 导入作业成绩，返回 (成功数, 错误列表)
    导入逻辑：CSV 中包含的学员更新成绩为 submitted，不在 CSV 中的学员标注为 pending（未提交）"""
    reader = smart_csv_read(csv_content)
    rows = list(reader)
    if not rows:
        return 0, ['文件为空']

    # 解析表头
    header = [h.strip() for h in rows[0]]
    name_candidates = ['姓名', 'name', '学员姓名']
    score_candidates = ['得分', '成绩', '分数', 'score']
    name_idx = next((header.index(c) for c in name_candidates if c in header), 0)
    score_idx = next((header.index(c) for c in score_candidates if c in header), 1)
    start = 1

    conn = get_db()
    cursor = conn.cursor()

    # 获取该作业所属班级的所有学员
    cursor.execute('SELECT class_id FROM assignments WHERE id = ?', (assignment_id,))
    assignment_row = cursor.fetchone()
    if not assignment_row:
        conn.close()
        return 0, ['作业不存在']
    class_id = assignment_row['class_id']
    
    # 获取班级学员
    cursor.execute('SELECT cs.student_id, s.name FROM class_students cs JOIN students s ON cs.student_id = s.id WHERE cs.class_id = ?', (class_id,))
    class_students = {row['student_id']: row['name'] for row in cursor.fetchall()}
    
    imported_ids = set()
    errors = []
    success = 0

    for idx, row in enumerate(rows[start:], 1):
        if not row or not row[0].strip():
            continue
        try:
            student_name = row[name_idx].strip() if name_idx < len(row) else ''
            score = _to_float(row[score_idx].strip() if score_idx < len(row) else '')

            if not student_name:
                errors.append(f'第 {idx} 行：学员姓名不能为空')
                continue
            if score is None:
                errors.append(f'第 {idx} 行：分数格式错误')
                continue

            # 查找学员ID
            found = None
            for sid, sname in class_students.items():
                if sname == student_name:
                    found = sid
                    break

            if not found:
                errors.append(f'第 {idx} 行：找不到学员 "{student_name}"（不在该班级中）')
                continue

            cursor.execute('''
                INSERT INTO assignment_submissions (assignment_id, student_id, status, score, submitted_at, note)
                VALUES (?, ?, 'submitted', ?, CURRENT_TIMESTAMP, '')
                ON CONFLICT(assignment_id, student_id) DO UPDATE SET
                    status = 'submitted',
                    score = excluded.score
            ''', (assignment_id, found, score))
            imported_ids.add(found)
            success += 1
        except Exception as e:
            errors.append(f'第 {idx} 行：{e}')

    # 未导入的学员标记为 pending
    for sid in class_students:
        if sid not in imported_ids:
            cursor.execute('''
                INSERT INTO assignment_submissions (assignment_id, student_id, status, score, note)
                VALUES (?, ?, 'pending', NULL, '')
                ON CONFLICT(assignment_id, student_id) DO UPDATE SET
                    status = 'pending',
                    score = NULL
            ''', (assignment_id, sid))

    conn.commit()
    conn.close()
    return success, errors


def get_student_assignment_scores(student_id):
    """获取学员所有作业成绩（用于学习追踪图表）"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT asub.score, asub.submitted_at, asub.status,
               a.title as assignment_title, a.deadline,
               c.name as class_name
        FROM assignment_submissions asub
        JOIN assignments a ON asub.assignment_id = a.id
        LEFT JOIN classes c ON a.class_id = c.id
        WHERE asub.student_id = ? AND asub.score IS NOT NULL
        ORDER BY a.deadline ASC, a.created_at ASC
    ''', (student_id,))
    rows = cursor.fetchall()
    conn.close()
    return [row_to_dict(row) for row in rows]


def get_assignments_with_sort(class_id=None, sort_by=None):
    """获取作业列表，支持按平均成绩排序"""
    conn = get_db()
    cursor = conn.cursor()
    query = '''
        SELECT a.*, c.name as class_name
        FROM assignments a
        LEFT JOIN classes c ON a.class_id = c.id
        WHERE 1=1
    '''
    params = []
    if class_id:
        query += ' AND a.class_id = ?'
        params.append(class_id)
    
    if sort_by == 'avg_score':
        query += '''
            ORDER BY (
                SELECT AVG(CAST(asub.score AS REAL))
                FROM assignment_submissions asub
                WHERE asub.assignment_id = a.id AND asub.score IS NOT NULL
            ) DESC NULLS LAST
        '''
    else:
        query += ' ORDER BY a.created_at DESC'
    
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return [row_to_dict(row) for row in rows]


# ===== 缴费相关操作 =====

def create_payment(data):
    conn = get_db()
    cursor = conn.cursor()
    student_id = _to_int(data.get('student_id'))
    class_id = _to_int(data.get('class_id'))
    amount = _to_float(data.get('amount'))
    cursor.execute('''
        INSERT INTO payments (student_id, class_id, amount, type, status, paid_at, due_date, note)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        student_id, class_id, amount,
        data.get('type', 'tuition'), data.get('status', 'paid'),
        data.get('paid_at'), data.get('due_date'), data.get('note')
    ))
    conn.commit()
    payment_id = cursor.lastrowid
    conn.close()
    return payment_id


def update_payment(payment_id, data):
    conn = get_db()
    cursor = conn.cursor()
    student_id = _to_int(data.get('student_id'))
    class_id = _to_int(data.get('class_id'))
    amount = _to_float(data.get('amount'))
    cursor.execute('''
        UPDATE payments SET
            student_id = ?, class_id = ?, amount = ?, type = ?,
            status = ?, paid_at = ?, due_date = ?, note = ?
        WHERE id = ?
    ''', (
        student_id, class_id, amount,
        data.get('type', 'tuition'), data.get('status', 'paid'),
        data.get('paid_at'), data.get('due_date'), data.get('note'), payment_id
    ))
    conn.commit()
    conn.close()


def get_payment(payment_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM payments WHERE id = ?', (payment_id,))
    row = cursor.fetchone()
    conn.close()
    return row_to_dict(row)


def get_payments(student_id=None, class_id=None, status=None):
    conn = get_db()
    cursor = conn.cursor()
    query = '''
        SELECT p.*, s.name as student_name, c.name as class_name
        FROM payments p
        JOIN students s ON p.student_id = s.id
        LEFT JOIN classes c ON p.class_id = c.id
        WHERE 1=1
    '''
    params = []
    if student_id:
        query += ' AND p.student_id = ?'
        params.append(student_id)
    if class_id:
        query += ' AND p.class_id = ?'
        params.append(class_id)
    if status:
        query += ' AND p.status = ?'
        params.append(status)
    query += ' ORDER BY p.created_at DESC'
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return [row_to_dict(row) for row in rows]


def delete_payment(payment_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM payments WHERE id = ?', (payment_id,))
    conn.commit()
    conn.close()


# ===== 仪表盘统计 =====

def get_dashboard_stats():
    conn = get_db()
    cursor = conn.cursor()
    
    stats = {}
    
    cursor.execute('SELECT COUNT(*) as count FROM students WHERE status = "active"')
    stats['total_students'] = cursor.fetchone()['count']
    
    cursor.execute('SELECT COUNT(*) as count FROM classes WHERE status = "active"')
    stats['total_classes'] = cursor.fetchone()['count']
    
    cursor.execute('SELECT COUNT(*) as count FROM courses WHERE status = "planned"')
    stats['total_courses'] = cursor.fetchone()['count']
    
    cursor.execute('SELECT COUNT(*) as count FROM payments WHERE status = "paid"')
    stats['total_payments'] = cursor.fetchone()['count']
    
    cursor.execute('SELECT COALESCE(SUM(amount), 0) as total FROM payments WHERE status = "paid"')
    stats['total_income'] = cursor.fetchone()['total'] or 0
    
    cursor.execute('SELECT COUNT(*) as count FROM payments WHERE status = "unpaid"')
    stats['unpaid_count'] = cursor.fetchone()['count']
    
    cursor.execute('''
        SELECT COUNT(*) as count FROM course_attendances a
        JOIN courses c ON a.course_id = c.id
        WHERE a.status = 'absent' AND c.scheduled_at >= date('now', '-7 days')
    ''')
    stats['recent_absences'] = cursor.fetchone()['count']
    
    cursor.execute('''
        SELECT c.*, cls.name as class_name, cls.grade
        FROM courses c
        LEFT JOIN classes cls ON c.class_id = cls.id
        WHERE c.scheduled_at >= date('now')
        AND c.status = 'planned'
        ORDER BY c.scheduled_at ASC
        LIMIT 5
    ''')
    stats['upcoming_courses'] = [row_to_dict(row) for row in cursor.fetchall()]
    
    conn.close()
    return stats


def get_grade_distribution():
    """获取成绩分布（用于图表）"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT 
            CASE 
                WHEN score >= 90 THEN '90-100'
                WHEN score >= 80 THEN '80-89'
                WHEN score >= 70 THEN '70-79'
                WHEN score >= 60 THEN '60-69'
                ELSE '60以下'
            END as range,
            COUNT(*) as count
        FROM grades
        GROUP BY range
        ORDER BY range
    ''')
    rows = cursor.fetchall()
    conn.close()
    
    distribution = [row_to_dict(row) for row in rows]
    total = sum(item['count'] for item in distribution)
    for item in distribution:
        item['percentage'] = round(item['count'] * 100 / total, 1) if total > 0 else 0
    
    return distribution


if __name__ == '__main__':
    init_db()
    print(f"数据库已初始化: {DATABASE_PATH}")
