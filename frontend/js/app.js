const API_BASE = '/api';

const PRIORITIES = {
    urgente: { label: 'URGENTE - 3 Horas', color: '#7B2D8E', icon: '🔮' },
    alta: { label: 'Alta - Hoy', color: '#DC3545', icon: '🔴' },
    media: { label: 'Media - 3 Días', color: '#FFC107', icon: '🟡' },
    baja: { label: 'Baja - 5 Días', color: '#28A745', icon: '🟢' }
};

const AREA_ICONS = {
    'RRHH': '👥', 'ASISTENTE RRHH': '🤝', 'FINANZAS': '💰', 'VENTAS': '📈',
    'ADMINISTRACION DE CONTRATOS': '📋', 'ADMINISTRACIÓN GENERAL': '🏢',
    'MARKETING': '📢', 'ATENCION AL CLIENTE': '🎧'
};

const COMPANY_COLORS = {
    'ProClean Facilities': '#1a73e8', 'Paper Office': '#ea4335',
    'Aromas Premium': '#34a853', 'BearClean': '#fbbc04'
};

let areas = [], companies = [], currentView = 'dashboard', currentAreaId = null, selectedCompanyId = null;
let kanbanMode = false, notifTimer = null;

async function fetchAPI(url, options = {}) {
    try {
        const res = await fetch(`${API_BASE}${url}`, {
            headers: { 'Content-Type': 'application/json', ...options.headers },
            ...options
        });
        if (res.status === 401) { window.location.href = '/login'; return null; }
        return await res.json();
    } catch (e) { console.error('API Error:', e); return null; }
}

function showNotification(message, type = 'success') {
    const container = document.getElementById('notification-container');
    const colors = { success: '#28A745', error: '#DC3545', info: '#1a73e8', warning: '#FFC107' };
    const div = document.createElement('div');
    div.className = `notification ${type}`;
    div.style.cssText = `background:${colors[type]||'#333'};color:white;padding:12px 20px;border-radius:8px;margin-bottom:8px;box-shadow:0 2px 10px rgba(0,0,0,0.2);animation:slideIn 0.3s ease;`;
    div.textContent = message;
    container.appendChild(div);
    setTimeout(() => { div.style.animation = 'slideOut 0.3s ease'; setTimeout(() => div.remove(), 300); }, 3000);
}

// ===== DARK MODE =====
function toggleDarkMode() {
    document.body.classList.toggle('dark-mode');
    localStorage.setItem('darkMode', document.body.classList.contains('dark-mode'));
}
if (localStorage.getItem('darkMode') === 'true') document.body.classList.add('dark-mode');

// ===== AUTH =====
async function loadUser() {
    const user = await fetchAPI('/auth/me');
    if (!user) return;
    document.getElementById('user-name').textContent = user.name || user.username;
    document.getElementById('header-user').textContent = `👤 ${user.name || user.username} · ${user.role === 'superadmin' ? 'Admin' : user.role === 'admin' ? 'Admin' : 'Área'}`;
    // Hide admin-only elements for area users
    if (user.role === 'area') {
        document.querySelectorAll('.admin-only').forEach(el => el.style.display = 'none');
    }
}

// ===== NOTIFICATIONS =====
async function loadNotifications() {
    const notifs = await fetchAPI('/notifications?limit=20');
    const container = document.getElementById('notifications-list');
    if (!notifs || notifs.length === 0) {
        container.innerHTML = '<div style="text-align:center;padding:20px;color:#999;">Sin notificaciones</div>';
        return;
    }
    container.innerHTML = '';
    notifs.forEach(n => {
        const icons = { task_created: '📝', status_change: '🔄', info: '💡', warning: '⚠️' };
        const div = document.createElement('div');
        div.className = `notif-item ${n.is_read ? '' : 'unread'}`;
        div.innerHTML = `<span>${icons[n.notification_type] || '💡'}</span>
            <div style="flex:1;min-width:0;"><div style="font-weight:${n.is_read?'400':'600'};font-size:13px;">${n.title}</div>
            <div style="font-size:11px;color:#999;">${n.created_at || ''}</div></div>
            ${!n.is_read ? `<button onclick="markNotifRead(${n.id})" style="background:none;border:none;color:#1a73e8;cursor:pointer;font-size:11px;">✓</button>` : ''}`;
        if (n.link) div.style.cursor = 'pointer';
        div.onclick = () => { if (n.link) window.location.href = n.link; };
        container.appendChild(div);
    });
}

async function loadNotifCount() {
    const data = await fetchAPI('/notifications/unread-count');
    if (!data) return;
    const badge = document.getElementById('notif-badge');
    if (data.count > 0) { badge.style.display = 'inline'; badge.textContent = data.count; }
    else badge.style.display = 'none';
}

function toggleNotifications() {
    const p = document.getElementById('notifications-panel');
    p.style.display = p.style.display === 'none' ? 'block' : 'none';
    if (p.style.display === 'block') loadNotifications();
}

async function markNotifRead(id) {
    await fetchAPI(`/notifications/${id}/read`, { method: 'PUT' });
    loadNotifications();
    loadNotifCount();
}

async function markAllRead() {
    await fetchAPI('/notifications/read-all', { method: 'PUT' });
    loadNotifications();
    loadNotifCount();
}

// ===== INIT =====
async function loadInitialData() {
    areas = await fetchAPI('/areas') || [];
    companies = await fetchAPI('/companies') || [];
    renderAreas();
    renderCompanySelector();
    loadDashboard();
    loadUser();
    loadNotifications();
    loadNotifCount();
    loadTemplates();
    setInterval(loadNotifCount, 15000);
    connectDashboardSocket();
}

