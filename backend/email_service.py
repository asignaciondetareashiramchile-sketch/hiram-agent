import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from database import get_db
from graph_email import send_email_via_graph, is_graph_configured

PRIORITY_MAP = {
    'urgente': ('URGENTE - 3 Horas', '#7B2D8E'),
    'alta': ('Alta Prioridad - Hoy', '#DC3545'),
    'media': ('Prioridad Media - 3 Días', '#FFC107'),
    'baja': ('Prioridad Baja - 5 Días', '#28A745')
}

COMPANY_COLORS = {
    'ProClean Facilities': '#1a73e8',
    'Paper Office': '#ea4335',
    'Aromas Premium': '#34a853',
    'BearClean': '#fbbc04'
}

def get_smtp_config():
    conn = get_db()
    settings = conn.execute('SELECT key, value FROM settings').fetchall()
    conn.close()
    config = {}
    for s in settings:
        config[s['key']] = s['value']
    return config

ADMIN_EMAIL = 'asignaciondetareashiramchile@gmail.com'

def get_base_url():
    config = get_smtp_config()
    return config.get('base_url', '') or os.environ.get('BASE_URL', 'http://localhost:8080')

def log_email(task_id, recipient, subject, email_type, status, error_message=None):
    try:
        conn = get_db()
        conn.execute('INSERT INTO email_logs (task_id, recipient, subject, email_type, status, error_message) VALUES (?, ?, ?, ?, ?, ?)',
                    (task_id, recipient, subject, email_type, status, error_message))
        conn.commit()
        conn.close()
    except:
        pass

def send_email(to_email, subject, html_content, task_id=None, email_type='general'):
    config = get_smtp_config()

    # Try Microsoft Graph API first if configured
    if config.get('graph_configured') == 'true' and config.get('graph_tenant_id'):
        ok = send_email_via_graph(to_email, subject, html_content, config=config)
        if ok:
            log_email(task_id, to_email, subject, email_type, 'sent_via_graph')
            return True
        print("[EMAIL] Graph API falló, probando SMTP...")

    # Fallback to SMTP
    if config.get('smtp_configured') == 'true' and config.get('smtp_user'):
        try:
            msg = MIMEMultipart('alternative')
            msg['From'] = config.get('from_email', 'notificaciones@hiramchile.cl')
            msg['To'] = to_email
            msg['Subject'] = subject

            part = MIMEText(html_content, 'html')
            msg.attach(part)

            server = smtplib.SMTP(config['smtp_server'], int(config['smtp_port']))
            server.starttls()
            server.login(config['smtp_user'], config['smtp_pass'])
            server.send_message(msg)
            server.quit()
            print(f"✅ Email enviado a {to_email}")
            log_email(task_id, to_email, subject, email_type, 'sent')
            return True
        except Exception as e:
            print(f"❌ Error enviando email a {to_email}: {e}")
            log_email(task_id, to_email, subject, email_type, 'error', str(e))
            return False

    print(f"[EMAIL MOCK] Para: {to_email} | Asunto: {subject}")
    log_email(task_id, to_email, subject, email_type, 'mock')
    return True

def send_test_email(to_email):
    config = get_smtp_config()

    # Try Graph API test first
    if config.get('graph_configured') == 'true' and config.get('graph_tenant_id'):
        from graph_email import send_test_email as graph_test
        ok = graph_test(to_email, config)
        if ok:
            log_email(None, to_email, "🔧 Prueba Graph API - Hiram Chile", 'test', 'sent_via_graph')
            return True
        print("[EMAIL] Graph test falló, intentando SMTP...")

    html = f'''
    <!DOCTYPE html>
    <html><head><meta charset="utf-8"></head>
    <body style="font-family:Arial;padding:20px;">
        <div style="max-width:600px;margin:auto;background:white;border-radius:8px;padding:30px;box-shadow:0 2px 10px rgba(0,0,0,0.1);">
            <div style="background:linear-gradient(135deg,#1a237e,#283593);padding:20px;border-radius:8px 8px 0 0;text-align:center;margin:-30px -30px 20px;">
                <h1 style="color:white;margin:0;font-size:20px;">Hiram Chile – ProClean Facilities</h1>
            </div>
            <h2 style="color:#333;">✅ Prueba de Configuración SMTP</h2>
            <p style="color:#666;">Si estás leyendo este correo, la configuración SMTP funciona correctamente.</p>
            <p style="color:#666;">El sistema de agentes IA está listo para enviar notificaciones.</p>
            <hr style="border:none;border-top:1px solid #eee;margin:20px 0;">
            <p style="color:#999;font-size:12px;text-align:center;">Sistema de Gestión de Tareas Hiram Chile</p>
        </div>
    </body></html>
    '''
    return send_email(to_email, "🔧 Prueba SMTP - Hiram Chile", html)

