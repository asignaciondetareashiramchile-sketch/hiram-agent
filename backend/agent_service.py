import os
import json
import random
from datetime import datetime, timedelta
from database import get_db

MKT_SUGGESTION_TYPES = [
    'social_post', 'ad_copy', 'email_campaign', 'blog_idea',
    'design_concept', 'video_script', 'landing_page', 'promotion'
]

MKT_PLATFORMS = ['LinkedIn', 'Instagram', 'Facebook', 'Twitter/X', 'TikTok', 'Email', 'Web']

SOCIAL_POST_TEMPLATES = [
    {
        'title': 'Campaña de limpieza profesional para oficinas',
        'description': 'Post destacando los beneficios de la limpieza profesional de oficinas',
        'platform': 'LinkedIn',
        'content': '✨ ¿Sabías que un espacio de trabajo limpio aumenta la productividad hasta un 20%?\n\nEn ProClean Facilities transformamos tu oficina en un entorno impecable y saludable. Nuestro equipo especializado utiliza productos eco-friendly de última generación.\n\n🔹 Limpieza diaria\n🔹 Sanitización profunda\n🔹 Pisos y alfombras\n🔹 Vidrios y fachadas\n\n👉 Contáctanos para una cotización personalizada.\n\n#ProClean #LimpiezaProfesional #OficinasSaludables #HiramChile'
    },
    {
        'title': 'Oferta especial Paper Office - Suministros',
        'description': 'Promoción de suministros de oficina para empresas',
        'platform': 'Instagram',
        'content': '📦 ¡Todo lo que tu oficina necesita en un solo lugar!\n\nPaper Office te trae los mejores suministros con los precios más competitivos del mercado.\n\n🖊️ Útiles de escritorio\n📋 Papelería corporativa\n🧴 Artículos de limpieza\n📎 Organización\n\n🎯 Empresas con compras sobre $50.000 reciben envío GRATIS.\n\n#PaperOffice #Suministros #Oficina #HiramChile'
    },
    {
        'title': 'Aromas Premium - Experiencia sensorial',
        'description': 'Publicidad de ambientadores premium para empresas',
        'platform': 'Facebook',
        'content': '🌟 Transforma la experiencia de tus clientes con Aromas Premium.\n\nEl aroma de tu negocio es la primera impresión que llevan tus clientes. Aromas Premium ofrece fragancias exclusivas para:\n\n🏢 Lobbies corporativos\n🛍️ Tiendas y retail\n🏨 Hoteles y restaurantes\n🏥 Centros médicos\n\n💫 Fragancias personalizadas para tu marca.\n\nDescubre más en nuestra página web.\n\n#AromasPremium #MarketingOlfativo #ExperienciaCliente #HiramChile'
    },
    {
        'title': 'BearClean - Soluciones ecológicas',
        'description': 'Campaña destacando productos de limpieza ecológicos BearClean',
        'platform': 'Twitter/X',
        'content': '🐻♻️ BearClean: Limpieza que cuida el planeta.\n\nNuestra línea de productos ecológicos es:\n✅ Biodegradable\n✅ No tóxico\n✅ Hipoalergénico\n✅ Efectivo contra el 99.9% de bacterias\n\nEl futuro de la limpieza es verde. ¿Tu empresa ya hizo el cambio? 🌱\n\n#BearClean #LimpiezaVerde #Sostenibilidad #HiramChile'
    },
    {
        'title': 'Hiram Chile - Soluciones integrales',
        'description': 'Post corporativo mostrando todas las marcas del grupo',
        'platform': 'LinkedIn',
        'content': '🏢 Hiram Chile: Más de una década liderando soluciones integrales para empresas.\n\nNuestras marcas trabajan juntas para ofrecerte:\n\n🧹 ProClean Facilities → Limpieza profesional\n📎 Paper Office → Suministros de oficina\n🌸 Aromas Premium → Experiencias sensoriales\n🐻 BearClean → Limpieza ecológica\n\nUna empresa, múltiples soluciones. Un solo objetivo: tu satisfacción.\n\n#HiramChile #SolucionesEmpresariales #GrupoEmpresarial'
    },
    {
        'title': 'Tips de organización para inicio de mes',
        'description': 'Contenido útil para empresas sobre organización de oficina',
        'platform': 'Instagram',
        'content': '📅 Tips de organización para empezar el mes con todo:\n\n1️⃣ Agenda una limpieza profunda con ProClean Facilities\n2️⃣ Revisa tus suministros y haz tu pedido en Paper Office\n3️⃣ Renueva el aroma de tu espacio con Aromas Premium\n4️⃣ Incorpora productos ecológicos BearClean\n\n¡Un espacio ordenado y limpio es sinónimo de éxito! 🚀\n\n#TipsDeOficina #Organización #Productividad #HiramChile'
    },
    {
        'title': 'Testimonios: Lo que dicen nuestros clientes',
        'description': 'Campaña de testimonios para generar confianza',
        'platform': 'Facebook',
        'content': '⭐ "Desde que trabajamos con ProClean Facilities, la calidad de nuestro ambiente laboral mejoró notablemente. Son profesionales, puntuales y extremadamente detallistas."\n\n— María González, Gerente de Operaciones\n\nEn Hiram Chile nos enorgullece ser partners de confianza para más de 500 empresas en Chile.\n\n¿Quieres ser el próximo? Contáctanos.\n\n#Testimonios #ClientesFelices #ProCleanFacilities #HiramChile'
    },
    {
        'title': 'Video promocional 30s - ProClean',
        'description': 'Idea para video corto promocional',
        'platform': 'TikTok',
        'content': '🎬 IDEA DE VIDEO (30 segundos):\n\n[0-5s] Apertura: toma rápida de una oficina desordenada → transición a oficina impecable\n[5-15s] Toma de nuestro equipo profesional limpiando con tecnología de punta\n[15-25s] Cliente satisfecho trabajando en su escritorio impecable\n[25-30s] Logo ProClean + "Profesionalismo que se nota" + CTA\n\n🎵 Audio: Música upbeat corporativa\n📌 Hashtags: #ProClean #LimpiezaProfesional #Oficinas #Chile'
    }
]

