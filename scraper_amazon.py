#!/usr/bin/env python3
"""
Scraper de precios de Amazon para el catálogo de BubuStore.
Permite consultar los precios de referencia vigentes de Amazon México
y guardarlos automáticamente en data/estado_productos.json.
"""

import json
import time
import random
import os
import sys
import urllib.request
from urllib.error import HTTPError, URLError
import re

# Archivos
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PRODUCTOS_FILE = os.path.join(BASE_DIR, "data", "productos.json")
ESTADO_FILE = os.path.join(BASE_DIR, "data", "estado_productos.json")

# Cabeceras para simular un navegador real en macOS
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Accept-Language': 'es-MX,es;q=0.9,en-US;q=0.8,en;q=0.7',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
    'Sec-Ch-Ua': '"Chromium";v="122", "Not(A:Brand";v="24", "Google Chrome";v="122"',
    'Sec-Ch-Ua-Mobile': '?0',
    'Sec-Ch-Ua-Platform': '"macOS"',
    'Sec-Fetch-Dest': 'document',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-Site': 'none',
    'Sec-Fetch-User': '?1',
    'Upgrade-Insecure-Requests': '1',
    'Connection': 'keep-alive'
}

def load_json(filepath):
    if not os.path.exists(filepath):
        return {}
    with open(filepath, 'r', encoding='utf-8') as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {}

def save_json(filepath, data):
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def extract_price(html):
    """
    Busca patrones de precio en el HTML de Amazon México.
    Prioriza el precio real de compra sobre precios tachados o de referencia.
    """
    # 1. PRIORIDAD: precio en contenedores oficiales de Amazon (evita capturar precios tachados)
    # Buscar apexPriceToPay / priceToPay / corePriceDisplay primero
    priority_patterns = [
        r'apexPriceToPay[^>]*>.*?<span class="a-offscreen">([^<]+)</span>',
        r'priceToPay[^>]*>.*?<span class="a-offscreen">([^<]+)</span>',
        r'corePriceDisplay[^>]*>.*?<span class="a-offscreen">([^<]+)</span>',
        r'corePrice[^>]*>.*?<span class="a-offscreen">([^<]+)</span>',
    ]
    for pattern in priority_patterns:
        match = re.search(pattern, html, re.DOTALL)
        if match:
            p = match.group(1).strip()
            if '$' in p:
                return p

    # 2. Precio dividido en entero y fracción (dentro de contenedores de precio real):
    match_whole = re.search(r'class="a-price(?:-symbol)?[^"]*">.*?class="a-price-whole">([^<]+)<', html, re.DOTALL)
    if not match_whole:
        match_whole = re.search(r'class="a-price-whole">([^<]+)<', html)
    match_fraction = re.search(r'class="a-price-fraction">([^<]+)<', html)
    if match_whole:
        whole = match_whole.group(1).replace('.', '').replace(',', '').strip()
        fraction = match_fraction.group(1).strip() if match_fraction else "00"
        if whole.isdigit():
            return f"${whole}.{fraction}"

    # 3. Fallback: primer a-offscreen con símbolo de peso
    # (puede capturar precio tachado — solo se usa si los métodos anteriores fallan)
    for match in re.finditer(r'<span class="a-offscreen">([^<]+)</span>', html):
        p = match.group(1).strip()
        if '$' in p:
            return p

    return None

def is_captcha(html):
    return ('api-services-support@amazon.com' in html or 
            'Enter the characters you see below' in html or 
            'Ingresa los caracteres que ves a continuación' in html)