// ===== SOCKET.IO DASHBOARD EN TIEMPO REAL =====
let dashboardSocket = null;

function connectDashboardSocket() {
    if (dashboardSocket) return;
    dashboardSocket = io({ transports: ['websocket', 'polling'] });
    dashboardSocket.on('connect', () => {
        dashboardSocket.emit('join_dashboard');
    });
    dashboardSocket.on('task_created', (data) => {
        showNotification('📝 Nueva tarea creada', 'info');
        loadDashboard();
    });
    dashboardSocket.on('task_status_changed', (data) => {
        if (currentAreaId && data.area_id == currentAreaId) {
            loadAreaTasks(currentAreaId);
        }
        loadDashboard();
    });
    dashboardSocket.on('task_deleted', () => {
        showNotification('🗑 Tarea eliminada', 'info');
        loadDashboard();
    });
    dashboardSocket.on('stats_update', () => {
        loadDashboard();
    });
    dashboardSocket.on('notification', (data) => {
        loadNotifCount();
    });
}

// ===== AREAS =====
function renderAreas() {
    const container = document.getElementById('areas-grid');
    container.innerHTML = '';
    areas.forEach(area => {
        const icon = AREA_ICONS[area.name] || '📋';
        const color = area.color || '#1a73e8';
        const card = document.createElement('div');
        card.className = 'area-card';
        card.style.setProperty('--area-color', color);
        card.innerHTML = `
            <div class="area-icon" style="background:${color}15;color:${color};">${icon}</div>
            <div class="area-name">${area.name}</div>
            <div class="area-email">${area.email}</div>
            <div class="area-stats" id="stats-${area.id}">
                <span class="badge pending">0 pend.</span>
                <span class="badge doing">0 gest.</span>
                <span class="badge done">0 done</span>
            </div>
            <div style="display:flex;gap:6px;margin-top:auto;">
                <button class="btn-assign" onclick="event.stopPropagation(); openTaskModal(${area.id}, '${area.name}', '${area.email}')" style="flex:1;background:${color};">
                    + Asignar
                </button>
                <button class="btn-view" onclick="event.stopPropagation(); viewAreaTasks(${area.id}, '${area.name}')" style="flex:1;">
                    📋 Ver Tareas
                </button>
            </div>
        `;
        card.style.cursor = 'pointer';
        card.onclick = () => viewAreaTasks(area.id, area.name);
        container.appendChild(card);
    });
}

function renderCompanySelector() {
    const container = document.getElementById('company-selector');
    if (!container) return;
    const modalSelect = document.getElementById('modal-company');
    modalSelect.innerHTML = '<option value="">Seleccionar empresa...</option>';
    companies.forEach(company => {
        const btn = document.createElement('button');
        btn.className = 'company-btn';
        btn.style.setProperty('--company-color', COMPANY_COLORS[company.name] || '#666');
        btn.dataset.companyId = company.id;
        btn.innerHTML = `<span class="company-dot"></span>${company.name}`;
        btn.onclick = () => selectCompany(company.id, btn);
        container.appendChild(btn);
        const opt = document.createElement('option');
        opt.value = company.id; opt.textContent = company.name;
        modalSelect.appendChild(opt);
    });
    const first = container.querySelector('.company-btn');
    if (first) selectCompany(companies[0]?.id, first);
}

function selectCompany(id, btn) {
    selectedCompanyId = id;
    document.querySelectorAll('.company-btn').forEach(b => b.classList.remove('active'));
    if (btn) btn.classList.add('active');
}

// ===== DASHBOARD =====
async function loadDashboard() {
    const stats = await fetchAPI('/tasks/stats');
    if (!stats) return;
    document.getElementById('total-tasks').textContent = stats.total || 0;
    document.getElementById('pending-tasks').textContent = stats.pendientes || 0;
    document.getElementById('doing-tasks').textContent = stats.gestionando || 0;
    document.getElementById('done-tasks').textContent = stats.realizadas || 0;
    const vencidasEl = document.getElementById('vencidas-tasks');
    if (vencidasEl) vencidasEl.textContent = stats.vencidas || 0;
    if (stats.by_area) {
        stats.by_area.forEach(a => {
            const el = document.getElementById(`stats-${a.id}`);
            if (el) el.innerHTML = `<span class="badge pending">${a.pendientes||0} pend.</span>
                <span class="badge doing">${a.gestionando||0} gest.</span>
                <span class="badge done">${a.realizadas||0} done</span>`;
        });
    }
    loadAgentStatus();
    loadMarketingSuggestions();
    loadActivityFeed();
    loadMetrics();
}

// ===== AGENT STATUS =====
async function loadAgentStatus() {
    const agents = await fetchAPI('/agent/status');
    const container = document.getElementById('agent-status');
    if (!agents || !container) return;
    container.innerHTML = '<div class="section-header"><h3>🤖 Estado de Agentes IA - 24/7</h3></div>';
    const grid = document.createElement('div');
    grid.className = 'agent-grid';
    agents.forEach(a => {
        const card = document.createElement('div');
        card.className = 'agent-card';
        const overdueBadge = a.overdue_tasks > 0 ? `<span style="background:#DC3545;color:white;padding:2px 6px;border-radius:4px;font-size:10px;margin-left:4px;">${a.overdue_tasks} venc.</span>` : '';
        card.innerHTML = `
            <div class="agent-header"><span class="agent-indicator ${a.agent_status === 'activo' ? 'online' : 'offline'}"></span>
                <strong>${a.area_name}</strong>${overdueBadge}</div>
            <div style="font-size:12px;color:#666;display:flex;gap:8px;margin-top:4px;">
                <span>📋 ${a.pending_tasks} pend.</span><span>✅ ${a.completed_today} hoy</span></div>
            <div class="agent-status-text" style="margin-top:4px;">${a.agent_status === 'activo' ? '🟢 Activo 24/7' : '⚪ Inactivo'}</div>`;
        grid.appendChild(card);
    });
    container.appendChild(grid);
}

