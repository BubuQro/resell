#!/usr/bin/env bash
# ==============================================================================
# Script de Inicio Automático en Red Local (LAN) — BubuStore (amazon-resell)
# Uso:
#   ./iniciar_servidor.sh          -> Inicia el servidor y abre el navegador
#   ./iniciar_servidor.sh --bg     -> Inicia el servidor en segundo plano (daemon)
#   ./iniciar_servidor.sh --stop   -> Detiene el servidor activo en el puerto 8000
# ==============================================================================

set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

PORT=8000
LOG_FILE="$PROJECT_DIR/server_lan.log"
PID_FILE="$PROJECT_DIR/.server_lan.pid"

# Función para detectar la IP de la red local (Wi-Fi / Ethernet) en macOS
get_lan_ip() {
    local ip=""
    ip="$(ipconfig getifaddr en0 2>/dev/null || true)"
    if [ -z "$ip" ]; then
        ip="$(ipconfig getifaddr en1 2>/dev/null || true)"
    fi
    if [ -z "$ip" ]; then
        ip="$(python3 -c 'import socket; s=socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.connect(("8.8.8.8",80)); print(s.getsockname()[0]); s.close()' 2>/dev/null || echo "127.0.0.1")"
    fi
    echo "$ip"
}

stop_existing_server() {
    local pids
    pids="$(lsof -ti :$PORT 2>/dev/null || true)"
    if [ -n "$pids" ]; then
        echo "🔄 Liberando puerto $PORT (deteniendo proceso previo: $pids)..."
        echo "$pids" | xargs kill -9 2>/dev/null || true
        sleep 0.5
    fi
    rm -f "$PID_FILE"
}

MODE="${1:-fg}"

if [ "$MODE" = "--stop" ] || [ "$MODE" = "stop" ]; then
    stop_existing_server
    echo "🛑 Servidor detenido."
    exit 0
fi

stop_existing_server

LAN_IP="$(get_lan_ip)"
LAN_URL="http://${LAN_IP}:${PORT}"
LOCAL_URL="http://localhost:${PORT}"

echo "=================================================================="
echo "🚀 BubuStore — Servidor Web Activo en Red Local (LAN)"
echo "=================================================================="
echo "📂 Directorio : $PROJECT_DIR"
echo "💻 En esta Mac: ${LOCAL_URL}/admin.html"
echo "🌐 Red Local  :"
echo "   • Catálogo Público : ${LAN_URL}/index.html"
echo "   • Administración   : ${LAN_URL}/admin.html"
echo "   • Generador Posts  : ${LAN_URL}/generador.html"
echo "   • Catálogo PDF     : ${LAN_URL}/Catalogo_Productos_BubuStore.pdf"
echo "=================================================================="

# Mostrar código QR en la terminal para escanear desde el celular si qrcode está instalado
python3 - "$LAN_URL" <<'PYEOF' 2>/dev/null || true
import sys
try:
    import qrcode
    url = sys.argv[1]
    qr = qrcode.QRCode(border=1)
    qr.add_data(url)
    qr.make(fit=True)
    print("\n📱 Escanea este QR con tu celular (conectado al mismo Wi-Fi):")
    qr.print_ascii(invert=True)
    print("")
except Exception:
    pass
PYEOF

if [ "$MODE" = "--bg" ] || [ "$MODE" = "bg" ]; then
    nohup python3 -u "$PROJECT_DIR/server.py" > "$LOG_FILE" 2>&1 &
    SERVER_PID=$!
    echo "$SERVER_PID" > "$PID_FILE"
    sleep 0.8
    echo "✅ Servidor corriendo en segundo plano (PID: $SERVER_PID)"
    echo "📄 Logs disponibles en: $LOG_FILE"
    echo "💡 Para detenerlo ejecuta: ./iniciar_servidor.sh --stop"
    open "${LAN_URL}/admin.html" 2>/dev/null || true
else
    echo "💡 Presiona Ctrl+C en cualquier momento para detener el servidor."
    echo "------------------------------------------------------------------"
    (sleep 1 && open "${LAN_URL}/admin.html" 2>/dev/null || true) &
    exec python3 -u "$PROJECT_DIR/server.py"
fi

