"""
Acceso seguro a data/productos.json y data/estado_productos.json.

• Escritura atómica (archivo .tmp + rename) para que el catálogo o server.py
  nunca lean un JSON a medio escribir.
• actualizar_estado() vuelve a leer el estado justo antes de guardar y solo
  mezcla los campos modificados, para no pisar cambios hechos desde admin.html.
• bloqueo_pipeline() evita dos ejecuciones simultáneas del pipeline.
"""

import contextlib
import fcntl
import json
import os
import shutil
import tempfile

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
PRODUCTOS_FILE = os.path.join(DATA_DIR, "productos.json")
ESTADO_FILE = os.path.join(DATA_DIR, "estado_productos.json")
IMAGES_DIR = os.path.join(BASE_DIR, "images")
CORRIDA_FILE = os.path.join(DATA_DIR, "ultima_corrida.json")
LOCK_FILE = os.path.join(BASE_DIR, ".pipeline.lock")
EXCLUIR_EXTENSION = os.path.join(os.path.dirname(BASE_DIR), "amazon-vine-scraper", "content", "excluir.json")

ESTADO_INICIAL = {"precio": "", "amazon_precio": "", "folio": "", "vendido": False}


def load_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path, 'r', encoding='utf-8') as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return default


def guardar_atomico(path, data, backup=False):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if backup and os.path.exists(path):
        shutil.copyfile(path, path + ".bak")
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".tmp_", suffix=".json")
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def cargar_productos():
    data = load_json(PRODUCTOS_FILE, [])
    if isinstance(data, dict) and "productos" in data:
        data = data["productos"]
    return data if isinstance(data, list) else []


def cargar_estado():
    data = load_json(ESTADO_FILE, {})
    return data if isinstance(data, dict) else {}


def ids_catalogo():
    return {str(p["id"]).upper() for p in cargar_productos() if p.get("id")}


def ids_excluidos_extension(path=None):
    """ASINs de amazon-vine-scraper/content/excluir.json (descartes manuales)."""
    data = load_json(path or EXCLUIR_EXTENSION, [])
    ids = set()
    for item in data if isinstance(data, list) else []:
        if isinstance(item, str):
            ids.add(item.strip().upper())
        elif isinstance(item, dict):
            pid = item.get("id") or item.get("asin") or item.get("ASIN")
            if pid:
                ids.add(str(pid).strip().upper())
    return ids


def limpiar_producto(item):
    """Copia ligera del producto (sin el arreglo de URLs de imágenes)."""
    pid = item["id"]
    return {
        "id": pid,
        "titulo": item.get("titulo") or "Sin título",
        "descripcion": item.get("descripcion", ""),
        "url": item.get("url") or f"https://www.amazon.com.mx/dp/{pid}",
        "paginaEncontrado": item.get("paginaEncontrado", 1),
        "urlPaginaListado": item.get("urlPaginaListado", ""),
        "tipoResena": item.get("tipoResena", ""),
    }


def agregar_productos(items, backup=True):
    """
    Agrega a productos.json los items cuyo ASIN no exista e inicializa su
    estado. Devuelve la lista de productos realmente agregados.
    """
    existentes = cargar_productos()
    ids = {p.get("id") for p in existentes}
    nuevos = []
    for item in items:
        pid = item.get("id")
        if not pid or pid in ids:
            continue
        nuevos.append(limpiar_producto(item))
        ids.add(pid)
    if not nuevos:
        return []

    guardar_atomico(PRODUCTOS_FILE, existentes + nuevos, backup=backup)
    actualizar_estado({p["id"]: {} for p in nuevos}, backup=backup)
    return nuevos


def actualizar_estado(cambios, backup=False):
    """
    cambios = {ASIN: {campo: valor}}. Relee el archivo, inicializa entradas
    nuevas con ESTADO_INICIAL y mezcla solo los campos indicados.
    """
    estado = cargar_estado()
    for pid, campos in cambios.items():
        entrada = estado.setdefault(pid, dict(ESTADO_INICIAL))
        entrada.update(campos)
    guardar_atomico(ESTADO_FILE, estado, backup=backup)
    return estado


@contextlib.contextmanager
def bloqueo_pipeline():
    f = open(LOCK_FILE, 'w')
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        f.close()
        raise RuntimeError("Ya hay otra ejecución del pipeline en curso (.pipeline.lock).")
    try:
        f.write(str(os.getpid()))
        f.flush()
        yield
    finally:
        fcntl.flock(f, fcntl.LOCK_UN)
        f.close()
        with contextlib.suppress(OSError):
            os.remove(LOCK_FILE)