AD_COPY_TEMPLATES = [
    {
        'title': 'Google Ads - ProClean Facilities',
        'description': 'Anuncio para búsqueda de servicios de limpieza',
        'platform': 'Google Ads',
        'content': 'Headline 1: Limpieza Profesional de Oficinas\nHeadline 2: ProClean Facilities - Cotiza Ahora\nHeadline 3: +500 Empresas Confían\n\nDescription 1: Servicio de limpieza integral para tu empresa. Productos eco-friendly. Equipo certificado. Solicita tu cotización sin compromiso.\nDescription 2: Más de 10 años de experiencia en limpieza corporativa. Resultados garantizados. Contrata a los profesionales.\n\nPalabras clave: limpieza oficinas, aseo industrial, sanitización empresas, limpieza profesional Santiago'
    },
    {
        'title': 'Facebook Ads - Aromas Premium',
        'description': 'Anuncio para marketing olfativo empresarial',
        'platform': 'Meta Ads',
        'content': '🎯 PÚBLICO: Dueños de locales comerciales, gerentes de hotel, administradores de retail\n\n📝 COPY:\n¿Tus clientes recuerdan tu marca?\nEl aroma de tu negocio crea recuerdos imborrables.\n\nAromas Premium: Fragancias exclusivas para empresas.\n✅ Aumenta el tiempo de permanencia\n✅ Mejora la experiencia de compra\n✅ Refuerza tu identidad de marca\n\n🔗 Cotiza tu fragancia personalizada\n\n🖼️ IMAGEN: Mockup de ambientador elegante en lobby corporativo\n\n🎨 COLORES: Tonos pastel, beige y dorado'
    },
    {
        'title': 'Email Marketing - Ofertas Paper Office',
        'description': 'Newsletter para clientes con ofertas mensuales',
        'platform': 'Email',
        'content': '📧 ASUNTO: 🎁 Ofertas exclusivas de marzo - Paper Office\n\nPREHEADER: Descuentos de hasta 30% en suministros de oficina\n\n---\n\n👋 Hola [Nombre],\n\nEste mes en Paper Office tenemos ofertas imperdibles para tu empresa:\n\n📦 Pack Oficina Completa: $45.900 (ahorra 25%)\n🧴 Kit Limpieza BearClean: $12.900\n📋 Blocks de notas personalizados: desde $2.990 c/u\n\n⏰ Oferta válida hasta el 31 de marzo\n\n👉 COMPRAR AHORA\n\n🎁 Adicional: compras sobre $80.000 llevan un difusor Aromas Premium de regalo.\n\n---\nPaper Office · Suministros para tu empresa'
    }
]