// ===== TASK MODAL =====
function openTaskModal(areaId, areaName, areaEmail) {
    document.getElementById('modal-area-id').value = areaId;
    document.getElementById('modal-area-name').textContent = `Área: ${areaName}`;
    document.querySelectorAll('.priority-btn').forEach(b => b.classList.remove('selected'));
    document.querySelector('.priority-btn[data-priority="media"]')?.classList.add('selected');
    document.getElementById('task-title').value = '';
    document.getElementById('task-desc').value = '';
    document.getElementById('task-files').value = '';
    if (selectedCompanyId) document.getElementById('modal-company').value = selectedCompanyId;
    document.getElementById('task-modal').style.display = 'flex';
    document.getElementById('task-modal').style.animation = 'fadeIn 0.2s ease';
}

function closeTaskModal() { document.getElementById('task-modal').style.display = 'none'; }

function selectPriority(element, priority) {
    document.querySelectorAll('.priority-btn').forEach(b => b.classList.remove('selected'));
    element.classList.add('selected');
}

async function submitTask() {
    const areaId = document.getElementById('modal-area-id').value;
    const companyId = parseInt(document.getElementById('modal-company').value) || selectedCompanyId;
    const title = document.getElementById('task-title').value.trim();
    const description = document.getElementById('task-desc').value.trim();
    const selectedPriority = document.querySelector('.priority-btn.selected');
    const priority = selectedPriority ? selectedPriority.dataset.priority : 'media';
    const files = document.getElementById('task-files').files;

    if (!areaId || !title) { showNotification('Debes completar el título de la tarea', 'error'); return; }
    if (!companyId) { showNotification('Debes seleccionar una empresa', 'error'); return; }

    const result = await fetchAPI('/tasks', {
        method: 'POST',
        body: JSON.stringify({ area_id: parseInt(areaId), company_id: companyId, title, description, priority })
    });

    if (result) {
        // Upload files if any
        if (files.length > 0 && result.id) {
            for (let file of files) {
                const fd = new FormData();
                fd.append('file', file);
                await fetch(`${API_BASE}/tasks/${result.id}/attachments`, { method: 'POST', body: fd });
            }
        }
        showNotification(`✅ Tarea asignada a ${areas.find(a => a.id == areaId)?.name || ''}`, 'success');
        closeTaskModal();
        loadDashboard();
        if (currentView === 'area-tasks') loadAreaTasks(currentAreaId);
    } else showNotification('Error al crear la tarea', 'error');
}

// ===== AREA TASKS =====
function viewAreaTasks(areaId, areaName) {
    currentAreaId = areaId;
    currentView = 'area-tasks';
    document.getElementById('dashboard-view').style.display = 'none';
    document.getElementById('area-tasks-view').style.display = 'block';
    document.getElementById('view-title').textContent = `Tareas de ${areaName}`;
    loadAreaTasks(areaId);
}

function showDashboard() {
    currentView = 'dashboard';
    document.getElementById('dashboard-view').style.display = 'block';
    document.getElementById('area-tasks-view').style.display = 'none';
    kanbanMode = false;
    document.getElementById('kanban-view').style.display = 'none';
    document.getElementById('area-tasks-list').style.display = 'block';
    loadDashboard();
}

function toggleKanban() {
    kanbanMode = !kanbanMode;
    document.getElementById('kanban-view').style.display = kanbanMode ? 'grid' : 'none';
    document.getElementById('area-tasks-list').style.display = kanbanMode ? 'none' : 'block';
    if (kanbanMode && currentAreaId) loadKanban(currentAreaId);
}

async function loadAreaTasks(areaId) {
    const statusFilter = document.getElementById('status-filter')?.value || '';
    let url = `/tasks?area_id=${areaId}`;
    if (statusFilter) url += `&status=${statusFilter}`;
    const tasks = await fetchAPI(url);
    const container = document.getElementById('area-tasks-list');
    container.innerHTML = '';
    if (!tasks || tasks.length === 0) {
        container.innerHTML = '<div class="empty-state">No hay tareas asignadas a esta área</div>';
        return;
    }
    tasks.forEach(task => { container.appendChild(createTaskCard(task)); });
}