def send_task_notification(task, area_email, area_name, company_name):
    priority_info = PRIORITY_MAP.get(task['priority'], ('Desconocida', '#000'))
    company_color = COMPANY_COLORS.get(company_name, '#000')
    base_url = get_base_url()

    html = f'''
    <!DOCTYPE html>
    <html>
    <head><meta charset="utf-8"></head>
    <body style="font-family:Arial;margin:0;padding:0;background:#f4f4f4;">
        <div style="max-width:600px;margin:20px auto;background:white;border-radius:8px;overflow:hidden;box-shadow:0 2px 10px rgba(0,0,0,0.1);">
            <div style="background:linear-gradient(135deg,#1a237e,#283593);padding:20px;text-align:center;">
                <h1 style="color:white;margin:0;font-size:20px;">Hiram Chile – ProClean Facilities</h1>
                <p style="color:#ffcdd2;margin:5px 0 0;">Nueva Tarea Asignada</p>
            </div>
            <div style="padding:20px;">
                <div style="background:{company_color};color:white;padding:5px 10px;border-radius:4px;display:inline-block;font-size:12px;margin-bottom:15px;">
                    {company_name}
                </div>
                <h2 style="color:#333;margin-top:0;">📋 Nueva Tarea Asignada a {area_name}</h2>
                <p style="color:#666;"><strong>Tarea:</strong> {task['title']}</p>
                <p style="color:#666;"><strong>Descripción:</strong> {task.get('description', 'Sin descripción')}</p>
                <p style="color:#666;"><strong>Prioridad:</strong>
                    <span style="background:{priority_info[1]};color:white;padding:3px 8px;border-radius:4px;font-size:12px;">
                        {priority_info[0]}
                    </span>
                </p>
                <p style="color:#666;"><strong>Fecha Límite:</strong> {task.get('due_date', 'No especificada')}</p>

                <div style="text-align:center;margin:25px 0;">
                    <a href="{base_url}/api/tasks/{task['id']}/status/gestionando"
                       style="display:inline-block;background:#FFC107;color:#333;text-decoration:none;padding:12px 25px;border-radius:5px;font-weight:bold;margin:5px;">
                        🔄 Gestionando
                    </a>
                    <a href="{base_url}/api/tasks/{task['id']}/status/realizada"
                       style="display:inline-block;background:#28A745;color:white;text-decoration:none;padding:12px 25px;border-radius:5px;font-weight:bold;margin:5px;">
                        ✅ Realizado
                    </a>
                </div>

                <hr style="border:none;border-top:1px solid #eee;margin:20px 0;">
                <p style="color:#999;font-size:12px;text-align:center;">
                    Sistema de Gestión de Tareas · Hiram Chile · ProClean Facilities<br>
                    Los agentes IA trabajan 24/7 dando seguimiento a tus tareas.
                </p>
            </div>
        </div>
    </body></html>
    '''
    return send_email(area_email, f"[{priority_info[0]}] Nueva Tarea: {task['title']} - {company_name}", html)

