import requests
import json
from datetime import datetime

TOKEN_URL = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
GRAPH_URL = "https://graph.microsoft.com/v1.0/users/{user}/sendMail"

_token_cache = {}
_token_expiry = {}

def get_access_token(tenant_id, client_id, client_secret):
    cache_key = f"{tenant_id}:{client_id}"
    if cache_key in _token_cache and _token_expiry.get(cache_key, 0) > datetime.now().timestamp():
        return _token_cache[cache_key]

    url = TOKEN_URL.format(tenant=tenant_id)
    data = {
        'client_id': client_id,
        'client_secret': client_secret,
        'scope': 'https://graph.microsoft.com/.default',
        'grant_type': 'client_credentials'
    }
    try:
        resp = requests.post(url, data=data, timeout=15)
        resp.raise_for_status()
        result = resp.json()
        token = result['access_token']
        expires_in = result.get('expires_in', 3600)
        _token_cache[cache_key] = token
        _token_expiry[cache_key] = datetime.now().timestamp() + expires_in - 60
        return token
    except Exception as e:
        print(f"[GRAPH] Error obteniendo token: {e}")
        return None

def send_email_via_graph(to_email, subject, html_content, from_email=None, config=None):
    if config is None:
        from database import get_db
        conn = get_db()
        settings = conn.execute('SELECT key, value FROM settings').fetchall()
        conn.close()
        config = {s['key']: s['value'] for s in settings}

    tenant_id = config.get('graph_tenant_id', '')
    client_id = config.get('graph_client_id', '')
    client_secret = config.get('graph_client_secret', '')
    user_email = config.get('graph_user_email', from_email or 'notificaciones@hiramchile.cl')

    if not all([tenant_id, client_id, client_secret]):
        print("[GRAPH] Configuración incompleta")
        return False

    token = get_access_token(tenant_id, client_id, client_secret)
    if not token:
        return False

    url = GRAPH_URL.format(user=user_email)
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json'
    }

    email_data = {
        'message': {
            'subject': subject,
            'body': {
                'contentType': 'HTML',
                'content': html_content
            },
            'toRecipients': [
                {
                    'emailAddress': {
                        'address': to_email
                    }
                }
            ]
        },
        'saveToSentItems': False
    }

    try:
        resp = requests.post(url, headers=headers, json=email_data, timeout=15)
        resp.raise_for_status()
        print(f"[GRAPH] Email enviado a {to_email} vía Microsoft Graph API")
        return True
    except Exception as e:
        print(f"[GRAPH] Error enviando email a {to_email}: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"[GRAPH] Detalle: {e.response.text}")
        return False

def send_test_email(to_email, config=None):
    if config is None:
        from database import get_db
        conn = get_db()
        settings = conn.execute('SELECT key, value FROM settings').fetchall()
        conn.close()
        config = {s['key']: s['value'] for s in settings}

    html = '''
    <!DOCTYPE html>
    <html><head><meta charset="utf-8"></head>
    <body style="font-family:Arial;padding:20px;">
        <div style="max-width:600px;margin:auto;background:white;border-radius:8px;padding:30px;box-shadow:0 2px 10px rgba(0,0,0,0.1);">
            <div style="background:linear-gradient(135deg,#1a237e,#283593);padding:20px;border-radius:8px 8px 0 0;text-align:center;margin:-30px -30px 20px;">
                <h1 style="color:white;margin:0;font-size:20px;">Hiram Chile – ProClean Facilities</h1>
            </div>
            <h2 style="color:#333;">✅ Prueba Microsoft Graph API</h2>
            <p style="color:#666;">Si estás leyendo este correo, la integración con Microsoft Graph API funciona correctamente.</p>
            <p style="color:#666;">El sistema ahora puede enviar correos desde Office 365 sin SMTP.</p>
            <hr style="border:none;border-top:1px solid #eee;margin:20px 0;">
            <p style="color:#999;font-size:12px;text-align:center;">Sistema de Gestión de Tareas Hiram Chile</p>
        </div>
    </body></html>
    '''
    return send_email_via_graph(to_email, "🔧 Prueba Graph API - Hiram Chile", html, config=config)

def is_graph_configured(config=None):
    if config is None:
        from database import get_db
        conn = get_db()
        settings = conn.execute('SELECT key, value FROM settings').fetchall()
        conn.close()
        config = {s['key']: s['value'] for s in settings}
    return bool(config.get('graph_tenant_id') and config.get('graph_client_id') and config.get('graph_client_secret'))
