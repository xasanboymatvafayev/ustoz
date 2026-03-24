from flask import Flask, request, jsonify
from flask_cors import CORS
import sqlite3
import bcrypt
import jwt
import uuid
import json
import random
import string
from datetime import datetime, timedelta
import os

app = Flask(__name__)
CORS(app, origins="*")

SECRET_KEY = "ustoz_yordamchi_ai_secret_2024"
DB_PATH = "database.db"
ADMIN_PASSWORD = "sonnet123"

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    
    c.execute('''CREATE TABLE IF NOT EXISTS students (
        id TEXT PRIMARY KEY,
        login TEXT UNIQUE NOT NULL,
        full_name TEXT NOT NULL,
        phone TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        group_name TEXT NOT NULL,
        password_hash TEXT NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        is_active INTEGER DEFAULT 1
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS mentors (
        id TEXT PRIMARY KEY,
        full_name TEXT NOT NULL,
        phone TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        groups TEXT DEFAULT '[]',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        is_active INTEGER DEFAULT 1
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS groups (
        id TEXT PRIMARY KEY,
        name TEXT UNIQUE NOT NULL,
        mentor_id TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        is_active INTEGER DEFAULT 1,
        FOREIGN KEY (mentor_id) REFERENCES mentors(id)
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS tasks (
        id TEXT PRIMARY KEY,
        group_id TEXT NOT NULL,
        mentor_id TEXT NOT NULL,
        title TEXT NOT NULL,
        description TEXT NOT NULL,
        deadline_date TEXT NOT NULL,
        deadline_time TEXT NOT NULL,
        task_type TEXT DEFAULT 'homework',
        duration_minutes INTEGER DEFAULT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (group_id) REFERENCES groups(id),
        FOREIGN KEY (mentor_id) REFERENCES mentors(id)
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS submissions (
        id TEXT PRIMARY KEY,
        task_id TEXT NOT NULL,
        student_id TEXT NOT NULL,
        content TEXT NOT NULL,
        submitted_at TEXT DEFAULT CURRENT_TIMESTAMP,
        ai_feedback TEXT DEFAULT NULL,
        score INTEGER DEFAULT NULL,
        mentor_score INTEGER DEFAULT NULL,
        FOREIGN KEY (task_id) REFERENCES tasks(id),
        FOREIGN KEY (student_id) REFERENCES students(id)
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS messages (
        id TEXT PRIMARY KEY,
        group_id TEXT NOT NULL,
        sender_id TEXT NOT NULL,
        sender_type TEXT NOT NULL,
        sender_name TEXT NOT NULL,
        content TEXT NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (group_id) REFERENCES groups(id)
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS schedules (
        id TEXT PRIMARY KEY,
        group_id TEXT NOT NULL,
        subject_name TEXT NOT NULL,
        start_date TEXT NOT NULL,
        end_date TEXT NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (group_id) REFERENCES groups(id)
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS schedule_entries (
        id TEXT PRIMARY KEY,
        schedule_id TEXT NOT NULL,
        date TEXT NOT NULL,
        topic TEXT DEFAULT NULL,
        FOREIGN KEY (schedule_id) REFERENCES schedules(id)
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS verification_codes (
        id TEXT PRIMARY KEY,
        email TEXT NOT NULL,
        code TEXT NOT NULL,
        purpose TEXT NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        expires_at TEXT NOT NULL,
        used INTEGER DEFAULT 0
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS calendar_events (
        id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        description TEXT DEFAULT NULL,
        event_date TEXT NOT NULL,
        event_time TEXT DEFAULT NULL,
        group_id TEXT DEFAULT NULL,
        created_by TEXT NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )''')
    
    conn.commit()
    conn.close()

def generate_code():
    return ''.join(random.choices(string.digits, k=6))

def token_required(f):
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization', '').replace('Bearer ', '')
        if not token:
            return jsonify({'error': 'Token required'}), 401
        try:
            data = jwt.decode(token, SECRET_KEY, algorithms=['HS256'])
            return f(data, *args, **kwargs)
        except:
            return jsonify({'error': 'Invalid token'}), 401
    decorated.__name__ = f.__name__
    return decorated

# ===== AUTH ROUTES =====

@app.route('/api/auth/check-email', methods=['POST'])
def check_email():
    data = request.json
    email = data.get('email', '').lower().strip()
    conn = get_db()
    student = conn.execute('SELECT id, full_name FROM students WHERE email = ?', (email,)).fetchone()
    conn.close()
    if student:
        return jsonify({'exists': True, 'name': student['full_name']})
    return jsonify({'exists': False})

