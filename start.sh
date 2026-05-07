#!/bin/bash

echo "=============================================="
echo "  🚀 SISTEMA DE AGENTES IA - HIRAM CHILE"
echo "  Hiram Chile – ProClean Facilities"
echo "=============================================="
echo ""

BASE_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$BASE_DIR/backend"
FRONTEND_DIR="$BASE_DIR/frontend"

echo "[1/3] Inicializando base de datos..."
cd "$BACKEND_DIR"
python3 database.py

echo ""
echo "[2/3] Verificando dependencias..."
python3 -c "import flask, flask_cors, apscheduler, openai; print('✅ Todas las dependencias OK')" 2>/dev/null || pip3 install flask flask-cors apscheduler openai -q

echo ""
echo "=============================================="
echo "  🚀 SISTEMA DE AGENTES IA - HIRAM CHILE"
echo "=============================================="
echo "  📋 DASHBOARD: http://localhost:8080"
echo "  📧 EMAILS:   Modo desarrollo (mock)"
echo "  🤖 AGENTES:  Sugerencias IA cada 6h"
echo "  ⏰ CRON:     Recordatorios diarios 9:00 AM"
echo "=============================================="
echo ""
echo "Para correos reales, configurar:"
echo "  export SMTP_USER=tu@email.com"
echo "  export SMTP_PASS=tu_password"
echo "  export FROM_EMAIL=notificaciones@hiramchile.cl"
echo "  export OPENAI_API_KEY=sk-... (IA avanzada)"
echo ""

cd "$BACKEND_DIR"
python3 app.py