function createTaskCard(task, compact = false) {
    const priority = PRIORITIES[task.priority] || { label: 'N/A', color: '#666', icon: '⚪' };
    const companyColor = COMPANY_COLORS[task.company_name] || '#666';
    const statusLabels = { pendiente: '⏳ Pendiente', gestionando: '🔄 Gestionando', realizada: '✅ Realizada', cancelada: '❌ Cancelada' };
    const statusColors = { pendiente: '#FFC107', gestionando: '#1a73e8', realizada: '#28A745', cancelada: '#DC3545' };

    const card = document.createElement('div');
    card.className = 'task-card';
    card.draggable = kanbanMode;
    card.dataset.taskId = task.id;
    card.dataset.status = task.status;

    if (compact) {
        card.innerHTML = `<div class="task-priority" style="background:${priority.color};width:4px;"></div>
            <div class="task-content"><div class="task-title" style="font-size:13px;">${task.title}</div>
            <div class="task-meta" style="font-size:10px;"><span style="color:${priority.color}">${priority.icon} ${priority.label}</span>
            ${task.due_date ? `<span>📅 ${task.due_date}</span>` : ''}</div></div>`;
        return card;
    }

    card.innerHTML = `
        <div class="task-priority" style="background:${priority.color}"></div>
        <div class="task-content">
            <div class="task-header">
                <span class="task-company" style="color:${companyColor};border-color:${companyColor}">${task.company_name}</span>
                <span class="task-status" style="color:${statusColors[task.status]||'#666'}">${statusLabels[task.status]||task.status}</span>
            </div>
            <div class="task-title">${task.title}</div>
            ${task.description ? `<div class="task-desc">${task.description}</div>` : ''}
            <div class="task-meta">
                <span style="color:${priority.color}">${priority.icon} ${priority.label}</span>
                <span>📅 Límite: ${task.due_date || 'N/A'}</span>
                <span>🕐 ${task.created_at || ''}</span>
            </div>
            <div class="task-actions">
                <button class="btn-sm btn-doing" onclick="updateTaskStatus(${task.id}, 'gestionando')">🔄 Gestionando</button>
                <button class="btn-sm btn-done" onclick="updateTaskStatus(${task.id}, 'realizada')">✅ Realizado</button>
                <button class="btn-sm btn-remind" onclick="sendReminder(${task.id})">📧 Recordatorio</button>
                <button class="btn-sm" style="background:#e3f2fd;color:#004085;" onclick="openChat(${task.id}, '${task.title.replace(/'/g, "\\'")}')">💬 Chat</button>
                ${task.id ? `<button class="btn-sm" style="background:#f0f0f0;" onclick="showAttachments(${task.id})">📎 Archivos</button>` : ''}
                ${task.status === 'realizada' && !task.approved_at ? `<button class="btn-sm" style="background:#D4EDDA;color:#155724;" onclick="approveTask(${task.id})">✍️ Aprobar</button>` : ''}
                ${task.status === 'realizada' && task.approved_at ? `<span style="font-size:11px;color:#28A745;font-weight:600;">✅ Aprobada</span>` : ''}
            </div>
        </div>`;
    return card;
}

// ===== KANBAN =====
async function loadKanban(areaId) {
    const tasks = await fetchAPI(`/tasks?area_id=${areaId}`);
    if (!tasks) return;
    const columns = { pendiente: [], gestionando: [], realizada: [], cancelada: [] };
    tasks.forEach(t => { if (columns[t.status]) columns[t.status].push(t); });
    Object.keys(columns).forEach(status => {
        const container = document.getElementById(`kanban-${status}`);
        container.innerHTML = '';
        columns[status].forEach(t => container.appendChild(createTaskCard(t, true)));
    });
}

async function updateTaskStatus(taskId, status) {
    const res = await fetch(`${API_BASE}/tasks/${taskId}/status/${status}`);
    if (res.ok) {
        showNotification(`Estado actualizado`, 'success');
        if (currentAreaId) { loadAreaTasks(currentAreaId); if (kanbanMode) loadKanban(currentAreaId); }
        loadDashboard();
    }
}

async function sendReminder(taskId) {
    const result = await fetchAPI(`/send-reminder/${taskId}`, { method: 'GET' });
    if (result) showNotification('📧 Recordatorio enviado al área', 'info');
}

function filterTasks() { if (currentAreaId) loadAreaTasks(currentAreaId); }

// ===== TEMPLATES =====
async function loadTemplates() {
    const container = document.getElementById('templates-grid');
    if (!container) return;
    const templates = await fetchAPI('/templates');
    if (!templates || templates.length === 0) {
        container.innerHTML = '<div style="text-align:center;padding:20px;color:#999;">📋 No hay plantillas disponibles. Crea una para agilizar la asignación de tareas recurrentes.</div>';
        return;
    }
    container.innerHTML = '';
    const priorityColors = { urgente: '#7B2D8E', alta: '#DC3545', media: '#FFC107', baja: '#28A745' };
    templates.forEach(t => {
        const card = document.createElement('div');
        card.style.cssText = 'background:#f8f9fa;border-radius:8px;padding:14px;border:1px solid #e0e0e0;';
        card.innerHTML = `
            <div style="display:flex;justify-content:space-between;align-items:start;margin-bottom:6px;">
                <span style="font-weight:600;font-size:14px;">${t.title}</span>
                <span style="background:${priorityColors[t.priority]||'#666'};color:white;padding:2px 8px;border-radius:4px;font-size:10px;">${t.priority}</span>
            </div>
            <div style="font-size:12px;color:#666;margin-bottom:4px;">${t.description || ''}</div>
            <div style="font-size:11px;color:#999;margin-bottom:8px;">🏢 ${t.area_name || ''} ${t.is_recurring ? '· 🔄 Cada '+t.recurring_days+' días' : ''}</div>
            <div style="display:flex;gap:6px;">
                <button onclick="applyTemplate(${t.id})" style="flex:1;background:#1a73e8;color:white;border:none;padding:6px;border-radius:4px;font-size:11px;cursor:pointer;">📋 Aplicar</button>
                <button onclick="deleteTemplate(${t.id})" style="background:#DC3545;color:white;border:none;padding:6px 10px;border-radius:4px;font-size:11px;cursor:pointer;">🗑</button>
            </div>`;
        container.appendChild(card);
    });
}

async function applyTemplate(tid) {
    const companyId = selectedCompanyId || 1;
    const result = await fetchAPI(`/templates/${tid}/apply`, {
        method: 'POST', body: JSON.stringify({ company_id: companyId })
    });
    if (result) {
        showNotification('✅ Tarea creada desde plantilla', 'success');
        loadDashboard();
    }
}