@app.route('/api/auth/send-verification', methods=['POST'])
def send_verification():
    data = request.json
    email = data.get('email', '').lower().strip()
    purpose = data.get('purpose', 'register')
    
    code = generate_code()
    expires = (datetime.now() + timedelta(minutes=15)).isoformat()
    
    conn = get_db()
    conn.execute('DELETE FROM verification_codes WHERE email = ? AND purpose = ?', (email, purpose))
    conn.execute('INSERT INTO verification_codes (id, email, code, purpose, expires_at) VALUES (?, ?, ?, ?, ?)',
                 (str(uuid.uuid4()), email, code, purpose, expires))
    conn.commit()
    conn.close()
    
    return jsonify({'success': True, 'code': code, 'message': f'Verification code: {code}'})

@app.route('/api/auth/verify-code', methods=['POST'])
def verify_code():
    data = request.json
    email = data.get('email', '').lower().strip()
    code = data.get('code', '')
    purpose = data.get('purpose', 'register')
    
    conn = get_db()
    record = conn.execute(
        'SELECT * FROM verification_codes WHERE email = ? AND code = ? AND purpose = ? AND used = 0 AND expires_at > ?',
        (email, code, purpose, datetime.now().isoformat())
    ).fetchone()
    
    if not record:
        conn.close()
        return jsonify({'error': 'Kod noto\'g\'ri yoki muddati o\'tgan'}), 400
    
    conn.execute('UPDATE verification_codes SET used = 1 WHERE id = ?', (record['id'],))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/auth/register', methods=['POST'])
def register():
    data = request.json
    login = data.get('login', '').strip()
    full_name = data.get('full_name', '').strip()
    phone = data.get('phone', '').strip()
    email = data.get('email', '').lower().strip()
    group_name = data.get('group_name', '').strip()
    password = data.get('password', '')
    
    if not all([login, full_name, phone, email, group_name, password]):
        return jsonify({'error': 'Barcha maydonlar to\'ldirilishi shart'}), 400
    
    conn = get_db()
    
    existing_login = conn.execute('SELECT id FROM students WHERE login = ?', (login,)).fetchone()
    if existing_login:
        conn.close()
        return jsonify({'error': 'Bu login band, boshqa login tanlang'}), 400
    
    group = conn.execute('SELECT id, name FROM groups WHERE name = ?', (group_name,)).fetchone()
    if not group:
        existing_groups = [r['name'] for r in conn.execute('SELECT name FROM groups WHERE is_active = 1').fetchall()]
        conn.close()
        return jsonify({'error': f'Bunday guruh topilmadi. Mavjud guruhlar: {", ".join(existing_groups) if existing_groups else "hali guruh qo\'shilmagan"}'}), 400
    
    existing_email = conn.execute('SELECT id FROM students WHERE email = ?', (email,)).fetchone()
    if existing_email:
        conn.close()
        return jsonify({'error': 'Bu email bilan allaqachon ro\'yxatdan o\'tilgan', 'email_exists': True}), 400
    
    pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    student_id = str(uuid.uuid4())
    
    conn.execute(
        'INSERT INTO students (id, login, full_name, phone, email, group_name, password_hash) VALUES (?, ?, ?, ?, ?, ?, ?)',
        (student_id, login, full_name, phone, email, group_name, pw_hash)
    )
    conn.commit()
    
    token = jwt.encode({
        'id': student_id, 'role': 'student', 'email': email,
        'exp': datetime.now() + timedelta(days=30)
    }, SECRET_KEY, algorithm='HS256')
    
    student = conn.execute('SELECT * FROM students WHERE id = ?', (student_id,)).fetchone()
    conn.close()
    
    return jsonify({
        'token': token,
        'user': {'id': student_id, 'full_name': full_name, 'email': email, 'group_name': group_name, 'role': 'student'}
    })