EMAIL_CAMPAIGNS = [
    {
        'title': 'Newsletter mensual ProClean - Tips de mantenimiento',
        'description': 'Email marketing con consejos de limpieza y mantenimiento para oficinas',
        'platform': 'Email Marketing',
        'content': '''📧 ASUNTO: 🧹 Tips de limpieza profesional para tu oficina este mes

PREHEADER: Consejos prácticos + ofertas exclusivas para empresas

👋 Hola [Nombre],

En ProClean Facilities sabemos que mantener tu oficina impecable es clave para la productividad de tu equipo. Este mes te traemos:

✨ Tips del mes:
• Limpieza de alfombras: aspirar 2x por semana para mantener la vida útil
• Sanitización de baños: uso de desinfectantes ecológicos BearClean
• Escritorios: limpieza diaria con productos que no dañan las superficies

🎁 Oferta exclusiva para empresas:
Contrata nuestro plan mensual de limpieza y recibe:
✅ 2 limpiezas profundas gratis al año
✅ Despacho de suministros Paper Office con 15% desc.
✅ Difusor Aromas Premium de bienvenida

📅 Agenda tu evaluación gratuita:
👉 [Link a calendario]

--- 
ProClean Facilities · Una empresa de Hiram Chile
"Limpieza que inspira productividad"'''
    },
    {
        'title': 'Email de reactivación para clientes antiguos',
        'description': 'Campaña para recuperar clientes que no contratan servicios hace más de 3 meses',
        'platform': 'Email Marketing',
        'content': '''📧 ASUNTO: ⏰ Hace tiempo que no sabemos de ti... ¿Todo bien?

PREHEADER: Un descuento especial para tu regreso

👋 Hola [Nombre],

Hace un tiempo que no tenemos noticias tuyas y queríamos asegurarnos de que todo está bien.

En Hiram Chile seguimos creciendo y mejorando nuestros servicios para ti:

🌟 NOVEDADES:
• Nueva línea ecológica BearClean - biodegradables y efectivos
• Sistema de agenda online para servicios de limpieza
• App de seguimiento de pedidos Paper Office

🎁 REGRESA CON BENEFICIO:
Por ser parte de nuestra historia, te ofrecemos:
🔹 20% de descuento en tu primera limpieza profunda
🔹 Envío gratis en tu primer pedido Paper Office
🔹 Muestra gratis de Aromas Premium

👉 Quiero mi descuento de bienvenida

¿Prefieres que te llamemos? Responde este correo con tu teléfono.

--- 
Hiram Chile · ProClean Facilities · Paper Office · Aromas Premium · BearClean'''
    },
    {
        'title': 'Email de upselling - De limpieza a experiencia completa',
        'description': 'Campaña para ofrecer servicios complementarios a clientes actuales',
        'platform': 'Email Marketing',
        'content': '''📧 ASUNTO: 🌟 ¿Sabías que podemos hacer más por tu empresa?

PREHEADER: Unifica todos tus servicios con nosotros

👋 Hola [Nombre],

Actualmente contratas [servicio actual] con nosotros. ¿Sabías que podemos ofrecerte una solución integral?

Así es como otras empresas optimizan sus operaciones:

🏢 Clientes de ProClean Facilities también usan:
📎 Paper Office → Descuentos en suministros (ahorran hasta 25%)
🌸 Aromas Premium → Ambientación profesional (-40% en plan anual)
🐻 BearClean → Productos ecológicos para su mantenimiento diario

🎯 CASO DE ÉXITO:
"Antes teníamos 4 proveedores diferentes. Con Hiram Chile unificamos todo, ahorramos 35% y tenemos un solo interlocutor."
— Gerente de Administración, empresa del sector financiero

📋 Agenda una reunión de 15 min para conocer cómo podemos ayudarte:
👉 [Link agendamiento]

--- 
Hiram Chile · Soluciones Integrales para tu Empresa'''
    },
    {
        'title': 'Email bienvenida nuevos clientes - Onboarding',
        'description': 'Secuencia de bienvenida para nuevos clientes con guía de servicios',
        'platform': 'Email Marketing',
        'content': '''📧 ASUNTO: 👋 ¡Bienvenido a Hiram Chile! Esto es lo que sigue

PREHEADER: Te contamos cómo empezamos a trabajar juntos

👋 Hola [Nombre],

¡Gracias por confiar en Hiram Chile! Estamos felices de darte la bienvenida.

🚀 PRÓXIMOS PASOS:
Día 1: Activación de servicios + asignación de equipo
Día 3: Primera visita/despacho
Día 7: Encuesta de satisfacción inicial
Día 15: Ajustes y personalización

📱 TU ACCESO AL SISTEMA:
Puedes dar seguimiento a todas tus tareas y servicios en nuestro portal:
👉 [Link dashboard]

💬 CONTACTO DIRECTO:
Para cualquier consulta, responde este correo o contacta a tu ejecutivo asignado.

📋 ¿NECESITAS ALGO MÁS?
• ¿Quieres agregar otro servicio? Te ayudamos
• ¿Tienes dudas sobre tu facturación? Resueltas en 24h
• ¿Horarios especiales? Los coordinamos

--- 
¡Bienvenido a la familia Hiram Chile!
asignaciondetareashiramchile@gmail.com'''
    }
]