async function deleteTemplate(tid) {
    if (!confirm('¿Eliminar plantilla?')) return;
    await fetchAPI(`/templates/${tid}`, { method: 'DELETE' });
    loadTemplates();
}

function showTemplateModal() {
    const sel = document.getElementById('tmpl-area');
    sel.innerHTML = '';
    areas.forEach(a => { const o = document.createElement('option'); o.value = a.id; o.textContent = a.name; sel.appendChild(o); });
    document.getElementById('tmpl-title').value = '';
    document.getElementById('tmpl-desc').value = '';
    document.getElementById('tmpl-priority').value = 'media';
    document.getElementById('tmpl-recurring').checked = false;
    document.getElementById('tmpl-days-group').style.display = 'none';
    document.getElementById('template-modal').style.display = 'flex';
}

function closeTemplateModal() { document.getElementById('template-modal').style.display = 'none'; }

document.getElementById('tmpl-recurring')?.addEventListener('change', function() {
    document.getElementById('tmpl-days-group').style.display = this.checked ? 'block' : 'none';
});

async function saveTemplate() {
    const data = {
        area_id: parseInt(document.getElementById('tmpl-area').value),
        title: document.getElementById('tmpl-title').value.trim(),
        description: document.getElementById('tmpl-desc').value.trim(),
        priority: document.getElementById('tmpl-priority').value,
        is_recurring: document.getElementById('tmpl-recurring').checked ? 1 : 0,
        recurring_days: parseInt(document.getElementById('tmpl-days').value) || 30
    };
    if (!data.title) { showNotification('Debes ingresar un título', 'error'); return; }
    const result = await fetchAPI('/templates', { method: 'POST', body: JSON.stringify(data) });
    if (result) { showNotification('✅ Plantilla creada', 'success'); closeTemplateModal(); loadTemplates(); }
}

// ===== ATTACHMENTS =====
async function showAttachments(taskId) {
    const atts = await fetchAPI(`/tasks/${taskId}/attachments`);
    if (!atts || atts.length === 0) {
        showNotification('Esta tarea no tiene archivos adjuntos', 'info');
        return;
    }
    let html = '<div style="font-size:13px;font-weight:600;margin-bottom:8px;">📎 Archivos adjuntos:</div>';
    atts.forEach(a => {
        const size = a.file_size > 1024 ? Math.round(a.file_size/1024) + 'KB' : a.file_size + 'B';
        html += `<div style="display:flex;align-items:center;gap:8px;padding:4px 0;">
            <a href="/api/uploads/${a.filename}" target="_blank" style="color:#1a73e8;font-size:12px;">${a.original_name}</a>
            <span style="font-size:10px;color:#999;">(${size})</span>
        </div>`;
    });
    const div = document.createElement('div');
    div.style.cssText = 'position:fixed;top:50%;left:50%;transform:translate(-50%,-50%);background:white;padding:24px;border-radius:12px;box-shadow:0 10px 40px rgba(0,0,0,0.2);z-index:1000;max-width:400px;width:90%;';
    div.innerHTML = html + '<button onclick="this.parentElement.remove()" style="margin-top:12px;padding:6px 16px;border:1px solid #ddd;border-radius:4px;cursor:pointer;">Cerrar</button>';
    document.body.appendChild(div);
    div.onclick = (e) => { if (e.target === div) div.remove(); };
}

// ===== MARKETING =====
async function loadMarketingSuggestions() {
    const container = document.getElementById('marketing-grid');
    if (!container) return;
    const suggestions = await fetchAPI('/marketing/suggestions?status=pendiente');
    if (!suggestions || suggestions.length === 0) {
        container.innerHTML = '<div style="text-align:center;padding:30px;color:#999;">✨ El agente de marketing generará sugerencias pronto. Programa: cada 4 horas. Haz clic en "Generar Ahora" para obtener ideas al instante.</div>';
        return;
    }
    container.innerHTML = '';
    suggestions.forEach(s => {
        const typeIcons = { social_post: '📱', ad_copy: '📢', email_campaign: '📧', blog_idea: '📝', design_concept: '🎨', video_script: '🎬', market_analysis: '📊', promotion: '🏷️' };
        const icon = typeIcons[s.suggestion_type] || '💡';
        const cardId = `mkt-${s.id}`;
        const isLong = s.content && s.content.length > 200;
        const card = document.createElement('div');
        card.style.cssText = 'background:#f8f9fa;border-radius:8px;padding:14px;border:1px solid #e0e0e0;transition:all 0.2s;';
        card.innerHTML = `
            <div style="display:flex;justify-content:space-between;align-items:start;margin-bottom:8px;">
                <span style="font-size:13px;font-weight:600;color:#1a73e8;">${icon} ${(s.suggestion_type||'').replace('_',' ').toUpperCase()}</span>
                <span style="font-size:11px;color:#666;background:#e3f2fd;padding:2px 8px;border-radius:4px;">${s.platform || 'General'}</span>
            </div>
            <div style="font-weight:600;font-size:14px;margin-bottom:4px;">${s.title}</div>
            <div style="font-size:12px;color:#666;margin-bottom:8px;">${s.description || ''}</div>
            <div id="${cardId}" style="background:white;border-radius:4px;padding:10px;font-size:12px;color:#333;margin-bottom:8px;border:1px solid #eee;${isLong ? 'max-height:80px;overflow:hidden;cursor:pointer;' : ''}white-space:pre-wrap;font-family:monospace;">
                ${s.content || ''}${isLong ? '<div style="text-align:center;padding:4px;color:#1a73e8;font-size:11px;">▼ Ver texto completo ▼</div>' : ''}
            </div>
            <div style="display:flex;gap:6px;">
                <a href="/api/marketing/approve/${s.id}" style="background:#28A745;color:white;text-decoration:none;padding:5px 12px;border-radius:4px;font-size:11px;font-weight:600;">✅ Aprobar</a>
                <a href="/api/marketing/reject/${s.id}" style="background:#DC3545;color:white;text-decoration:none;padding:5px 12px;border-radius:4px;font-size:11px;font-weight:600;">❌ Rechazar</a>
            </div>`;
        container.appendChild(card);
        if (isLong) {
            const contentDiv = document.getElementById(cardId);
            let expanded = false;
            contentDiv.onclick = () => {
                expanded = !expanded;
                contentDiv.style.maxHeight = expanded ? 'none' : '80px';
                const toggle = contentDiv.querySelector('div:last-child');
                if (toggle) toggle.textContent = expanded ? '▲ Ver menos ▲' : '▼ Ver texto completo ▼';
            };
        }
    });
}