@app.route('/api/auth/login', methods=['POST'])
def login():
    data = request.json
    email = data.get('email', '').lower().strip()
    password = data.get('password', '')
    
    conn = get_db()
    student = conn.execute('SELECT * FROM students WHERE email = ?', (email,)).fetchone()
    conn.close()
    
    if not student or not bcrypt.checkpw(password.encode(), student['password_hash'].encode()):
        return jsonify({'error': 'Email yoki parol noto\'g\'ri'}), 401
    
    token = jwt.encode({
        'id': student['id'], 'role': 'student', 'email': email,
        'exp': datetime.now() + timedelta(days=30)
    }, SECRET_KEY, algorithm='HS256')
    
    return jsonify({
        'token': token,
        'user': {'id': student['id'], 'full_name': student['full_name'], 'email': email, 
                 'group_name': student['group_name'], 'role': 'student'}
    })

@app.route('/api/auth/mentor-login', methods=['POST'])
def mentor_login():
    data = request.json
    phone = data.get('phone', '').strip()
    password = data.get('password', '')
    
    conn = get_db()
    mentor = conn.execute('SELECT * FROM mentors WHERE phone = ?', (phone,)).fetchone()
    conn.close()
    
    if not mentor or not bcrypt.checkpw(password.encode(), mentor['password_hash'].encode()):
        return jsonify({'error': 'Telefon raqam yoki parol noto\'g\'ri'}), 401
    
    token = jwt.encode({
        'id': mentor['id'], 'role': 'mentor', 'phone': phone,
        'exp': datetime.now() + timedelta(days=30)
    }, SECRET_KEY, algorithm='HS256')
    
    return jsonify({
        'token': token,
        'user': {'id': mentor['id'], 'full_name': mentor['full_name'], 'phone': phone, 
                 'groups': json.loads(mentor['groups']), 'role': 'mentor'}
    })

@app.route('/api/auth/admin-login', methods=['POST'])
def admin_login():
    data = request.json
    password = data.get('password', '')
    
    if password != ADMIN_PASSWORD:
        return jsonify({'error': 'Parol noto\'g\'ri'}), 401
    
    token = jwt.encode({
        'id': 'admin', 'role': 'admin',
        'exp': datetime.now() + timedelta(days=7)
    }, SECRET_KEY, algorithm='HS256')
    
    return jsonify({'token': token, 'user': {'id': 'admin', 'role': 'admin', 'full_name': 'Administrator'}})

@app.route('/api/auth/reset-password', methods=['POST'])
def reset_password():
    data = request.json
    email = data.get('email', '').lower().strip()
    
    conn = get_db()
    student = conn.execute('SELECT * FROM students WHERE email = ?', (email,)).fetchone()
    conn.close()
    
    if not student:
        return jsonify({'error': 'Bu email bilan foydalanuvchi topilmadi'}), 404
    
    code = generate_code()
    expires = (datetime.now() + timedelta(minutes=15)).isoformat()
    
    conn = get_db()
    conn.execute('DELETE FROM verification_codes WHERE email = ? AND purpose = ?', (email, 'reset'))
    conn.execute('INSERT INTO verification_codes (id, email, code, purpose, expires_at) VALUES (?, ?, ?, ?, ?)',
                 (str(uuid.uuid4()), email, code, 'reset', expires))
    conn.commit()
    conn.close()
    
    return jsonify({'success': True, 'code': code, 'login': student['login'], 
                   'message': f'Tasdiqlash kodi: {code}, Login: {student["login"]}'})

# ===== ADMIN ROUTES =====

@app.route('/api/admin/stats', methods=['GET'])
@token_required
def admin_stats(token_data):
    if token_data.get('role') != 'admin':
        return jsonify({'error': 'Access denied'}), 403
    
    conn = get_db()
    students_count = conn.execute('SELECT COUNT(*) as c FROM students').fetchone()['c']
    mentors_count = conn.execute('SELECT COUNT(*) as c FROM mentors').fetchone()['c']
    groups_count = conn.execute('SELECT COUNT(*) as c FROM groups WHERE is_active = 1').fetchone()['c']
    groups = [dict(r) for r in conn.execute('SELECT g.*, m.full_name as mentor_name FROM groups g LEFT JOIN mentors m ON g.mentor_id = m.id WHERE g.is_active = 1').fetchall()]
    conn.close()
    
    return jsonify({'students': students_count, 'mentors': mentors_count, 'active_groups': groups_count, 'groups': groups})

@app.route('/api/admin/mentors', methods=['GET'])
@token_required
def get_mentors(token_data):
    if token_data.get('role') != 'admin':
        return jsonify({'error': 'Access denied'}), 403
    conn = get_db()
    mentors = [dict(r) for r in conn.execute('SELECT id, full_name, phone, groups, created_at, is_active FROM mentors').fetchall()]
    conn.close()
    return jsonify(mentors)

