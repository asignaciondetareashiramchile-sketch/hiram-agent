import os
import sys
import json
import tempfile
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app import app
from database import init_db, get_db, hash_password

@pytest.fixture
def client():
    app.config['TESTING'] = True
    app.secret_key = 'test-secret'
    db_fd, db_path = tempfile.mkstemp(suffix='.db')
    import database
    database.DB_PATH = db_path
    with app.test_client() as client:
        with app.app_context():
            init_db()
            conn = get_db()
            conn.execute('INSERT INTO users (username, password_hash, role, name) VALUES (?, ?, ?, ?)',
                        ('testadmin', hash_password('test123'), 'superadmin', 'Test Admin'))
            conn.execute('INSERT INTO users (username, password_hash, role, name, area_id) VALUES (?, ?, ?, ?, ?)',
                        ('testarea', hash_password('test123'), 'area', 'Test Area', 1))
            conn.commit()
            conn.close()
        yield client
    os.close(db_fd)
    os.unlink(db_path)

def login(client, username='testadmin', password='test123'):
    return client.post('/api/auth/login', json={'username': username, 'password': password})

class TestAuth:
    def test_login_success(self, client):
        resp = login(client)
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data['username'] == 'testadmin'
        assert data['role'] == 'superadmin'

    def test_login_fail(self, client):
        resp = client.post('/api/auth/login', json={'username': 'bad', 'password': 'bad'})
        assert resp.status_code == 401

    def test_me_unauthorized(self, client):
        resp = client.get('/api/auth/me')
        assert resp.status_code == 401

    def test_me_authorized(self, client):
        login(client)
        resp = client.get('/api/auth/me')
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data['username'] == 'testadmin'

class TestAreas:
    def test_get_areas(self, client):
        login(client)
        resp = client.get('/api/areas')
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert len(data) >= 8

class TestCompanies:
    def test_get_companies(self, client):
        login(client)
        resp = client.get('/api/companies')
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert len(data) >= 4

class TestTasks:
    def test_create_task(self, client):
        login(client)
        resp = client.post('/api/tasks', json={
            'area_id': 1, 'company_id': 1,
            'title': 'Test task', 'description': 'Test desc',
            'priority': 'alta'
        })
        assert resp.status_code == 201
        data = json.loads(resp.data)
        assert data['title'] == 'Test task'
        assert data['status'] == 'pendiente'

    def test_get_tasks(self, client):
        login(client)
        client.post('/api/tasks', json={
            'area_id': 1, 'company_id': 1,
            'title': 'Test task', 'priority': 'media'
        })
        resp = client.get('/api/tasks')
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert len(data) >= 1

    def test_update_status(self, client):
        login(client)
        client.post('/api/tasks', json={
            'area_id': 1, 'company_id': 1,
            'title': 'Status test', 'priority': 'media'
        })
        resp = client.get('/api/tasks/1/status/gestionando')
        assert resp.status_code == 200

    def test_delete_task(self, client):
        login(client)
        client.post('/api/tasks', json={
            'area_id': 1, 'company_id': 1,
            'title': 'Delete me', 'priority': 'baja'
        })
        resp = client.delete('/api/tasks/1')
        assert resp.status_code == 200

class TestStats:
    def test_stats(self, client):
        login(client)
        client.post('/api/tasks', json={
            'area_id': 1, 'company_id': 1,
            'title': 'Stats test', 'priority': 'urgente'
        })
        resp = client.get('/api/tasks/stats')
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert 'total' in data
        assert 'by_area' in data

class TestTemplates:
    def test_get_templates(self, client):
        login(client)
        resp = client.get('/api/templates')
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert len(data) >= 1

    def test_apply_template(self, client):
        login(client)
        resp = client.post('/api/templates/1/apply', json={'company_id': 1})
        assert resp.status_code == 201
        data = json.loads(resp.data)
        assert 'task_id' in data

class TestMarketing:
    def test_get_suggestions(self, client):
        login(client)
        resp = client.get('/api/marketing/suggestions?status=pendiente')
        assert resp.status_code == 200

class TestActivity:
    def test_activity(self, client):
        login(client)
        resp = client.get('/api/activity?limit=10')
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert isinstance(data, list)

class TestNotifications:
    def test_notifications(self, client):
        login(client)
        resp = client.get('/api/notifications')
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert isinstance(data, list)

    def test_unread_count(self, client):
        login(client)
        resp = client.get('/api/notifications/unread-count')
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert 'count' in data

class TestSettings:
    def test_get_settings(self, client):
        resp = client.get('/api/settings')
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert 'smtp_server' in data

    def test_update_settings(self, client):
        login(client)
        resp = client.put('/api/settings', json={'smtp_server': 'test.smtp.com'})
        assert resp.status_code == 200
        resp2 = client.get('/api/settings')
        data = json.loads(resp2.data)
        assert data['smtp_server'] == 'test.smtp.com'

class TestMetrics:
    def test_metrics(self, client):
        login(client)
        resp = client.get('/api/metrics')
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert 'avg_resolution_time' in data
        assert 'priority_stats' in data

class TestAgent:
    def test_agent_status(self, client):
        resp = client.get('/api/agent/status')
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert isinstance(data, list)

class TestFollowups:
    def test_get_followups(self, client):
        login(client)
        resp = client.get('/api/followups')
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert isinstance(data, list)

class TestAreaAccess:
    def test_area_user_sees_only_own_area(self, client):
        login(client, 'testarea', 'test123')
        resp = client.get('/api/areas')
        data = json.loads(resp.data)
        assert len(data) == 1
        assert data[0]['id'] == 1

    def test_area_user_cannot_access_settings(self, client):
        login(client, 'testarea', 'test123')
        resp = client.get('/settings')
        assert resp.status_code == 403
