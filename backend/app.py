from flask import Flask, request, jsonify
from flask_cors import CORS
import sqlite3
import bcrypt
import uuid
import json
import random
import string
import hashlib
import hmac
import base64
from datetime import datetime, timedelta
import os

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})

@app.after_request
def after_request(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
    if request.method == 'OPTIONS':
        response.status_code = 200
    return response

SECRET_KEY = 'ustoz2024secret'
DB_PATH    = 'database.db'
ADMIN_PASS = os.environ.get('ADMIN_PASSWORD', 'sonnet123')
AI_KEY     = os.environ.get('ANTHROPIC_API_KEY', '')

def make_token(payload):
    body = base64.b64encode(json.dumps(payload).encode()).decode()
    sig  = hmac.new(SECRET_KEY.encode(), body.encode(), hashlib.sha256).hexdigest()
    return f"{body}.{sig}"

def read_token(token):
    try:
        body, sig = token.rsplit('.', 1)
        expected = hmac.new(SECRET_KEY.encode(), body.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return None
        payload = json.loads(base64.b64decode(body))
        if payload.get('exp') and datetime.now().timestamp() > payload['exp']:
            return None
        return payload
    except:
        return None

def token_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if request.method == 'OPTIONS':
            return jsonify({}), 200
        header  = request.headers.get('Authorization', '')
        token   = header.replace('Bearer ', '').strip()
        if not token:
            return jsonify({'error': 'Token kerak'}), 401
        payload = read_token(token)
        if payload is None:
            return jsonify({'error': 'Token yaroqsiz'}), 401
        return f(payload, *args, **kwargs)
    return decorated

def days(n=30):
    return (datetime.now() + timedelta(days=n)).timestamp()

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def uid(): return str(uuid.uuid4())
def code6(): return ''.join(random.choices(string.digits, k=6))
def exp15(): return (datetime.now() + timedelta(minutes=15)).isoformat()

def init_db():
    conn = get_db()
    conn.executescript('''
    CREATE TABLE IF NOT EXISTS students (
        id TEXT PRIMARY KEY, login TEXT UNIQUE NOT NULL, full_name TEXT NOT NULL,
        phone TEXT NOT NULL, email TEXT UNIQUE NOT NULL, group_name TEXT NOT NULL,
        password_hash TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP, is_active INTEGER DEFAULT 1
    );
    CREATE TABLE IF NOT EXISTS mentors (
        id TEXT PRIMARY KEY, full_name TEXT NOT NULL, phone TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL, groups TEXT DEFAULT "[]",
        created_at TEXT DEFAULT CURRENT_TIMESTAMP, is_active INTEGER DEFAULT 1
    );
    CREATE TABLE IF NOT EXISTS groups (
        id TEXT PRIMARY KEY, name TEXT UNIQUE NOT NULL, mentor_id TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP, is_active INTEGER DEFAULT 1
    );
    CREATE TABLE IF NOT EXISTS tasks (
        id TEXT PRIMARY KEY, group_id TEXT NOT NULL, mentor_id TEXT NOT NULL,
        title TEXT NOT NULL, description TEXT NOT NULL, deadline_date TEXT NOT NULL,
        deadline_time TEXT NOT NULL, task_type TEXT DEFAULT "homework",
        duration_minutes INTEGER, created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS submissions (
        id TEXT PRIMARY KEY, task_id TEXT NOT NULL, student_id TEXT NOT NULL,
        content TEXT NOT NULL, submitted_at TEXT DEFAULT CURRENT_TIMESTAMP,
        ai_feedback TEXT, mentor_score INTEGER
    );
    CREATE TABLE IF NOT EXISTS messages (
        id TEXT PRIMARY KEY, group_id TEXT NOT NULL, sender_id TEXT NOT NULL,
        sender_type TEXT NOT NULL, sender_name TEXT NOT NULL, content TEXT NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS schedules (
        id TEXT PRIMARY KEY, group_id TEXT NOT NULL, subject_name TEXT NOT NULL,
        start_date TEXT NOT NULL, end_date TEXT NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS schedule_entries (
        id TEXT PRIMARY KEY, schedule_id TEXT NOT NULL, date TEXT NOT NULL, topic TEXT
    );
    CREATE TABLE IF NOT EXISTS verification_codes (
        id TEXT PRIMARY KEY, email TEXT NOT NULL, code TEXT NOT NULL,
        purpose TEXT NOT NULL, expires_at TEXT NOT NULL, used INTEGER DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS calendar_events (
        id TEXT PRIMARY KEY, title TEXT NOT NULL, description TEXT,
        event_date TEXT NOT NULL, event_time TEXT, group_id TEXT,
        created_by TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    ''')
    conn.commit()
    for g in ['Python-1', 'Python-2', 'Django-1', 'JavaScript-1', 'React-1']:
        if not conn.execute('SELECT id FROM groups WHERE name=?', (g,)).fetchone():
            conn.execute('INSERT INTO groups (id,name) VALUES (?,?)', (uid(), g))
    conn.commit()
    conn.close()

# HEALTH
@app.route('/api/health')
def health():
    return jsonify({'status': 'ok', 'message': 'Ustoz Yordamchi ishlayapti'})

# AUTH
@app.route('/api/auth/check-email', methods=['POST', 'OPTIONS'])
def check_email():
    email = (request.json or {}).get('email', '').lower().strip()
    conn  = get_db()
    s     = conn.execute('SELECT full_name FROM students WHERE email=?', (email,)).fetchone()
    conn.close()
    return jsonify({'exists': bool(s), 'name': s['full_name'] if s else ''})

@app.route('/api/auth/send-verification', methods=['POST', 'OPTIONS'])
def send_verification():
    d       = request.json or {}
    email   = d.get('email', '').lower().strip()
    purpose = d.get('purpose', 'register')
    code    = code6()
    conn    = get_db()
    conn.execute('DELETE FROM verification_codes WHERE email=? AND purpose=?', (email, purpose))
    conn.execute('INSERT INTO verification_codes (id,email,code,purpose,expires_at) VALUES (?,?,?,?,?)',
                 (uid(), email, code, purpose, exp15()))
    conn.commit(); conn.close()
    return jsonify({'success': True, 'code': code})

@app.route('/api/auth/verify-code', methods=['POST', 'OPTIONS'])
def verify_code():
    d       = request.json or {}
    email   = d.get('email', '').lower().strip()
    code    = d.get('code', '')
    purpose = d.get('purpose', 'register')
    conn    = get_db()
    row = conn.execute(
        'SELECT id FROM verification_codes WHERE email=? AND code=? AND purpose=? AND used=0 AND expires_at>?',
        (email, code, purpose, datetime.now().isoformat())
    ).fetchone()
    if not row:
        conn.close(); return jsonify({'error': "Kod noto'g'ri yoki muddati o'tgan"}), 400
    conn.execute('UPDATE verification_codes SET used=1 WHERE id=?', (row['id'],))
    conn.commit(); conn.close()
    return jsonify({'success': True})

@app.route('/api/auth/register', methods=['POST', 'OPTIONS'])
def register():
    d = request.json or {}
    login = d.get('login','').strip(); full_name = d.get('full_name','').strip()
    phone = d.get('phone','').strip(); email = d.get('email','').lower().strip()
    group_name = d.get('group_name','').strip(); password = d.get('password','')
    if not all([login, full_name, phone, email, group_name, password]):
        return jsonify({'error': "Barcha maydonlarni to'ldiring"}), 400
    conn = get_db()
    if conn.execute('SELECT id FROM students WHERE login=?', (login,)).fetchone():
        conn.close(); return jsonify({'error': 'Bu login band'}), 400
    if conn.execute('SELECT id FROM students WHERE email=?', (email,)).fetchone():
        conn.close(); return jsonify({'error': "Bu email allaqachon ro'yxatdan o'tgan", 'email_exists': True}), 400
    grp = conn.execute('SELECT id FROM groups WHERE name=?', (group_name,)).fetchone()
    if not grp:
        gs = [r['name'] for r in conn.execute('SELECT name FROM groups WHERE is_active=1').fetchall()]
        conn.close(); return jsonify({'error': f"Bunday guruh yo'q. Mavjud: {', '.join(gs)}"}), 400
    pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    sid = uid()
    conn.execute('INSERT INTO students (id,login,full_name,phone,email,group_name,password_hash) VALUES (?,?,?,?,?,?,?)',
                 (sid, login, full_name, phone, email, group_name, pw_hash))
    conn.commit(); conn.close()
    token = make_token({'id': sid, 'role': 'student', 'exp': days(30)})
    return jsonify({'token': token, 'user': {'id': sid, 'full_name': full_name, 'email': email, 'group_name': group_name, 'role': 'student'}})

@app.route('/api/auth/login', methods=['POST', 'OPTIONS'])
def login():
    d = request.json or {}
    email = d.get('email','').lower().strip(); pw = d.get('password','')
    conn = get_db()
    s = conn.execute('SELECT * FROM students WHERE email=?', (email,)).fetchone()
    conn.close()
    if not s or not bcrypt.checkpw(pw.encode(), s['password_hash'].encode()):
        return jsonify({'error': "Email yoki parol noto'g'ri"}), 401
    token = make_token({'id': s['id'], 'role': 'student', 'exp': days(30)})
    return jsonify({'token': token, 'user': {'id': s['id'], 'full_name': s['full_name'], 'email': email, 'group_name': s['group_name'], 'role': 'student'}})

@app.route('/api/auth/mentor-login', methods=['POST', 'OPTIONS'])
def mentor_login():
    d = request.json or {}
    phone = d.get('phone','').strip(); pw = d.get('password','')
    conn  = get_db()
    m = conn.execute('SELECT * FROM mentors WHERE phone=?', (phone,)).fetchone()
    conn.close()
    if not m or not bcrypt.checkpw(pw.encode(), m['password_hash'].encode()):
        return jsonify({'error': "Telefon yoki parol noto'g'ri"}), 401
    token = make_token({'id': m['id'], 'role': 'mentor', 'exp': days(30)})
    return jsonify({'token': token, 'user': {'id': m['id'], 'full_name': m['full_name'], 'phone': phone, 'groups': json.loads(m['groups']), 'role': 'mentor'}})

@app.route('/api/auth/admin-login', methods=['POST', 'OPTIONS'])
def admin_login():
    pw = (request.json or {}).get('password', '')
    if pw != ADMIN_PASS:
        return jsonify({'error': "Parol noto'g'ri"}), 401
    token = make_token({'id': 'admin', 'role': 'admin', 'exp': days(7)})
    return jsonify({'token': token, 'user': {'id': 'admin', 'role': 'admin', 'full_name': 'Administrator'}})

@app.route('/api/auth/reset-password', methods=['POST', 'OPTIONS'])
def reset_password():
    email = (request.json or {}).get('email','').lower().strip()
    conn  = get_db()
    s     = conn.execute('SELECT * FROM students WHERE email=?', (email,)).fetchone()
    if not s:
        conn.close(); return jsonify({'error': 'Bu email topilmadi'}), 404
    code = code6()
    conn.execute('DELETE FROM verification_codes WHERE email=? AND purpose=?', (email,'reset'))
    conn.execute('INSERT INTO verification_codes (id,email,code,purpose,expires_at) VALUES (?,?,?,?,?)',
                 (uid(), email, code, 'reset', exp15()))
    conn.commit(); conn.close()
    return jsonify({'success': True, 'code': code, 'login': s['login']})

# ADMIN
@app.route('/api/admin/stats', methods=['GET', 'OPTIONS'])
@token_required
def admin_stats(tok):
    if tok['role'] != 'admin': return jsonify({'error': "Ruxsat yo'q"}), 403
    conn = get_db()
    students = conn.execute('SELECT COUNT(*) as c FROM students').fetchone()['c']
    mentors  = conn.execute('SELECT COUNT(*) as c FROM mentors').fetchone()['c']
    groups   = [dict(r) for r in conn.execute('SELECT g.*,m.full_name as mentor_name FROM groups g LEFT JOIN mentors m ON g.mentor_id=m.id WHERE g.is_active=1').fetchall()]
    conn.close()
    return jsonify({'students': students, 'mentors': mentors, 'active_groups': len(groups), 'groups': groups})

@app.route('/api/admin/mentors', methods=['GET', 'POST', 'OPTIONS'])
@token_required
def admin_mentors(tok):
    if tok['role'] != 'admin': return jsonify({'error': "Ruxsat yo'q"}), 403
    conn = get_db()
    if request.method == 'GET':
        ms = [dict(r) for r in conn.execute('SELECT id,full_name,phone,groups,created_at,is_active FROM mentors').fetchall()]
        conn.close(); return jsonify(ms)
    d = request.json or {}
    full_name = d.get('full_name','').strip(); phone = d.get('phone','').strip()
    password  = d.get('password','').strip(); groups = d.get('groups', [])
    if not all([full_name, phone, password]):
        conn.close(); return jsonify({'error': "Barcha maydonlarni to'ldiring"}), 400
    pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    mid = uid()
    try:
        conn.execute('INSERT INTO mentors (id,full_name,phone,password_hash,groups) VALUES (?,?,?,?,?)',
                     (mid, full_name, phone, pw_hash, json.dumps(groups)))
        for g in groups:
            ex = conn.execute('SELECT id FROM groups WHERE name=?', (g,)).fetchone()
            if ex: conn.execute('UPDATE groups SET mentor_id=? WHERE name=?', (mid, g))
            else:  conn.execute('INSERT INTO groups (id,name,mentor_id) VALUES (?,?,?)', (uid(), g, mid))
        conn.commit(); conn.close()
        return jsonify({'success': True, 'id': mid})
    except sqlite3.IntegrityError:
        conn.close(); return jsonify({'error': 'Bu telefon raqam band'}), 400

@app.route('/api/admin/mentors/<mid>', methods=['DELETE', 'OPTIONS'])
@token_required
def admin_delete_mentor(tok, mid):
    if tok['role'] != 'admin': return jsonify({'error': "Ruxsat yo'q"}), 403
    conn = get_db()
    conn.execute('UPDATE mentors SET is_active=0 WHERE id=?', (mid,))
    conn.commit(); conn.close()
    return jsonify({'success': True})

@app.route('/api/admin/groups', methods=['GET', 'OPTIONS'])
@token_required
def admin_groups(tok):
    conn = get_db()
    gs = [dict(r) for r in conn.execute('SELECT g.*,m.full_name as mentor_name FROM groups g LEFT JOIN mentors m ON g.mentor_id=m.id WHERE g.is_active=1').fetchall()]
    conn.close(); return jsonify(gs)

@app.route('/api/admin/students', methods=['GET', 'OPTIONS'])
@token_required
def admin_students(tok):
    if tok['role'] != 'admin': return jsonify({'error': "Ruxsat yo'q"}), 403
    conn = get_db()
    ss = [dict(r) for r in conn.execute('SELECT id,login,full_name,phone,email,group_name,created_at,is_active FROM students').fetchall()]
    conn.close(); return jsonify(ss)

@app.route('/api/admin/calendar', methods=['POST', 'OPTIONS'])
@token_required
def admin_calendar_add(tok):
    if tok['role'] != 'admin': return jsonify({'error': "Ruxsat yo'q"}), 403
    d = request.json or {}
    eid = uid(); conn = get_db()
    conn.execute('INSERT INTO calendar_events (id,title,description,event_date,event_time,group_id,created_by) VALUES (?,?,?,?,?,?,?)',
                 (eid, d.get('title'), d.get('description'), d.get('event_date'), d.get('event_time'), d.get('group_id'), 'admin'))
    conn.commit(); conn.close()
    return jsonify({'success': True, 'id': eid})

@app.route('/api/calendar', methods=['GET', 'OPTIONS'])
@token_required
def get_calendar(tok):
    conn = get_db()
    evs = [dict(r) for r in conn.execute('SELECT * FROM calendar_events ORDER BY event_date').fetchall()]
    conn.close(); return jsonify(evs)

# MENTOR
@app.route('/api/mentor/profile', methods=['GET', 'OPTIONS'])
@token_required
def mentor_profile(tok):
    if tok['role'] != 'mentor': return jsonify({'error': "Ruxsat yo'q"}), 403
    conn = get_db()
    m = conn.execute('SELECT id,full_name,phone,groups FROM mentors WHERE id=?', (tok['id'],)).fetchone()
    if not m: conn.close(); return jsonify({'error': 'Topilmadi'}), 404
    gs  = json.loads(m['groups'])
    cnt = sum(conn.execute('SELECT COUNT(*) as c FROM students WHERE group_name=?', (g,)).fetchone()['c'] for g in gs)
    conn.close()
    return jsonify({**dict(m), 'students_count': cnt})

@app.route('/api/mentor/groups', methods=['GET', 'OPTIONS'])
@token_required
def mentor_groups(tok):
    if tok['role'] != 'mentor': return jsonify({'error': "Ruxsat yo'q"}), 403
    conn = get_db()
    m  = conn.execute('SELECT groups FROM mentors WHERE id=?', (tok['id'],)).fetchone()
    gs = json.loads(m['groups']) if m else []
    result = []
    for gn in gs:
        g = conn.execute('SELECT * FROM groups WHERE name=?', (gn,)).fetchone()
        if g:
            cnt = conn.execute('SELECT COUNT(*) as c FROM students WHERE group_name=?', (gn,)).fetchone()['c']
            result.append({**dict(g), 'students_count': cnt})
    conn.close(); return jsonify(result)

@app.route('/api/mentor/groups/<gid>/students', methods=['GET', 'OPTIONS'])
@token_required
def mentor_group_students(tok, gid):
    conn = get_db()
    g  = conn.execute('SELECT * FROM groups WHERE id=?', (gid,)).fetchone()
    if not g: conn.close(); return jsonify({'error': 'Guruh topilmadi'}), 404
    ss = [dict(r) for r in conn.execute('SELECT id,login,full_name,phone,email,created_at FROM students WHERE group_name=?', (g['name'],)).fetchall()]
    conn.close(); return jsonify(ss)

# TASKS
@app.route('/api/mentor/tasks', methods=['POST', 'OPTIONS'])
@token_required
def create_task(tok):
    if tok['role'] != 'mentor': return jsonify({'error': "Ruxsat yo'q"}), 403
    d = request.json or {}; tid = uid(); conn = get_db()
    conn.execute('INSERT INTO tasks (id,group_id,mentor_id,title,description,deadline_date,deadline_time,task_type,duration_minutes) VALUES (?,?,?,?,?,?,?,?,?)',
                 (tid, d['group_id'], tok['id'], d['title'], d['description'], d['deadline_date'], d['deadline_time'], d.get('task_type','homework'), d.get('duration_minutes')))
    conn.commit(); conn.close()
    return jsonify({'success': True, 'id': tid})

@app.route('/api/tasks/<gid>', methods=['GET', 'OPTIONS'])
@token_required
def get_tasks(tok, gid):
    conn = get_db()
    ts = [dict(r) for r in conn.execute('SELECT * FROM tasks WHERE group_id=? ORDER BY created_at DESC', (gid,)).fetchall()]
    conn.close(); return jsonify(ts)

@app.route('/api/tasks/<tid>/submissions', methods=['GET', 'OPTIONS'])
@token_required
def get_submissions(tok, tid):
    conn = get_db()
    ss = [dict(r) for r in conn.execute('SELECT s.*,st.full_name,st.login FROM submissions s JOIN students st ON s.student_id=st.id WHERE s.task_id=?', (tid,)).fetchall()]
    conn.close(); return jsonify(ss)

@app.route('/api/student/submit', methods=['POST', 'OPTIONS'])
@token_required
def submit_task(tok):
    if tok['role'] != 'student': return jsonify({'error': "Ruxsat yo'q"}), 403
    d = request.json or {}; tid = d.get('task_id'); content = d.get('content','')
    conn = get_db()
    task = conn.execute('SELECT * FROM tasks WHERE id=?', (tid,)).fetchone()
    if not task: conn.close(); return jsonify({'error': 'Vazifa topilmadi'}), 404
    dl = datetime.strptime(f"{task['deadline_date']} {task['deadline_time']}", "%Y-%m-%d %H:%M")
    if datetime.now() > dl: conn.close(); return jsonify({'error': "Muddati o'tgan"}), 400
    ex = conn.execute('SELECT id FROM submissions WHERE task_id=? AND student_id=?', (tid, tok['id'])).fetchone()
    if ex:
        conn.execute('UPDATE submissions SET content=?,submitted_at=CURRENT_TIMESTAMP WHERE id=?', (content, ex['id'])); sid = ex['id']
    else:
        sid = uid()
        conn.execute('INSERT INTO submissions (id,task_id,student_id,content) VALUES (?,?,?,?)', (sid, tid, tok['id'], content))
    conn.commit(); conn.close()
    return jsonify({'success': True, 'id': sid})

@app.route('/api/submissions/<sid>/score', methods=['POST', 'OPTIONS'])
@token_required
def score_submission(tok, sid):
    if tok['role'] != 'mentor': return jsonify({'error': "Ruxsat yo'q"}), 403
    d = request.json or {}; conn = get_db()
    conn.execute('UPDATE submissions SET mentor_score=?,ai_feedback=? WHERE id=?', (d.get('score'), d.get('feedback',''), sid))
    conn.commit(); conn.close()
    return jsonify({'success': True})

# CHAT
@app.route('/api/chat/<gid>', methods=['GET', 'POST', 'OPTIONS'])
@token_required
def chat(tok, gid):
    conn = get_db()
    if request.method == 'GET':
        ms = [dict(r) for r in conn.execute('SELECT * FROM messages WHERE group_id=? ORDER BY created_at ASC LIMIT 100', (gid,)).fetchall()]
        conn.close(); return jsonify(ms)
    if tok['role'] == 'student':
        s = conn.execute('SELECT full_name FROM students WHERE id=?', (tok['id'],)).fetchone()
        name = s['full_name'] if s else "O'quvchi"
    else:
        m = conn.execute('SELECT full_name FROM mentors WHERE id=?', (tok['id'],)).fetchone()
        name = m['full_name'] if m else 'Mentor'
    mid = uid()
    conn.execute('INSERT INTO messages (id,group_id,sender_id,sender_type,sender_name,content) VALUES (?,?,?,?,?,?)',
                 (mid, gid, tok['id'], tok['role'], name, (request.json or {}).get('content','')))
    conn.commit(); conn.close()
    return jsonify({'success': True, 'id': mid})

# SCHEDULE
@app.route('/api/schedules/<gid>', methods=['GET', 'OPTIONS'])
@token_required
def get_schedules(tok, gid):
    conn = get_db()
    ss = [dict(r) for r in conn.execute('SELECT * FROM schedules WHERE group_id=?', (gid,)).fetchall()]
    for s in ss:
        s['entries'] = [dict(e) for e in conn.execute('SELECT * FROM schedule_entries WHERE schedule_id=? ORDER BY date', (s['id'],)).fetchall()]
    conn.close(); return jsonify(ss)

@app.route('/api/schedules', methods=['POST', 'OPTIONS'])
@token_required
def create_schedule(tok):
    if tok['role'] != 'mentor': return jsonify({'error': "Ruxsat yo'q"}), 403
    from datetime import date as dt, timedelta as td
    d = request.json or {}
    start = datetime.strptime(d['start_date'], '%Y-%m-%d').date()
    end   = datetime.strptime(d['end_date'],   '%Y-%m-%d').date()
    sid   = uid(); conn = get_db()
    conn.execute('INSERT INTO schedules (id,group_id,subject_name,start_date,end_date) VALUES (?,?,?,?,?)',
                 (sid, d['group_id'], d['subject_name'], d['start_date'], d['end_date']))
    cur = start
    while cur <= end:
        conn.execute('INSERT INTO schedule_entries (id,schedule_id,date) VALUES (?,?,?)', (uid(), sid, cur.isoformat()))
        cur += td(days=1)
    conn.commit(); conn.close()
    return jsonify({'success': True, 'id': sid})

# STUDENT
@app.route('/api/student/profile', methods=['GET', 'OPTIONS'])
@token_required
def student_profile(tok):
    if tok['role'] != 'student': return jsonify({'error': "Ruxsat yo'q"}), 403
    conn = get_db()
    s = conn.execute('SELECT id,login,full_name,phone,email,group_name,created_at FROM students WHERE id=?', (tok['id'],)).fetchone()
    conn.close()
    return jsonify(dict(s)) if s else (jsonify({'error': 'Topilmadi'}), 404)

@app.route('/api/student/change-password', methods=['POST', 'OPTIONS'])
@token_required
def change_password(tok):
    if tok['role'] != 'student': return jsonify({'error': "Ruxsat yo'q"}), 403
    d = request.json or {}
    conn = get_db()
    s = conn.execute('SELECT * FROM students WHERE id=?', (tok['id'],)).fetchone()
    if not bcrypt.checkpw(d.get('old_password','').encode(), s['password_hash'].encode()):
        conn.close(); return jsonify({'error': "Eski parol noto'g'ri"}), 400
    nh = bcrypt.hashpw(d.get('new_password','').encode(), bcrypt.gensalt()).decode()
    conn.execute('UPDATE students SET password_hash=? WHERE id=?', (nh, tok['id']))
    conn.commit(); conn.close()
    return jsonify({'success': True})

@app.route('/api/student/group', methods=['GET', 'OPTIONS'])
@token_required
def student_group(tok):
    if tok['role'] != 'student': return jsonify({'error': "Ruxsat yo'q"}), 403
    conn = get_db()
    s = conn.execute('SELECT group_name FROM students WHERE id=?', (tok['id'],)).fetchone()
    g = conn.execute('SELECT * FROM groups WHERE name=?', (s['group_name'],)).fetchone()
    conn.close()
    return jsonify(dict(g)) if g else (jsonify({'error': 'Guruh topilmadi'}), 404)

@app.route('/api/student/tasks', methods=['GET', 'OPTIONS'])
@token_required
def student_tasks(tok):
    if tok['role'] != 'student': return jsonify({'error': "Ruxsat yo'q"}), 403
    conn = get_db()
    s = conn.execute('SELECT group_name FROM students WHERE id=?', (tok['id'],)).fetchone()
    g = conn.execute('SELECT id FROM groups WHERE name=?', (s['group_name'],)).fetchone()
    if not g: conn.close(); return jsonify([])
    ts = [dict(r) for r in conn.execute('SELECT * FROM tasks WHERE group_id=? ORDER BY created_at DESC', (g['id'],)).fetchall()]
    for t in ts:
        sub = conn.execute('SELECT * FROM submissions WHERE task_id=? AND student_id=?', (t['id'], tok['id'])).fetchone()
        t['my_submission'] = dict(sub) if sub else None
    conn.close(); return jsonify(ts)

# AI REVIEW
@app.route('/api/ai-review', methods=['POST', 'OPTIONS'])
@token_required
def ai_review(tok):
    import urllib.request as ur
    d = request.json or {}
    code   = d.get('code', ''); sub_id = d.get('submission_id', ''); title = d.get('task_title', 'Vazifa')
    if not AI_KEY:
        fb = "AI kaliti yo'q. Railway Variables da ANTHROPIC_API_KEY qo'ying."
    else:
        prompt  = f"Sen IT Park AI tekshiruvchisisiz.\nVazifa: {title}\nTalaba javobi:\n{code[:2000]}\n\nO'zbek tilida: 1.Baho(0-100) 2.Kuchli tomonlar 3.Zaif tomonlar 4.Tavsiyalar. Qisqa yoz."
        payload = json.dumps({"model":"claude-sonnet-4-20250514","max_tokens":800,"messages":[{"role":"user","content":prompt}]}).encode()
        req     = ur.Request('https://api.anthropic.com/v1/messages', data=payload,
                             headers={'Content-Type':'application/json','anthropic-version':'2023-06-01','x-api-key':AI_KEY}, method='POST')
        try:
            with ur.urlopen(req, timeout=30) as r:
                fb = json.loads(r.read())['content'][0]['text']
        except Exception as e:
            fb = f"AI vaqtincha mavjud emas: {str(e)[:80]}"
    conn = get_db()
    conn.execute('UPDATE submissions SET ai_feedback=? WHERE id=?', (fb, sub_id))
    conn.commit(); conn.close()
    return jsonify({'feedback': fb})

if __name__ == '__main__':
    init_db()
    port = int(os.environ.get('PORT', 8080))
    print(f"Server: http://0.0.0.0:{port}")
    app.run(host='0.0.0.0', port=port, debug=False)