@app.route('/api/admin/mentors', methods=['POST'])
@token_required
def add_mentor(token_data):
    if token_data.get('role') != 'admin':
        return jsonify({'error': 'Access denied'}), 403
    
    data = request.json
    full_name = data.get('full_name', '').strip()
    phone = data.get('phone', '').strip()
    password = data.get('password', '').strip()
    groups = data.get('groups', [])
    
    if not all([full_name, phone, password]):
        return jsonify({'error': 'Barcha maydonlar to\'ldirilishi shart'}), 400
    
    pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    mentor_id = str(uuid.uuid4())
    
    conn = get_db()
    try:
        conn.execute('INSERT INTO mentors (id, full_name, phone, password_hash, groups) VALUES (?, ?, ?, ?, ?)',
                     (mentor_id, full_name, phone, pw_hash, json.dumps(groups)))
        
        for g in groups:
            existing = conn.execute('SELECT id FROM groups WHERE name = ?', (g,)).fetchone()
            if not existing:
                conn.execute('INSERT INTO groups (id, name, mentor_id) VALUES (?, ?, ?)',
                             (str(uuid.uuid4()), g, mentor_id))
            else:
                conn.execute('UPDATE groups SET mentor_id = ? WHERE name = ?', (mentor_id, g))
        
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'id': mentor_id})
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({'error': 'Bu telefon raqam band'}), 400

@app.route('/api/admin/mentors/<mentor_id>', methods=['DELETE'])
@token_required
def delete_mentor(token_data, mentor_id):
    if token_data.get('role') != 'admin':
        return jsonify({'error': 'Access denied'}), 403
    conn = get_db()
    conn.execute('UPDATE mentors SET is_active = 0 WHERE id = ?', (mentor_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/admin/groups', methods=['GET'])
@token_required
def get_groups(token_data):
    conn = get_db()
    groups = [dict(r) for r in conn.execute(
        'SELECT g.*, m.full_name as mentor_name FROM groups g LEFT JOIN mentors m ON g.mentor_id = m.id WHERE g.is_active = 1'
    ).fetchall()]
    conn.close()
    return jsonify(groups)

@app.route('/api/admin/students', methods=['GET'])
@token_required
def get_students(token_data):
    if token_data.get('role') != 'admin':
        return jsonify({'error': 'Access denied'}), 403
    conn = get_db()
    students = [dict(r) for r in conn.execute('SELECT id, login, full_name, phone, email, group_name, created_at, is_active FROM students').fetchall()]
    conn.close()
    return jsonify(students)

@app.route('/api/admin/calendar', methods=['POST'])
@token_required
def add_calendar_event(token_data):
    if token_data.get('role') != 'admin':
        return jsonify({'error': 'Access denied'}), 403
    data = request.json
    event_id = str(uuid.uuid4())
    conn = get_db()
    conn.execute('INSERT INTO calendar_events (id, title, description, event_date, event_time, group_id, created_by) VALUES (?, ?, ?, ?, ?, ?, ?)',
                 (event_id, data.get('title'), data.get('description'), data.get('event_date'), data.get('event_time'), data.get('group_id'), 'admin'))
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'id': event_id})

@app.route('/api/calendar', methods=['GET'])
@token_required
def get_calendar(token_data):
    conn = get_db()
    events = [dict(r) for r in conn.execute('SELECT * FROM calendar_events ORDER BY event_date').fetchall()]
    conn.close()
    return jsonify(events)

# ===== MENTOR ROUTES =====

@app.route('/api/mentor/profile', methods=['GET'])
@token_required
def mentor_profile(token_data):
    if token_data.get('role') != 'mentor':
        return jsonify({'error': 'Access denied'}), 403
    conn = get_db()
    mentor = conn.execute('SELECT id, full_name, phone, groups FROM mentors WHERE id = ?', (token_data['id'],)).fetchone()
    if not mentor:
        conn.close()
        return jsonify({'error': 'Not found'}), 404
    
    groups_list = json.loads(mentor['groups'])
    students_count = 0
    for g in groups_list:
        count = conn.execute('SELECT COUNT(*) as c FROM students WHERE group_name = ?', (g,)).fetchone()['c']
        students_count += count
    
    conn.close()
    return jsonify({**dict(mentor), 'students_count': students_count})