def send_task_reminder(task, area_email, area_name, company_name):
    priority_info = PRIORITY_MAP.get(task['priority'], ('Desconocida', '#000'))
    company_color = COMPANY_COLORS.get(company_name, '#000')
    base_url = get_base_url()

    html = f'''
    <!DOCTYPE html>
    <html>
    <head><meta charset="utf-8"></head>
    <body style="font-family:Arial;margin:0;padding:0;background:#f4f4f4;">
        <div style="max-width:600px;margin:20px auto;background:white;border-radius:8px;overflow:hidden;box-shadow:0 2px 10px rgba(0,0,0,0.1);">
            <div style="background:linear-gradient(135deg,#1a237e,#283593);padding:20px;text-align:center;">
                <h1 style="color:white;margin:0;font-size:20px;">Hiram Chile – ProClean Facilities</h1>
                <p style="#81d4fa;margin:5px 0 0;">🤖 Recordatorio del Agente IA</p>
            </div>
            <div style="padding:20px;">
                <div style="background:{company_color};color:white;padding:5px 10px;border-radius:4px;display:inline-block;font-size:12px;margin-bottom:15px;">
                    {company_name}
                </div>
                <h2 style="color:#333;margin-top:0;">⏰ Recordatorio de Tarea Pendiente</h2>
                <p style="color:#666;"><strong>Área:</strong> {area_name}</p>
                <p style="color:#666;"><strong>Tarea:</strong> {task['title']}</p>
                <p style="color:#666;"><strong>Prioridad:</strong>
                    <span style="background:{priority_info[1]};color:white;padding:3px 8px;border-radius:4px;font-size:12px;">
                        {priority_info[0]}
                    </span>
                </p>
                <p style="color:#666;"><strong>Estado:</strong> {task['status']}</p>
                <p style="color:#666;"><strong>Fecha Límite:</strong> {task.get('due_date', 'No especificada')}</p>

                <div style="background:#fff3cd;border-left:4px solid #FFC107;padding:12px;margin:15px 0;border-radius:4px;">
                    <p style="margin:0;color:#856404;">🤖 El agente IA de {area_name} está haciendo seguimiento a esta tarea. Por favor, actualiza el estado.</p>
                </div>

                <div style="text-align:center;margin:25px 0;">
                    <a href="{base_url}/api/tasks/{task['id']}/status/gestionando"
                       style="display:inline-block;background:#FFC107;color:#333;text-decoration:none;padding:12px 25px;border-radius:5px;font-weight:bold;margin:5px;">
                        🔄 Gestionando
                    </a>
                    <a href="{base_url}/api/tasks/{task['id']}/status/realizada"
                       style="display:inline-block;background:#28A745;color:white;text-decoration:none;padding:12px 25px;border-radius:5px;font-weight:bold;margin:5px;">
                        ✅ Realizado
                    </a>
                </div>

                <hr style="border:none;border-top:1px solid #eee;margin:20px 0;">
                <p style="color:#999;font-size:12px;text-align:center;">
                    Seguimiento automático del Agente IA · Hiram Chile<br>
                    Los agentes están monitoreando 24/7 el progreso de tus tareas.
                </p>
            </div>
        </div>
    </body></html>
    '''
    return send_email(area_email, f"⏰ Recordatorio IA: {task['title']} - {company_name}", html)

