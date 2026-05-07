import os
import re
import hashlib
from datetime import datetime, date as date_type

DATABASE_URL = os.environ.get('DATABASE_URL', '')
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'hiram.db')

_engine = None
_engine_module = None

def detect_engine():
    global _engine
    if _engine:
        return _engine
    url = DATABASE_URL.lower() if DATABASE_URL else ''
    if url.startswith('postgresql'):
        _engine = 'postgresql'
    else:
        _engine = 'sqlite'
    return _engine

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def adapt_params(params):
    if params is None:
        return None
    if detect_engine() == 'postgresql' and isinstance(params, (list, tuple)):
        return tuple(params)
    return params

def adapt_sql(sql):
    if detect_engine() == 'postgresql':
        sql = re.sub(r'\?', '%s', sql)
        sql = re.sub(r"date\('now'\)", 'CURRENT_DATE', sql, flags=re.IGNORECASE)
        sql = re.sub(r"datetime\('now'\)", 'NOW()', sql, flags=re.IGNORECASE)
        sql = re.sub(r"julianday\(([^)]+)\)", r"EXTRACT(EPOCH FROM \1)", sql)
        sql = re.sub(r"INSERT\s+OR\s+IGNORE", "INSERT", sql, flags=re.IGNORECASE)
        sql = re.sub(r"INSERT\s+OR\s+REPLACE", "INSERT", sql, flags=re.IGNORECASE)
        sql = re.sub(r"last_insert_rowid\(\)", "lastval()", sql, flags=re.IGNORECASE)
    return sql

class CursorProxy:
    def __init__(self, cursor, engine):
        self._cursor = cursor
        self._engine = engine
        self._description = None

    def __getattr__(self, name):
        return getattr(self._cursor, name)

    def fetchone(self):
        row = self._cursor.fetchone()
        if row is None or self._engine != 'postgresql' or self._cursor.description is None:
            return row
        desc = [d[0].lower() for d in self._cursor.description]
        return _RowProxy(desc, row)

    def fetchall(self):
        if self._engine != 'postgresql' or self._cursor.description is None:
            return self._cursor.fetchall()
        desc = [d[0].lower() for d in self._cursor.description]
        rows = self._cursor.fetchall()
        return [_RowProxy(desc, r) for r in rows]

    @property
    def lastrowid(self):
        if self._engine == 'postgresql':
            if self._cursor.description:
                row = self._cursor.fetchone()
                return row[0] if row else None
            return None
        return self._cursor.lastrowid

class _RowProxy:
    def __init__(self, keys, values):
        self._keys = keys
        self._values = values

    def __getitem__(self, key):
        if isinstance(key, str):
            idx = self._keys.index(key.lower())
            val = self._values[idx]
            if isinstance(val, date_type):
                return val.isoformat()
            return val
        val = self._values[key]
        if isinstance(val, date_type):
            return val.isoformat()
        return val

    def __getattr__(self, key):
        try:
            idx = self._keys.index(key.lower())
            return self._values[idx]
        except (ValueError, IndexError):
            raise AttributeError(key)

    def get(self, key, default=None):
        try:
            idx = self._keys.index(key.lower())
            return self._values[idx]
        except (ValueError, IndexError):
            return default

    def keys(self):
        return self._keys

    def __iter__(self):
        return iter(self._keys)

    def __len__(self):
        return len(self._keys)

    def __contains__(self, key):
        return key.lower() in self._keys

class ConnectionProxy:
    def __init__(self, conn, engine):
        object.__setattr__(self, '_conn', conn)
        object.__setattr__(self, '_engine', engine)

    def __setattr__(self, name, value):
        if name in ('_conn', '_engine'):
            object.__setattr__(self, name, value)
        else:
            setattr(self._conn, name, value)

    def __getattr__(self, name):
        if name in ('_conn', '_engine'):
            raise AttributeError(name)
        return getattr(self._conn, name)

    def execute(self, sql, params=None):
        sql_adapted = adapt_sql(sql)
        params_adapted = adapt_params(params)
        if self._engine == 'postgresql':
            cur = self._conn.cursor()
            if params_adapted is None:
                cur.execute(sql_adapted)
            else:
                cur.execute(sql_adapted, params_adapted)
            return CursorProxy(cur, self._engine)
        if params_adapted is None:
            return self._conn.execute(sql_adapted)
        return self._conn.execute(sql_adapted, params_adapted)

    def executemany(self, sql, params_list):
        sql_adapted = adapt_sql(sql)
        if self._engine == 'postgresql':
            cur = self._conn.cursor()
            for params in params_list:
                p = adapt_params(params)
                if p is None:
                    cur.execute(sql_adapted)
                else:
                    cur.execute(sql_adapted, p)
            return cur
        return self._conn.executemany(sql_adapted, params_list)

    def executescript(self, sql):
        if self._engine == 'postgresql':
            cur = self._conn.cursor()
            for statement in sql.split(';'):
                stmt = statement.strip()
                if stmt:
                    try:
                        cur.execute(stmt)
                    except Exception:
                        pass
            return cur
        return self._conn.executescript(sql)

    def commit(self):
        self._conn.commit()

    def close(self):
        if self._engine == 'postgresql':
            self._conn.close()
        else:
            self._conn.close()

    def cursor(self):
        if self._engine == 'postgresql':
            return self._conn.cursor()
        return self._conn.cursor()

