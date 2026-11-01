import http.server
import socketserver
import json
import os
import urllib.parse

PORT = 8000
DATA_FILE = "data/estado_productos.json"

class CustomHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        # Prevent caching for dynamic and code files
        if self.path.endswith('.json') or self.path.endswith('.html') or self.path.endswith('.js') or self.path.endswith('.css'):
            self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
            self.send_header('Pragma', 'no-cache')
            self.send_header('Expires', '0')
        super().end_headers()

    def do_POST(self):
        parsed_path = urllib.parse.urlparse(self.path)
        if parsed_path.path == '/api/update':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            
            try:
                # Expecting {"id": "...", "precio": "...", "vendido": true/false}
                data = json.loads(post_data.decode('utf-8'))
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
        else:
            self.send_error(404, "Not Found")

with socketserver.TCPServer(("", PORT), CustomHandler) as httpd:
    print(f"Servidor personalizado corriendo en el puerto {PORT}")
    httpd.serve_forever()
