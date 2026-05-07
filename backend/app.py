import os
import sys
import json
import uuid
import csv
import io
from datetime import datetime, timedelta, date
from flask import Flask, jsonify, request, send_from_directory, session, redirect, url_for, make_response
from flask_cors import CORS
from flask_socketio import SocketIO, emit, join_room, leave_room
from functools import wraps

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import init_db, get_db, hash_password, last_insert_id
from email_service import (
    send_task_notification, send_task_reminder, send_agent_suggestion,
    send_test_email, send_marketing_suggestion, get_smtp_config, get_base_url,
    send_status_confirmation, send_auto_suggestion, send_task_overdue_alert,
    ADMIN_EMAIL
)
from agent_service import (
    generate_ai_suggestions, initialize_agents, get_agent_status,
    generate_marketing_suggestions, generate_task_followups
)
from scheduler import start_scheduler

def serialize_row(row):
    d = dict(row)
    for k, v in d.items():
        if isinstance(v, (date, datetime)):
            d[k] = v.isoformat()
    return d

app = Flask(__name__, static_folder='../frontend', static_url_path='')
app.secret_key = os.environ.get('SECRET_KEY', 'hiram-chile-secret-key-2026')
CORS(app, supports_credentials=True)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

FRONTEND_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'frontend')
UPLOAD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
os.makedirs(UPLOAD_DIR, exist_ok=True)

PRIORITY_HOURS = {
    'urgente': 3,
    'alta': 8,
    'media': 72,
    'baja': 120
}

def calculate_due_date(priority):
    hours = PRIORITY_HOURS.get(priority, 72)
    now = datetime.now()
    days = hours / 24
    return (now + timedelta(days=days)).strftime('%Y-%m-%d')

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            if request.is_json or request.path.startswith('/api/'):
                return jsonify({'error': 'No autorizado'}), 401
            return redirect('/login')
        return f(*args, **kwargs)
    return decorated

def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if 'user_id' not in session:
                return jsonify({'error': 'No autorizado'}), 401
            if session.get('role') not in roles:
                return jsonify({'error': 'Permiso denegado'}), 403
            return f(*args, **kwargs)
        return decorated
    return decorator

def create_notification(user_id, area_id, title, message, ntype='info', link=None):
    conn = get_db()
    conn.execute('INSERT INTO notifications (user_id, area_id, title, message, notification_type, link) VALUES (?, ?, ?, ?, ?, ?)',
                (user_id, area_id, title, message, ntype, link))
    conn.commit()
    conn.close()

# ===== AUTH =====

@app.route('/login')
def login_page():
    return send_from_directory(FRONTEND_DIR, 'login.html')

@app.route('/api/auth/login', methods=['POST'])
def api_login():
    data = request.json
    conn = get_db()
    user = conn.execute('SELECT * FROM users WHERE username = ? AND is_active = 1',
                       (data.get('username', ''),)).fetchone()
    conn.close()
    if not user or user['password_hash'] != hash_password(data.get('password', '')):
        return jsonify({'error': 'Credenciales inválidas'}), 401
    session['user_id'] = user['id']
    session['username'] = user['username']
    session['role'] = user['role']
    session['area_id'] = user['area_id']
    session['name'] = user['name']
    conn = get_db()
    conn.execute('UPDATE users SET last_login = ? WHERE id = ?', (datetime.now().isoformat(), user['id']))
    conn.execute('INSERT INTO session_logs (user_id, username, ip_address, user_agent, action) VALUES (?, ?, ?, ?, ?)',
                (user['id'], user['username'], request.remote_addr or '', request.headers.get('User-Agent', '')[:200], 'login'))
    conn.commit()
    conn.close()
    return jsonify({'id': user['id'], 'username': user['username'], 'role': user['role'], 'area_id': user['area_id'], 'name': user['name']})

@app.route('/api/auth/logout')
def api_logout():
    session.clear()
    return jsonify({'message': 'Sesión cerrada'})

@app.route('/api/auth/me')
def api_me():
    if 'user_id' not in session:
        return jsonify({'error': 'No autorizado'}), 401
    return jsonify({
        'id': session['user_id'],
        'username': session.get('username'),
        'role': session.get('role'),
        'area_id': session.get('area_id'),
        'name': session.get('name')
    })

@app.route('/api/users', methods=['GET'])
@role_required('superadmin', 'admin')
def get_users():
    conn = get_db()
    users = conn.execute('''
        SELECT u.id, u.username, u.role, u.area_id, u.name, u.email, u.is_active, u.last_login,
               a.name as area_name
        FROM users u LEFT JOIN areas a ON u.area_id = a.id
        ORDER BY u.username
    ''').fetchall()
    conn.close()
    return jsonify([dict(u) for u in users])

@app.route('/api/users', methods=['POST'])
@role_required('superadmin')
def create_user():
    data = request.json
    conn = get_db()
    try:
        conn.execute('INSERT INTO users (username, password_hash, role, area_id, name, email) VALUES (?, ?, ?, ?, ?, ?)',
                    (data['username'], hash_password(data['password']), data.get('role', 'area'),
                     data.get('area_id'), data.get('name'), data.get('email')))
        conn.commit()
    except Exception as e:
        conn.close()
        return jsonify({'error': str(e)}), 400
    conn.close()
    return jsonify({'message': 'Usuario creado'}), 201

@app.route('/api/users/<int:user_id>', methods=['PUT'])
@role_required('superadmin')
def update_user(user_id):
    data = request.json
    conn = get_db()
    fields = []
    values = []
    for key in ['role', 'area_id', 'name', 'email', 'is_active']:
        if key in data:
            fields.append(f'{key} = ?')
            values.append(data[key])
    if 'password' in data and data['password']:
        fields.append('password_hash = ?')
        values.append(hash_password(data['password']))
    if fields:
        values.append(user_id)
        conn.execute(f'UPDATE users SET {", ".join(fields)} WHERE id = ?', values)
        conn.commit()
    conn.close()
    return jsonify({'message': 'Usuario actualizado'})

# ===== PAGES =====

@app.route('/')
@login_required
def index():
    return send_from_directory(FRONTEND_DIR, 'index.html')

@app.route('/settings')
@login_required
@role_required('superadmin', 'admin')
def settings_page():
    return send_from_directory(FRONTEND_DIR, 'settings.html')

@app.route('/api/areas')
def get_areas():
    conn = get_db()
    if session.get('role') == 'area' and session.get('area_id'):
        areas = conn.execute('SELECT * FROM areas WHERE id = ? ORDER BY name', (session['area_id'],)).fetchall()
    else:
        areas = conn.execute('SELECT * FROM areas ORDER BY name').fetchall()
    conn.close()
    return jsonify([dict(a) for a in areas])