def send_agent_suggestion(suggestion, user_email=None):
    if user_email is None:
        user_email = ADMIN_EMAIL
    base_url = get_base_url()
    html = f'''
    <!DOCTYPE html><html><head><meta charset="utf-8"></head>
    <body style="font-family:Arial;margin:0;padding:0;background:#f4f4f4;">
        <div style="max-width:600px;margin:20px auto;background:white;border-radius:8px;overflow:hidden;box-shadow:0 2px 10px rgba(0,0,0,0.1);">
            <div style="background:linear-gradient(135deg,#1a237e,#283593);padding:20px;text-align:center;">
                <h1 style="color:white;margin:0;font-size:20px;">Hiram Chile – ProClean Facilities</h1>
                <p style="color:#81d4fa;margin:5px 0 0;">🤖 Sugerencia del Agente IA</p>
            </div>
            <div style="padding:20px;">
                <h2 style="color:#333;">Nueva Sugerencia de Tarea</h2>
                <div style="background:#e3f2fd;border-left:4px solid #1a73e8;padding:15px;margin:10px 0;border-radius:4px;">
                    <p style="margin:0;color:#333;"><strong>📋 Título:</strong> {suggestion.get('title', '')}</p>
                    <p style="margin:5px 0;color:#333;"><strong>📝 Descripción:</strong> {suggestion.get('description', '')}</p>
                    <p style="margin:5px 0;color:#333;"><strong>🏢 Empresa:</strong> {suggestion.get('company', '')}</p>
                    <p style="margin:5px 0;color:#333;"><strong>👥 Área:</strong> {suggestion.get('area', '')}</p>
                    <p style="margin:5px 0;color:#333;"><strong>🎯 Prioridad:</strong> {suggestion.get('priority', '')}</p>
                </div>
                <p style="color:#666;font-style:italic;">{suggestion.get('reason', '')}</p>
                <div style="text-align:center;margin:25px 0;">
                    <a href="{base_url}/api/agent/approve/{suggestion.get('id')}"
                       style="display:inline-block;background:#28A745;color:white;text-decoration:none;padding:12px 25px;border-radius:5px;font-weight:bold;margin:5px;">✅ Aprobar</a>
                    <a href="{base_url}/api/agent/reject/{suggestion.get('id')}"
                       style="display:inline-block;background:#DC3545;color:white;text-decoration:none;padding:12px 25px;border-radius:5px;font-weight:bold;margin:5px;">❌ Rechazar</a>
                </div>
                <hr style="border:none;border-top:1px solid #eee;margin:20px 0;">
                <p style="color:#999;font-size:12px;text-align:center;">Los agentes IA trabajan 24/7 analizando y sugiriendo tareas. Las tareas solo se crean tras su aprobación.</p>
            </div>
        </div>
    </body></html>
    '''
    return send_email(user_email, f"🤖 Sugerencia IA: {suggestion.get('title', 'Nueva tarea')}", html)

def send_marketing_suggestion(suggestion):
    base_url = get_base_url()

    html = f'''
    <!DOCTYPE html>
    <html>
    <head><meta charset="utf-8"></head>
    <body style="font-family:Arial;margin:0;padding:0;background:#f4f4f4;">
        <div style="max-width:600px;margin:20px auto;background:white;border-radius:8px;overflow:hidden;box-shadow:0 2px 10px rgba(0,0,0,0.1);">
            <div style="background:linear-gradient(135deg,#1a237e,#283593);padding:20px;text-align:center;">
                <h1 style="color:white;margin:0;font-size:20px;">Hiram Chile – ProClean Facilities</h1>
                <p style="color:#81d4fa;margin:5px 0 0;">🎨 Sugerencia del Agente de Marketing</p>
            </div>
            <div style="padding:20px;">
                <h2 style="color:#333;">🎨 Nueva Sugerencia de Diseño</h2>
                <div style="background:#e3f2fd;border-left:4px solid #1a73e8;padding:15px;margin:10px 0;border-radius:4px;">
                    <p style="margin:0;color:#333;"><strong>📌 Título:</strong> {suggestion.get('title', '')}</p>
                    <p style="margin:5px 0;color:#333;"><strong>📝 Descripción:</strong> {suggestion.get('description', '')}</p>
                    <p style="margin:5px 0;color:#333;"><strong>🎯 Tipo:</strong> {suggestion.get('suggestion_type', '')}</p>
                    <p style="margin:5px 0;color:#333;"><strong>📱 Plataforma:</strong> {suggestion.get('platform', 'General')}</p>
                </div>
                <div style="background:#f5f5f5;padding:15px;margin:10px 0;border-radius:4px;">
                    <p style="margin:0;color:#333;white-space:pre-wrap;">{suggestion.get('content', '')}</p>
                </div>

                <div style="text-align:center;margin:25px 0;">
                    <a href="{base_url}/api/marketing/approve/{suggestion.get('id')}"
                       style="display:inline-block;background:#28A745;color:white;text-decoration:none;padding:12px 25px;border-radius:5px;font-weight:bold;margin:5px;">
                        ✅ Aprobar
                    </a>
                    <a href="{base_url}/api/marketing/reject/{suggestion.get('id')}"
                       style="display:inline-block;background:#DC3545;color:white;text-decoration:none;padding:12px 25px;border-radius:5px;font-weight:bold;margin:5px;">
                        ❌ Rechazar
                    </a>
                </div>

                <hr style="border:none;border-top:1px solid #eee;margin:20px 0;">
                <p style="color:#999;font-size:12px;text-align:center;">
                    Agente de Marketing IA generando sugerencias en tiempo real · Hiram Chile
                </p>
            </div>
        </div>
    </body></html>
    '''
    return send_email(ADMIN_EMAIL, f"🎨 Sugerencia Marketing: {suggestion.get('title', '')}", html)