async function generateMarketingSuggestions() {
    const btn = document.querySelector('#marketing-section .btn-assign');
    btn.disabled = true; btn.textContent = '⏳ Generando...';
    const result = await fetchAPI('/marketing/generate', { method: 'POST' });
    if (result) { showNotification(`🎨 ${result.count} sugerencias de marketing generadas`, 'success'); loadMarketingSuggestions(); }
    btn.disabled = false; btn.textContent = '🔄 Generar Ahora';
}

// ===== ACTIVITY =====
async function loadActivityFeed() {
    const container = document.getElementById('activity-feed');
    if (!container) return;
    const activity = await fetchAPI('/activity?limit=50');
    if (!activity || activity.length === 0) { container.innerHTML = '<div style="text-align:center;padding:20px;color:#999;">Aún no hay actividad registrada</div>'; return; }
    container.innerHTML = '';
    const typeConfig = {
        task_created: { icon: '📝', label: 'Creada', color: '#1a73e8' },
        status_change: { icon: '🔄', label: 'Cambio', color: '#FFC107' },
        marketing: { icon: '🎨', label: 'Marketing', color: '#34a853' },
        followup: { icon: '📧', label: 'Seguimiento', color: '#7B2D8E' }
    };
    activity.forEach(item => {
        const cfg = typeConfig[item.type] || { icon: '📌', label: 'Evento', color: '#666' };
        let actorText = '';
        if (item.type === 'status_change') {
            const m = {'Cambió de pendiente a gestionando': '→ Gest.','Cambió de gestionando a realizada': '→ Done','Cambió de gestionando a gestionando': '→ Gest.','Cambió de pendiente a realizada': '→ Done','Cambió de gestionando a cancelada': '→ Canc.','Cambió de pendiente a cancelada': '→ Canc.'};
            actorText = m[item.actor] || item.actor;
        } else if (item.type === 'marketing') actorText = item.actor === 'pendiente' ? '🆕 Nueva' : item.actor === 'aprobada' ? '✅ Aprobada' : item.actor === 'rechazada' ? '❌ Rechazada' : item.actor;
        else if (item.type === 'followup') actorText = item.actor === 'recordatorio' ? '📧 Recordatorio' : item.actor === 'overdue_alert' ? '⚠️ Vencimiento' : item.actor === 'auto_suggestion' ? '🤖 Sugerencia' : item.actor;
        else if (item.type === 'task_created') actorText = `Por: ${item.actor || 'usuario'}`;

        const time = item.created_at ? new Date(item.created_at + 'Z').toLocaleString('es-CL', { day:'2-digit', month:'2-digit', hour:'2-digit', minute:'2-digit' }) : '';
        const row = document.createElement('div');
        row.style.cssText = 'display:flex;align-items:center;gap:10px;padding:8px 16px;border-bottom:1px solid #eee;font-size:13px;';
        row.innerHTML = `<span style="font-size:16px;">${cfg.icon}</span>
            <div style="flex:1;min-width:0;">
                <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap;">
                    <span style="font-weight:600;color:#333;white-space:nowrap;">${item.title||''}</span>
                    <span style="font-size:11px;color:${cfg.color};background:${cfg.color}15;padding:1px 6px;border-radius:3px;font-weight:500;">${cfg.label}</span></div>
                <div style="display:flex;gap:8px;font-size:11px;color:#666;margin-top:2px;">
                    ${item.area_name ? `<span>🏢 ${item.area_name}</span>` : ''}
                    ${item.company_name ? `<span>🏷️ ${item.company_name}</span>` : ''}
                    ${actorText ? `<span>${actorText}</span>` : ''}</div></div>
            <span style="font-size:10px;color:#999;white-space:nowrap;">${time}</span>`;
        container.appendChild(row);
    });
}