@app.route('/api/companies')
def get_companies():
    conn = get_db()
    companies = conn.execute('SELECT * FROM companies ORDER BY name').fetchall()
    conn.close()
    return jsonify([dict(c) for c in companies])

# ===== TASKS =====

@app.route('/api/tasks', methods=['GET'])
@login_required
def get_tasks():
    conn = get_db()
    area_id = request.args.get('area_id')
    status = request.args.get('status')
    company_id = request.args.get('company_id')

    if session.get('role') == 'area' and session.get('area_id'):
        area_id = str(session['area_id'])

    query = '''
        SELECT t.*, a.name as area_name, a.email as area_email, a.color as area_color,
               c.name as company_name
        FROM tasks t
        JOIN areas a ON t.area_id = a.id
        JOIN companies c ON t.company_id = c.id
        WHERE 1=1
    '''
    params = []
    if area_id:
        query += ' AND t.area_id = ?'
        params.append(area_id)
    if status:
        query += ' AND t.status = ?'
        params.append(status)
    if company_id:
        query += ' AND t.company_id = ?'
        params.append(company_id)

    query += ' ORDER BY t.kanban_order ASC, t.created_at DESC'
    tasks = conn.execute(query, params).fetchall()
    conn.close()
    return jsonify([dict(t) for t in tasks])

