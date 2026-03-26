from flask import Flask, request, jsonify
from flask_cors import CORS
import psycopg2
from psycopg2.extras import RealDictCursor
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
import traceback
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

app = Flask(__name__)

CORS(app, 
     resources={r"/api/*": {
         "origins": [
             "https://ustozyordamchiai.vercel.app",
             "https://ustoz-production.up.railway.app",
             "http://localhost:3000",
             "http://localhost:5000",
             "*"
         ],
         "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
         "allow_headers": ["Content-Type", "Authorization", "Accept"],
         "expose_headers": ["Content-Type", "Authorization"],
         "supports_credentials": True,
         "max_age": 3600
     }})

@app.after_request
def after_request(response):
    response.headers['Access-Control-Allow-Origin'] = 'https://ustozyordamchiai.vercel.app'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, Accept, X-Requested-With'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS, PATCH'
    response.headers['Access-Control-Allow-Credentials'] = 'true'
    if request.method == 'OPTIONS':
        response.status_code = 200
    return response

SECRET_KEY = os.environ.get('SECRET_KEY', 'ustoz2024secret')
ADMIN_PASS = os.environ.get('ADMIN_PASSWORD', 'sonnet123')
AI_KEY = os.environ.get('ANTHROPIC_API_KEY', '')
DATABASE_URL = os.environ.get('DATABASE_URL', '')

EMAIL_HOST = os.environ.get('EMAIL_HOST', 'smtp.gmail.com')
EMAIL_PORT = int(os.environ.get('EMAIL_PORT', 587))
EMAIL_USER = os.environ.get('EMAIL_USER', '')
EMAIL_PASSWORD = os.environ.get('EMAIL_PASSWORD', '')

print("=== Ustoz Yordamchi AI Starting ===")
print(f"DATABASE_URL exists: {bool(DATABASE_URL)}")
print(f"EMAIL_USER exists: {bool(EMAIL_USER)}")

def send_email(to_email, subject, message):
    if not EMAIL_USER or not EMAIL_PASSWORD:
        print("Email sozlamalari yo'q")
        return False
    try:
        msg = MIMEMultipart()
        msg['From'] = EMAIL_USER
        msg['To'] = to_email
        msg['Subject'] = subject
        msg.attach(MIMEText(message, 'plain', 'utf-8'))
        server = smtplib.SMTP(EMAIL_HOST, EMAIL_PORT)
        server.starttls()
        server.login(EMAIL_USER, EMAIL_PASSWORD)
        server.send_message(msg)
        server.quit()
        print(f"Email yuborildi: {to_email}")
        return True
    except Exception as e:
        print(f"Email yuborish xatosi: {e}")
        return False

def make_token(payload):
    body = base64.b64encode(json.dumps(payload).encode()).decode()
    sig = hmac.new(SECRET_KEY.encode(), body.encode(), hashlib.sha256).hexdigest()
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
        header = request.headers.get('Authorization', '')
        token = header.replace('Bearer ', '').strip()
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
    if not DATABASE_URL:
        raise Exception("DATABASE_URL not set!")
    try:
        conn = psycopg2.connect(DATABASE_URL)
        conn.autocommit = False
        return conn
    except Exception as e:
        print(f"Database connection error: {e}")
        raise

def uid():
    return str(uuid.uuid4())

def code6():
    return ''.join(random.choices(string.digits, k=6))

def exp15():
    return (datetime.now() + timedelta(minutes=15)).isoformat()

def upgrade_db():
    try:
        conn = get_db()
        cur = conn.cursor()
        try:
            cur.execute("ALTER TABLE groups ADD COLUMN schedule_type TEXT DEFAULT 'juft'")
        except: pass
        try:
            cur.execute("ALTER TABLE groups ADD COLUMN schedule_time TEXT DEFAULT '19:00'")
        except: pass
        try:
            cur.execute("ALTER TABLE schedule_entries ADD COLUMN has_task INTEGER DEFAULT 0")
        except: pass
        try:
            cur.execute("ALTER TABLE schedule_entries ADD COLUMN task_id TEXT")
        except: pass
        try:
            cur.execute("ALTER TABLE tasks ADD COLUMN schedule_entry_id TEXT")
        except: pass
        try:
            cur.execute("ALTER TABLE students ADD COLUMN total_score INTEGER DEFAULT 0")
        except: pass
        conn.commit()
        cur.close()
        conn.close()
        print("✅ Database upgraded!")
    except Exception as e:
        print(f"Upgrade error: {e}")