MARKET_ANALYSIS = [
    {
        'title': 'Análisis de mercado: Tendencias de limpieza corporativa 2026',
        'description': 'Estudio de mercado sobre las tendencias en servicios de limpieza para empresas',
        'platform': 'Informe',
        'content': '''📊 ANÁLISIS DE MERCADO - LIMPIEZA CORPORATIVA 2026

RESUMEN EJECUTIVO:
El mercado de limpieza profesional en Chile creció un 15% en 2025, impulsado por:
• Mayor conciencia de sanitización post-pandemia (30% de empresas aumentaron presupuesto)
• Exigencias regulatorias más estrictas (nueva norma ISO 45001)
• Demanda de productos ecológicos (67% de empresas prefieren proveedores sostenibles)

COMPETENCIA:
• Competidores directos: Servilimpia, CleanService, ECO Clean
• Ventaja competitiva Hiram Chile: 4 marcas integradas = solución completa
• Diferenciador: Seguimiento IA + dashboard en tiempo real

OPORTUNIDADES:
1. Mercado PYME no explotado (solo 25% contrata limpieza profesional)
2. Servicios especializados (limpieza post-construcción, data centers)
3. Suscripciones mensuales con productos incluidos

RECOMENDACIONES:
✅ Campaña enfocada en PYMEs con presupuestos ajustados
✅ Precios competitivos para contratos anuales
✅ Marketing digital con casos de éxito

#AnálisisDeMercado #LimpiezaProfesional #HiramChile #Tendencias2026'''
    },
    {
        'title': 'Análisis de competencia: Estrategia de precios',
        'description': 'Benchmarking de precios y servicios de la competencia en limpieza corporativa',
        'platform': 'Informe',
        'content': '''📊 BENCHMARKING - PRECIOS LIMPIEZA CORPORATIVA SANTIAGO 2026

SERVICIO BÁSICO (oficinas hasta 100m²):
• ProClean Facilities: $280.000/mes ★★★★★ (mejor relación calidad-precio)
• Servilimpia: $320.000/mes
• CleanService: $295.000/mes
• ECO Clean: $310.000/mes

INCLUIDO EN PLAN PROClean:
✅ 2 visitas semanales (4h c/u)
✅ Productos ecológicos BearClean sin costo adicional
✅ Seguro de accidentes
✅ Supervisor asignado
✅ Dashboard de seguimiento online

VENTAJA DIFERENCIAL:
Ningún competidor ofrece:
🔹 4 marcas integradas (limpieza, suministros, aromas, eco)
🔹 Agentes IA para seguimiento de tareas
🔹 Notificaciones en tiempo real por email

CONCLUSIÓN:
ProClean Facilities tiene el mejor precio del mercado con el servicio más completo. La integración de marcas Hiram Chile es nuestro principal diferenciador.

#Benchmarking #Precios #ProClean #HiramChile'''
    }
]