// ===== METRICS =====
async function loadMetrics() {
    const metrics = await fetchAPI('/metrics');
    if (!metrics) return;
    // Avg resolution time
    const avgContainer = document.getElementById('avg-time-chart');
    if (avgContainer && metrics.avg_resolution_time) {
        avgContainer.innerHTML = '';
        const max = Math.max(...metrics.avg_resolution_time.map(m => m.avg_hours || 0), 1);
        metrics.avg_resolution_time.forEach(m => {
            const pct = Math.min((m.avg_hours || 0) / max * 100, 100);
            const color = m.area_color || '#1a73e8';
            avgContainer.innerHTML += `
                <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;font-size:12px;">
                    <span style="width:160px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${m.name}</span>
                    <div style="flex:1;height:20px;background:#e0e0e0;border-radius:4px;overflow:hidden;">
                        <div style="height:100%;width:${pct}%;background:${color};border-radius:4px;display:flex;align-items:center;justify-content:flex-end;padding-right:4px;box-sizing:border-box;">
                            <span style="color:white;font-size:9px;font-weight:600;">${Math.round(m.avg_hours || 0)}h</span>
                        </div>
                    </div>
                    <span style="color:#999;font-size:10px;min-width:30px;text-align:right;">${m.total_completed || 0}</span>
                </div>`;
        });
    }
    // Priority chart
    const priContainer = document.getElementById('priority-chart');
    if (priContainer && metrics.priority_stats) {
        priContainer.innerHTML = '';
        const colors = { urgente: '#7B2D8E', alta: '#DC3545', media: '#FFC107', baja: '#28A745' };
        const labels = { urgente: 'Urgente', alta: 'Alta', media: 'Media', baja: 'Baja' };
        const total = metrics.priority_stats.reduce((s, p) => s + p.count, 0) || 1;
        metrics.priority_stats.forEach(p => {
            const pct = (p.count / total * 100);
            priContainer.innerHTML += `
                <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;font-size:12px;">
                    <span style="width:60px;">${labels[p.priority] || p.priority}</span>
                    <div style="flex:1;height:20px;background:#e0e0e0;border-radius:4px;overflow:hidden;">
                        <div style="height:100%;width:${pct}%;background:${colors[p.priority]||'#666'};border-radius:4px;display:flex;align-items:center;justify-content:center;">
                            <span style="color:white;font-size:9px;font-weight:600;">${p.count}</span>
                        </div>
                    </div>
                </div>`;
        });
    }
}

// ===== DOCUMENT READY =====
// ===== CHAT INTERNO =====
let chatSocket = null;
let chatTaskId = null;

function openChat(taskId, taskTitle) {
    chatTaskId = taskId;
    document.getElementById('chat-title').textContent = `💬 ${taskTitle}`;
    document.getElementById('chat-modal').style.display = 'flex';
    document.getElementById('chat-messages').innerHTML = '<div style="text-align:center;padding:20px;color:#999;">Cargando mensajes...</div>';
    loadChatMessages(taskId);
    connectChatSocket(taskId);
}

function closeChatModal() {
    document.getElementById('chat-modal').style.display = 'none';
    if (chatSocket) { chatSocket.emit('leave', {task_id: chatTaskId}); chatSocket.disconnect(); chatSocket = null; }
    chatTaskId = null;
}

function connectChatSocket(taskId) {
    if (chatSocket) { chatSocket.disconnect(); }
    chatSocket = io({transports: ['websocket', 'polling']});
    chatSocket.on('connect', () => {
        chatSocket.emit('join', {task_id: taskId});
    });
    chatSocket.on('new_message', (msg) => {
        const container = document.getElementById('chat-messages');
        container.appendChild(createChatBubble(msg));
        container.scrollTop = container.scrollHeight;
    });
}

async function loadChatMessages(taskId) {
    const msgs = await fetchAPI(`/chat/${taskId}`);
    const container = document.getElementById('chat-messages');
    container.innerHTML = '';
    if (!msgs || msgs.length === 0) {
        container.innerHTML = '<div style="text-align:center;padding:20px;color:#999;">💬 Sin mensajes aún. Inicia la conversación.</div>';
        return;
    }
    msgs.forEach(m => container.appendChild(createChatBubble(m)));
    container.scrollTop = container.scrollHeight;
}

function createChatBubble(msg) {
    const div = document.createElement('div');
    const isMine = msg.user_id === chatSocket?.auth?.userId;
    div.style.cssText = `display:flex;flex-direction:column;align-items:${isMine?'flex-end':'flex-start'};margin-bottom:10px;`;
    div.innerHTML = `
        <div style="font-size:10px;color:#999;margin-bottom:2px;padding:0 4px;">${msg.username || msg.user_name || 'Usuario'} · ${msg.created_at ? new Date(msg.created_at+'Z').toLocaleTimeString('es-CL',{hour:'2-digit',minute:'2-digit'}) : ''}</div>
        <div style="background:${isMine?'#1a73e8':'white'};color:${isMine?'white':'#333'};padding:8px 12px;border-radius:12px;${isMine?'border-bottom-right-radius:4px':'border-bottom-left-radius:4px'};max-width:80%;font-size:13px;box-shadow:0 1px 3px rgba(0,0,0,0.1);white-space:pre-wrap;">${msg.message}</div>`;
    return div;
}

async function sendChatMessage() {
    const input = document.getElementById('chat-input');
    const message = input.value.trim();
    if (!message || !chatTaskId) return;
    input.value = '';
    if (chatSocket && chatSocket.connected) {
        chatSocket.emit('send_message', {task_id: chatTaskId, message});
    } else {
        await fetchAPI(`/chat/${chatTaskId}`, {
            method: 'POST',
            body: JSON.stringify({message})
        });
        loadChatMessages(chatTaskId);
    }
}

// ===== BÚSQUEDA GLOBAL =====
let searchTimeout = null;
function debounceSearch(value) {
    clearTimeout(searchTimeout);
    const results = document.getElementById('search-results');
    if (value.length < 2) { results.style.display = 'none'; return; }
    searchTimeout = setTimeout(() => doSearch(value), 300);
}