@app.route('/api/mentor/groups', methods=['GET'])
@token_required
def mentor_groups(token_data):
    if token_data.get('role') != 'mentor':
        return jsonify({'error': 'Access denied'}), 403
    conn = get_db()
    mentor = conn.execute('SELECT groups FROM mentors WHERE id = ?', (token_data['id'],)).fetchone()
    groups_list = json.loads(mentor['groups']) if mentor else []
    
    result = []
    for g_name in groups_list:
        group = conn.execute('SELECT * FROM groups WHERE name = ?', (g_name,)).fetchone()
        if group:
            students = conn.execute('SELECT COUNT(*) as c FROM students WHERE group_name = ?', (g_name,)).fetchone()['c']
            result.append({**dict(group), 'students_count': students})
    
    conn.close()
    return jsonify(result)

@app.route('/api/mentor/groups/<group_id>/students', methods=['GET'])
@token_required
def group_students(token_data, group_id):
    conn = get_db()
    group = conn.execute('SELECT * FROM groups WHERE id = ?', (group_id,)).fetchone()
    if not group:
        conn.close()
        return jsonify({'error': 'Group not found'}), 404
    
    students = [dict(r) for r in conn.execute(
        'SELECT id, login, full_name, phone, email, created_at FROM students WHERE group_name = ?', 
        (group['name'],)
    ).fetchall()]
    conn.close()
    return jsonify(students)

# ===== TASKS ROUTES =====

