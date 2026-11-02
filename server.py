import http.server
import socketserver
import json
import os
import urllib.parse
import requests

PORT = 8000
DATA_FILE = "data/estado_productos.json"
FB_CONFIG_FILE = "data/facebook_config.json"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

class CustomHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        # Prevent caching for dynamic and code files
        if self.path.endswith('.json') or self.path.endswith('.html') or self.path.endswith('.js') or self.path.endswith('.css'):
            self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
            self.send_header('Pragma', 'no-cache')
            self.send_header('Expires', '0')
        super().end_headers()

    def do_GET(self):
        parsed_path = urllib.parse.urlparse(self.path)
        if parsed_path.path == '/api/facebook/config':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            cfg = {"access_token": "", "groups": []}
            if os.path.exists(FB_CONFIG_FILE):
                try:
                    with open(FB_CONFIG_FILE, 'r', encoding='utf-8') as f:
                        cfg = json.load(f)
                except Exception:
                    pass
            self.wfile.write(json.dumps(cfg, ensure_ascii=False).encode('utf-8'))
            return
        super().do_GET()

    def do_POST(self):
        parsed_path = urllib.parse.urlparse(self.path)
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length) if content_length > 0 else b'{}'
        
        try:
            body = json.loads(post_data.decode('utf-8'))
        except Exception:
            body = {}

        if parsed_path.path == '/api/update':
            try:
                # Expecting {"id": "...", "precio": "...", "vendido": true/false}
                data = body
                product_id = data.get('id')
                
                if not product_id:
                    self.send_error(400, "Missing product ID")
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
                    state[product_id]['vendido'] = data['vendido']
                if 'folio' in data:
                    state[product_id]['folio'] = data['folio']
                    
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
                os.makedirs(os.path.dirname(FB_CONFIG_FILE), exist_ok=True)
                with open(FB_CONFIG_FILE, 'w', encoding='utf-8') as f:
                    json.dump(body, f, ensure_ascii=False, indent=2)
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"status": "success", "saved": body}).encode('utf-8'))
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
                self.send_response(400)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"status": "error", "message": "Se requiere Access Token y Target/Group ID."}).encode('utf-8'))
                return

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

        else:
            self.send_error(404, "Not Found")

with socketserver.TCPServer(("", PORT), CustomHandler) as httpd:
    print(f"Servidor personalizado corriendo en el puerto {PORT}")
    httpd.serve_forever()