def send_status_confirmation(task, area_email, area_name, company_name, new_status, old_status):
    base_url = get_base_url()
    status_emoji = {'gestionando': '🔄', 'realizada': '✅', 'pendiente': '⏳', 'cancelada': '❌'}
    status_text = {'gestionando': 'está GESTIONANDO la tarea', 'realizada': 'ha COMPLETADO la tarea', 'pendiente': 'ha REASIGNADO la tarea', 'cancelada': 'ha CANCELADO la tarea'}
    emoji = status_emoji.get(new_status, '📋')
    text = status_text.get(new_status, f'cambió estado a {new_status}')

    html = f'''
    <!DOCTYPE html><html><head><meta charset="utf-8"></head>
    <body style="font-family:Arial;margin:0;padding:0;background:#f4f4f4;">
        <div style="max-width:600px;margin:20px auto;background:white;border-radius:8px;overflow:hidden;box-shadow:0 2px 10px rgba(0,0,0,0.1);">
            <div style="background:linear-gradient(135deg,#1a237e,#283593);padding:20px;text-align:center;">
                <h1 style="color:white;margin:0;font-size:20px;">Hiram Chile – ProClean Facilities</h1>
                <p style="color:#81d4fa;margin:5px 0 0;">{emoji} Notificación de Estado</p>
            </div>
            <div style="padding:20px;">
                <h2 style="color:#333;">{emoji} Actualización de Tarea</h2>
                <div style="background:#e8f5e9;border-left:4px solid #28A745;padding:15px;margin:10px 0;border-radius:4px;">
                    <p style="margin:0;color:#333;font-size:16px;"><strong>{area_name}</strong> {text}:</p>
                </div>
                <p style="color:#666;"><strong>Tarea:</strong> {task['title']}</p>
                <p style="color:#666;"><strong>Empresa:</strong> {company_name}</p>
                <p style="color:#666;"><strong>Estado anterior:</strong> {old_status}</p>
                <p style="color:#666;"><strong>Estado actual:</strong> {new_status}</p>
                <p style="color:#666;"><strong>Fecha:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>

                <div style="text-align:center;margin:25px 0;">
                    <a href="{base_url}/"
                       style="display:inline-block;background:#1a237e;color:white;text-decoration:none;padding:12px 25px;border-radius:5px;font-weight:bold;">📋 Ir al Dashboard</a>
                </div>

                <hr style="border:none;border-top:1px solid #eee;margin:20px 0;">
                <p style="color:#999;font-size:12px;text-align:center;">
                    Sistema de Gestión de Tareas · Agentes IA 24/7 · Hiram Chile
                </p>
            </div>
        </div>
    </body></html>
    '''
    return send_email(ADMIN_EMAIL, f"{emoji} {area_name} {text}: {task['title']}", html)

