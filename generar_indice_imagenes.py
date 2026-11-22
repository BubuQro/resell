#!/usr/bin/env python3
"""
Genera data/imagenes.json: la lista de fotos que existen para cada producto.

El catálogo (index.html) usa este índice para mostrar TODAS las fotos de cada
producto sin adivinar nombres de archivo (evita peticiones a fotos inexistentes).
Se ejecuta automáticamente desde actualizar_sitio.sh antes de publicar.

Reglas:
  • Solo archivos images/<ASIN>_<NN>.jpg
  • Se descartan archivos dañados o vacíos
  • Se descartan miniaturas diminutas (lado menor < 200 px), que se ven borrosas
    (solo si Pillow está instalado; si no, se incluyen todas las fotos válidas)

Uso:  python3 generar_indice_imagenes.py
"""
import json
import os
import re
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
IMAGES_DIR = os.path.join(BASE_DIR, "images")
OUTPUT = os.path.join(BASE_DIR, "data", "imagenes.json")
MIN_SIDE = 200
PATTERN = re.compile(r"^([A-Za-z0-9_-]+)_(\d{2,3})\.jpg$")

try:
    from PIL import Image  # opcional
except ImportError:  # pragma: no cover
    Image = None


def es_valida(path):
    if os.path.getsize(path) == 0:
        return False
    if Image is None:
        return True
    try:
        with Image.open(path) as im:
            im.verify()  # detecta archivos dañados
        with Image.open(path) as im:
            return min(im.size) >= MIN_SIDE
    except Exception:
        return False


def main():
    if not os.path.isdir(IMAGES_DIR):
        print("No existe la carpeta images/", file=sys.stderr)
        return 1

    indice = {}
    descartadas = 0
    for nombre in os.listdir(IMAGES_DIR):
        m = PATTERN.match(nombre)
        if not m:
            continue
        if not es_valida(os.path.join(IMAGES_DIR, nombre)):
            descartadas += 1
            continue
        indice.setdefault(m.group(1), []).append(m.group(2))

    for asin in indice:
        indice[asin].sort(key=int)

    os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(dict(sorted(indice.items())), f, separators=(",", ":"))

    total = sum(len(v) for v in indice.values())
    print(f"Índice de imágenes: {len(indice)} productos, {total} fotos "
          f"({descartadas} descartadas por dañadas o diminutas) → data/imagenes.json")
    if Image is None:
        print("  (Pillow no está instalado: no se filtraron miniaturas)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