async function doSearch(q) {
    const results = await fetchAPI(`/search?q=${encodeURIComponent(q)}`);
    const container = document.getElementById('search-results');
    if (!results || results.length === 0) {
        container.innerHTML = '<div style="padding:12px;color:#999;text-align:center;">Sin resultados</div>';
        container.style.display = 'block';
        return;
    }
    const colors = {pendiente:'#FFC107',gestionando:'#1a73e8',realizada:'#28A745',cancelada:'#DC3545'};
    container.innerHTML = results.map(t => `
        <div class="search-item" onclick="viewAreaTasks(${t.id},'${t.area_name}')">
            <div style="display:flex;align-items:center;gap:6px;">
                <span style="width:8px;height:8px;border-radius:50%;background:${colors[t.status]||'#999'};display:inline-block;"></span>
                <strong style="font-size:13px;">${t.title}</strong>
            </div>
            <div style="font-size:11px;color:#666;">🏢 ${t.area_name} · 🏷️ ${t.company_name} · 📅 ${t.due_date||''}</div>
        </div>
    `).join('');
    container.style.display = 'block';
}

document.addEventListener('click', (e) => {
    if (!e.target.closest('.search-box')) document.getElementById('search-results').style.display = 'none';
});

// ===== CALENDARIO =====
async function loadCalendar() {
    const container = document.getElementById('calendar-grid');
    if (!container) return;
    const events = await fetchAPI('/calendar');
    if (!events || events.length === 0) {
        container.innerHTML = '<div style="text-align:center;padding:20px;color:#999;grid-column:1/-1;">📅 No hay tareas con fecha límite en los próximos 60 días</div>';
        return;
    }
    const statusLabels = {pendiente:'⏳ Pendiente',gestionando:'🔄 Gest.',realizada:'✅ Done',cancelada:'❌ Canc.'};
    const priorityColors = {urgente:'#7B2D8E',alta:'#DC3545',media:'#FFC107',baja:'#28A745'};

    // Group by date
    const grouped = {};
    events.forEach(e => {
        const d = e.start || 'sin-fecha';
        if (!grouped[d]) grouped[d] = [];
        grouped[d].push(e);
    });

    container.innerHTML = '';
    Object.keys(grouped).sort().forEach(date => {
        const day = document.createElement('div');
        day.style.cssText = 'background:#f8f9fa;border-radius:8px;padding:10px;border:1px solid #e0e0e0;';
        const [y, m, d] = date.split('-');
        const dateStr = new Date(parseInt(y), parseInt(m)-1, parseInt(d)).toLocaleDateString('es-CL', {day:'numeric',month:'short'});
        const isOverdue = date < new Date().toISOString().split('T')[0];
        day.innerHTML = `<div style="font-size:11px;font-weight:700;color:${isOverdue?'#DC3545':'#333'};margin-bottom:6px;">
            ${isOverdue?'⚠️ ':''}${dateStr}${isOverdue?' (VENCIDA)':''}</div>`;
        grouped[date].forEach(e => {
            const priColor = priorityColors[e.extendedProps?.priority] || '#666';
            day.innerHTML += `<div style="display:flex;align-items:center;gap:6px;padding:4px 0;border-bottom:1px solid #f0f0f0;cursor:pointer;"
                onclick="viewAreaTasks(${e.id},'${e.extendedProps?.area||''}')">
                <span style="width:4px;height:4px;border-radius:50%;background:${e.backgroundColor};display:inline-block;"></span>
                <span style="font-size:12px;flex:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${e.title}</span>
                <span style="font-size:9px;color:${priColor};font-weight:600;">${e.extendedProps?.priority||''}</span>
            </div>`;
        });
        container.appendChild(day);
    });
}

// ===== APROBACIÓN =====
async function approveTask(taskId) {
    const result = await fetchAPI(`/tasks/${taskId}/approve`, { method: 'POST' });
    if (result) {
        showNotification('✅ Tarea aprobada', 'success');
        if (currentAreaId) loadAreaTasks(currentAreaId);
        loadDashboard();
    } else {
        showNotification('Solo se pueden aprobar tareas completadas', 'error');
    }
}

// ===== EXPORT =====
function exportTasks(format = 'csv') {
    const params = new URLSearchParams({format});
    if (currentAreaId) params.set('area_id', currentAreaId);
    const statusFilter = document.getElementById('status-filter')?.value;
    if (statusFilter) params.set('status', statusFilter);
    window.location.href = `/api/export/tasks?${params.toString()}`;
    showNotification('📄 Exportando reporte...', 'info');
}

// ===== RECURRING =====
async function runRecurring() {
    const result = await fetchAPI('/recurring/run', { method: 'POST' });
    if (result) showNotification(`🔄 ${result.created} tareas recurrentes creadas`, 'success');
}

// ===== CALENDAR LOAD =====
// Extend loadDashboard to include calendar
const origLoadDashboard = loadDashboard;
loadDashboard = function() {
    origLoadDashboard();
    loadCalendar();
};

// ===== DOCUMENT READY =====
document.addEventListener('DOMContentLoaded', () => {
    loadInitialData();
    document.getElementById('task-modal').addEventListener('click', (e) => { if (e.target === document.getElementById('task-modal')) closeTaskModal(); });
    document.getElementById('template-modal').addEventListener('click', (e) => { if (e.target === document.getElementById('template-modal')) closeTemplateModal(); });
    document.getElementById('chat-modal').addEventListener('click', (e) => { if (e.target === document.getElementById('chat-modal')) closeChatModal(); });
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape') { closeTaskModal(); closeTemplateModal(); closeChatModal(); } });
    document.addEventListener('click', (e) => {
        const panel = document.getElementById('notifications-panel');
        if (panel && panel.style.display === 'block' && !e.target.closest('.notification-bell') && !e.target.closest('.notifications-panel'))
            panel.style.display = 'none';
    });
});