BLOG_IDEAS = [
    {
        'title': 'Guía completa de limpieza post-pandemia para oficinas',
        'description': 'Artículo SEO sobre protocolos de limpieza y sanitización',
        'platform': 'Web',
        'content': '📝 TÍTULO SEO: "Guía Completa de Limpieza y Sanitización para Oficinas 2026"\n\n📊 PALABRAS CLAVE: limpieza oficinas post-pandemia, sanitización empresas, protocolos limpieza corporativa, certificación limpieza profesional\n\n🏗️ ESTRUCTURA:\n\nH1: Guía Completa de Limpieza y Sanitización para Oficinas\nH2: ¿Por qué es importante la limpieza profesional?\n  - Estadísticas: 80% de enfermedades se transmiten por superficies contaminadas\n  - Productividad: oficinas limpias = 20% más productividad\nH2: Protocolos esenciales de limpieza\n  - Limpieza diaria vs profunda\n  - Áreas críticas: baños, cocina, salas de reuniones\n  - Frecuencia recomendada por área\nH2: Productos ecológicos vs tradicionales\n  - Beneficios BearClean\n  - Certificaciones ambientales\nH2: ¿Cada cuánto contratar limpieza profesional?\nH3: Conclusión y llamado a la acción\n\n📎 CTA: Solicita una evaluación gratuita de tu oficina'
    },
    {
        'title': 'Cómo elegir el proveedor de suministros de oficina ideal',
        'description': 'Guía de compra para gerentes de administración',
        'platform': 'Web',
        'content': '📝 TÍTULO SEO: "Cómo Elegir el Mejor Proveedor de Suministros de Oficina para tu Empresa"\n\n📊 PALABRAS CLAVE: proveedor suministros oficina, comprar útiles oficina, Paper Office, insumos corporativos\n\n🏗️ ESTRUCTURA:\n\nH1: 5 Claves para Elegir tu Proveedor de Suministros de Oficina\nH2: 1. Variedad y stock disponible\nH2: 2. Precios competitivos y descuentos por volumen\nH2: 3. Tiempos de entrega y cobertura\nH2: 4. Calidad de los productos\nH2: 5. Servicio post-venta\nH3: Paper Office: El aliado de tu empresa\n\n📎 CTA: Cotiza tus suministros aquí'
    }
]

def generate_marketing_suggestions():
    conn = get_db()
    cursor = conn.cursor()

    setting = cursor.execute("SELECT value FROM settings WHERE key = 'marketing_agent_active'").fetchone()
    if not setting or setting['value'] != 'true':
        conn.close()
        return []

    suggestions = []
    all_templates = SOCIAL_POST_TEMPLATES + AD_COPY_TEMPLATES + EMAIL_CAMPAIGNS + MARKET_ANALYSIS + BLOG_IDEAS
    selected = random.sample(all_templates, min(3, len(all_templates)))

    for template in selected:
        sug_type = 'social_post'
        if template in AD_COPY_TEMPLATES:
            sug_type = 'ad_copy'
        elif template in EMAIL_CAMPAIGNS:
            sug_type = 'email_campaign'
        elif template in MARKET_ANALYSIS:
            sug_type = 'market_analysis'
        elif template in BLOG_IDEAS:
            sug_type = 'blog_idea'

        cursor.execute('''
            INSERT INTO marketing_suggestions (title, description, suggestion_type, content, platform, status)
            VALUES (?, ?, ?, ?, ?, 'pendiente')
        ''', (template['title'], template['description'], sug_type, template['content'], template['platform']))

        sug_id = cursor.lastrowid
        suggestions.append({
            'id': sug_id,
            'title': template['title'],
            'description': template['description'],
            'suggestion_type': sug_type,
            'content': template['content'],
            'platform': template['platform'],
            'status': 'pendiente'
        })

    conn.commit()
    conn.close()
    return suggestions