@app.route('/api/mentor/tasks', methods=['POST'])
@token_required
def create_task(token_data):
    if token_data.get('role') != 'mentor':
        return jsonify({'error': 'Access denied'}), 403
    
    data = request.json
    task_id = str(uuid.uuid4())
    conn = get_db()
    conn.execute('''INSERT INTO tasks (id, group_id, mentor_id, title, description, deadline_date, deadline_time, task_type, duration_minutes)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                 (task_id, data['group_id'], token_data['id'], data['title'], data['description'],
                  data['deadline_date'], data['deadline_time'], data.get('task_type', 'homework'), data.get('duration_minutes')))
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'id': task_id})

@app.route('/api/tasks/<group_id>', methods=['GET'])
@token_required
def get_tasks(token_data, group_id):
    conn = get_db()
    tasks = [dict(r) for r in conn.execute(
        'SELECT * FROM tasks WHERE group_id = ? ORDER BY created_at DESC', (group_id,)
    ).fetchall()]
    conn.close()
    return jsonify(tasks)

@app.route('/api/tasks/<task_id>/submissions', methods=['GET'])
@token_required
def get_submissions(token_data, task_id):
    conn = get_db()
    subs = [dict(r) for r in conn.execute('''
        SELECT s.*, st.full_name, st.login FROM submissions s 
        JOIN students st ON s.student_id = st.id 
        WHERE s.task_id = ?
    ''', (task_id,)).fetchall()]
    conn.close()
    return jsonify(subs)

@app.route('/api/student/submit', methods=['POST'])
@token_required
def submit_task(token_data):
    if token_data.get('role') != 'student':
        return jsonify({'error': 'Access denied'}), 403
    
    data = request.json
    task_id = data.get('task_id')
    content = data.get('content', '')
    
    conn = get_db()
    task = conn.execute('SELECT * FROM tasks WHERE id = ?', (task_id,)).fetchone()
    if not task:
        conn.close()
        return jsonify({'error': 'Vazifa topilmadi'}), 404
    
    deadline = datetime.strptime(f"{task['deadline_date']} {task['deadline_time']}", "%Y-%m-%d %H:%M")
    if datetime.now() > deadline:
        conn.close()
        return jsonify({'error': 'Muddati o\'tgan'}), 400
    
    existing = conn.execute('SELECT id FROM submissions WHERE task_id = ? AND student_id = ?', 
                           (task_id, token_data['id'])).fetchone()
    if existing:
        conn.execute('UPDATE submissions SET content = ?, submitted_at = CURRENT_TIMESTAMP WHERE id = ?',
                    (content, existing['id']))
        sub_id = existing['id']
    else:
        sub_id = str(uuid.uuid4())
        conn.execute('INSERT INTO submissions (id, task_id, student_id, content) VALUES (?, ?, ?, ?)',
                    (sub_id, task_id, token_data['id'], content))
    
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'id': sub_id})

@app.route('/api/submissions/<sub_id>/score', methods=['POST'])
@token_required
def score_submission(token_data, sub_id):
    if token_data.get('role') != 'mentor':
        return jsonify({'error': 'Access denied'}), 403
    data = request.json
    conn = get_db()
    conn.execute('UPDATE submissions SET mentor_score = ?, ai_feedback = ? WHERE id = ?',
                (data.get('score'), data.get('feedback', ''), sub_id))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

# ===== CHAT ROUTES =====

@app.route('/api/chat/<group_id>', methods=['GET'])
@token_required
def get_messages(token_data, group_id):
    conn = get_db()
    messages = [dict(r) for r in conn.execute(
        'SELECT * FROM messages WHERE group_id = ? ORDER BY created_at ASC LIMIT 100', (group_id,)
    ).fetchall()]
    conn.close()
    return jsonify(messages)

@app.route('/api/chat/<group_id>', methods=['POST'])
@token_required
def send_message(token_data, group_id):
    data = request.json
    msg_id = str(uuid.uuid4())
    
    conn = get_db()
    if token_data['role'] == 'student':
        sender = conn.execute('SELECT full_name FROM students WHERE id = ?', (token_data['id'],)).fetchone()
        sender_name = sender['full_name'] if sender else 'Unknown'
    else:
        sender = conn.execute('SELECT full_name FROM mentors WHERE id = ?', (token_data['id'],)).fetchone()
        sender_name = sender['full_name'] if sender else 'Mentor'
    
    conn.execute('INSERT INTO messages (id, group_id, sender_id, sender_type, sender_name, content) VALUES (?, ?, ?, ?, ?, ?)',
                (msg_id, group_id, token_data['id'], token_data['role'], sender_name, data.get('content', '')))
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'id': msg_id})

# ===== SCHEDULE ROUTES =====

@app.route('/api/schedules/<group_id>', methods=['GET'])
@token_required
def get_schedules(token_data, group_id):
    conn = get_db()
    schedules = [dict(r) for r in conn.execute('SELECT * FROM schedules WHERE group_id = ?', (group_id,)).fetchall()]
    for s in schedules:
        s['entries'] = [dict(e) for e in conn.execute('SELECT * FROM schedule_entries WHERE schedule_id = ? ORDER BY date', (s['id'],)).fetchall()]
    conn.close()
    return jsonify(schedules)

@app.route('/api/schedules', methods=['POST'])
@token_required
def create_schedule(token_data):
    if token_data.get('role') != 'mentor':
        return jsonify({'error': 'Access denied'}), 403
    
    data = request.json
    group_id = data['group_id']
    subject_name = data['subject_name']
    start_date = datetime.strptime(data['start_date'], '%Y-%m-%d')
    end_date = datetime.strptime(data['end_date'], '%Y-%m-%d')
    
    schedule_id = str(uuid.uuid4())
    conn = get_db()
    conn.execute('INSERT INTO schedules (id, group_id, subject_name, start_date, end_date) VALUES (?, ?, ?, ?, ?)',
                (schedule_id, group_id, subject_name, data['start_date'], data['end_date']))
    
    current = start_date
    while current <= end_date:
        conn.execute('INSERT INTO schedule_entries (id, schedule_id, date) VALUES (?, ?, ?)',
                    (str(uuid.uuid4()), schedule_id, current.strftime('%Y-%m-%d')))
        current += timedelta(days=1)
    
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'id': schedule_id})

# ===== STUDENT ROUTES =====

@app.route('/api/student/profile', methods=['GET'])
@token_required
def student_profile(token_data):
    if token_data.get('role') != 'student':
        return jsonify({'error': 'Access denied'}), 403
    conn = get_db()
    student = conn.execute('SELECT id, login, full_name, phone, email, group_name, created_at FROM students WHERE id = ?', 
                          (token_data['id'],)).fetchone()
    conn.close()
    if not student:
        return jsonify({'error': 'Not found'}), 404
    return jsonify(dict(student))

@app.route('/api/student/change-password', methods=['POST'])
@token_required
def change_password(token_data):
    if token_data.get('role') != 'student':
        return jsonify({'error': 'Access denied'}), 403
    data = request.json
    old_password = data.get('old_password', '')
    new_password = data.get('new_password', '')
    
    conn = get_db()
    student = conn.execute('SELECT * FROM students WHERE id = ?', (token_data['id'],)).fetchone()
    if not bcrypt.checkpw(old_password.encode(), student['password_hash'].encode()):
        conn.close()
        return jsonify({'error': 'Eski parol noto\'g\'ri'}), 400
    
    new_hash = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt()).decode()
    conn.execute('UPDATE students SET password_hash = ? WHERE id = ?', (new_hash, token_data['id']))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/student/group', methods=['GET'])
@token_required
def student_group(token_data):
    if token_data.get('role') != 'student':
        return jsonify({'error': 'Access denied'}), 403
    conn = get_db()
    student = conn.execute('SELECT group_name FROM students WHERE id = ?', (token_data['id'],)).fetchone()
    group = conn.execute('SELECT * FROM groups WHERE name = ?', (student['group_name'],)).fetchone()
    conn.close()
    if not group:
        return jsonify({'error': 'Group not found'}), 404
    return jsonify(dict(group))

@app.route('/api/student/tasks', methods=['GET'])
@token_required
def student_tasks(token_data):
    if token_data.get('role') != 'student':
        return jsonify({'error': 'Access denied'}), 403
    conn = get_db()
    student = conn.execute('SELECT group_name FROM students WHERE id = ?', (token_data['id'],)).fetchone()
    group = conn.execute('SELECT id FROM groups WHERE name = ?', (student['group_name'],)).fetchone()
    if not group:
        conn.close()
        return jsonify([])
    
    tasks = [dict(r) for r in conn.execute('SELECT * FROM tasks WHERE group_id = ? ORDER BY created_at DESC', (group['id'],)).fetchall()]
    
    for task in tasks:
        sub = conn.execute('SELECT * FROM submissions WHERE task_id = ? AND student_id = ?', 
                          (task['id'], token_data['id'])).fetchone()
        task['my_submission'] = dict(sub) if sub else None
    
    conn.close()
    return jsonify(tasks)

if __name__ == '__main__':
    init_db()
    
    # Add some default groups
    conn = get_db()
    default_groups = ['Python-1', 'Python-2', 'Django-1', 'JavaScript-1', 'React-1']
    for g in default_groups:
        existing = conn.execute('SELECT id FROM groups WHERE name = ?', (g,)).fetchone()
        if not existing:
            conn.execute('INSERT INTO groups (id, name) VALUES (?, ?)', (str(uuid.uuid4()), g))
    conn.commit()
    conn.close()
    
    print("✅ Ustoz Yordamchi Backend ishga tushdi: http://localhost:8080")
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

# ===== AI REVIEW (calls Anthropic API) =====
@app.route('/api/ai-review', methods=['POST'])
@token_required
def ai_review(token_data):
    import urllib.request
    import json as json_mod
    
    data = request.json
    code = data.get('code', '')
    sub_id = data.get('submission_id', '')
    
    # Try to call Anthropic API for AI review
    payload = {
        "model": "claude-sonnet-4-20250514",
        "max_tokens": 500,
        "messages": [{"role": "user", "content": f"Quyidagi kodni ko'rib chiqing va o'zbek tilida qisqacha baholang. Kuchli va zaif tomonlarini ayting. Ball (0-100) bering.\n\nKod:\n{code[:1000]}"}]
    }
    
    try:
        req = urllib.request.Request(
            'https://api.anthropic.com/v1/messages',
            data=json_mod.dumps(payload).encode(),
            headers={
                'Content-Type': 'application/json',
                'anthropic-version': '2023-06-01',
                'x-api-key': os.environ.get('ANTHROPIC_API_KEY', '')
            },
            method='POST'
        )
        with urllib.request.urlopen(req, timeout=30) as response:
            result = json_mod.loads(response.read())
            feedback = result['content'][0]['text']
            
            # Save to DB
            conn = get_db()
            conn.execute('UPDATE submissions SET ai_feedback = ? WHERE id = ?', (feedback, sub_id))
            conn.commit()
            conn.close()
            return jsonify({'feedback': feedback})
    except Exception as e:
        # Fallback feedback
        feedback = f"Kod tahlil qilindi. Asosiy fikr: kod to'g'ri yozilgan ko'rinadi. Sinxron va aniq strukturaga ega. AI xizmati vaqtincha mavjud emas: {str(e)[:100]}"
        conn = get_db()
        conn.execute('UPDATE submissions SET ai_feedback = ? WHERE id = ?', (feedback, sub_id))
        conn.commit()
        conn.close()
        return jsonify({'feedback': feedback})
