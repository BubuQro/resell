"""
Extracción de precios de Amazon y cálculo del precio de venta de BubuStore.

La regla de venta se configura en data/config_precios.json:

    {
      "tramos": [
        {"hasta": 300,  "descuento": 0.20},
        {"hasta": 1000, "descuento": 0.25},
        {"hasta": null, "descuento": 0.30}
      ],
      "descuento_min": 0.20,
      "descuento_max": 0.30,
      "terminar_en_9": true
    }

El precio final SIEMPRE queda dentro de [descuento_min, descuento_max].
"""

import json
import math
import os
import re

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_FILE = os.path.join(BASE_DIR, "data", "config_precios.json")

CONFIG_DEFAULT = {
    "tramos": [
        {"hasta": 300, "descuento": 0.20},
        {"hasta": 1000, "descuento": 0.25},
        {"hasta": None, "descuento": 0.30},
    ],
    "descuento_min": 0.20,
    "descuento_max": 0.30,
    "terminar_en_9": True,
}


# ── Lectura de precios del HTML de Amazon ─────────────────────
def extract_price(html):
    """
    Busca patrones de precio en el HTML de Amazon México.
    Prioriza el precio real de compra sobre precios tachados o de referencia.
    """
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

    match_whole = re.search(r'class="a-price(?:-symbol)?[^"]*">.*?class="a-price-whole">([^<]+)<', html, re.DOTALL)
    if not match_whole:
        match_whole = re.search(r'class="a-price-whole">([^<]+)<', html)
    match_fraction = re.search(r'class="a-price-fraction">([^<]+)<', html)
    if match_whole:
        whole = match_whole.group(1).replace('.', '').replace(',', '').strip()
        fraction = match_fraction.group(1).strip() if match_fraction else "00"
        if whole.isdigit():
            return f"${whole}.{fraction}"

    # Fallback: primer a-offscreen con símbolo de peso (puede ser un precio tachado)
    for match in re.finditer(r'<span class="a-offscreen">([^<]+)</span>', html):
        p = match.group(1).strip()
        if '$' in p:
            return p

    return None


def is_captcha(html):
    return ('api-services-support@amazon.com' in html or
            'Enter the characters you see below' in html or
            'Ingresa los caracteres que ves a continuación' in html or
            'validateCaptcha' in html)


def parse_precio(valor):
    """'$1,299.00' → 1299.0 ; '' / None / texto inválido → None."""
    if valor is None:
        return None
    if isinstance(valor, (int, float)):
        return float(valor) if valor > 0 else None
    limpio = re.sub(r'[^\d.]', '', str(valor).replace(',', ''))
    if not limpio:
        return None
    try:
        num = float(limpio)
    except ValueError:
        return None
    return num if num > 0 else None


# ── Regla de precio de venta ──────────────────────────────────
def cargar_config(path=None):
    path = path or CONFIG_FILE
    config = dict(CONFIG_DEFAULT)
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                config.update(json.load(f))
        except (OSError, json.JSONDecodeError) as e:
            print(f"⚠️  config_precios.json inválido ({e}); usando valores por defecto.")
    return config


def descuento_para(amazon, config):
    for tramo in config["tramos"]:
        hasta = tramo.get("hasta")
        if hasta is None or amazon < hasta:
            return float(tramo["descuento"])
    return float(config["tramos"][-1]["descuento"])


def calcular_precio_venta(amazon_precio, config=None):
    """
    Devuelve el precio de venta entero (sin centavos) o None si el precio de
    Amazon no es válido. El resultado queda entre (1 - max) y (1 - min) del
    precio de Amazon; si se pide, se ajusta a un número terminado en 9.
    """
    config = config or CONFIG_DEFAULT
    amazon = parse_precio(amazon_precio)
    if amazon is None:
        return None

    d_min = float(config["descuento_min"])
    d_max = float(config["descuento_max"])
    descuento = min(max(descuento_para(amazon, config), d_min), d_max)

    piso = math.ceil(amazon * (1 - d_max))     # precio más bajo permitido
    techo = math.floor(amazon * (1 - d_min))   # precio más alto permitido
    base = int(round(amazon * (1 - descuento)))
    base = min(max(base, piso), techo) if piso <= techo else base

    if config.get("terminar_en_9") and base >= 20:
        # Candidatos terminados en 9 más cercanos al precio base
        abajo = base - ((base - 9) % 10)
        arriba = abajo + 10
        candidatos = sorted(
            (c for c in (abajo, arriba) if piso <= c <= techo),
            key=lambda c: abs(c - base),
        )
        if candidatos:
            return candidatos[0]
    return max(base, 1)