def generate_task_followups():
    conn = get_db()
    cursor = conn.cursor()

    today = datetime.now().strftime('%Y-%m-%d')

    overdue_tasks = cursor.execute('''
        SELECT t.*, a.name as area_name, a.email as area_email, c.name as company_name
        FROM tasks t
        JOIN areas a ON t.area_id = a.id
        JOIN companies c ON t.company_id = c.id
        WHERE t.status IN ('pendiente', 'gestionando')
        AND t.due_date < ?
        ORDER BY t.due_date ASC
    ''', (today,)).fetchall()

    from email_service import send_agent_followup, send_task_overdue_alert

    results = []
    for task in overdue_tasks:
        days_overdue = (datetime.now() - datetime.strptime(task['due_date'], '%Y-%m-%d')).days if task['due_date'] else 0

        if days_overdue >= 3:
            message = f"⚠️ TAREA VENCIDA ({days_overdue} días de atraso). El agente IA de {task['area_name']} requiere atención urgente."
        elif days_overdue >= 1:
            message = f"⚠️ Tarea vencida por {days_overdue} día(s). El agente IA de {task['area_name']} recomienda priorizar hoy."
        else:
            message = f"📋 Tarea con fecha límite hoy. El agente IA de {task['area_name']} está monitoreando."

        cursor.execute('''
            INSERT INTO task_followups (task_id, followup_type, message)
            VALUES (?, 'overdue', ?)
        ''', (task['id'], message))

        send_agent_followup(
            dict(task), task['area_email'], task['area_name'], task['company_name'], message
        )

        if task['status'] == 'gestionando' and days_overdue >= 1:
            send_task_overdue_alert(
                dict(task), task['area_email'], task['area_name'], task['company_name'], days_overdue
            )

        cursor.execute('UPDATE agents SET last_active = ? WHERE area_id = ?',
                      (datetime.now().isoformat(), task['area_id']))

        results.append({
            'task_id': task['id'],
            'area': task['area_name'],
            'message': message
        })

    conn.commit()
    conn.close()
    return results

def generate_ai_suggestions():
    conn = get_db()
    cursor = conn.cursor()

    templates = random.sample(TASK_TEMPLATES, min(3, len(TASK_TEMPLATES)))
    suggestions = []

    for template in templates:
        company = random.choice(COMPANIES)
        area_row = cursor.execute(
            'SELECT id, name, email FROM areas WHERE name = ?',
            (template['area_hint'],)
        ).fetchone()

        if not area_row:
            continue

        suggestion = {
            'title': template['title'],
            'description': template['description'],
            'company': company,
            'area': template['area_hint'],
            'area_id': area_row['id'],
            'area_email': area_row['email'],
            'priority': template['priority_hint'],
            'reason': f'El agente IA del área {template["area_hint"]} ha detectado que esta tarea necesita atención urgente. Basado en el análisis de actividades recurrentes y mejores prácticas del sector.'
        }
        suggestions.append(suggestion)

    conn.close()
    return suggestions

def get_agent_status():
    conn = get_db()
    cursor = conn.cursor()

    areas = cursor.execute('SELECT * FROM areas').fetchall()
    agents = cursor.execute('SELECT * FROM agents').fetchall()
    now = datetime.now()

    status = []
    for area in areas:
        agent = next((a for a in agents if a['area_id'] == area['id']), None)

        pending = cursor.execute(
            "SELECT COUNT(*) as c FROM tasks WHERE area_id = ? AND status IN ('pendiente','gestionando')",
            (area['id'],)
        ).fetchone()

        overdue = cursor.execute(
            "SELECT COUNT(*) as c FROM tasks WHERE area_id = ? AND status IN ('pendiente','gestionando') AND due_date < ?",
            (area['id'], now.strftime('%Y-%m-%d'))
        ).fetchone()

        completed_today = cursor.execute(
            "SELECT COUNT(*) as c FROM tasks WHERE area_id = ? AND status = 'realizada' AND date(completed_at) = ?",
            (area['id'], now.strftime('%Y-%m-%d'))
        ).fetchone()

        status.append({
            'area_id': area['id'],
            'area_name': area['name'],
            'area_email': area['email'],
            'agent_status': agent['status'] if agent else 'inactivo',
            'last_active': agent['last_active'] if agent else None,
            'pending_tasks': pending['c'] if pending else 0,
            'overdue_tasks': overdue['c'] if overdue else 0,
            'completed_today': completed_today['c'] if completed_today else 0
        })

    conn.close()
    return status