def send_task_overdue_alert(task, area_email, area_name, company_name, days_overdue):
    base_url = get_base_url()
    html = f'''
    <!DOCTYPE html><html><head><meta charset="utf-8"></head>
    <body style="font-family:Arial;margin:0;padding:0;background:#f4f4f4;">
        <div style="max-width:600px;margin:20px auto;background:white;border-radius:8px;overflow:hidden;box-shadow:0 2px 10px rgba(0,0,0,0.1);">
            <div style="background:linear-gradient(135deg,#DC3545,#a71d2a);padding:20px;text-align:center;">
                <h1 style="color:white;margin:0;font-size:20px;">Hiram Chile – ProClean Facilities</h1>
                <p style="color:#ffcdd2;margin:5px 0 0;">⚠️ TAREA VENCIDA</p>
            </div>
            <div style="padding:20px;">
                <h2 style="color:#333;">⚠️ Alerta de Tarea Vencida</h2>
                <div style="background:#fff3cd;border-left:4px solid #FFC107;padding:15px;margin:10px 0;border-radius:4px;">
                    <p style="margin:0;color:#856404;font-size:16px;"><strong>⚠️ Esta tarea lleva {days_overdue} día(s) de atraso.</strong></p>
                </div>
                <p style="color:#666;"><strong>Tarea:</strong> {task['title']}</p>
                <p style="color:#666;"><strong>Área:</strong> {area_name}</p>
                <p style="color:#666;"><strong>Empresa:</strong> {company_name}</p>
                <p style="color:#666;"><strong>Fecha límite:</strong> {task.get('due_date', 'N/A')}</p>
                <p style="color:#666;"><strong>Estado actual:</strong> {task.get('status', 'pendiente')}</p>

                <div style="text-align:center;margin:25px 0;">
                    <a href="{base_url}/api/tasks/{task['id']}/status/realizada"
                       style="display:inline-block;background:#28A745;color:white;text-decoration:none;padding:12px 25px;border-radius:5px;font-weight:bold;margin:5px;">✅ Marcar Realizada</a>
                    <a href="{base_url}/"
                       style="display:inline-block;background:#1a73e8;color:white;text-decoration:none;padding:12px 25px;border-radius:5px;font-weight:bold;margin:5px;">📋 Ver Dashboard</a>
                </div>

                <hr style="border:none;border-top:1px solid #eee;margin:20px 0;">
                <p style="color:#999;font-size:12px;text-align:center;">
                    Recordatorio automático del Agente IA · Hiram Chile
                </p>
            </div>
        </div>
    </body></html>
    '''
    result = send_email(area_email, f"⚠️ TAREA VENCIDA: {task['title']} - {days_overdue} día(s) de atraso", html)
    send_email(ADMIN_EMAIL, f"⚠️ [COPIA] TAREA VENCIDA: {task['title']} - {area_name} - {days_overdue} día(s)", html)
    return result

def send_auto_suggestion(area_name, area_email, company_name):
    base_url = get_base_url()
    suggestions_map = {
        'RRHH': {
            'title': 'Revisión de procesos de contratación',
            'desc': 'Actualizar los perfiles de cargo y procesos de selección activos.',
            'priority': 'media'
        },
        'ASISTENTE RRHH': {
            'title': 'Organización de expedientes del personal',
            'desc': 'Digitalizar y ordenar los expedientes de los empleados activos.',
            'priority': 'baja'
        },
        'FINANZAS': {
            'title': 'Revisión de flujo de caja semanal',
            'desc': 'Actualizar el reporte de flujo de caja y proyectar la próxima semana.',
            'priority': 'alta'
        },
        'VENTAS': {
            'title': 'Seguimiento a clientes sin respuesta',
            'desc': 'Contactar a los prospectos que no han respondido en los últimos 5 días.',
            'priority': 'media'
        },
        'MARKETING': {
            'title': 'Creación de contenido semanal para redes sociales',
            'desc': 'Planificar y crear el calendario de contenidos para la próxima semana.',
            'priority': 'media'
        },
        'ADMINISTRACION DE CONTRATOS': {
            'title': 'Revisión de vencimientos de contratos',
            'desc': 'Verificar los contratos próximos a vencer y preparar renovaciones.',
            'priority': 'alta'
        },
        'ADMINISTRACIÓN GENERAL': {
            'title': 'Actualización de procedimientos operativos',
            'desc': 'Revisar y actualizar los manuales de procedimientos internos.',
            'priority': 'baja'
        },
        'ATENCION AL CLIENTE': {
            'title': 'Encuesta de satisfacción a clientes',
            'desc': 'Preparar y enviar encuestas de satisfacción a los clientes del último mes.',
            'priority': 'media'
        }
    }

    sug = suggestions_map.get(area_name, {
        'title': 'Revisión general de pendientes',
        'desc': 'Revisar y priorizar las tareas pendientes del área.',
        'priority': 'media'
    })

    html = f'''
    <!DOCTYPE html><html><head><meta charset="utf-8"></head>
    <body style="font-family:Arial;margin:0;padding:0;background:#f4f4f4;">
        <div style="max-width:600px;margin:20px auto;background:white;border-radius:8px;overflow:hidden;box-shadow:0 2px 10px rgba(0,0,0,0.1);">
            <div style="background:linear-gradient(135deg,#1a237e,#283593);padding:20px;text-align:center;">
                <h1 style="color:white;margin:0;font-size:20px;">Hiram Chile – ProClean Facilities</h1>
                <p style="color:#81d4fa;margin:5px 0 0;">🤖 Nueva Sugerencia Automática</p>
            </div>
            <div style="padding:20px;">
                <div style="background:#e3f2fd;border-left:4px solid #1a73e8;padding:15px;margin:10px 0;border-radius:4px;">
                    <p style="margin:0;color:#333;"><strong>📌 {sug['title']}</strong></p>
                    <p style="margin:5px 0;color:#666;">{sug['desc']}</p>
                    <p style="margin:5px 0;color:#666;"><strong>🏢 Empresa:</strong> {company_name}</p>
                </div>
                <div style="text-align:center;margin:25px 0;">
                    <a href="{base_url}/"
                       style="display:inline-block;background:#28A745;color:white;text-decoration:none;padding:12px 25px;border-radius:5px;font-weight:bold;">✅ Asignar esta tarea</a>
                </div>
                <hr style="border:none;border-top:1px solid #eee;margin:20px 0;">
                <p style="color:#999;font-size:12px;text-align:center;">Sugerencia generada automáticamente por el Agente IA de {area_name}</p>
            </div>
        </div>
    </body></html>
    '''
    return send_email(ADMIN_EMAIL, f"🤖 [Sugerencia IA] {sug['title']} - {area_name}", html)

