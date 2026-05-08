from datetime import datetime, timedelta
from database import get_db
from email_service import send_task_reminder, send_task_overdue_alert
from agent_service import generate_ai_suggestions, generate_marketing_suggestions, generate_task_followups, initialize_agents

def daily_reminder_job():
    print(f"[{datetime.now()}] Ejecutando recordatorio diario de tareas...")
    conn = get_db()

    pending = conn.execute('''
        SELECT t.*, a.name as area_name, a.email as area_email, c.name as company_name
        FROM tasks t
        JOIN areas a ON t.area_id = a.id
        JOIN companies c ON t.company_id = c.id
        WHERE t.status IN ('pendiente', 'gestionando')
    ''').fetchall()

    sent = 0
    for task in pending:
        ok = send_task_reminder(
            dict(task),
            task['area_email'],
            task['area_name'],
            task['company_name']
        )
        if ok:
            sent += 1

    conn.close()
    print(f"Recordatorios diarios: {sent}/{len(pending)} enviados")

def agent_suggestion_job():
    print(f"[{datetime.now()}] Agente IA generó sugerencias — pendientes de aprobación del administrador")
    # Las sugerencias solo se crean cuando el administrador las autoriza manualmente
    # desde la interfaz. No se auto-crean tareas.

def marketing_suggestion_job():
    print(f"[{datetime.now()}] Agente de Marketing generando sugerencias de diseño...")
    suggestions = generate_marketing_suggestions()

    from email_service import send_marketing_suggestion
    for sug in suggestions:
        send_marketing_suggestion(sug)

    print(f"Agente de Marketing generó {len(suggestions)} sugerencias de diseño")

def task_followup_job():
    print(f"[{datetime.now()}] Agentes IA haciendo seguimiento de tareas...")
    results = generate_task_followups()
    print(f"Seguimiento completado: {len(results)} tareas con seguimiento")

def recurring_tasks_job():
    print(f"[{datetime.now()}] Creando tareas recurrentes...")
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
    print(f"Tareas recurrentes creadas: {created}")

def overdue_check_job():
    print(f"[{datetime.now()}] Revisando tareas vencidas...")
    conn = get_db()
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    today_str = datetime.now().strftime('%Y-%m-%d')

    overdue = conn.execute('''
        SELECT t.*, a.name as area_name, a.email as area_email, c.name as company_name
        FROM tasks t
        JOIN areas a ON t.area_id = a.id
        JOIN companies c ON t.company_id = c.id
        WHERE t.status IN ('pendiente', 'gestionando')
        AND t.due_date < ?
    ''', (today_str,)).fetchall()

    from app import socketio, create_notification
    notified = 0
    for task in overdue:
        task_id = task['id']
        check = conn.execute(
            "SELECT COUNT(*) as c FROM task_logs WHERE task_id = ? AND action = 'overdue_alert' AND date(created_at) = ?",
            (task_id, today_str)
        ).fetchone()
        if check['c'] == 0:
            due = task.get('due_date')
            days_overdue = 0
            if due:
                try:
                    due_date = datetime.strptime(str(due)[:10], '%Y-%m-%d')
                    days_overdue = (datetime.now() - due_date).days
                except:
                    pass
            send_task_overdue_alert(dict(task), task['area_email'], task['area_name'], task['company_name'], days_overdue)
            create_notification(None, task['area_id'], f'⚠️ Tarea vencida: {task["title"]}',
                              f'Lleva {days_overdue} día(s) de atraso', 'overdue', f'/?area_id={task["area_id"]}')
            conn.execute(
                "INSERT INTO task_logs (task_id, action, detail) VALUES (?, 'overdue_alert', ?)",
                (task_id, f'Alerta de vencimiento enviada - {days_overdue} día(s) de atraso')
            )
            socketio.emit('task_overdue', {'task_id': task_id, 'title': task['title'], 'days_overdue': days_overdue, 'area_id': task['area_id']}, room='dashboard')
            notified += 1

    conn.commit()
    conn.close()
    print(f"Alertas de vencimiento: {notified} enviadas, {len(overdue)} vencidas total")

def start_scheduler(app):
    from apscheduler.schedulers.background import BackgroundScheduler

    scheduler = BackgroundScheduler()

    scheduler.add_job(
        func=daily_reminder_job,
        trigger='cron',
        hour=9,
        minute=0,
        id='daily_reminder',
        name='Recordatorio diario de tareas',
        replace_existing=True
    )

    scheduler.add_job(
        func=agent_suggestion_job,
        trigger='interval',
        hours=6,
        id='agent_suggestions',
        name='Sugerencias del agente IA',
        replace_existing=True
    )

    scheduler.add_job(
        func=marketing_suggestion_job,
        trigger='interval',
        hours=4,
        id='marketing_suggestions',
        name='Sugerencias de marketing',
        replace_existing=True
    )

    scheduler.add_job(
        func=task_followup_job,
        trigger='interval',
        hours=3,
        id='task_followup',
        name='Seguimiento de tareas',
        replace_existing=True
    )

    scheduler.add_job(
        func=initialize_agents,
        trigger='interval',
        hours=24,
        id='init_agents',
        name='Inicializar agentes',
        replace_existing=True
    )

    scheduler.add_job(
        func=recurring_tasks_job,
        trigger='cron',
        hour=6,
        minute=0,
        id='recurring_tasks',
        name='Tareas recurrentes',
        replace_existing=True
    )

    scheduler.add_job(
        func=overdue_check_job,
        trigger='interval',
        hours=1,
        id='overdue_check',
        name='Revisar tareas vencidas',
        replace_existing=True
    )

    scheduler.start()
    print("="*60)
    print("📋 PLANIFICADOR DE AGENTES IA INICIADO")
    print("="*60)
    print("⏰ 09:00 - Recordatorio diario de tareas")
    print("🤖 Cada 6h  - Sugerencias de tareas IA")
    print("🎨 Cada 4h  - Sugerencias de Marketing")
    print("📊 Cada 3h  - Seguimiento de tareas")
    print("🔄 06:00 - Tareas recurrentes (plantillas)")
    print("⚠️ Cada 1h - Revisión de tareas vencidas")
    print("="*60)
    return scheduler