def get_db():
    engine = detect_engine()
    if engine == 'postgresql':
        conn = _get_pg_conn()
    else:
        conn = _get_sqlite_conn()
    return ConnectionProxy(conn, engine)

def _get_sqlite_conn():
    import sqlite3
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn

def _get_pg_conn():
    import psycopg2
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = False
    return conn

def last_insert_id(conn):
    engine = detect_engine()
    if engine == 'postgresql':
        cur = conn.execute('SELECT lastval() as id')
        return cur.fetchone()['id']
    else:
        return conn.execute('SELECT last_insert_rowid() as id').fetchone()['id']

def row_to_dict(row):
    if row is None:
        return None
    if isinstance(row, _RowProxy):
        return {k: row[k] for k in row._keys}
    if hasattr(row, 'keys'):
        return dict(row)
    return dict(row)

def rows_to_list(rows):
    return [row_to_dict(r) for r in rows]

def init_db():
    engine = detect_engine()
    if engine == 'postgresql':
        _init_pg()
    else:
        _init_sqlite()

def _init_sqlite():
    conn = get_db()
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS areas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            email TEXT NOT NULL,
            description TEXT,
            color TEXT DEFAULT '#1a73e8',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS companies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'area' CHECK(role IN ('superadmin','admin','area')),
            area_id INTEGER,
            name TEXT,
            email TEXT,
            is_active INTEGER DEFAULT 1,
            last_login TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (area_id) REFERENCES areas(id)
        );
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            area_id INTEGER NOT NULL,
            company_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            priority TEXT NOT NULL CHECK(priority IN ('urgente','alta','media','baja')),
            status TEXT NOT NULL DEFAULT 'pendiente' CHECK(status IN ('pendiente','gestionando','realizada','cancelada')),
            due_date DATE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP,
            created_by TEXT DEFAULT 'sistema',
            template_id INTEGER,
            kanban_order INTEGER DEFAULT 0,
            approved_at TIMESTAMP,
            approved_by TEXT,
            FOREIGN KEY (area_id) REFERENCES areas(id),
            FOREIGN KEY (company_id) REFERENCES companies(id)
        );
        CREATE TABLE IF NOT EXISTS task_attachments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER NOT NULL,
            filename TEXT NOT NULL,
            original_name TEXT NOT NULL,
            file_size INTEGER,
            mime_type TEXT,
            uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS task_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER NOT NULL,
            action TEXT NOT NULL,
            detail TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (task_id) REFERENCES tasks(id)
        );
        CREATE TABLE IF NOT EXISTS task_templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            area_id INTEGER NOT NULL,
            company_id INTEGER DEFAULT 1,
            title TEXT NOT NULL,
            description TEXT,
            priority TEXT DEFAULT 'media',
            is_recurring INTEGER DEFAULT 0,
            recurring_days INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(area_id, title),
            FOREIGN KEY (area_id) REFERENCES areas(id),
            FOREIGN KEY (company_id) REFERENCES companies(id)
        );
        CREATE TABLE IF NOT EXISTS agents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            area_id INTEGER NOT NULL,
            status TEXT DEFAULT 'activo',
            last_active TIMESTAMP,
            FOREIGN KEY (area_id) REFERENCES areas(id)
        );
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS marketing_suggestions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            suggestion_type TEXT,
            content TEXT,
            platform TEXT,
            status TEXT DEFAULT 'pendiente',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            approved_at TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS task_followups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER NOT NULL,
            followup_type TEXT NOT NULL,
            message TEXT,
            sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            response TEXT,
            FOREIGN KEY (task_id) REFERENCES tasks(id)
        );
        CREATE TABLE IF NOT EXISTS email_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER,
            recipient TEXT NOT NULL,
            subject TEXT NOT NULL,
            email_type TEXT NOT NULL,
            status TEXT DEFAULT 'sent',
            error_message TEXT,
            sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS chat_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            username TEXT NOT NULL,
            message TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS area_chat_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            area_id INTEGER NOT NULL,
            company_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            username TEXT NOT NULL,
            message TEXT NOT NULL,
            urgency_color TEXT DEFAULT '#FFC107',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (area_id) REFERENCES areas(id) ON DELETE CASCADE,
            FOREIGN KEY (company_id) REFERENCES companies(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            area_id INTEGER,
            title TEXT NOT NULL,
            message TEXT,
            notification_type TEXT DEFAULT 'info',
            is_read INTEGER DEFAULT 0,
            link TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS session_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            username TEXT NOT NULL,
            ip_address TEXT,
            user_agent TEXT,
            action TEXT DEFAULT 'login',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS metrics_daily (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            area_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            tasks_created INTEGER DEFAULT 0,
            tasks_completed INTEGER DEFAULT 0,
            tasks_overdue INTEGER DEFAULT 0,
            avg_completion_hours REAL,
            UNIQUE(area_id, date),
            FOREIGN KEY (area_id) REFERENCES areas(id)
        );
    ''')

    areas_data = [
        ('RRHH', 'rrhh@poffice.cl', 'Recursos Humanos', '#1a73e8'),
        ('ASISTENTE RRHH', 'asistenterrhh@poffice.cl', 'Asistente de Recursos Humanos', '#ea4335'),
        ('FINANZAS', 'finanzas@poffice.cl', 'Departamento de Finanzas', '#34a853'),
        ('VENTAS', 'ventas@poffice.cl', 'Departamento de Ventas', '#fbbc04'),
        ('ADMINISTRACION DE CONTRATOS', 'supervisiongeneral@poffice.cl', 'Administración de Contratos', '#ff6d01'),
        ('ADMINISTRACIÓN GENERAL', 'administracion@poffice.cl', 'Administración General', '#46bdc6'),
        ('MARKETING', 'marketing@poffice.cl', 'Departamento de Marketing', '#7B2D8E'),
        ('ATENCION AL CLIENTE', 'atencionalcliente@poffice.cl', 'Atención al Cliente', '#e91e63')
    ]
    for name, email, desc, color in areas_data:
        conn.execute('INSERT OR IGNORE INTO areas (name, email, description, color) VALUES (?, ?, ?, ?)',
                     (name, email, desc, color))

    for company in ['ProClean Facilities', 'Paper Office', 'Aromas Premium', 'BearClean']:
        conn.execute('INSERT OR IGNORE INTO companies (name) VALUES (?)', (company,))

    user_count = conn.execute('SELECT COUNT(*) as c FROM users').fetchone()['c']
    if user_count == 0:
        conn.execute('INSERT INTO users (username, password_hash, role, name, email) VALUES (?, ?, ?, ?, ?)',
                     ('admin', hash_password('admin123'), 'superadmin', 'Administrador',
                      'asignaciondetareashiramchile@gmail.com'))
        area_users = [
            (1, 'rrhh', 'rrhh2026', 'RRHH'),
            (2, 'asistente_rrhh', 'asistente_rrhh2026', 'Asistente RRHH'),
            (3, 'finanzas', 'finanzas2026', 'Finanzas'),
            (4, 'ventas', 'ventas2026', 'Ventas'),
            (5, 'contratos', 'contratos2026', 'Admin Contratos'),
            (6, 'admin_general', 'admin_general2026', 'Admin General'),
            (7, 'marketing', 'marketing2026', 'Marketing'),
            (8, 'atencion', 'atencion2026', 'Atencion Cliente'),
        ]
        for area_id, username, password, name in area_users:
            conn.execute('INSERT INTO users (username, password_hash, role, area_id, name) VALUES (?, ?, ?, ?, ?)',
                         (username, hash_password(password), 'area', area_id, name))

    templates_data = [
        (1, 'Revisión de contratos del personal', 'Revisar y actualizar contratos vigentes del personal', 'media', 1, 30),
        (1, 'Informe de novedades RRHH', 'Preparar informe semanal de novedades del personal', 'media', 1, 7),
        (2, 'Actualización de expedientes', 'Digitalizar y ordenar expedientes pendientes', 'baja', 1, 15),
        (3, 'Cierre contable mensual', 'Realizar cierre contable del mes', 'alta', 1, 30),
        (3, 'Revisión de flujo de caja', 'Actualizar flujo de caja semanal', 'alta', 1, 7),
        (4, 'Seguimiento a clientes', 'Contactar prospectos sin respuesta', 'media', 1, 7),
        (4, 'Reporte de ventas semanal', 'Preparar reporte de ventas de la semana', 'media', 1, 7),
        (5, 'Revisión vencimientos contratos', 'Verificar contratos próximos a vencer', 'alta', 1, 15),
        (6, 'Actualización procedimientos', 'Revisar manuales de procedimientos internos', 'baja', 1, 30),
        (7, 'Calendario de contenidos', 'Planificar contenido semanal para redes sociales', 'media', 1, 7),
        (7, 'Newsletter mensual', 'Preparar y enviar newsletter del mes', 'media', 1, 30),
        (8, 'Encuesta satisfacción', 'Preparar encuestas de satisfacción a clientes', 'media', 1, 15)
    ]
    for area_id, title, desc, priority, recurring, days in templates_data:
        conn.execute(
            'INSERT OR IGNORE INTO task_templates (area_id, title, description, priority, is_recurring, recurring_days) VALUES (?, ?, ?, ?, ?, ?)',
            (area_id, title, desc, priority, recurring, days))

    default_settings = [
        ('smtp_server', 'smtp.gmail.com'), ('smtp_port', '587'), ('smtp_user', ''),
        ('smtp_pass', ''), ('from_email', 'notificaciones@hiramchile.cl'),
        ('smtp_configured', 'false'), ('agent_interval_hours', '6'),
        ('daily_reminder_hour', '9'), ('marketing_agent_active', 'true'),
        ('graph_tenant_id', ''), ('graph_client_id', ''), ('graph_client_secret', ''),
        ('graph_user_email', ''), ('graph_configured', 'false'),
    ]
    for key, value in default_settings:
        conn.execute('INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)', (key, value))

    for col in ['approved_at', 'approved_by']:
        try:
            conn.execute(f'ALTER TABLE tasks ADD COLUMN {col} TEXT')
        except:
            pass
    try:
        conn.execute('CREATE INDEX IF NOT EXISTS idx_tasks_search ON tasks(title, description)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_chat_task ON chat_messages(task_id, created_at)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications(user_id, is_read)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_session_logs_user ON session_logs(user_id, created_at)')
    except:
        pass

    conn.commit()
    conn.close()
    print("Base de datos SQLite inicializada correctamente.")

def _init_pg():
    conn = get_db()
    cur = conn.cursor()

    tables = [
        '''
        CREATE TABLE IF NOT EXISTS areas (
            id SERIAL PRIMARY KEY, name TEXT NOT NULL UNIQUE, email TEXT NOT NULL,
            description TEXT, color TEXT DEFAULT '#1a73e8',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''',
        '''
        CREATE TABLE IF NOT EXISTS companies (
            id SERIAL PRIMARY KEY, name TEXT NOT NULL UNIQUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''',
        '''
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY, username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'area' CHECK(role IN ('superadmin','admin','area')),
            area_id INTEGER REFERENCES areas(id), name TEXT, email TEXT,
            is_active INTEGER DEFAULT 1, last_login TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''',
        '''
        CREATE TABLE IF NOT EXISTS tasks (
            id SERIAL PRIMARY KEY, area_id INTEGER NOT NULL REFERENCES areas(id),
            company_id INTEGER NOT NULL REFERENCES companies(id),
            title TEXT NOT NULL, description TEXT,
            priority TEXT NOT NULL CHECK(priority IN ('urgente','alta','media','baja')),
            status TEXT NOT NULL DEFAULT 'pendiente' CHECK(status IN ('pendiente','gestionando','realizada','cancelada')),
            due_date DATE, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP, created_by TEXT DEFAULT 'sistema',
            template_id INTEGER, kanban_order INTEGER DEFAULT 0,
            approved_at TIMESTAMP, approved_by TEXT
        )''',
        '''
        CREATE TABLE IF NOT EXISTS task_attachments (
            id SERIAL PRIMARY KEY, task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
            filename TEXT NOT NULL, original_name TEXT NOT NULL,
            file_size INTEGER, mime_type TEXT,
            uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''',
        '''
        CREATE TABLE IF NOT EXISTS task_logs (
            id SERIAL PRIMARY KEY, task_id INTEGER NOT NULL REFERENCES tasks(id),
            action TEXT NOT NULL, detail TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''',
        '''
        CREATE TABLE IF NOT EXISTS task_templates (
            id SERIAL PRIMARY KEY, area_id INTEGER NOT NULL REFERENCES areas(id),
            company_id INTEGER DEFAULT 1, title TEXT NOT NULL, description TEXT,
            priority TEXT DEFAULT 'media', is_recurring INTEGER DEFAULT 0,
            recurring_days INTEGER, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''',
        '''
        CREATE TABLE IF NOT EXISTS agents (
            id SERIAL PRIMARY KEY, name TEXT NOT NULL,
            area_id INTEGER NOT NULL REFERENCES areas(id),
            status TEXT DEFAULT 'activo', last_active TIMESTAMP
        )''',
        '''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY, value TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''',
        '''
        CREATE TABLE IF NOT EXISTS marketing_suggestions (
            id SERIAL PRIMARY KEY, title TEXT NOT NULL, description TEXT,
            suggestion_type TEXT, content TEXT, platform TEXT,
            status TEXT DEFAULT 'pendiente', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            approved_at TIMESTAMP
        )''',
        '''
        CREATE TABLE IF NOT EXISTS task_followups (
            id SERIAL PRIMARY KEY, task_id INTEGER NOT NULL REFERENCES tasks(id),
            followup_type TEXT NOT NULL, message TEXT,
            sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, response TEXT
        )''',
        '''
        CREATE TABLE IF NOT EXISTS email_logs (
            id SERIAL PRIMARY KEY, task_id INTEGER, recipient TEXT NOT NULL,
            subject TEXT NOT NULL, email_type TEXT NOT NULL, status TEXT DEFAULT 'sent',
            error_message TEXT, sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )        ''',
        '''
        CREATE TABLE IF NOT EXISTS chat_messages (
            id SERIAL PRIMARY KEY, task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
            user_id INTEGER NOT NULL REFERENCES users(id), username TEXT NOT NULL,
            message TEXT NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''',
        '''
        CREATE TABLE IF NOT EXISTS area_chat_messages (
            id SERIAL PRIMARY KEY, area_id INTEGER NOT NULL REFERENCES areas(id) ON DELETE CASCADE,
            company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            user_id INTEGER NOT NULL REFERENCES users(id), username TEXT NOT NULL,
            message TEXT NOT NULL, urgency_color TEXT DEFAULT '#FFC107',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''',
        '''
        CREATE TABLE IF NOT EXISTS notifications (
            id SERIAL PRIMARY KEY, user_id INTEGER, area_id INTEGER,
            title TEXT NOT NULL, message TEXT, notification_type TEXT DEFAULT 'info',
            is_read INTEGER DEFAULT 0, link TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''',
        '''
        CREATE TABLE IF NOT EXISTS session_logs (
            id SERIAL PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
            username TEXT NOT NULL, ip_address TEXT, user_agent TEXT,
            action TEXT DEFAULT 'login', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''',
        '''
        CREATE TABLE IF NOT EXISTS metrics_daily (
            id SERIAL PRIMARY KEY, area_id INTEGER NOT NULL REFERENCES areas(id),
            date TEXT NOT NULL, tasks_created INTEGER DEFAULT 0,
            tasks_completed INTEGER DEFAULT 0, tasks_overdue INTEGER DEFAULT 0,
            avg_completion_hours REAL, UNIQUE(area_id, date)
        )'''
    ]
    for t in tables:
        cur.execute(t)

    areas = [
        ('RRHH', 'rrhh@poffice.cl', 'Recursos Humanos', '#1a73e8'),
        ('ASISTENTE RRHH', 'asistenterrhh@poffice.cl', 'Asistente de Recursos Humanos', '#ea4335'),
        ('FINANZAS', 'finanzas@poffice.cl', 'Departamento de Finanzas', '#34a853'),
        ('VENTAS', 'ventas@poffice.cl', 'Departamento de Ventas', '#fbbc04'),
        ('ADMINISTRACION DE CONTRATOS', 'supervisiongeneral@poffice.cl', 'Administración de Contratos', '#ff6d01'),
        ('ADMINISTRACIÓN GENERAL', 'administracion@poffice.cl', 'Administración General', '#46bdc6'),
        ('MARKETING', 'marketing@poffice.cl', 'Departamento de Marketing', '#7B2D8E'),
        ('ATENCION AL CLIENTE', 'atencionalcliente@poffice.cl', 'Atención al Cliente', '#e91e63')
    ]
    for name, email, desc, color in areas:
        cur.execute('INSERT INTO areas (name, email, description, color) VALUES (%s,%s,%s,%s) ON CONFLICT (name) DO NOTHING', (name, email, desc, color))

    for company in ['ProClean Facilities', 'Paper Office', 'Aromas Premium', 'BearClean']:
        cur.execute('INSERT INTO companies (name) VALUES (%s) ON CONFLICT (name) DO NOTHING', (company,))

    cur.execute("SELECT COUNT(*) FROM users")
    if cur.fetchone()[0] == 0:
        cur.execute('INSERT INTO users (username, password_hash, role, name, email) VALUES (%s,%s,%s,%s,%s)',
                    ('admin', hash_password('admin123'), 'superadmin', 'Administrador', 'asignaciondetareashiramchile@gmail.com'))
        area_users = [
            (1, 'rrhh', 'rrhh2026', 'RRHH'),
            (2, 'asistente_rrhh', 'asistente_rrhh2026', 'Asistente RRHH'),
            (3, 'finanzas', 'finanzas2026', 'Finanzas'),
            (4, 'ventas', 'ventas2026', 'Ventas'),
            (5, 'contratos', 'contratos2026', 'Admin Contratos'),
            (6, 'admin_general', 'admin_general2026', 'Admin General'),
            (7, 'marketing', 'marketing2026', 'Marketing'),
            (8, 'atencion', 'atencion2026', 'Atencion Cliente'),
        ]
        for area_id, username, password, name in area_users:
            cur.execute('INSERT INTO users (username, password_hash, role, area_id, name) VALUES (%s,%s,%s,%s,%s)',
                        (username, hash_password(password), 'area', area_id, name))

    templates = [
        (1, 'Revisión de contratos del personal', 'Revisar y actualizar contratos vigentes del personal', 'media', 1, 30),
        (1, 'Informe de novedades RRHH', 'Preparar informe semanal de novedades del personal', 'media', 1, 7),
        (2, 'Actualización de expedientes', 'Digitalizar y ordenar expedientes pendientes', 'baja', 1, 15),
        (3, 'Cierre contable mensual', 'Realizar cierre contable del mes', 'alta', 1, 30),
        (3, 'Revisión de flujo de caja', 'Actualizar flujo de caja semanal', 'alta', 1, 7),
        (4, 'Seguimiento a clientes', 'Contactar prospectos sin respuesta', 'media', 1, 7),
        (4, 'Reporte de ventas semanal', 'Preparar reporte de ventas de la semana', 'media', 1, 7),
        (5, 'Revisión vencimientos contratos', 'Verificar contratos próximos a vencer', 'alta', 1, 15),
        (6, 'Actualización procedimientos', 'Revisar manuales de procedimientos internos', 'baja', 1, 30),
        (7, 'Calendario de contenidos', 'Planificar contenido semanal para redes sociales', 'media', 1, 7),
        (7, 'Newsletter mensual', 'Preparar y enviar newsletter del mes', 'media', 1, 30),
        (8, 'Encuesta satisfacción', 'Preparar encuestas de satisfacción a clientes', 'media', 1, 15)
    ]
    for area_id, title, desc, priority, recurring, days in templates:
        cur.execute(
            'INSERT INTO task_templates (area_id, title, description, priority, is_recurring, recurring_days) VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING',
            (area_id, title, desc, priority, recurring, days))

    settings = [
        ('smtp_server', 'smtp.gmail.com'), ('smtp_port', '587'), ('smtp_user', ''),
        ('smtp_pass', ''), ('from_email', 'notificaciones@hiramchile.cl'),
        ('smtp_configured', 'false'), ('agent_interval_hours', '6'),
        ('daily_reminder_hour', '9'), ('marketing_agent_active', 'true'),
        ('graph_tenant_id', ''), ('graph_client_id', ''), ('graph_client_secret', ''),
        ('graph_user_email', ''), ('graph_configured', 'false'),
    ]
    for key, value in settings:
        cur.execute('INSERT INTO settings (key, value) VALUES (%s,%s) ON CONFLICT (key) DO NOTHING', (key, value))

    try:
        cur.execute('CREATE INDEX IF NOT EXISTS idx_tasks_search ON tasks(title, description)')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_chat_task ON chat_messages(task_id, created_at)')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications(user_id, is_read)')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_session_logs_user ON session_logs(user_id, created_at)')
    except:
        pass

    conn.commit()
    conn.close()
    print("Base de datos PostgreSQL inicializada correctamente.")

if __name__ == '__main__':
    init_db()
