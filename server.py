import http.server
import ipaddress
import re
import socket
import socketserver
import json
import os
import urllib.parse
import requests

PORT = 8000
HOST = "0.0.0.0"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE_DIR, "data", "estado_productos.json")
FB_CONFIG_FILE = os.path.join(BASE_DIR, "data", "facebook_config.json")

MAX_BODY_BYTES = 1 * 1024 * 1024  # 1 MB es más que suficiente para la API
SAFE_ID_RE = re.compile(r'^[A-Za-z0-9_-]{1,64}$')

# Rutas que nunca deben servirse como archivos estáticos (ni en LAN)
BLOCKED_FILES = {
    'data/facebook_config.json',
    'server_lan.log',
}
BLOCKED_EXTENSIONS = ('.py', '.pyc', '.sh', '.command', '.log', '.pid', '.spec', '.bak', '.zip')

# Endpoints que manejan el token de Facebook: solo desde esta misma Mac
LOCAL_ONLY_PATHS = {
    '/api/facebook/config',
    '/api/facebook/test_token',
    '/api/facebook/publish',
}


def is_loopback(addr):
    try:
        ip = ipaddress.ip_address(addr)
        if ip.version == 6 and ip.ipv4_mapped:
            ip = ip.ipv4_mapped
        return ip.is_loopback
    except ValueError:
        return False


def get_local_ip():
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"


class ThreadedHTTPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True


class CustomHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        # Servir siempre desde la carpeta del proyecto, sin importar el cwd
        super().__init__(*args, directory=BASE_DIR, **kwargs)

    def end_headers(self):
        # Sin "Access-Control-Allow-Origin: *": las páginas del propio servidor no lo
        # necesitan y con él cualquier sitio web abierto en tu navegador podría leer
        # la API local (incluido el token de Facebook).
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'same-origin')
        # Prevent caching for dynamic and code files
        path_only = urllib.parse.urlparse(self.path).path
        if path_only.endswith(('.json', '.html', '.js', '.css')) or path_only.startswith('/api/'):
            self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
            self.send_header('Pragma', 'no-cache')
            self.send_header('Expires', '0')
        super().end_headers()

    # ---------- utilidades ----------
    def _send_json(self, status, payload):
        data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _is_blocked_path(self, raw_path):
        """Evita servir el repo .git, el token, logs y scripts por HTTP."""
        path = urllib.parse.unquote(urllib.parse.urlparse(raw_path).path)
        norm = os.path.normpath(path).replace('\\', '/').lstrip('/')
        if norm.startswith('..'):
            return True
        parts = [p for p in norm.split('/') if p]
        if any(p.startswith('.') for p in parts):  # .git, .githooks, .DS_Store, .server_lan.pid
            return True
        if norm in BLOCKED_FILES:
            return True
        if norm.lower().endswith(BLOCKED_EXTENSIONS):
            return True
        if parts and parts[0] in ('GeneradorPubs', 'build', 'dist', '__pycache__'):
            return True
        return False

    def _client_is_local(self):
        return is_loopback(self.client_address[0])

    def _origin_ok(self):
        """Protección CSRF: un POST solo se acepta desde páginas de este mismo servidor."""
        origin = self.headers.get('Origin')
        if origin is None:
            return True  # clientes que no son navegador (curl, scripts locales)
        host = self.headers.get('Host', '')
        return urllib.parse.urlparse(origin).netloc == host

    def list_directory(self, path):
        # No exponer listados de carpetas (images/ tiene miles de archivos)
        self.send_error(404, "Not Found")
        return None

    def do_HEAD(self):
        if self._is_blocked_path(self.path):
            self.send_error(404, "Not Found")
            return
        super().do_HEAD()

    def do_GET(self):
        parsed_path = urllib.parse.urlparse(self.path)
        if parsed_path.path == '/api/facebook/config':
            if not self._client_is_local():
                self._send_json(403, {"status": "error", "message": "La configuración de Facebook solo está disponible desde la Mac que ejecuta el servidor."})
                return
            cfg = {"access_token": "", "groups": []}
            if os.path.exists(FB_CONFIG_FILE):
                try:
                    with open(FB_CONFIG_FILE, 'r', encoding='utf-8') as f:
                        cfg = json.load(f)
                except Exception:
                    pass
            self._send_json(200, cfg)
            return
        if self._is_blocked_path(self.path):
            self.send_error(404, "Not Found")
            return
        super().do_GET()

    def do_POST(self):
        parsed_path = urllib.parse.urlparse(self.path)

        if not self._origin_ok():
            self._send_json(403, {"status": "error", "message": "Origen no permitido."})
            return

        content_type = (self.headers.get('Content-Type') or '').split(';')[0].strip().lower()
        if content_type != 'application/json':
            self._send_json(415, {"status": "error", "message": "Se requiere Content-Type: application/json."})
            return

        if parsed_path.path in LOCAL_ONLY_PATHS and not self._client_is_local():
            self._send_json(403, {"status": "error", "message": "Las funciones de Facebook solo se pueden usar desde la Mac que ejecuta el servidor."})
            return

        try:
            content_length = int(self.headers.get('Content-Length', 0))
        except ValueError:
            content_length = 0
        if content_length > MAX_BODY_BYTES:
            self._send_json(413, {"status": "error", "message": "Solicitud demasiado grande."})
            return
        post_data = self.rfile.read(content_length) if content_length > 0 else b'{}'

        try:
            body = json.loads(post_data.decode('utf-8'))
        except Exception:
            body = {}
        if not isinstance(body, dict):
            body = {}

        if parsed_path.path == '/api/update':
            try:
                # Expecting {"id": "...", "precio": "...", "vendido": true/false}
                data = body
                product_id = data.get('id')
                
                if not product_id or not isinstance(product_id, str) or not SAFE_ID_RE.match(product_id):
                    self.send_error(400, "Missing or invalid product ID")
                    return
                
                # Load existing state
                state = {}
                if os.path.exists(DATA_FILE):
                    with open(DATA_FILE, 'r', encoding='utf-8') as f:
                        try:
                            state = json.load(f)
                        except json.JSONDecodeError:
                            pass
                
                # Update state
                if product_id not in state:
                    state[product_id] = {}
                
                if 'precio' in data:
                    raw_precio = data['precio']
                    # Validar y normalizar el precio: debe ser número válido o vacío
                    if raw_precio is None or str(raw_precio).strip() == '':
                        state[product_id]['precio'] = ''
                    else:
                        # Limpiar formato: remover comas de miles, espacios, símbolo $
                        precio_str = str(raw_precio).strip().replace('$', '').replace(',', '').replace(' ', '')
                        try:
                            precio_num = float(precio_str)
                            if precio_num < 0:
                                raise ValueError("Precio negativo")
                            # Guardar como entero redondeado sin centavos
                            state[product_id]['precio'] = int(round(precio_num))
                        except (ValueError, TypeError):
                            # Si no es número válido, conservar el valor previo o vacío
                            state[product_id]['precio'] = state[product_id].get('precio', '')
                if 'vendido' in data:
                    state[product_id]['vendido'] = bool(data['vendido'])
                if 'folio' in data:
                    # Texto corto, sin HTML (se muestra en el catálogo público)
                    folio = re.sub(r'[<>"\'&]', '', str(data['folio'] or '')).strip()[:20]
                    state[product_id]['folio'] = folio
                    
                # Save state
                with open(DATA_FILE, 'w', encoding='utf-8') as f:
                    json.dump(state, f, ensure_ascii=False, indent=2)
                    
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"status": "success"}).encode('utf-8'))
                
            except Exception as e:
                self.send_error(500, f"Server Error: {str(e)}")

        elif parsed_path.path == '/api/facebook/config':
            try:
                cfg = {
                    "access_token": str(body.get('access_token', '') or '').strip(),
                    "groups": body.get('groups') if isinstance(body.get('groups'), list) else [],
                }
                os.makedirs(os.path.dirname(FB_CONFIG_FILE), exist_ok=True)
                # Archivo legible solo por tu usuario de macOS (contiene el token)
                fd = os.open(FB_CONFIG_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
                with os.fdopen(fd, 'w', encoding='utf-8') as f:
                    json.dump(cfg, f, ensure_ascii=False, indent=2)
                os.chmod(FB_CONFIG_FILE, 0o600)
                # No devolver el token en la respuesta
                self._send_json(200, {"status": "success", "groups": len(cfg["groups"])})
            except Exception as e:
                self.send_error(500, f"Error saving Facebook config: {str(e)}")

        elif parsed_path.path == '/api/facebook/test_token':
            token = body.get('access_token', '').strip()
            if not token:
                self.send_response(400)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"status": "error", "message": "Token de acceso no proporcionado."}).encode('utf-8'))
                return
            
            try:
                # 1. Validar usuario
                me_resp = requests.get('https://graph.facebook.com/v19.0/me', params={
                    'fields': 'id,name,picture',
                    'access_token': token
                }, timeout=12)
                me_json = me_resp.json()

                if 'error' in me_json:
                    err_msg = me_json['error'].get('message', 'Token inválido o expirado.')
                    self.send_response(200)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({"status": "error", "message": err_msg, "error": me_json['error']}).encode('utf-8'))
                    return

                # 2. Intentar obtener grupos del usuario
                groups = []
                try:
                    gr_resp = requests.get('https://graph.facebook.com/v19.0/me/groups', params={
                        'fields': 'id,name,privacy',
                        'limit': '100',
                        'access_token': token
                    }, timeout=10)
                    gr_data = gr_resp.json()
                    if 'data' in gr_data:
                        groups = gr_data['data']
                except Exception:
                    pass

                # 3. Intentar obtener páginas del usuario
                pages = []
                try:
                    pg_resp = requests.get('https://graph.facebook.com/v19.0/me/accounts', params={
                        'fields': 'id,name,access_token',
                        'limit': '100',
                        'access_token': token
                    }, timeout=10)
                    pg_data = pg_resp.json()
                    if 'data' in pg_data:
                        pages = pg_data['data']
                except Exception:
                    pass

                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({
                    "status": "success",
                    "user": me_json,
                    "groups": groups,
                    "pages": pages
                }, ensure_ascii=False).encode('utf-8'))

            except Exception as e:
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"status": "error", "message": f"Error de conexión con Facebook: {str(e)}"}).encode('utf-8'))

        elif parsed_path.path == '/api/facebook/publish':
            token = body.get('access_token', '').strip()
            target_id = body.get('target_id', '').strip()
            message = body.get('message', '').strip()
            post_type = body.get('post_type', 'photo')
            product_id = body.get('product_id', '')
            photo_num = body.get('photo_num', '01')
            image_url = body.get('image_url', '')

            if not token or not target_id:
                self._send_json(400, {"status": "error", "message": "Se requiere Access Token y Target/Group ID."})
                return

            # Evitar rutas manipuladas (../) hacia otros archivos o endpoints de la Graph API
            if not re.match(r'^[A-Za-z0-9_.]{1,64}$', target_id) or '..' in target_id:
                self._send_json(400, {"status": "error", "message": "Target/Group ID inválido."})
                return
            product_id = str(product_id)
            photo_num = str(photo_num)
            if product_id and not SAFE_ID_RE.match(product_id):
                self._send_json(400, {"status": "error", "message": "ID de producto inválido."})
                return
            if not re.match(r'^[0-9]{1,3}$', photo_num):
                photo_num = '01'
            if image_url and not str(image_url).startswith(('https://', 'http://')):
                image_url = ''

            try:
                # Caso 1: Publicar Foto con Copy
                if post_type == 'photo':
                    # Buscar imagen local
                    local_img = os.path.join(BASE_DIR, 'images', f"{product_id}_{photo_num}.jpg")
                    if os.path.exists(local_img):
                        with open(local_img, 'rb') as img_f:
                            files = {'source': (f"{product_id}_{photo_num}.jpg", img_f, 'image/jpeg')}
                            payload = {'caption': message, 'access_token': token}
                            fb_res = requests.post(
                                f"https://graph.facebook.com/v19.0/{target_id}/photos",
                                data=payload,
                                files=files,
                                timeout=35
                            )
                    elif image_url:
                        payload = {'caption': message, 'url': image_url, 'access_token': token}
                        fb_res = requests.post(
                            f"https://graph.facebook.com/v19.0/{target_id}/photos",
                            data=payload,
                            timeout=35
                        )
                    else:
                        # Si no hay imagen, publicar en /feed
                        payload = {'message': message, 'access_token': token}
                        fb_res = requests.post(
                            f"https://graph.facebook.com/v19.0/{target_id}/feed",
                            data=payload,
                            timeout=30
                        )
                else:
                    # Caso 2: Solo feed de texto y enlace
                    payload = {'message': message, 'access_token': token}
                    if body.get('link'):
                        payload['link'] = body.get('link')
                    fb_res = requests.post(
                        f"https://graph.facebook.com/v19.0/{target_id}/feed",
                        data=payload,
                        timeout=30
                    )

                fb_json = fb_res.json()
                if fb_res.status_code == 200 and 'id' in fb_json:
                    self.send_response(200)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({
                        "status": "success",
                        "id": fb_json.get('id'),
                        "post_id": fb_json.get('post_id', fb_json.get('id')),
                        "target_id": target_id
                    }).encode('utf-8'))
                else:
                    err_info = fb_json.get('error', {})
                    err_msg = err_info.get('message', f"Error HTTP {fb_res.status_code} desde Facebook.")
                    self.send_response(200)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({
                        "status": "error",
                        "message": err_msg,
                        "error": err_info,
                        "target_id": target_id
                    }, ensure_ascii=False).encode('utf-8'))

            except Exception as e:
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"status": "error", "message": str(e), "target_id": target_id}).encode('utf-8'))

        elif parsed_path.path == '/api/actualizar_sitio' or parsed_path.path == '/api/git/sync':
            try:
                import subprocess
                script_path = os.path.join(BASE_DIR, 'actualizar_sitio.sh')
                proc = subprocess.run(
                    ['bash', script_path],
                    cwd=BASE_DIR,
                    capture_output=True,
                    text=True,
                    timeout=180
                )
                output = ((proc.stdout or '') + '\n' + (proc.stderr or '')).strip()
                if proc.returncode == 0:
                    self.send_response(200)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({
                        "status": "success",
                        "message": "Sitio actualizado y subido a GitHub exitosamente.",
                        "output": output
                    }, ensure_ascii=False).encode('utf-8'))
                else:
                    self.send_response(200)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({
                        "status": "error",
                        "message": f"Error al ejecutar script de actualización (código {proc.returncode}).",
                        "output": output
                    }, ensure_ascii=False).encode('utf-8'))
            except Exception as e:
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({
                    "status": "error",
                    "message": f"Error interno en el servidor: {str(e)}"
                }, ensure_ascii=False).encode('utf-8'))

        else:
            self.send_error(404, "Not Found")

if __name__ == '__main__':
    port = int(os.environ.get('PORT', PORT))
    with ThreadedHTTPServer((HOST, port), CustomHandler) as httpd:
        local_ip = get_local_ip()
        print(f"Servidor personalizado corriendo en el puerto {port}")
        print(f"  • Local:     http://localhost:{port}")
        print(f"  • Red Local: http://{local_ip}:{port}")
        httpd.serve_forever()