def init_db():
    try:
        print("Initializing PostgreSQL database...")
        conn = get_db()
        cur = conn.cursor()
        
        cur.execute('''
        CREATE TABLE IF NOT EXISTS students (
            id TEXT PRIMARY KEY,
            login TEXT UNIQUE NOT NULL,
            full_name TEXT NOT NULL,
            phone TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            group_name TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_active INTEGER DEFAULT 1,
            total_score INTEGER DEFAULT 0
        )
        ''')
        
        cur.execute('''
        CREATE TABLE IF NOT EXISTS mentors (
            id TEXT PRIMARY KEY,
            full_name TEXT NOT NULL,
            phone TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            groups TEXT DEFAULT '[]',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_active INTEGER DEFAULT 1
        )
        ''')
        
        cur.execute('''
        CREATE TABLE IF NOT EXISTS groups (
            id TEXT PRIMARY KEY,
            name TEXT UNIQUE NOT NULL,
            mentor_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_active INTEGER DEFAULT 1,
            schedule_type TEXT DEFAULT 'juft',
            schedule_time TEXT DEFAULT '19:00'
        )
        ''')
        
        cur.execute('''
        CREATE TABLE IF NOT EXISTS tasks (
            id TEXT PRIMARY KEY,
            group_id TEXT NOT NULL,
            mentor_id TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            deadline_date TEXT NOT NULL,
            deadline_time TEXT NOT NULL,
            task_type TEXT DEFAULT 'homework',
            duration_minutes INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            schedule_entry_id TEXT
        )
        ''')
        
        cur.execute('''
        CREATE TABLE IF NOT EXISTS submissions (
            id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL,
            student_id TEXT NOT NULL,
            content TEXT NOT NULL,
            submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            ai_feedback TEXT,
            mentor_score INTEGER,
            status TEXT DEFAULT 'pending'
        )
        ''')
        
        cur.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id TEXT PRIMARY KEY,
            group_id TEXT NOT NULL,
            sender_id TEXT NOT NULL,
            sender_type TEXT NOT NULL,
            sender_name TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        
        cur.execute('''
        CREATE TABLE IF NOT EXISTS schedules (
            id TEXT PRIMARY KEY,
            group_id TEXT NOT NULL,
            subject_name TEXT NOT NULL,
            start_date TEXT NOT NULL,
            end_date TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        
        cur.execute('''
        CREATE TABLE IF NOT EXISTS schedule_entries (
            id TEXT PRIMARY KEY,
            schedule_id TEXT NOT NULL,
            date TEXT NOT NULL,
            topic TEXT,
            has_task INTEGER DEFAULT 0,
            task_id TEXT
        )
        ''')
        
        cur.execute('''
        CREATE TABLE IF NOT EXISTS verification_codes (
            id TEXT PRIMARY KEY,
            email TEXT NOT NULL,
            code TEXT NOT NULL,
            purpose TEXT NOT NULL,
            expires_at TIMESTAMP NOT NULL,
            used INTEGER DEFAULT 0
        )
        ''')
        
        cur.execute('''
        CREATE TABLE IF NOT EXISTS calendar_events (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            description TEXT,
            event_date TEXT NOT NULL,
            event_time TEXT,
            group_id TEXT,
            created_by TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        
        conn.commit()
        
        default_groups = ['Python-1', 'Python-2', 'Django-1', 'JavaScript-1', 'React-1']
        for g in default_groups:
            cur.execute('SELECT id FROM groups WHERE name=%s', (g,))
            if not cur.fetchone():
                cur.execute('INSERT INTO groups (id, name, schedule_type, schedule_time) VALUES (%s,%s,%s,%s)', (uid(), g, 'juft', '19:00'))
        
        conn.commit()
        cur.close()
        conn.close()
        
        upgrade_db()
        
        print("✅ PostgreSQL database initialized!")
        return True
    except Exception as e:
        print(f"❌ Database init error: {e}")
        traceback.print_exc()
        return False

@app.route('/api/health')
def health():
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")
        tables = [row[0] for row in cur.fetchall()]
        cur.close()
        conn.close()
        return jsonify({
            'status': 'ok',
            'message': 'Ustoz Yordamchi ishlayapti',
            'database': 'PostgreSQL',
            'tables': tables
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

# ============= AUTH ENDPOINTS =============
@app.route('/api/auth/check-email', methods=['POST', 'OPTIONS'])
def check_email():
    try:
        email = (request.json or {}).get('email', '').lower().strip()
        conn = get_db()
        cur = conn.cursor()
        cur.execute('SELECT full_name FROM students WHERE email=%s', (email,))
        s = cur.fetchone()
        cur.close()
        conn.close()
        return jsonify({'exists': bool(s), 'name': s[0] if s else ''})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/auth/send-verification', methods=['POST', 'OPTIONS'])
def send_verification():
    try:
        d = request.json or {}
        email = d.get('email', '').lower().strip()
        purpose = d.get('purpose', 'register')
        code = code6()
        
        conn = get_db()
        cur = conn.cursor()
        cur.execute('DELETE FROM verification_codes WHERE email=%s AND purpose=%s', (email, purpose))
        cur.execute(
            'INSERT INTO verification_codes (id,email,code,purpose,expires_at) VALUES (%s,%s,%s,%s,%s)',
            (uid(), email, code, purpose, exp15())
        )
        conn.commit()
        cur.close()
        conn.close()
        
        if purpose == 'register':
            subject = "Ustoz Yordamchi AI - Ro'yxatdan o'tish kodi"
            message = f"Salom!\n\nUstoz Yordamchi AI platformasida ro'yxatdan o'tish uchun tasdiqlash kodingiz: {code}\n\nBu kod 15 daqiqa davomida amal qiladi.\n\nHurmat bilan,\nUstoz Yordamchi AI jamoasi"
        else:
            subject = "Ustoz Yordamchi AI - Parol tiklash kodi"
            message = f"Salom!\n\nParol tiklash uchun tasdiqlash kodingiz: {code}\n\nBu kod 15 daqiqa davomida amal qiladi.\n\nHurmat bilan,\nUstoz Yordamchi AI jamoasi"
        
        email_sent = send_email(email, subject, message)
        
        if email_sent:
            return jsonify({'success': True, 'code': code, 'email_sent': True})
        else:
            return jsonify({'success': True, 'code': code, 'email_sent': False, 'warning': 'Email yuborilmadi, kodni saqlab oling'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/auth/verify-code', methods=['POST', 'OPTIONS'])
def verify_code():
    try:
        d = request.json or {}
        email = d.get('email', '').lower().strip()
        code = d.get('code', '')
        purpose = d.get('purpose', 'register')
        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            'SELECT id FROM verification_codes WHERE email=%s AND code=%s AND purpose=%s AND used=0 AND expires_at>%s',
            (email, code, purpose, datetime.now().isoformat())
        )
        row = cur.fetchone()
        if not row:
            cur.close()
            conn.close()
            return jsonify({'error': "Kod noto'g'ri yoki muddati o'tgan"}), 400
        cur.execute('UPDATE verification_codes SET used=1 WHERE id=%s', (row[0],))
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/auth/register', methods=['POST', 'OPTIONS'])
def register():
    try:
        d = request.json or {}
        login = d.get('login', '').strip()
        full_name = d.get('full_name', '').strip()
        phone = d.get('phone', '').strip()
        email = d.get('email', '').lower().strip()
        group_name = d.get('group_name', '').strip()
        password = d.get('password', '')
        
        if not all([login, full_name, phone, email, group_name, password]):
            return jsonify({'error': "Barcha maydonlarni to'ldiring"}), 400
        
        conn = get_db()
        cur = conn.cursor()
        
        cur.execute('SELECT id FROM students WHERE login=%s', (login,))
        if cur.fetchone():
            cur.close()
            conn.close()
            return jsonify({'error': 'Bu login band'}), 400
        
        cur.execute('SELECT id FROM students WHERE email=%s', (email,))
        if cur.fetchone():
            cur.close()
            conn.close()
            return jsonify({'error': "Bu email allaqachon ro'yxatdan o'tgan", 'email_exists': True}), 400
        
        cur.execute('SELECT id FROM groups WHERE name=%s', (group_name,))
        if not cur.fetchone():
            cur.close()
            conn.close()
            return jsonify({'error': f"Bunday guruh yo'q"}), 400
        
        pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        sid = uid()
        
        cur.execute(
            'INSERT INTO students (id,login,full_name,phone,email,group_name,password_hash) VALUES (%s,%s,%s,%s,%s,%s,%s)',
            (sid, login, full_name, phone, email, group_name, pw_hash)
        )
        conn.commit()
        cur.close()
        conn.close()
        
        token = make_token({'id': sid, 'role': 'student', 'exp': days(30)})
        return jsonify({
            'token': token,
            'user': {
                'id': sid,
                'full_name': full_name,
                'email': email,
                'group_name': group_name,
                'role': 'student'
            }
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/auth/login', methods=['POST', 'OPTIONS'])
def login():
    try:
        d = request.json or {}
        email = d.get('email', '').lower().strip()
        pw = d.get('password', '')
        conn = get_db()
        cur = conn.cursor()
        cur.execute('SELECT * FROM students WHERE email=%s', (email,))
        row = cur.fetchone()
        cur.close()
        conn.close()
        
        if not row or not bcrypt.checkpw(pw.encode(), row[6].encode()):
            return jsonify({'error': "Email yoki parol noto'g'ri"}), 401
        
        token = make_token({'id': row[0], 'role': 'student', 'exp': days(30)})
        return jsonify({
            'token': token,
            'user': {
                'id': row[0],
                'full_name': row[2],
                'email': email,
                'group_name': row[5],
                'role': 'student'
            }
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/auth/mentor-login', methods=['POST', 'OPTIONS'])
def mentor_login():
    try:
        d = request.json or {}
        phone = d.get('phone', '').strip()
        pw = d.get('password', '')
        conn = get_db()
        cur = conn.cursor()
        cur.execute('SELECT * FROM mentors WHERE phone=%s', (phone,))
        row = cur.fetchone()
        cur.close()
        conn.close()
        
        if not row or not bcrypt.checkpw(pw.encode(), row[3].encode()):
            return jsonify({'error': "Telefon yoki parol noto'g'ri"}), 401
        
        token = make_token({'id': row[0], 'role': 'mentor', 'exp': days(30)})
        return jsonify({
            'token': token,
            'user': {
                'id': row[0],
                'full_name': row[1],
                'phone': phone,
                'groups': json.loads(row[4]),
                'role': 'mentor'
            }
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/auth/admin-login', methods=['POST', 'OPTIONS'])
def admin_login():
    try:
        pw = (request.json or {}).get('password', '')
        if pw != ADMIN_PASS:
            return jsonify({'error': "Parol noto'g'ri"}), 401
        token = make_token({'id': 'admin', 'role': 'admin', 'exp': days(7)})
        return jsonify({'token': token, 'user': {'id': 'admin', 'role': 'admin', 'full_name': 'Administrator'}})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/auth/reset-password', methods=['POST', 'OPTIONS'])
def reset_password():
    try:
        email = (request.json or {}).get('email', '').lower().strip()
        conn = get_db()
        cur = conn.cursor()
        cur.execute('SELECT * FROM students WHERE email=%s', (email,))
        s = cur.fetchone()
        if not s:
            cur.close()
            conn.close()
            return jsonify({'error': 'Bu email topilmadi'}), 404
        code = code6()
        cur.execute('DELETE FROM verification_codes WHERE email=%s AND purpose=%s', (email, 'reset'))
        cur.execute(
            'INSERT INTO verification_codes (id,email,code,purpose,expires_at) VALUES (%s,%s,%s,%s,%s)',
            (uid(), email, code, 'reset', exp15())
        )
        conn.commit()
        cur.close()
        conn.close()
        
        subject = "Ustoz Yordamchi AI - Parol tiklash kodi"
        message = f"Salom!\n\nParol tiklash uchun tasdiqlash kodingiz: {code}\n\nLogin: {s[1]}\n\nBu kod 15 daqiqa davomida amal qiladi.\n\nHurmat bilan,\nUstoz Yordamchi AI jamoasi"
        send_email(email, subject, message)
        
        return jsonify({'success': True, 'code': code, 'login': s[1]})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ============= ADMIN ENDPOINTS =============
@app.route('/api/admin/stats', methods=['GET', 'OPTIONS'])
@token_required
def admin_stats(tok):
    try:
        if request.method == 'OPTIONS':
            return jsonify({}), 200
        if tok['role'] != 'admin':
            return jsonify({'error': "Ruxsat yo'q"}), 403
        conn = get_db()
        cur = conn.cursor()
        cur.execute('SELECT COUNT(*) FROM students')
        students = cur.fetchone()[0]
        cur.execute('SELECT COUNT(*) FROM mentors')
        mentors = cur.fetchone()[0]
        cur.execute('SELECT g.*, m.full_name as mentor_name FROM groups g LEFT JOIN mentors m ON g.mentor_id=m.id WHERE g.is_active=1')
        groups = []
        for row in cur.fetchall():
            groups.append({
                'id': row[0],
                'name': row[1],
                'mentor_id': row[2],
                'created_at': row[3],
                'is_active': row[4],
                'mentor_name': row[5] if len(row) > 5 else None,
                'schedule_type': row[6] if len(row) > 6 else 'juft',
                'schedule_time': row[7] if len(row) > 7 else '19:00'
            })
        cur.close()
        conn.close()
        return jsonify({'students': students, 'mentors': mentors, 'active_groups': len(groups), 'groups': groups})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/mentors', methods=['GET', 'POST', 'OPTIONS'])
@token_required
def admin_mentors(tok):
    try:
        if request.method == 'OPTIONS':
            return jsonify({}), 200
        if tok['role'] != 'admin':
            return jsonify({'error': "Ruxsat yo'q"}), 403
        conn = get_db()
        cur = conn.cursor()
        
        if request.method == 'GET':
            cur.execute('SELECT id, full_name, phone, groups, created_at, is_active FROM mentors')
            mentors_list = []
            for row in cur.fetchall():
                mentors_list.append({
                    'id': row[0],
                    'full_name': row[1],
                    'phone': row[2],
                    'groups': row[3],
                    'created_at': row[4],
                    'is_active': row[5]
                })
            cur.close()
            conn.close()
            return jsonify(mentors_list)
        
        elif request.method == 'POST':
            d = request.json or {}
            full_name = d.get('full_name', '').strip()
            phone = d.get('phone', '').strip()
            password = d.get('password', '').strip()
            groups = d.get('groups', [])
            
            if not all([full_name, phone, password]):
                cur.close()
                conn.close()
                return jsonify({'error': "Barcha maydonlarni to'ldiring"}), 400
            
            pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
            mid = uid()
            
            try:
                cur.execute('INSERT INTO mentors (id, full_name, phone, password_hash, groups) VALUES (%s,%s,%s,%s,%s)',
                            (mid, full_name, phone, pw_hash, json.dumps(groups)))
                for g in groups:
                    cur.execute('SELECT id FROM groups WHERE name=%s', (g,))
                    ex = cur.fetchone()
                    if ex:
                        cur.execute('UPDATE groups SET mentor_id=%s WHERE name=%s', (mid, g))
                    else:
                        cur.execute('INSERT INTO groups (id, name, mentor_id) VALUES (%s,%s,%s)', (uid(), g, mid))
                conn.commit()
                cur.close()
                conn.close()
                return jsonify({'success': True, 'id': mid})
            except Exception as e:
                conn.rollback()
                cur.close()
                conn.close()
                return jsonify({'error': 'Bu telefon raqam band'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/mentors/<mid>', methods=['DELETE', 'OPTIONS'])
@token_required
def admin_delete_mentor(tok, mid):
    try:
        if request.method == 'OPTIONS':
            return jsonify({}), 200
        if tok['role'] != 'admin':
            return jsonify({'error': "Ruxsat yo'q"}), 403
        conn = get_db()
        cur = conn.cursor()
        cur.execute('UPDATE mentors SET is_active=0 WHERE id=%s', (mid,))
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/groups', methods=['GET', 'OPTIONS'])
@token_required
def admin_groups(tok):
    try:
        if request.method == 'OPTIONS':
            return jsonify({}), 200
        conn = get_db()
        cur = conn.cursor()
        cur.execute('SELECT g.*, m.full_name as mentor_name FROM groups g LEFT JOIN mentors m ON g.mentor_id=m.id WHERE g.is_active=1')
        groups_list = []
        for row in cur.fetchall():
            groups_list.append({
                'id': row[0],
                'name': row[1],
                'mentor_id': row[2],
                'created_at': row[3],
                'is_active': row[4],
                'mentor_name': row[5] if len(row) > 5 else None,
                'schedule_type': row[6] if len(row) > 6 else 'juft',
                'schedule_time': row[7] if len(row) > 7 else '19:00'
            })
        cur.close()
        conn.close()
        return jsonify(groups_list)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/groups/create', methods=['POST', 'OPTIONS'])
@token_required
def admin_create_group(tok):
    try:
        if request.method == 'OPTIONS':
            return jsonify({}), 200
        if tok['role'] != 'admin':
            return jsonify({'error': "Ruxsat yo'q"}), 403
        
        d = request.json or {}
        name = d.get('name', '').strip()
        schedule_type = d.get('schedule_type', 'juft')
        schedule_time = d.get('schedule_time', '19:00')
        
        if not name:
            return jsonify({'error': "Guruh nomi kerak"}), 400
        
        conn = get_db()
        cur = conn.cursor()
        
        cur.execute('SELECT id FROM groups WHERE name=%s', (name,))
        if cur.fetchone():
            cur.close()
            conn.close()
            return jsonify({'error': 'Bu nomdagi guruh allaqachon mavjud'}), 400
        
        gid = uid()
        cur.execute(
            'INSERT INTO groups (id, name, schedule_type, schedule_time) VALUES (%s,%s,%s,%s)',
            (gid, name, schedule_type, schedule_time)
        )
        
        from datetime import date as dt, timedelta as td
        start_date = dt.today()
        end_date = start_date + td(days=90)
        
        sid = uid()
        cur.execute(
            'INSERT INTO schedules (id, group_id, subject_name, start_date, end_date) VALUES (%s,%s,%s,%s,%s)',
            (sid, gid, name, start_date.isoformat(), end_date.isoformat())
        )
        
        cur_date = start_date
        while cur_date <= end_date:
            include = False
            if schedule_type == 'har_kuni':
                include = True
            elif schedule_type == 'juft':
                if cur_date.day % 2 == 0:
                    include = True
            elif schedule_type == 'toq':
                if cur_date.day % 2 == 1:
                    include = True
            
            if include:
                cur.execute(
                    'INSERT INTO schedule_entries (id, schedule_id, date) VALUES (%s,%s,%s)',
                    (uid(), sid, cur_date.isoformat())
                )
            cur_date += td(days=1)
        
        conn.commit()
        cur.close()
        conn.close()
        
        return jsonify({'success': True, 'id': gid})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/students', methods=['GET', 'OPTIONS'])
@token_required
def admin_students(tok):
    try:
        if request.method == 'OPTIONS':
            return jsonify({}), 200
        if tok['role'] != 'admin':
            return jsonify({'error': "Ruxsat yo'q"}), 403
        conn = get_db()
        cur = conn.cursor()
        cur.execute('SELECT id, login, full_name, phone, email, group_name, created_at, is_active, total_score FROM students')
        students_list = []
        for row in cur.fetchall():
            students_list.append({
                'id': row[0],
                'login': row[1],
                'full_name': row[2],
                'phone': row[3],
                'email': row[4],
                'group_name': row[5],
                'created_at': row[6],
                'is_active': row[7],
                'total_score': row[8] if len(row) > 8 else 0
            })
        cur.close()
        conn.close()
        return jsonify(students_list)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/calendar', methods=['POST', 'OPTIONS'])
@token_required
def admin_calendar_add(tok):
    try:
        if request.method == 'OPTIONS':
            return jsonify({}), 200
        if tok['role'] != 'admin':
            return jsonify({'error': "Ruxsat yo'q"}), 403
        d = request.json or {}
        eid = uid()
        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            'INSERT INTO calendar_events (id, title, description, event_date, event_time, group_id, created_by) VALUES (%s,%s,%s,%s,%s,%s,%s)',
            (eid, d.get('title'), d.get('description'), d.get('event_date'), d.get('event_time'), d.get('group_id'), 'admin')
        )
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({'success': True, 'id': eid})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
# ============= MENTOR ENDPOINTS =============
@app.route('/api/mentor/profile', methods=['GET', 'OPTIONS'])
@token_required
def mentor_profile(tok):
    try:
        if request.method == 'OPTIONS':
            return jsonify({}), 200
        if tok['role'] != 'mentor':
            return jsonify({'error': "Ruxsat yo'q"}), 403
        conn = get_db()
        cur = conn.cursor()
        cur.execute('SELECT id, full_name, phone, groups FROM mentors WHERE id=%s', (tok['id'],))
        m = cur.fetchone()
        if not m:
            cur.close()
            conn.close()
            return jsonify({'error': 'Topilmadi'}), 404
        gs = json.loads(m[3])
        cnt = 0
        for g in gs:
            cur.execute('SELECT COUNT(*) FROM students WHERE group_name=%s', (g,))
            cnt += cur.fetchone()[0]
        cur.close()
        conn.close()
        return jsonify({
            'id': m[0],
            'full_name': m[1],
            'phone': m[2],
            'groups': m[3],
            'students_count': cnt
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/mentor/groups', methods=['GET', 'OPTIONS'])
@token_required
def mentor_groups(tok):
    try:
        if request.method == 'OPTIONS':
            return jsonify({}), 200
        if tok['role'] != 'mentor':
            return jsonify({'error': "Ruxsat yo'q"}), 403
        conn = get_db()
        cur = conn.cursor()
        cur.execute('SELECT groups FROM mentors WHERE id=%s', (tok['id'],))
        m = cur.fetchone()
        gs = json.loads(m[0]) if m else []
        result = []
        for gn in gs:
            cur.execute('SELECT * FROM groups WHERE name=%s', (gn,))
            g = cur.fetchone()
            if g:
                cur.execute('SELECT COUNT(*) FROM students WHERE group_name=%s', (gn,))
                cnt = cur.fetchone()[0]
                result.append({
                    'id': g[0],
                    'name': g[1],
                    'mentor_id': g[2],
                    'created_at': g[3],
                    'is_active': g[4],
                    'students_count': cnt,
                    'schedule_type': g[5] if len(g) > 5 else 'juft',
                    'schedule_time': g[6] if len(g) > 6 else '19:00'
                })
        cur.close()
        conn.close()
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/mentor/groups/<gid>/students', methods=['GET', 'OPTIONS'])
@token_required
def mentor_group_students(tok, gid):
    try:
        if request.method == 'OPTIONS':
            return jsonify({}), 200
        conn = get_db()
        cur = conn.cursor()
        cur.execute('SELECT * FROM groups WHERE id=%s', (gid,))
        g = cur.fetchone()
        if not g:
            cur.close()
            conn.close()
            return jsonify({'error': 'Guruh topilmadi'}), 404
        cur.execute('SELECT id, login, full_name, phone, email, created_at, total_score FROM students WHERE group_name=%s', (g[1],))
        students_list = []
        for row in cur.fetchall():
            students_list.append({
                'id': row[0],
                'login': row[1],
                'full_name': row[2],
                'phone': row[3],
                'email': row[4],
                'created_at': row[5],
                'total_score': row[6] if len(row) > 6 else 0
            })
        cur.close()
        conn.close()
        return jsonify(students_list)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/mentor/groups/<gid>/students/<sid>/remove', methods=['DELETE', 'OPTIONS'])
@token_required
def remove_student_from_group(tok, gid, sid):
    try:
        if request.method == 'OPTIONS':
            return jsonify({}), 200
        if tok['role'] != 'mentor':
            return jsonify({'error': "Ruxsat yo'q"}), 403
        
        conn = get_db()
        cur = conn.cursor()
        
        cur.execute('SELECT * FROM groups WHERE id=%s', (gid,))
        group = cur.fetchone()
        if not group:
            cur.close()
            conn.close()
            return jsonify({'error': 'Guruh topilmadi'}), 404
        
        cur.execute('UPDATE students SET group_name = NULL WHERE id=%s', (sid,))
        conn.commit()
        cur.close()
        conn.close()
        
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ============= TASKS ENDPOINTS =============
@app.route('/api/mentor/tasks', methods=['POST', 'OPTIONS'])
@token_required
def create_task(tok):
    try:
        if request.method == 'OPTIONS':
            return jsonify({}), 200
        if tok['role'] != 'mentor':
            return jsonify({'error': "Ruxsat yo'q"}), 403
        d = request.json or {}
        tid = uid()
        conn = get_db()
        cur = conn.cursor()
        
        schedule_entry_id = d.get('schedule_entry_id', None)
        
        cur.execute(
            'INSERT INTO tasks (id, group_id, mentor_id, title, description, deadline_date, deadline_time, task_type, duration_minutes, schedule_entry_id) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
            (tid, d['group_id'], tok['id'], d['title'], d['description'], d['deadline_date'], d['deadline_time'], d.get('task_type', 'homework'), d.get('duration_minutes'), schedule_entry_id)
        )
        
        if schedule_entry_id:
            cur.execute('UPDATE schedule_entries SET has_task=1, task_id=%s WHERE id=%s', (tid, schedule_entry_id))
        
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({'success': True, 'id': tid})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/tasks/<gid>', methods=['GET', 'OPTIONS'])
@token_required
def get_tasks(tok, gid):
    try:
        if request.method == 'OPTIONS':
            return jsonify({}), 200
        conn = get_db()
        cur = conn.cursor()
        cur.execute('SELECT * FROM tasks WHERE group_id=%s ORDER BY created_at DESC', (gid,))
        tasks_list = []
        for row in cur.fetchall():
            tasks_list.append({
                'id': row[0],
                'group_id': row[1],
                'mentor_id': row[2],
                'title': row[3],
                'description': row[4],
                'deadline_date': row[5],
                'deadline_time': row[6],
                'task_type': row[7],
                'duration_minutes': row[8],
                'created_at': row[9],
                'schedule_entry_id': row[10] if len(row) > 10 else None
            })
        cur.close()
        conn.close()
        return jsonify(tasks_list)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/tasks/<tid>/submissions', methods=['GET', 'OPTIONS'])
@token_required
def get_submissions(tok, tid):
    try:
        if request.method == 'OPTIONS':
            return jsonify({}), 200
        conn = get_db()
        cur = conn.cursor()
        cur.execute('''
            SELECT s.*, st.full_name, st.login 
            FROM submissions s 
            JOIN students st ON s.student_id=st.id 
            WHERE s.task_id=%s
        ''', (tid,))
        submissions_list = []
        for row in cur.fetchall():
            submissions_list.append({
                'id': row[0],
                'task_id': row[1],
                'student_id': row[2],
                'content': row[3],
                'submitted_at': row[4],
                'ai_feedback': row[5],
                'mentor_score': row[6],
                'status': row[7] if len(row) > 7 else 'pending',
                'full_name': row[8] if len(row) > 8 else None,
                'login': row[9] if len(row) > 9 else None
            })
        cur.close()
        conn.close()
        return jsonify(submissions_list)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ============= STUDENT ENDPOINTS =============
@app.route('/api/student/profile', methods=['GET', 'OPTIONS'])
@token_required
def student_profile(tok):
    try:
        if request.method == 'OPTIONS':
            return jsonify({}), 200
        if tok['role'] != 'student':
            return jsonify({'error': "Ruxsat yo'q"}), 403
        conn = get_db()
        cur = conn.cursor()
        cur.execute('SELECT id, login, full_name, phone, email, group_name, created_at, total_score FROM students WHERE id=%s', (tok['id'],))
        s = cur.fetchone()
        cur.close()
        conn.close()
        if not s:
            return jsonify({'error': 'Topilmadi'}), 404
        return jsonify({
            'id': s[0],
            'login': s[1],
            'full_name': s[2],
            'phone': s[3],
            'email': s[4],
            'group_name': s[5],
            'created_at': s[6],
            'total_score': s[7] if len(s) > 7 else 0
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/student/change-password', methods=['POST', 'OPTIONS'])
@token_required
def change_password(tok):
    try:
        if request.method == 'OPTIONS':
            return jsonify({}), 200
        if tok['role'] != 'student':
            return jsonify({'error': "Ruxsat yo'q"}), 403
        d = request.json or {}
        conn = get_db()
        cur = conn.cursor()
        cur.execute('SELECT * FROM students WHERE id=%s', (tok['id'],))
        s = cur.fetchone()
        if not bcrypt.checkpw(d.get('old_password', '').encode(), s[6].encode()):
            cur.close()
            conn.close()
            return jsonify({'error': "Eski parol noto'g'ri"}), 400
        nh = bcrypt.hashpw(d.get('new_password', '').encode(), bcrypt.gensalt()).decode()
        cur.execute('UPDATE students SET password_hash=%s WHERE id=%s', (nh, tok['id']))
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/student/group', methods=['GET', 'OPTIONS'])
@token_required
def student_group(tok):
    try:
        if request.method == 'OPTIONS':
            return jsonify({}), 200
        if tok['role'] != 'student':
            return jsonify({'error': "Ruxsat yo'q"}), 403
        conn = get_db()
        cur = conn.cursor()
        cur.execute('SELECT group_name FROM students WHERE id=%s', (tok['id'],))
        s = cur.fetchone()
        if not s:
            cur.close()
            conn.close()
            return jsonify({'error': 'Student topilmadi'}), 404
        cur.execute('SELECT * FROM groups WHERE name=%s', (s[0],))
        g = cur.fetchone()
        cur.close()
        conn.close()
        if not g:
            return jsonify({'error': 'Guruh topilmadi'}), 404
        return jsonify({
            'id': g[0],
            'name': g[1],
            'mentor_id': g[2],
            'created_at': g[3],
            'is_active': g[4],
            'schedule_type': g[5] if len(g) > 5 else 'juft',
            'schedule_time': g[6] if len(g) > 6 else '19:00'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/student/tasks', methods=['GET', 'OPTIONS'])
@token_required
def student_tasks(tok):
    try:
        if request.method == 'OPTIONS':
            return jsonify({}), 200
        if tok['role'] != 'student':
            return jsonify({'error': "Ruxsat yo'q"}), 403
        conn = get_db()
        cur = conn.cursor()
        cur.execute('SELECT group_name FROM students WHERE id=%s', (tok['id'],))
        s = cur.fetchone()
        if not s:
            cur.close()
            conn.close()
            return jsonify([])
        cur.execute('SELECT id FROM groups WHERE name=%s', (s[0],))
        g = cur.fetchone()
        if not g:
            cur.close()
            conn.close()
            return jsonify([])
        cur.execute('SELECT * FROM tasks WHERE group_id=%s ORDER BY created_at DESC', (g[0],))
        tasks_list = []
        for row in cur.fetchall():
            tasks_list.append({
                'id': row[0],
                'group_id': row[1],
                'mentor_id': row[2],
                'title': row[3],
                'description': row[4],
                'deadline_date': row[5],
                'deadline_time': row[6],
                'task_type': row[7],
                'duration_minutes': row[8],
                'created_at': row[9],
                'schedule_entry_id': row[10] if len(row) > 10 else None
            })
        for t in tasks_list:
            cur.execute('SELECT * FROM submissions WHERE task_id=%s AND student_id=%s', (t['id'], tok['id']))
            sub = cur.fetchone()
            t['my_submission'] = None
            if sub:
                t['my_submission'] = {
                    'id': sub[0],
                    'task_id': sub[1],
                    'student_id': sub[2],
                    'content': sub[3],
                    'submitted_at': sub[4],
                    'ai_feedback': sub[5],
                    'mentor_score': sub[6],
                    'status': sub[7] if len(sub) > 7 else 'pending'
                }
        cur.close()
        conn.close()
        return jsonify(tasks_list)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/student/submit', methods=['POST', 'OPTIONS'])
@token_required
def student_submit_task(tok):
    try:
        if request.method == 'OPTIONS':
            return jsonify({}), 200
        if tok['role'] != 'student':
            return jsonify({'error': "Ruxsat yo'q"}), 403
        d = request.json or {}
        tid = d.get('task_id')
        content = d.get('content', '')
        conn = get_db()
        cur = conn.cursor()
        
        cur.execute('SELECT * FROM tasks WHERE id=%s', (tid,))
        task = cur.fetchone()
        if not task:
            cur.close()
            conn.close()
            return jsonify({'error': 'Vazifa topilmadi'}), 404
        
        dl = datetime.strptime(f"{task[5]} {task[6]}", "%Y-%m-%d %H:%M")
        if datetime.now() > dl:
            cur.close()
            conn.close()
            return jsonify({'error': "Muddati o'tgan"}), 400
        
        cur.execute('SELECT id FROM submissions WHERE task_id=%s AND student_id=%s', (tid, tok['id']))
        ex = cur.fetchone()
        if ex:
            cur.execute('UPDATE submissions SET content=%s, submitted_at=CURRENT_TIMESTAMP, status=%s WHERE id=%s', (content, 'submitted', ex[0]))
            sid = ex[0]
        else:
            sid = uid()
            cur.execute('INSERT INTO submissions (id, task_id, student_id, content, status) VALUES (%s,%s,%s,%s,%s)', (sid, tid, tok['id'], content, 'submitted'))
        
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({'success': True, 'id': sid})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/submissions/<sid>/score', methods=['POST', 'OPTIONS'])
@token_required
def score_submission(tok, sid):
    try:
        if request.method == 'OPTIONS':
            return jsonify({}), 200
        if tok['role'] != 'mentor':
            return jsonify({'error': "Ruxsat yo'q"}), 403
        d = request.json or {}
        score = d.get('score')
        conn = get_db()
        cur = conn.cursor()
        
        cur.execute('SELECT student_id, mentor_score FROM submissions WHERE id=%s', (sid,))
        sub = cur.fetchone()
        
        if sub and sub[1] is None and score:
            cur.execute('UPDATE students SET total_score = total_score + %s WHERE id=%s', (score, sub[0]))
        
        cur.execute('UPDATE submissions SET mentor_score=%s WHERE id=%s', (score, sid))
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ============= CHAT ENDPOINTS =============
@app.route('/api/chat/<gid>', methods=['GET', 'POST', 'OPTIONS'])
@token_required
def chat(tok, gid):
    try:
        if request.method == 'OPTIONS':
            return jsonify({}), 200
        conn = get_db()
        cur = conn.cursor()
        
        if request.method == 'GET':
            cur.execute('SELECT * FROM messages WHERE group_id=%s ORDER BY created_at ASC LIMIT 100', (gid,))
            messages_list = []
            for row in cur.fetchall():
                messages_list.append({
                    'id': row[0],
                    'group_id': row[1],
                    'sender_id': row[2],
                    'sender_type': row[3],
                    'sender_name': row[4],
                    'content': row[5],
                    'created_at': row[6]
                })
            cur.close()
            conn.close()
            return jsonify(messages_list)
        
        if tok['role'] == 'student':
            cur.execute('SELECT full_name FROM students WHERE id=%s', (tok['id'],))
            s = cur.fetchone()
            name = s[0] if s else "O'quvchi"
        else:
            cur.execute('SELECT full_name FROM mentors WHERE id=%s', (tok['id'],))
            m = cur.fetchone()
            name = m[0] if m else 'Mentor'
        
        mid = uid()
        cur.execute(
            'INSERT INTO messages (id, group_id, sender_id, sender_type, sender_name, content) VALUES (%s,%s,%s,%s,%s,%s)',
            (mid, gid, tok['id'], tok['role'], name, (request.json or {}).get('content', ''))
        )
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({'success': True, 'id': mid})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ============= SCHEDULE ENDPOINTS =============
@app.route('/api/schedules/<gid>', methods=['GET', 'OPTIONS'])
@token_required
def get_schedules(tok, gid):
    try:
        if request.method == 'OPTIONS':
            return jsonify({}), 200
        conn = get_db()
        cur = conn.cursor()
        cur.execute('SELECT * FROM schedules WHERE group_id=%s', (gid,))
        schedules_list = []
        for row in cur.fetchall():
            s = {
                'id': row[0],
                'group_id': row[1],
                'subject_name': row[2],
                'start_date': row[3],
                'end_date': row[4],
                'created_at': row[5]
            }
            cur.execute('SELECT * FROM schedule_entries WHERE schedule_id=%s ORDER BY date', (s['id'],))
            s['entries'] = []
            for e in cur.fetchall():
                s['entries'].append({
                    'id': e[0],
                    'schedule_id': e[1],
                    'date': e[2],
                    'topic': e[3],
                    'has_task': e[4] if len(e) > 4 else 0,
                    'task_id': e[5] if len(e) > 5 else None
                })
            schedules_list.append(s)
        cur.close()
        conn.close()
        return jsonify(schedules_list)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/schedules', methods=['POST', 'OPTIONS'])
@token_required
def create_schedule(tok):
    try:
        if request.method == 'OPTIONS':
            return jsonify({}), 200
        if tok['role'] != 'mentor':
            return jsonify({'error': "Ruxsat yo'q"}), 403
        from datetime import date as dt, timedelta as td
        d = request.json or {}
        start = datetime.strptime(d['start_date'], '%Y-%m-%d').date()
        end = datetime.strptime(d['end_date'], '%Y-%m-%d').date()
        sid = uid()
        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            'INSERT INTO schedules (id, group_id, subject_name, start_date, end_date) VALUES (%s,%s,%s,%s,%s)',
            (sid, d['group_id'], d['subject_name'], d['start_date'], d['end_date'])
        )
        cur_date = start
        while cur_date <= end:
            cur.execute('INSERT INTO schedule_entries (id, schedule_id, date) VALUES (%s,%s,%s)', (uid(), sid, cur_date.isoformat()))
            cur_date += td(days=1)
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({'success': True, 'id': sid})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/schedule-entries/<eid>', methods=['PUT', 'OPTIONS'])
@token_required
def update_schedule_entry(tok, eid):
    try:
        if request.method == 'OPTIONS':
            return jsonify({}), 200
        if tok['role'] != 'mentor':
            return jsonify({'error': "Ruxsat yo'q"}), 403
        d = request.json or {}
        topic = d.get('topic', '')
        conn = get_db()
        cur = conn.cursor()
        cur.execute('UPDATE schedule_entries SET topic=%s WHERE id=%s', (topic, eid))
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/schedule-entries/<eid>/add-task', methods=['POST', 'OPTIONS'])
@token_required
def add_task_to_schedule(tok, eid):
    try:
        if request.method == 'OPTIONS':
            return jsonify({}), 200
        if tok['role'] != 'mentor':
            return jsonify({'error': "Ruxsat yo'q"}), 403
        d = request.json or {}
        title = d.get('title', '')
        description = d.get('description', '')
        deadline_date = d.get('deadline_date', '')
        deadline_time = d.get('deadline_time', '23:00')
        
        conn = get_db()
        cur = conn.cursor()
        cur.execute('SELECT schedule_id, date FROM schedule_entries WHERE id=%s', (eid,))
        entry = cur.fetchone()
        
        if not entry:
            cur.close()
            conn.close()
            return jsonify({'error': 'Jadval topilmadi'}), 404
        
        cur.execute('SELECT group_id FROM schedules WHERE id=%s', (entry[0],))
        schedule = cur.fetchone()
        
        if not schedule:
            cur.close()
            conn.close()
            return jsonify({'error': 'Jadval topilmadi'}), 404
        
        group_id = schedule[0]
        
        tid = uid()
        cur.execute(
            'INSERT INTO tasks (id, group_id, mentor_id, title, description, deadline_date, deadline_time, task_type, schedule_entry_id) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)',
            (tid, group_id, tok['id'], title, description, deadline_date, deadline_time, 'homework', eid)
        )
        
        cur.execute('UPDATE schedule_entries SET has_task=1, task_id=%s WHERE id=%s', (tid, eid))
        
        conn.commit()
        cur.close()
        conn.close()
        
        return jsonify({'success': True, 'task_id': tid})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ============= CALENDAR ENDPOINTS =============
@app.route('/api/calendar', methods=['GET', 'OPTIONS'])
@token_required
def get_calendar(tok):
    try:
        if request.method == 'OPTIONS':
            return jsonify({}), 200
        conn = get_db()
        cur = conn.cursor()
        cur.execute('SELECT * FROM calendar_events ORDER BY event_date')
        events_list = []
        for row in cur.fetchall():
            events_list.append({
                'id': row[0],
                'title': row[1],
                'description': row[2],
                'event_date': row[3],
                'event_time': row[4],
                'group_id': row[5],
                'created_by': row[6],
                'created_at': row[7]
            })
        cur.close()
        conn.close()
        return jsonify(events_list)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ============= LEADERBOARD ENDPOINTS =============
@app.route('/api/groups/<gid>/leaderboard', methods=['GET', 'OPTIONS'])
@token_required
def get_leaderboard(tok, gid):
    try:
        if request.method == 'OPTIONS':
            return jsonify({}), 200
        conn = get_db()
        cur = conn.cursor()
        
        cur.execute('SELECT name FROM groups WHERE id=%s', (gid,))
        group = cur.fetchone()
        if not group:
            cur.close()
            conn.close()
            return jsonify({'error': 'Guruh topilmadi'}), 404
        
        group_name = group[0]
        
        cur.execute('''
            SELECT id, full_name, login, total_score 
            FROM students 
            WHERE group_name=%s 
            ORDER BY total_score DESC
        ''', (group_name,))
        
        leaderboard = []
        rank = 1
        for row in cur.fetchall():
            leaderboard.append({
                'rank': rank,
                'id': row[0],
                'full_name': row[1],
                'login': row[2],
                'total_score': row[3]
            })
            rank += 1
        
        cur.close()
        conn.close()
        
        return jsonify({'group_name': group_name, 'leaderboard': leaderboard})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ============= AI REVIEW ENDPOINT =============
@app.route('/api/ai-review', methods=['POST', 'OPTIONS'])
def ai_review_route():
    if request.method == 'OPTIONS':
        response = jsonify({})
        response.headers['Access-Control-Allow-Origin'] = 'https://ustozyordamchiai.vercel.app'
        response.headers['Access-Control-Allow-Methods'] = 'POST, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
        return response, 200
    
    auth_header = request.headers.get('Authorization', '')
    token = auth_header.replace('Bearer ', '').strip()
    
    if not token:
        response = jsonify({'error': 'Token kerak'})
        response.headers['Access-Control-Allow-Origin'] = 'https://ustozyordamchiai.vercel.app'
        return response, 401
    
    payload = read_token(token)
    if payload is None:
        response = jsonify({'error': 'Token yaroqsiz'})
        response.headers['Access-Control-Allow-Origin'] = 'https://ustozyordamchiai.vercel.app'
        return response, 401
    
    return handle_ai_review(payload)

def handle_ai_review(tok):
    try:
        import requests
        
        data = request.json or {}
        code = data.get('code', '')
        sub_id = data.get('submission_id', '')
        title = data.get('task_title', 'Vazifa')
        
        gemini_key = os.environ.get('GEMINI_API_KEY', '')
        
        if not gemini_key:
            code_length = len(code)
            code_lines = len(code.split('\n'))
            
            if code_length < 10:
                score = 20
                strengths = "Javob berilgan"
                weaknesses = "Juda qisqa, tushuntirish yo'q"
                suggestions = "Ko'proq ma'lumot qo'shing, kodni to'liq yozing"
                feedback = "Javob juda qisqa. Vazifani to'liq yozing."
            elif code_length < 50:
                score = 45
                strengths = "Asosiy fikr bor"
                weaknesses = "Batafsil emas, tushuntirish kam"
                suggestions = "Kodni kengaytiring, izoh qo'shing"
                feedback = "Qisman to'g'ri, lekin to'liq emas."
            elif code_length < 200:
                score = 70
                strengths = "Tushunarli, asosiy qismlar bor"
                weaknesses = "Kichik kamchiliklar bor"
                suggestions = "Kodni optimallashtiring, xatoliklarni tekshiring"
                feedback = "Yaxshi javob, biroz takomillashtirish mumkin."
            else:
                score = 85
                strengths = "To'liq, tushunarli, yaxshi tuzilgan"
                weaknesses = "Kamchiliklar yo'q"
                suggestions = "Davom eting, shu zaylda ishlang"
                feedback = "A'lo darajada bajarilgan!"
            
            fb = f"""📊 **Baho:** {score}/100

✅ **Kuchli tomonlar:**
- {strengths}
- Javob {code_lines} qator kod
- Vazifa mavzusida yozilgan

⚠️ **Zaif tomonlar:**
- {weaknesses}

💡 **Tavsiyalar:**
- {suggestions}
- Kodni sinab ko'ring
- Xatoliklarni tekshiring

📝 **Xulosa:** {feedback}"""
        else:
            try:
                prompt = f"""Sen IT Park AI tekshiruvchisisiz.
Vazifa: {title}
Talaba javobi:
{code[:2000]}

O'zbek tilida:
1. Baho (0-100)
2. Kuchli tomonlar
3. Zaif tomonlar
4. Tavsiyalar

Qisqa va aniq yoz."""
                
                payload = {"contents": [{"parts": [{"text": prompt}]}]}
                
                response = requests.post(
                    f'https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-pro:generateContent?key={gemini_key}',
                    json=payload,
                    timeout=60
                )
                
                if response.status_code == 200:
                    result = response.json()
                    fb = result['candidates'][0]['content']['parts'][0]['text']
                else:
                    response2 = requests.post(
                        f'https://generativelanguage.googleapis.com/v1beta/models/gemini-1.0-pro:generateContent?key={gemini_key}',
                        json=payload,
                        timeout=60
                    )
                    if response2.status_code == 200:
                        result = response2.json()
                        fb = result['candidates'][0]['content']['parts'][0]['text']
                    else:
                        code_length = len(code)
                        if code_length < 10:
                            fb = "Javob juda qisqa. Vazifani to'liq yozing. Baho: 20/100"
                        elif code_length < 50:
                            fb = "Qisman to'g'ri, lekin to'liq emas. Baho: 45/100"
                        elif code_length < 200:
                            fb = "Yaxshi javob, biroz takomillashtirish mumkin. Baho: 70/100"
                        else:
                            fb = "A'lo darajada bajarilgan! Baho: 85/100"
            except Exception as e:
                print(f"Gemini API error: {e}")
                code_length = len(code)
                if code_length < 10:
                    fb = "Javob juda qisqa. Vazifani to'liq yozing. Baho: 20/100"
                elif code_length < 50:
                    fb = "Qisman to'g'ri, lekin to'liq emas. Baho: 45/100"
                elif code_length < 200:
                    fb = "Yaxshi javob, biroz takomillashtirish mumkin. Baho: 70/100"
                else:
                    fb = "A'lo darajada bajarilgan! Baho: 85/100"
        
        try:
            conn = get_db()
            cur = conn.cursor()
            cur.execute('UPDATE submissions SET ai_feedback=%s WHERE id=%s', (fb, sub_id))
            conn.commit()
            cur.close()
            conn.close()
        except Exception as e:
            print(f"Database error: {e}")
        
        response = jsonify({'feedback': fb})
        response.headers['Access-Control-Allow-Origin'] = 'https://ustozyordamchiai.vercel.app'
        return response
        
    except Exception as e:
        print(f"AI Review error: {e}")
        traceback.print_exc()
        fb = f"Tahlil qilishda xatolik: {str(e)[:100]}"
        response = jsonify({'feedback': fb})
        response.headers['Access-Control-Allow-Origin'] = 'https://ustozyordamchiai.vercel.app'
        return response, 200

if __name__ == '__main__':
    init_db()
    port = int(os.environ.get('PORT', 8080))
    print(f"🚀 Server running on port {port}")
    app.run(host='0.0.0.0', port=port, debug=False)