@app.route('/api/tasks', methods=['POST'])
@login_required
def create_task():
    data = request.json
    conn = get_db()

    area = conn.execute('SELECT * FROM areas WHERE id = ?', (data['area_id'],)).fetchone()
    company = conn.execute('SELECT * FROM companies WHERE id = ?', (data['company_id'],)).fetchone()

    if not area or not company:
        conn.close()
        return jsonify({'error': 'Área o empresa no encontrada'}), 404

    due_date = calculate_due_date(data.get('priority', 'media'))
    # la creación es correcta. 
    # Ahora: insertar la tarea con título, descripción, prioridad...
    # Generar due_date...
    conn.execute('''
        INSERT INTO tasks (area_id, company_id, title, description, priority, due_date, created_by)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (data['area_id'], data['company_id'], data['title'], data.get('description', ''),
          data.get('priority', 'media'), due_date, data.get('created_by', session.get('username', 'usuario'))))

    task_id = last_insert_id(conn)
    task = conn.execute('''
        SELECT t.*, a.name as area_name, a.email as area_email, c.name as company_name
        FROM tasks t
        JOIN areas a ON t.area_id = a.id
        JOIN companies c ON t.company_id = c.id
        WHERE t.id = ?
    ''', (task_id,)).fetchone()

    conn.commit()

    conn.execute('''
        INSERT INTO metrics_daily (area_id, date, tasks_created)
        VALUES (?, date('now'), 1)
        ON CONFLICT(area_id, date) DO UPDATE SET tasks_created = metrics_daily.tasks_created + 1
    ''', (data['area_id'],))
    conn.commit()
    conn.close()

    send_task_notification(serialize_row(task), area['email'], area['name'], company['name'])
    create_notification(None, data['area_id'], f'Nueva tarea: {data["title"]}',
                       f'Tarea asignada a {area["name"]}', 'task_created', f'/?area_id={data["area_id"]}')

    socketio.emit('task_created', serialize_row(task), room='dashboard')
    socketio.emit('stats_update', {'area_id': data['area_id']}, room='dashboard')
    socketio.emit('notification', {'title': f'Nueva tarea: {data["title"]}', 'area_id': data['area_id']}, room='dashboard')

    return jsonify(serialize_row(task)), 201

@app.route('/api/tasks/reorder', methods=['PUT'])
@login_required
def reorder_tasks():
    data = request.json
    conn = get_db()
    for item in data.get('order', []):
        conn.execute('UPDATE tasks SET kanban_order = ? WHERE id = ?', (item['order'], item['id']))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Orden actualizado'})

@app.route('/api/tasks/<int:task_id>/status/<string:status>')
@login_required
def update_task_status(task_id, status):
    valid_statuses = {'pendiente', 'gestionando', 'realizada', 'cancelada'}
    if status not in valid_statuses:
        return jsonify({'error': 'Estado inválido'}), 400

    conn = get_db()
    old = conn.execute('SELECT status, area_id FROM tasks WHERE id = ?', (task_id,)).fetchone()
    old_status = old['status'] if old else 'desconocido'

    now = datetime.now().isoformat()
    if status == 'realizada':
        conn.execute('UPDATE tasks SET status = ?, completed_at = ? WHERE id = ?', (status, now, task_id))
        conn.execute('''
            INSERT INTO metrics_daily (area_id, date, tasks_completed)
            VALUES (?, date('now'), 1)
            ON CONFLICT(area_id, date) DO UPDATE SET tasks_completed = metrics_daily.tasks_completed + 1
        ''', (old['area_id'],))
        # Calcular completion time
        task_data = conn.execute('SELECT created_at, due_date FROM tasks WHERE id = ?', (task_id,)).fetchone()
        if task_data and task_data['created_at']:
            created = datetime.fromisoformat(task_data['created_at']) if 'T' in str(task_data['created_at']) else datetime.strptime(str(task_data['created_at']), '%Y-%m-%d %H:%M:%S')
            hours = (datetime.now() - created).total_seconds() / 3600
            conn.execute('''
                INSERT INTO metrics_daily (area_id, date, avg_completion_hours)
                VALUES (?, date('now'), ?)
                ON CONFLICT(area_id, date) DO UPDATE SET avg_completion_hours = (metrics_daily.avg_completion_hours + ?) / 2
            ''', (old['area_id'], hours, hours))
    else:
        conn.execute('UPDATE tasks SET status = ? WHERE id = ?', (status, task_id))

    conn.execute('INSERT INTO task_logs (task_id, action, detail) VALUES (?, ?, ?)',
                (task_id, f'status_change:{status}', f'Cambió de {old_status} a {status}'))

    task = conn.execute('''
        SELECT t.*, a.name as area_name, a.email as area_email, c.name as company_name
        FROM tasks t
        JOIN areas a ON t.area_id = a.id
        JOIN companies c ON t.company_id = c.id
        WHERE t.id = ?
    ''', (task_id,)).fetchone()
    conn.commit()
    conn.close()

    if task and status in ('gestionando', 'realizada'):
        send_status_confirmation(serialize_row(task), task['area_email'], task['area_name'], task['company_name'], status, old_status)

    if task and status == 'realizada':
        send_auto_suggestion(task['area_name'], task['area_email'], task['company_name'])

    status_emoji = {'gestionando': '🔄', 'realizada': '✅', 'pendiente': '⏳', 'cancelada': '❌'}
    create_notification(None, task['area_id'], f'{status_emoji.get(status, "📋")} Tarea {status}: {task["title"]}',
                       f'{task["area_name"]} cambió de "{old_status}" a "{status}"', 'status_change', f'/?area_id={task["area_id"]}')

    socketio.emit('task_status_changed', {'task_id': task_id, 'status': status, 'area_id': task['area_id']}, room='dashboard')
    socketio.emit('stats_update', {'area_id': task['area_id']}, room='dashboard')

    t = task
    html = f'''
    <!DOCTYPE html><html><head><meta charset="utf-8"><meta http-equiv="refresh" content="3;url=/">
    <style>body{{font-family:Arial;display:flex;justify-content:center;align-items:center;height:100vh;margin:0;background:#f4f4f4;}}
    .card{{background:white;padding:40px;border-radius:8px;text-align:center;box-shadow:0 2px 10px rgba(0,0,0,0.1);}}
    .success{{color:#28A745;font-size:48px;}}h2{{color:#333;}}p{{color:#666;}}</style>
    </head><body><div class="card">
        <div class="success">{"✅" if status == "realizada" else "🔄"}</div>
        <h2>{"✅ Tarea Completada" if status == "realizada" else "🔄 Tarea en Gestión"}</h2>
        <p style="font-size:18px;font-weight:600;">{t["title"] if t else ""}</p>
        <p style="color:#333;">Estado actual: <strong>{status}</strong></p>
        <p style="color:#666;">Notificación enviada al administrador.</p>
        <p style="color:#999;font-size:12px;margin-top:20px;">Redirigiendo al dashboard en 3 segundos...</p>
    </div></body></html>
    '''
    return html

@app.route('/api/tasks/<int:task_id>', methods=['PUT'])
@login_required
def update_task(task_id):
    data = request.json
    conn = get_db()
    conn.execute('UPDATE tasks SET title=?, description=?, priority=?, area_id=?, company_id=? WHERE id=?',
                (data['title'], data.get('description',''), data.get('priority', 'media'),
                 data['area_id'], data['company_id'], task_id))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Tarea actualizada'})

@app.route('/api/tasks/<int:task_id>', methods=['DELETE'])
@login_required
@role_required('superadmin', 'admin')
def delete_task(task_id):
    conn = get_db()
    conn.execute('DELETE FROM tasks WHERE id = ?', (task_id,))
    conn.execute('DELETE FROM task_logs WHERE task_id = ?', (task_id,))
    conn.commit()
    conn.close()
    socketio.emit('task_deleted', {'task_id': task_id}, room='dashboard')
    socketio.emit('stats_update', {}, room='dashboard')
    return jsonify({'message': 'Tarea eliminada'})

# ===== ATTACHMENTS =====

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf', 'doc', 'docx', 'xls', 'xlsx', 'txt', 'zip'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/api/tasks/<int:task_id>/attachments', methods=['POST'])
@login_required
def upload_attachment(task_id):
    if 'file' not in request.files:
        return jsonify({'error': 'No se envió archivo'}), 400
    file = request.files['file']
    if file.filename == '' or not allowed_file(file.filename):
        return jsonify({'error': 'Tipo de archivo no permitido'}), 400

    ext = file.filename.rsplit('.', 1)[1].lower()
    stored_name = f"{uuid.uuid4().hex}.{ext}"
    filepath = os.path.join(UPLOAD_DIR, stored_name)
    file.save(filepath)
    file_size = os.path.getsize(filepath)

    conn = get_db()
    conn.execute('INSERT INTO task_attachments (task_id, filename, original_name, file_size, mime_type) VALUES (?, ?, ?, ?, ?)',
                (task_id, stored_name, file.filename, file_size, file.content_type or 'application/octet-stream'))
    conn.commit()
    att_id = last_insert_id(conn)
    conn.close()
    return jsonify({'id': att_id, 'filename': stored_name, 'original_name': file.filename, 'file_size': file_size}), 201

@app.route('/api/tasks/<int:task_id>/attachments')
@login_required
def get_attachments(task_id):
    conn = get_db()
    atts = conn.execute('SELECT * FROM task_attachments WHERE task_id = ? ORDER BY uploaded_at', (task_id,)).fetchall()
    conn.close()
    return jsonify([dict(a) for a in atts])

@app.route('/api/attachments/<int:att_id>', methods=['DELETE'])
@login_required
def delete_attachment(att_id):
    conn = get_db()
    att = conn.execute('SELECT * FROM task_attachments WHERE id = ?', (att_id,)).fetchone()
    if not att:
        conn.close()
        return jsonify({'error': 'No encontrado'}), 404
    filepath = os.path.join(UPLOAD_DIR, att['filename'])
    if os.path.exists(filepath):
        os.remove(filepath)
    conn.execute('DELETE FROM task_attachments WHERE id = ?', (att_id,))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Archivo eliminado'})

@app.route('/api/uploads/<filename>')
def serve_upload(filename):
    return send_from_directory(UPLOAD_DIR, filename)

# ===== TEMPLATES =====

@app.route('/api/templates')
@login_required
def get_templates():
    conn = get_db()
    area_id = request.args.get('area_id')
    if session.get('role') == 'area' and session.get('area_id'):
        area_id = str(session['area_id'])
    query = '''
        SELECT tt.*, a.name as area_name
        FROM task_templates tt
        JOIN areas a ON tt.area_id = a.id
        WHERE 1=1
    '''
    params = []
    if area_id:
        query += ' AND tt.area_id = ?'
        params.append(area_id)
    query += ' ORDER BY tt.area_id, tt.title'
    templates = conn.execute(query, params).fetchall()
    conn.close()
    return jsonify([dict(t) for t in templates])

@app.route('/api/templates', methods=['POST'])
@login_required
def create_template():
    data = request.json
    conn = get_db()
    conn.execute('INSERT INTO task_templates (area_id, company_id, title, description, priority, is_recurring, recurring_days) VALUES (?, ?, ?, ?, ?, ?, ?)',
                (data['area_id'], data.get('company_id', 1), data['title'], data.get('description', ''),
                 data.get('priority', 'media'), data.get('is_recurring', 0), data.get('recurring_days')))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Plantilla creada'}), 201

@app.route('/api/templates/<int:tid>', methods=['DELETE'])
@login_required
def delete_template(tid):
    conn = get_db()
    conn.execute('DELETE FROM task_templates WHERE id = ?', (tid,))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Plantilla eliminada'})

@app.route('/api/templates/<int:tid>/apply', methods=['POST'])
@login_required
def apply_template(tid):
    conn = get_db()
    tmpl = conn.execute('SELECT * FROM task_templates WHERE id = ?', (tid,)).fetchone()
    if not tmpl:
        conn.close()
        return jsonify({'error': 'Plantilla no encontrada'}), 404
    company_id = request.json.get('company_id', tmpl['company_id'])
    due_date = calculate_due_date(tmpl['priority'])
    conn.execute('''
        INSERT INTO tasks (area_id, company_id, title, description, priority, due_date, created_by, template_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (tmpl['area_id'], company_id, tmpl['title'], tmpl['description'], tmpl['priority'],
          due_date, session.get('username', 'usuario'), tmpl['id']))
    task_id = last_insert_id(conn)
    conn.commit()
    conn.close()
    msg_title = tmpl['title']
    socketio.emit('task_created', {'id': task_id, 'title': msg_title}, room='dashboard')
    socketio.emit('stats_update', {}, room='dashboard')
    return jsonify({'task_id': task_id, 'message': 'Tarea creada desde plantilla'}), 201

# ===== SETTINGS =====

@app.route('/api/settings', methods=['GET'])
def get_settings():
    conn = get_db()
    settings = conn.execute('SELECT key, value FROM settings').fetchall()
    conn.close()
    return jsonify({s['key']: s['value'] for s in settings})

@app.route('/api/settings', methods=['PUT'])
@login_required
@role_required('superadmin', 'admin')
def update_settings():
    data = request.json
    conn = get_db()
    for key, value in data.items():
        conn.execute('INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?, ?, ?)',
                    (key, value, datetime.now().isoformat()))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Configuración guardada'})

@app.route('/api/settings/test-email', methods=['POST'])
@login_required
@role_required('superadmin', 'admin')
def test_email():
    data = request.json
    to_email = data.get('email', 'test@poffice.cl')
    ok = send_test_email(to_email)
    if ok:
        return jsonify({'message': f'Email de prueba enviado a {to_email}'})
    return jsonify({'error': 'Error al enviar email. Verifica la configuración SMTP.'}), 400

@app.route('/api/settings/test-graph', methods=['POST'])
@login_required
@role_required('superadmin', 'admin')
def test_graph_email():
    from graph_email import send_test_email as graph_test, is_graph_configured
    config = get_smtp_config()
    if not is_graph_configured(config):
        return jsonify({'error': 'Graph API no está configurado. Completa Tenant ID, Client ID y Client Secret.'}), 400
    data = request.json
    to_email = data.get('email', config.get('graph_user_email', 'admin@poffice.cl'))
    ok = graph_test(to_email, config)
    if ok:
        return jsonify({'message': f'Email de prueba enviado a {to_email} vía Microsoft Graph API'})
    return jsonify({'error': 'Error al enviar email vía Graph API. Verifica las credenciales.'}), 400

# ===== AGENT =====

@app.route('/api/agent/status')
def agent_status():
    return jsonify(get_agent_status())

@app.route('/api/agent/suggest')
@login_required
def agent_suggest():
    return jsonify(generate_ai_suggestions())

@app.route('/api/agent/approve/<int:task_id>')
@login_required
def approve_suggestion(task_id):
    conn = get_db()
    task = conn.execute('''
        SELECT t.*, a.name as area_name, a.email as area_email, c.name as company_name
        FROM tasks t JOIN areas a ON t.area_id = a.id JOIN companies c ON t.company_id = c.id
        WHERE t.id = ?
    ''', (task_id,)).fetchone()
    if not task:
        conn.close()
        return jsonify({'error': 'Tarea no encontrada'}), 404
    conn.execute('UPDATE tasks SET title = ?, created_by = ? WHERE id = ?',
                (task['title'].replace('[SUGERIDO] ', ''), 'aprobado', task_id))
    conn.execute('INSERT INTO task_logs (task_id, action, detail) VALUES (?, ?, ?)',
                (task_id, 'aprobada', 'Tarea sugerida por IA aprobada por el administrador'))
    conn.commit()
    conn.close()
    send_task_notification(serialize_row(task), task['area_email'], task['area_name'], task['company_name'])
    html = '''
    <!DOCTYPE html><html><head><meta charset="utf-8"><meta http-equiv="refresh" content="3;url=/">
    <style>body{font-family:Arial;display:flex;justify-content:center;align-items:center;height:100vh;margin:0;background:#f4f4f4;}
    .card{background:white;padding:40px;border-radius:8px;text-align:center;box-shadow:0 2px 10px rgba(0,0,0,0.1);}
    .success{color:#28A745;font-size:48px;}h2{color:#333;}p{color:#666;}</style>
    </head><body><div class="card"><div class="success">✅</div><h2>Sugerencia Aprobada</h2>
    <p>La tarea ha sido creada y notificada al área correspondiente.</p></div></body></html>
    '''
    return html

@app.route('/api/agent/reject/<int:task_id>')
@login_required
def reject_suggestion(task_id):
    conn = get_db()
    conn.execute("UPDATE tasks SET status = 'cancelada', created_by = 'rechazado' WHERE id = ?", (task_id,))
    conn.execute('INSERT INTO task_logs (task_id, action, detail) VALUES (?, ?, ?)',
                (task_id, 'rechazada', 'Sugerencia del agente IA rechazada'))
    conn.commit()
    conn.close()
    html = '''
    <!DOCTYPE html><html><head><meta charset="utf-8"><meta http-equiv="refresh" content="3;url=/">
    <style>body{font-family:Arial;display:flex;justify-content:center;align-items:center;height:100vh;margin:0;background:#f4f4f4;}
    .card{background:white;padding:40px;border-radius:8px;text-align:center;box-shadow:0 2px 10px rgba(0,0,0,0.1);}
    .info{color:#FFC107;font-size:48px;}h2{color:#333;}p{color:#666;}</style>
    </head><body><div class="card"><div class="info">ℹ️</div><h2>Sugerencia Rechazada</h2>
    <p>La tarea sugerida ha sido rechazada.</p></div></body></html>
    '''
    return html

@app.route('/api/agent/followup', methods=['POST'])
@login_required
def trigger_followup():
    results = generate_task_followups()
    return jsonify({'followups': len(results), 'details': results})

# ===== ACTIVITY =====

@app.route('/api/activity')
@login_required
def get_activity():
    conn = get_db()
    limit = min(int(request.args.get('limit', 50)), 200)

    rows = conn.execute('''
        SELECT 'task_created' as type, t.id as ref_id, t.title as title,
               a.name as area_name, a.color as area_color, c.name as company_name,
               t.created_at as created_at, t.created_by as actor
        FROM tasks t
        JOIN areas a ON t.area_id = a.id
        JOIN companies c ON t.company_id = c.id

        UNION ALL

        SELECT 'status_change' as type, tl.task_id as ref_id, t.title as title,
               a.name as area_name, a.color as area_color, c.name as company_name,
               tl.created_at as created_at, tl.detail as actor
        FROM task_logs tl
        JOIN tasks t ON tl.task_id = t.id
        JOIN areas a ON t.area_id = a.id
        JOIN companies c ON t.company_id = c.id

        UNION ALL

        SELECT 'marketing' as type, ms.id as ref_id, ms.title as title,
               'MARKETING' as area_name, '#7B2D8E' as area_color, '' as company_name,
               ms.created_at as created_at, ms.status as actor
        FROM marketing_suggestions ms

        UNION ALL

        SELECT 'followup' as type, f.task_id as ref_id, t.title as title,
               a.name as area_name, a.color as area_color, c.name as company_name,
               f.sent_at as created_at, f.followup_type as actor
        FROM task_followups f
        JOIN tasks t ON f.task_id = t.id
        JOIN areas a ON t.area_id = a.id
        JOIN companies c ON t.company_id = c.id

        ORDER BY created_at DESC LIMIT ?
    ''', (limit,)).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

# ===== STATS =====

@app.route('/api/tasks/stats')
def task_stats():
    conn = get_db()
    area_filter = ''
    params = []
    is_area = session.get('role') == 'area' and session.get('area_id')
    area_id = session.get('area_id') if is_area else None

    if is_area:
        by_area = conn.execute('''
            SELECT a.id, a.name, a.email, a.color, COUNT(t.id) as total,
                   SUM(CASE WHEN t.status='pendiente' THEN 1 ELSE 0 END) as pendientes,
                   SUM(CASE WHEN t.status='gestionando' THEN 1 ELSE 0 END) as gestionando,
                   SUM(CASE WHEN t.status='realizada' THEN 1 ELSE 0 END) as realizadas,
                   SUM(CASE WHEN t.status IN ('pendiente','gestionando') AND t.due_date < date('now') THEN 1 ELSE 0 END) as vencidas
            FROM areas a LEFT JOIN tasks t ON a.id = t.area_id AND t.area_id = ?
            WHERE a.id = ?
            GROUP BY a.id ORDER BY a.name
        ''', (area_id, area_id)).fetchall()
        total = sum(a['total'] for a in by_area)
        pendientes = sum(a['pendientes'] for a in by_area)
        gestionando = sum(a['gestionando'] for a in by_area)
        realizadas = sum(a['realizadas'] for a in by_area)
        vencidas = sum(a['vencidas'] for a in by_area)
    else:
        by_area = conn.execute('''
            SELECT a.id, a.name, a.email, a.color, COUNT(t.id) as total,
                   SUM(CASE WHEN t.status='pendiente' THEN 1 ELSE 0 END) as pendientes,
                   SUM(CASE WHEN t.status='gestionando' THEN 1 ELSE 0 END) as gestionando,
                   SUM(CASE WHEN t.status='realizada' THEN 1 ELSE 0 END) as realizadas,
                   SUM(CASE WHEN t.status IN ('pendiente','gestionando') AND t.due_date < date('now') THEN 1 ELSE 0 END) as vencidas
            FROM areas a LEFT JOIN tasks t ON a.id = t.area_id
            GROUP BY a.id ORDER BY a.name
        ''').fetchall()
        total = conn.execute('SELECT COUNT(*) as c FROM tasks').fetchone()['c']
        pendientes = conn.execute("SELECT COUNT(*) as c FROM tasks WHERE status='pendiente'").fetchone()['c']
        gestionando = conn.execute("SELECT COUNT(*) as c FROM tasks WHERE status='gestionando'").fetchone()['c']
        realizadas = conn.execute("SELECT COUNT(*) as c FROM tasks WHERE status='realizada'").fetchone()['c']
        vencidas = conn.execute("SELECT COUNT(*) as c FROM tasks WHERE status IN ('pendiente','gestionando') AND due_date < date('now')").fetchone()['c']

    conn.close()
    return jsonify({
        'total': total, 'pendientes': pendientes, 'gestionando': gestionando,
        'realizadas': realizadas, 'vencidas': vencidas,
        'by_area': [dict(a) for a in by_area]
    })

# ===== LOGS =====

@app.route('/api/tasks/<int:task_id>/logs')
@login_required
def task_logs(task_id):
    conn = get_db()
    logs = conn.execute('SELECT * FROM task_logs WHERE task_id = ? ORDER BY created_at DESC', (task_id,)).fetchall()
    conn.close()
    return jsonify([dict(l) for l in logs])

@app.route('/api/email-logs')
@login_required
@role_required('superadmin', 'admin')
def get_email_logs():
    conn = get_db()
    limit = min(int(request.args.get('limit', 50)), 200)
    logs = conn.execute('''
        SELECT el.*, t.title as task_title
        FROM email_logs el
        LEFT JOIN tasks t ON el.task_id = t.id
        ORDER BY el.sent_at DESC LIMIT ?
    ''', (limit,)).fetchall()
    conn.close()
    return jsonify([dict(l) for l in logs])

@app.route('/api/send-reminder/<int:task_id>')
@login_required
def send_manual_reminder(task_id):
    conn = get_db()
    task = conn.execute('''
        SELECT t.*, a.name as area_name, a.email as area_email, c.name as company_name
        FROM tasks t JOIN areas a ON t.area_id = a.id JOIN companies c ON t.company_id = c.id
        WHERE t.id = ?
    ''', (task_id,)).fetchone()
    conn.close()
    if not task:
        return jsonify({'error': 'Tarea no encontrada'}), 404
    send_task_reminder(serialize_row(task), task['area_email'], task['area_name'], task['company_name'])
    return jsonify({'message': 'Recordatorio enviado'})

# ===== NOTIFICATIONS =====

@app.route('/api/notifications')
@login_required
def get_notifications():
    conn = get_db()
    limit = min(int(request.args.get('limit', 20)), 100)
    if session['role'] == 'superadmin':
        notifs = conn.execute('''
            SELECT * FROM notifications ORDER BY created_at DESC LIMIT ?
        ''', (limit,)).fetchall()
    elif session['role'] == 'admin':
        notifs = conn.execute('''
            SELECT * FROM notifications WHERE area_id IS NULL OR user_id = ?
            ORDER BY created_at DESC LIMIT ?
        ''', (session['user_id'], limit)).fetchall()
    else:
        notifs = conn.execute('''
            SELECT * FROM notifications WHERE area_id = ? OR user_id = ?
            ORDER BY created_at DESC LIMIT ?
        ''', (session['area_id'], session['user_id'], limit)).fetchall()
    conn.close()
    return jsonify([dict(n) for n in notifs])

@app.route('/api/notifications/unread-count')
@login_required
def unread_count():
    conn = get_db()
    if session['role'] == 'superadmin':
        count = conn.execute("SELECT COUNT(*) as c FROM notifications WHERE is_read = 0").fetchone()['c']
    elif session['role'] == 'admin':
        count = conn.execute("SELECT COUNT(*) as c FROM notifications WHERE is_read = 0 AND (area_id IS NULL OR user_id = ?)",
                           (session['user_id'],)).fetchone()['c']
    else:
        count = conn.execute("SELECT COUNT(*) as c FROM notifications WHERE is_read = 0 AND (area_id = ? OR user_id = ?)",
                           (session['area_id'], session['user_id'])).fetchone()['c']
    conn.close()
    return jsonify({'count': count})

@app.route('/api/notifications/<int:nid>/read', methods=['PUT'])
@login_required
def mark_read(nid):
    conn = get_db()
    conn.execute('UPDATE notifications SET is_read = 1 WHERE id = ?', (nid,))
    conn.commit()
    conn.close()
    return jsonify({'message': 'OK'})

@app.route('/api/notifications/read-all', methods=['PUT'])
@login_required
def mark_all_read():
    conn = get_db()
    if session['role'] == 'superadmin':
        conn.execute('UPDATE notifications SET is_read = 1')
    elif session['role'] == 'admin':
        conn.execute('UPDATE notifications SET is_read = 1 WHERE area_id IS NULL OR user_id = ?', (session['user_id'],))
    else:
        conn.execute('UPDATE notifications SET is_read = 1 WHERE area_id = ? OR user_id = ?', (session['area_id'], session['user_id']))
    conn.commit()
    conn.close()
    return jsonify({'message': 'OK'})

# ===== MARKETING =====

@app.route('/api/marketing/suggestions')
@login_required
def get_marketing_suggestions():
    conn = get_db()
    status = request.args.get('status', 'pendiente')
    suggestions = conn.execute('''
        SELECT * FROM marketing_suggestions WHERE status = ? ORDER BY created_at DESC
    ''', (status,)).fetchall()
    conn.close()
    return jsonify([dict(s) for s in suggestions])

@app.route('/api/marketing/generate', methods=['POST'])
@login_required
@role_required('superadmin', 'admin')
def generate_marketing():
    suggestions = generate_marketing_suggestions()
    return jsonify({'count': len(suggestions), 'suggestions': suggestions})

@app.route('/api/marketing/approve/<int:sug_id>')
@login_required
def approve_marketing(sug_id):
    conn = get_db()
    conn.execute("UPDATE marketing_suggestions SET status = 'aprobada', approved_at = ? WHERE id = ?",
                (datetime.now().isoformat(), sug_id))
    sug = conn.execute('SELECT * FROM marketing_suggestions WHERE id = ?', (sug_id,)).fetchone()
    conn.commit()
    conn.close()
    if sug:
        conn2 = get_db()
        conn2.execute('''
            INSERT INTO tasks (area_id, company_id, title, description, priority, status, created_by)
            VALUES ((SELECT id FROM areas WHERE name='MARKETING'), (SELECT id FROM companies WHERE name='ProClean Facilities'),
                    ?, ?, 'media', 'pendiente', 'marketing_ia')
        ''', (f"[MARKETING] {sug['title']}", sug['description']))
        conn2.commit()
        conn2.close()
    html = f'''
    <!DOCTYPE html><html><head><meta charset="utf-8"><meta http-equiv="refresh" content="3;url=/">
    <style>body{{font-family:Arial;display:flex;justify-content:center;align-items:center;height:100vh;margin:0;background:#f4f4f4;}}
    .card{{background:white;padding:40px;border-radius:8px;text-align:center;box-shadow:0 2px 10px rgba(0,0,0,0.1);}}
    .success{{color:#28A745;font-size:48px;}}h2{{color:#333;}}p{{color:#666;}}</style>
    </head><body><div class="card"><div class="success">🎨</div>
    <h2>Sugerencia Aprobada</h2>
    <p>La sugerencia de marketing ha sido convertida en tarea para el área de Marketing.</p></div></body></html>
    '''
    return html

@app.route('/api/marketing/reject/<int:sug_id>')
@login_required
def reject_marketing(sug_id):
    conn = get_db()
    conn.execute("UPDATE marketing_suggestions SET status = 'rechazada' WHERE id = ?", (sug_id,))
    conn.commit()
    conn.close()
    html = '''
    <!DOCTYPE html><html><head><meta charset="utf-8"><meta http-equiv="refresh" content="3;url=/">
    <style>body{font-family:Arial;display:flex;justify-content:center;align-items:center;height:100vh;margin:0;background:#f4f4f4;}
    .card{background:white;padding:40px;border-radius:8px;text-align:center;box-shadow:0 2px 10px rgba(0,0,0,0.1);}
    .info{color:#FFC107;font-size:48px;}h2{color:#333;}p{color:#666;}</style>
    </head><body><div class="card"><div class="info">ℹ️</div><h2>Sugerencia Rechazada</h2></div></body></html>
    '''
    return html

# ===== FOLLOWUPS =====

@app.route('/api/followups')
@login_required
def get_followups():
    conn = get_db()
    limit = request.args.get('limit', 20)
    followups = conn.execute('''
        SELECT f.*, t.title as task_title, a.name as area_name
        FROM task_followups f
        JOIN tasks t ON f.task_id = t.id
        JOIN areas a ON t.area_id = a.id
        ORDER BY f.sent_at DESC LIMIT ?
    ''', (limit,)).fetchall()
    conn.close()
    return jsonify([dict(f) for f in followups])

# ===== METRICS =====

@app.route('/api/metrics/daily')
@login_required
def get_daily_metrics():
    conn = get_db()
    days = int(request.args.get('days', 30))
    area_filter = ''
    params = [days]
    if session.get('role') == 'area' and session.get('area_id'):
        area_filter = ' AND md.area_id = ?'
        params.append(session['area_id'])

    metrics = conn.execute(f'''
        SELECT md.*, a.name as area_name, a.color as area_color
        FROM metrics_daily md
        JOIN areas a ON md.area_id = a.id
        WHERE md.date >= date('now', '-' || ? || ' days'){area_filter}
        ORDER BY md.date DESC, a.name
    ''', params).fetchall()
    conn.close()
    return jsonify([dict(m) for m in metrics])

@app.route('/api/metrics')
@login_required
def get_metrics():
    conn = get_db()
    area_filter = ''
    params = []
    if session.get('role') == 'area' and session.get('area_id'):
        area_filter = ' WHERE t.area_id = ?'
        params.append(session['area_id'])

    # Tiempo promedio de resolución por área
    avg_time = conn.execute(f'''
        SELECT a.id, a.name, a.color,
               AVG(
                 (julianday(COALESCE(t.completed_at, datetime('now'))) - julianday(t.created_at)) * 24
               ) as avg_hours,
               COUNT(t.id) as total_completed
        FROM tasks t
        JOIN areas a ON t.area_id = a.id
        WHERE t.status = 'realizada' AND t.completed_at IS NOT NULL{area_filter.replace('WHERE', 'AND') if area_filter else ''}
        GROUP BY a.id
        ORDER BY a.name
    ''', params).fetchall()

    # Tareas por prioridad
    priority_stats = conn.execute(f'''
        SELECT priority, COUNT(*) as count
        FROM tasks t{area_filter}
        GROUP BY priority
    ''', params).fetchall()

    conn.close()
    return jsonify({
        'avg_resolution_time': [dict(a) for a in avg_time],
        'priority_stats': [dict(p) for p in priority_stats]
    })

# ===== WEBHOOK FOR EMAIL LOGGING =====

@app.route('/api/email/webhook', methods=['POST'])
def email_webhook():
    data = request.json
    conn = get_db()
    conn.execute('INSERT INTO email_logs (task_id, recipient, subject, email_type, status, error_message) VALUES (?, ?, ?, ?, ?, ?)',
                (data.get('task_id'), data.get('recipient'), data.get('subject'), data.get('email_type', 'general'),
                 data.get('status', 'sent'), data.get('error_message')))
    conn.commit()
    conn.close()
    return jsonify({'message': 'ok'}), 201

# ===== CHAT INTERNO =====

@socketio.on('join')
def handle_join(data):
    room = f"task_{data.get('task_id')}"
    join_room(room)

@socketio.on('leave')
def handle_leave(data):
    room = f"task_{data.get('task_id')}"
    leave_room(room)

@socketio.on('send_message')
def handle_message(data):
    if 'user_id' not in session:
        return
    task_id = data.get('task_id')
    message = data.get('message', '').strip()
    if not task_id or not message:
        return
    conn = get_db()
    conn.execute('INSERT INTO chat_messages (task_id, user_id, username, message) VALUES (?, ?, ?, ?)',
                (task_id, session['user_id'], session.get('name', session.get('username', 'Usuario')), message))
    conn.commit()
    msg_id = last_insert_id(conn)
    msg = conn.execute('''
        SELECT cm.*, u.name as user_name
        FROM chat_messages cm
        LEFT JOIN users u ON cm.user_id = u.id
        WHERE cm.id = ?
    ''', (msg_id,)).fetchone()
    conn.close()
    room = f"task_{task_id}"
    emit('new_message', dict(msg), room=room)

# ===== DASHBOARD EN TIEMPO REAL =====

@socketio.on('join_dashboard')
def handle_join_dashboard():
    join_room('dashboard')

@socketio.on('leave_dashboard')
def handle_leave_dashboard():
    leave_room('dashboard')

@app.route('/api/chat/<int:task_id>')
@login_required
def get_chat_messages(task_id):
    conn = get_db()
    msgs = conn.execute('''
        SELECT cm.*, u.name as user_name
        FROM chat_messages cm
        LEFT JOIN users u ON cm.user_id = u.id
        WHERE cm.task_id = ?
        ORDER BY cm.created_at ASC
    ''', (task_id,)).fetchall()
    conn.close()
    return jsonify([dict(m) for m in msgs])

# ===== BÚSQUEDA GLOBAL =====

@app.route('/api/search')
@login_required
def global_search():
    q = request.args.get('q', '').strip()
    if len(q) < 2:
        return jsonify([])
    conn = get_db()
    area_filter = ''
    params = [f'%{q}%', f'%{q}%']
    if session.get('role') == 'area' and session.get('area_id'):
        area_filter = ' AND t.area_id = ?'
        params.append(session['area_id'])
    results = conn.execute(f'''
        SELECT t.id, t.title, t.description, t.status, t.priority, t.due_date,
               a.name as area_name, c.name as company_name
        FROM tasks t
        JOIN areas a ON t.area_id = a.id
        JOIN companies c ON t.company_id = c.id
        WHERE (t.title LIKE ? OR t.description LIKE ?){area_filter}
        ORDER BY t.created_at DESC LIMIT 20
    ''', params).fetchall()
    conn.close()
    return jsonify([dict(r) for r in results])

# ===== CALENDARIO =====

@app.route('/api/calendar')
@login_required
def get_calendar():
    conn = get_db()
    start = request.args.get('start', (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d'))
    end = request.args.get('end', (datetime.now() + timedelta(days=60)).strftime('%Y-%m-%d'))
    area_filter = ''
    params = [start, end]
    if session.get('role') == 'area' and session.get('area_id'):
        area_filter = ' AND t.area_id = ?'
        params.append(session['area_id'])
    tasks = conn.execute(f'''
        SELECT t.id, t.title, t.status, t.priority, t.due_date, t.created_at, t.completed_at,
               a.name as area_name, a.color as area_color, c.name as company_name
        FROM tasks t
        JOIN areas a ON t.area_id = a.id
        JOIN companies c ON t.company_id = c.id
        WHERE t.due_date BETWEEN ? AND ?{area_filter}
        ORDER BY t.due_date ASC
    ''', params).fetchall()
    conn.close()
    events = []
    colors = {'pendiente': '#FFC107', 'gestionando': '#1a73e8', 'realizada': '#28A745', 'cancelada': '#DC3545'}
    for t in tasks:
        if t['due_date']:
            events.append({
                'id': t['id'],
                'title': f"[{t['area_name']}] {t['title']}",
                'start': t['due_date'],
                'allDay': True,
                'backgroundColor': colors.get(t['status'], '#999'),
                'borderColor': colors.get(t['status'], '#999'),
                'textColor': '#fff',
                'extendedProps': {
                    'status': t['status'],
                    'priority': t['priority'],
                    'area': t['area_name'],
                    'company': t['company_name']
                }
            })
    return jsonify(events)

# ===== EXPORTAR REPORTES =====

@app.route('/api/export/tasks')
@login_required
def export_tasks():
    conn = get_db()
    area_id = request.args.get('area_id')
    status = request.args.get('status')
    start_date = request.args.get('start')
    end_date = request.args.get('end')
    fmt = request.args.get('format', 'csv')

    params = []
    where = ['1=1']
    if area_id:
        where.append('t.area_id = ?')
        params.append(area_id)
    if status:
        where.append('t.status = ?')
        params.append(status)
    if start_date:
        where.append('t.created_at >= ?')
        params.append(start_date)
    if end_date:
        where.append('t.created_at <= ?')
        params.append(end_date)

    tasks = conn.execute(f'''
        SELECT t.id, t.title, t.description, t.status, t.priority, t.due_date,
               t.created_at, t.completed_at, t.created_by,
               a.name as area_name, c.name as company_name
        FROM tasks t
        JOIN areas a ON t.area_id = a.id
        JOIN companies c ON t.company_id = c.id
        WHERE {' AND '.join(where)}
        ORDER BY t.created_at DESC
    ''', params).fetchall()
    conn.close()

    if fmt == 'csv':
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['ID', 'Título', 'Descripción', 'Área', 'Empresa', 'Estado', 'Prioridad',
                        'Fecha Límite', 'Creada', 'Completada', 'Creado por'])
        for t in tasks:
            writer.writerow([t['id'], t['title'], t['description'], t['area_name'], t['company_name'],
                           t['status'], t['priority'], t['due_date'], t['created_at'], t['completed_at'], t['created_by']])
        csv_output = output.getvalue()
        output.close()
        resp = make_response(csv_output)
        resp.headers['Content-Type'] = 'text/csv; charset=utf-8'
        resp.headers['Content-Disposition'] = f'attachment; filename=tareas_{datetime.now().strftime("%Y%m%d")}.csv'
        return resp

    return jsonify([dict(t) for t in tasks])

# ===== APROBACIÓN DE TAREAS =====

@app.route('/api/tasks/<int:task_id>/approve', methods=['POST'])
@login_required
@role_required('superadmin', 'admin')
def approve_task(task_id):
    conn = get_db()
    task = conn.execute('SELECT * FROM tasks WHERE id = ?', (task_id,)).fetchone()
    if not task:
        conn.close()
        return jsonify({'error': 'No encontrada'}), 404
    if task['status'] != 'realizada':
        conn.close()
        return jsonify({'error': 'Solo se pueden aprobar tareas completadas'}), 400
    now = datetime.now().isoformat()
    conn.execute('UPDATE tasks SET approved_at = ?, approved_by = ? WHERE id = ?',
                (now, session.get('username', 'admin'), task_id))
    conn.execute('INSERT INTO task_logs (task_id, action, detail) VALUES (?, ?, ?)',
                (task_id, 'aprobada', f'Tarea aprobada por {session.get("username", "admin")}'))
    conn.commit()
    conn.close()
    create_notification(None, task['area_id'], f'✅ Tarea aprobada: {task["title"]}',
                       f'Aprobada por {session.get("username", "admin")}', 'info')
    return jsonify({'message': 'Tarea aprobada', 'approved_at': now})

# ===== SESSION LOGS =====

@app.route('/api/session-logs')
@login_required
@role_required('superadmin', 'admin')
def get_session_logs():
    conn = get_db()
    limit = min(int(request.args.get('limit', 50)), 200)
    logs = conn.execute('''
        SELECT sl.*, u.name as user_name
        FROM session_logs sl
        JOIN users u ON sl.user_id = u.id
        ORDER BY sl.created_at DESC LIMIT ?
    ''', (limit,)).fetchall()
    conn.close()
    return jsonify([dict(l) for l in logs])

# ===== RECURRING TASKS =====

@app.route('/api/recurring/run', methods=['POST'])
@login_required
@role_required('superadmin', 'admin')
def run_recurring():
    conn = get_db()
    templates = conn.execute('''
        SELECT * FROM task_templates WHERE is_recurring = 1 AND recurring_days IS NOT NULL
    ''').fetchall()
    created = 0
    for tmpl in templates:
        t = dict(tmpl)
        last = conn.execute('''
            SELECT MAX(created_at) as last_created FROM tasks
            WHERE template_id = ? AND created_by != 'recurring'
        ''', (t['id'],)).fetchone()
        should_create = False
        if not last or not last['last_created']:
            should_create = True
        else:
            try:
                last_date = datetime.fromisoformat(str(last['last_created']).replace('Z', ''))
                if (datetime.now() - last_date).days >= t['recurring_days']:
                    should_create = True
            except:
                should_create = True
        if should_create:
            due_date = (datetime.now() + timedelta(days=3)).strftime('%Y-%m-%d')
            conn.execute('''
                INSERT INTO tasks (area_id, company_id, title, description, priority, due_date, created_by, template_id)
                VALUES (?, ?, ?, ?, ?, ?, 'recurring', ?)
            ''', (t['area_id'], t.get('company_id', 1), t['title'],
                 t['description'], t['priority'], due_date, t['id']))
            created += 1
    conn.commit()
    conn.close()
    return jsonify({'created': created, 'message': f'{created} tareas recurrentes creadas'})

_db_init_error = None

@app.route('/api/db-status')
def db_status():
    return jsonify({
        'engine': 'postgresql' if os.environ.get('DATABASE_URL', '').startswith('postgresql') else 'sqlite',
        'init_error': _db_init_error
    })

if __name__ == '__main__':
    print("Inicializando base de datos...")
    try:
        init_db()
    except Exception as e:
        _db_init_error = str(e)
        print(f"ERROR iniciando DB: {e}")
        import traceback
        traceback.print_exc()
        os.environ.pop('DATABASE_URL', None)
        from database import _engine
        import database
        database._engine = None
        print("Fallback a SQLite...")
        init_db()

    print("Inicializando agentes IA...")
    initialize_agents()

    print("Iniciando planificador...")
    scheduler = start_scheduler(app)

    print("\n" + "="*60)
    print("🚀 SISTEMA DE AGENTES IA - HIRAM CHILE")
    print("="*60)
    print(f"📋 Dashboard:     http://localhost:8080")
    print(f"🔐 Login:         http://localhost:8080/login")
    print(f"⚙️  Config SMTP:  http://localhost:8080/settings")
    print(f"📧 Recordatorios: 09:00 AM (diario)")
    print(f"🤖 Sugerencias:   cada 6 horas")
    print(f"🎨 Marketing:     cada 4 horas")
    print(f"📊 Seguimiento:   cada 3 horas")
    print("="*60 + "\n")

    try:
        port = int(os.environ.get('PORT', 8080))
        socketio.run(app, host='0.0.0.0', port=port, debug=True, allow_unsafe_werkzeug=True)
    except KeyboardInterrupt:
        scheduler.shutdown()
        print("\nSistema detenido.")