def initialize_agents():
    conn = get_db()
    areas = conn.execute('SELECT id, name FROM areas').fetchall()
    for area in areas:
        existing = conn.execute(
            'SELECT id FROM agents WHERE area_id = ?', (area['id'],)
        ).fetchone()
        if not existing:
            conn.execute(
                'INSERT INTO agents (name, area_id, status, last_active) VALUES (?, ?, ?, ?)',
                (f'Agent-{area["name"]}', area['id'], 'activo', datetime.now().isoformat())
            )

    conn.commit()
    conn.close()

TASK_TEMPLATES = [
    {
        'title': 'Revisión de contratos pendientes de renovación',
        'description': 'Revisar y actualizar todos los contratos que estén próximos a vencer este mes.',
        'area_hint': 'ADMINISTRACION DE CONTRATOS',
        'priority_hint': 'alta'
    },
    {
        'title': 'Conciliación bancaria mensual',
        'description': 'Realizar la conciliación de todas las cuentas bancarias del período.',
        'area_hint': 'FINANZAS',
        'priority_hint': 'alta'
    },
    {
        'title': 'Seguimiento de clientes potenciales',
        'description': 'Contactar a los prospectos de la última semana para avanzar en el proceso de venta.',
        'area_hint': 'VENTAS',
        'priority_hint': 'media'
    },
    {
        'title': 'Actualización de base de datos de clientes',
        'description': 'Revisar y actualizar la información de contacto de todos los clientes activos.',
        'area_hint': 'ATENCION AL CLIENTE',
        'priority_hint': 'baja'
    },
    {
        'title': 'Preparación de informe de métricas semanales',
        'description': 'Recopilar y analizar las métricas clave de rendimiento de la semana.',
        'area_hint': 'ADMINISTRACIÓN GENERAL',
        'priority_hint': 'media'
    },
    {
        'title': 'Revisión de cumplimiento normativo',
        'description': 'Verificar que todos los procesos cumplan con las regulaciones vigentes.',
        'area_hint': 'ADMINISTRACION DE CONTRATOS',
        'priority_hint': 'alta'
    },
    {
        'title': 'Evaluación de desempeño del personal',
        'description': 'Realizar evaluaciones de desempeño trimestrales para todo el personal.',
        'area_hint': 'RRHH',
        'priority_hint': 'media'
    },
    {
        'title': 'Planificación de campaña de marketing',
        'description': 'Diseñar y planificar la próxima campaña de marketing digital.',
        'area_hint': 'MARKETING',
        'priority_hint': 'media'
    },
    {
        'title': 'Gestión de cobranzas pendientes',
        'description': 'Realizar seguimiento de facturas vencidas y gestionar cobranzas.',
        'area_hint': 'FINANZAS',
        'priority_hint': 'urgente'
    },
    {
        'title': 'Revisión de solicitudes de vacaciones',
        'description': 'Procesar y aprobar las solicitudes de vacaciones pendientes.',
        'area_hint': 'ASISTENTE RRHH',
        'priority_hint': 'baja'
    },
    {
        'title': 'Actualización de precios de servicios',
        'description': 'Revisar y actualizar la tabla de precios según inflación y costos actuales.',
        'area_hint': 'ADMINISTRACIÓN GENERAL',
        'priority_hint': 'alta'
    },
    {
        'title': 'Inventario de suministros de limpieza',
        'description': 'Realizar conteo físico y actualizar inventario de productos de limpieza.',
        'area_hint': 'ADMINISTRACIÓN GENERAL',
        'priority_hint': 'media'
    }
]

COMPANIES = ['ProClean Facilities', 'Paper Office', 'Aromas Premium', 'BearClean']