def main():
    print("=" * 60)
    print("🔍 BubuStore - Consultor de Precios de Amazon México")
    print("=" * 60)

    productos_data = load_json(PRODUCTOS_FILE)
    estado_data = load_json(ESTADO_FILE)

    products_list = []
    if isinstance(productos_data, list):
        products_list = productos_data
    elif isinstance(productos_data, dict) and "productos" in productos_data:
        products_list = productos_data["productos"]

    if not products_list:
        print("❌ No se encontraron productos en data/productos.json.")
        return

    # Opciones de filtrado por argumentos
    args = sys.argv[1:]
    solo_nuevos = False
    forzar = "--forzar" in args
    target_id = None
    limit = None

    for i, arg in enumerate(args):
        if arg in ["--nuevos", "-n"]:
            solo_nuevos = True
        elif arg.startswith("B0"):
            target_id = arg
        elif arg in ["--limit", "-l"] and i + 1 < len(args):
            try:
                limit = int(args[i + 1])
            except ValueError:
                pass

    # Selección de productos a consultar
    pendientes = []
    
    if target_id:
        # Modo producto específico
        pendientes = [p for p in products_list if p.get("id") == target_id]
        print(f"🎯 Modo producto único: {target_id}")
    elif solo_nuevos:
        # Los últimos 178 productos (los agregados en la última importación)
        ultimos_178 = products_list[-178:] if len(products_list) >= 178 else products_list
        pendientes = [p for p in ultimos_178 if forzar or not estado_data.get(p.get("id"), {}).get("amazon_precio")]
        print(f"✨ Modo productos nuevos: {len(pendientes)} artículos pendientes de precio.")
    else:
        # Por defecto: todos los que falten de precio, ordenados empezando por los más recientes
        pendientes = [p for p in reversed(products_list) if forzar or not estado_data.get(p.get("id"), {}).get("amazon_precio")]
        print(f"📋 Modo general: {len(pendientes)} artículos sin precio de Amazon registrado.")

    if limit and limit > 0:
        pendientes = pendientes[:limit]
        print(f"⚡ Límite aplicado: procesando los primeros {limit} artículos.")

    if not pendientes:
        print("✅ ¡Todos los productos seleccionados ya tienen su precio de Amazon registrado!")
        print("💡 Si deseas forzar una actualización de precios, usa: python3 scraper_amazon.py --forzar")
        return

    print(f"\nIniciando consulta para {len(pendientes)} productos...")
    print("Tip: Puedes detenerlo en cualquier momento con Ctrl+C (los precios obtenidos ya habrán quedado guardados).\n")

    exitos = 0
    no_encontrados = 0

    for idx, prod in enumerate(pendientes, 1):
        prod_id = prod.get("id")
        url = prod.get("url") or f"https://www.amazon.com.mx/dp/{prod_id}"
        titulo = prod.get("titulo", "")[:45]

        print(f"[{idx}/{len(pendientes)}] {prod_id} - {titulo}...")
        
        req = urllib.request.Request(url, headers=HEADERS)
        try:
            with urllib.request.urlopen(req, timeout=12) as response:
                html = response.read().decode('utf-8', errors='ignore')
                
                if is_captcha(html):
                    print("  ⚠️ Amazon presentó un Captcha o detección de tráfico.")
                    print("  Pausando temporalmente por 15 segundos...")
                    time.sleep(15)
                    continue

                precio = extract_price(html)
                
                if precio:
                    print(f"  💰 Precio Amazon: {precio}")
                    if prod_id not in estado_data:
                        estado_data[prod_id] = {}
                    estado_data[prod_id]["amazon_precio"] = precio
                    
                    # Calcular precio de venta con 20% de descuento (redondeado sin centavos)
                    try:
                        clean_amz = re.sub(r'[^\d.]', '', str(precio).replace(',', ''))
                        nuevo_precio_venta = int(round(float(clean_amz) * 0.8))
                        estado_data[prod_id]["precio"] = nuevo_precio_venta
                        print(f"  🏷️  Precio de venta (-20%): ${nuevo_precio_venta}")
                    except Exception:
                        pass

                    save_json(ESTADO_FILE, estado_data)
                    exitos += 1
                else:
                    print("  ⚪ No se detectó precio (puede ser producto agotado o sin stock).")
                    no_encontrados += 1

        except HTTPError as e:
            if e.code == 404:
                print(f"  ❌ Error 404: Producto no disponible en Amazon.")
            elif e.code == 503:
                print(f"  ⚠️ Error 503: Servicio ocupado. Pausando 10 segundos...")
                time.sleep(10)
            else:
                print(f"  ⚠️ Error HTTP {e.code}.")
            no_encontrados += 1
        except URLError as e:
            print(f"  ⚠️ Error de red: {e.reason}")
            no_encontrados += 1
        except Exception as e:
            print(f"  ⚠️ Error inesperado: {str(e)}")
            no_encontrados += 1

        # Pausa aleatoria prudente para no saturar Amazon (entre 2.0 y 3.8 seg)
        if idx < len(pendientes):
            sleep_time = random.uniform(2.0, 3.8)
            time.sleep(sleep_time)

    print("\n" + "=" * 60)
    print("🏁 Consulta de precios finalizada.")
    print(f"✅ Precios actualizados con éxito: {exitos}")
    print(f"⚪ No disponibles o agotados: {no_encontrados}")
    print("=" * 60)

if __name__ == "__main__":
    main()
