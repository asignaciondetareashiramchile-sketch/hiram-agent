from datetime import datetime
from database import get_db
from email_service import send_task_reminder
from agent_service import generate_ai_suggestions, generate_marketing_suggestions, generate_task_followups, initialize_agents

def daily_reminder_job():
    print(f"[{datetime.now()}] Ejecutando recordatorio diario de tareas...")
    conn = get_db()
    cursor = conn.cursor()

    pending = cursor.execute('''
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
    print(f"[{datetime.now()}] Agente IA generando sugerencias de tareas...")
    suggestions = generate_ai_suggestions()

    conn = get_db()
    cursor = conn.cursor()

    for sug in suggestions:
        cursor.execute('''
            INSERT INTO tasks (area_id, company_id, title, description, priority, status, created_by)
            VALUES (
                (SELECT id FROM areas WHERE name = ?),
                (SELECT id FROM companies WHERE name = ?),
                ?, ?, ?, 'pendiente', 'agente_ia'
            )
        ''', (sug['area'], sug['company'], f"[SUGERIDO] {sug['title']}", sug['description'], sug['priority']))

        task_id = cursor.lastrowid
        from email_service import send_agent_suggestion
        send_agent_suggestion({
            'id': task_id,
            'title': f"[SUGERIDO] {sug['title']}",
            'description': sug['description'],
            'company': sug['company'],
            'area': sug['area'],
            'priority': sug['priority'],
            'reason': sug['reason']
        })

    conn.commit()
    conn.close()
    print(f"Agente IA generó {len(suggestions)} sugerencias de tareas")

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
            from datetime import timedelta
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

    scheduler.start()
    print("="*60)
    print("📋 PLANIFICADOR DE AGENTES IA INICIADO")
    print("="*60)
    print("⏰ 09:00 - Recordatorio diario de tareas")
    print("🤖 Cada 6h  - Sugerencias de tareas IA")
    print("🎨 Cada 4h  - Sugerencias de Marketing")
    print("📊 Cada 3h  - Seguimiento de tareas")
    print("🔄 06:00 - Tareas recurrentes (plantillas)")
    print("="*60)
    return scheduler