def send_agent_followup(task, area_email, area_name, company_name, message):
    base_url = get_base_url()

    html = f'''
    <!DOCTYPE html>
    <html>
    <head><meta charset="utf-8"></head>
    <body style="font-family:Arial;margin:0;padding:0;background:#f4f4f4;">
        <div style="max-width:600px;margin:20px auto;background:white;border-radius:8px;overflow:hidden;box-shadow:0 2px 10px rgba(0,0,0,0.1);">
            <div style="background:linear-gradient(135deg,#1a237e,#283593);padding:20px;text-align:center;">
                <h1 style="color:white;margin:0;font-size:20px;">Hiram Chile – ProClean Facilities</h1>
                <p style="color:#81d4fa;margin:5px 0 0;">🤖 Seguimiento del Agente IA</p>
            </div>
            <div style="padding:20px;">
                <h2 style="color:#333;">🤖 Seguimiento Automático de Tarea</h2>
                <div style="background:#e8f5e9;border-left:4px solid #28A745;padding:15px;margin:10px 0;border-radius:4px;">
                    <p style="margin:0;color:#333;">{message}</p>
                </div>
                <p style="color:#666;"><strong>Tarea:</strong> {task['title']}</p>
                <p style="color:#666;"><strong>Empresa:</strong> {company_name}</p>

                <div style="text-align:center;margin:25px 0;">
                    <a href="{base_url}/api/tasks/{task['id']}/status/gestionando"
                       style="display:inline-block;background:#FFC107;color:#333;text-decoration:none;padding:12px 25px;border-radius:5px;font-weight:bold;margin:5px;">
                        🔄 Gestionando
                    </a>
                    <a href="{base_url}/api/tasks/{task['id']}/status/realizada"
                       style="display:inline-block;background:#28A745;color:white;text-decoration:none;padding:12px 25px;border-radius:5px;font-weight:bold;margin:5px;">
                        ✅ Realizado
                    </a>
                </div>

                <hr style="border:none;border-top:1px solid #eee;margin:20px 0;">
                <p style="color:#999;font-size:12px;text-align:center;">
                    Este es un seguimiento automático del Agente IA de {area_name}
                </p>
            </div>
        </div>
    </body></html>
    '''
    return send_email(area_email, f"🤖 Seguimiento IA: {task['title']} - {company_name}", html)
