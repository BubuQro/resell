#!/usr/bin/env python3
"""
Script de importación masiva de productos e imágenes para BubuStore.
Permite importar nuevos productos desde archivos como 'productos_completo_both.json'
y copiar automáticamente sus imágenes a la carpeta 'images/'.
"""

import os
import sys
import json
import shutil

# Rutas del proyecto
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PRODUCTOS_FILE = os.path.join(BASE_DIR, "data", "productos.json")
ESTADO_FILE = os.path.join(BASE_DIR, "data", "estado_productos.json")
IMAGES_DIR = os.path.join(BASE_DIR, "images")

DEFAULT_SOURCE_DIR = "/Volumes/Apple/Descargas/22-10-2026"

def importar_lote(source_dir=DEFAULT_SOURCE_DIR, max_images_per_product=5):
    """
    Importa productos e imágenes desde una carpeta descargada por Amazon Vine Scraper.
    :param source_dir: Carpeta donde se encuentra el JSON y las imágenes.
    :param max_images_per_product: Cantidad máxima de imágenes a copiar por producto (0 para todas).
    """
    print("=" * 60)
    print("📦 BubuStore - Importador de Lote de Productos e Imágenes")
    print("=" * 60)
    print(f"Carpeta origen: {source_dir}")

    if not os.path.exists(source_dir):
        print(f"❌ Error: La carpeta origen no existe: {source_dir}")
        return False

    # Buscar el archivo JSON en la carpeta origen
    posibles_nombres = [
        "productos_completo_both.json",
        "productos_completo_completed.json",
        "productos_completo_pending_review.json",
        "productos.json"
    ]
    json_path = None
    for nombre in posibles_nombres:
        p = os.path.join(source_dir, nombre)
        if os.path.exists(p):
            json_path = p
            break

    if not json_path:
        print(f"❌ Error: No se encontró ningún archivo de productos JSON en {source_dir}")
        return False

    print(f"📄 Archivo JSON encontrado: {os.path.basename(json_path)}")

    with open(json_path, 'r', encoding='utf-8') as f:
        try:
            nuevos_datos = json.load(f)
        except Exception as e:
            print(f"❌ Error al leer el archivo JSON: {e}")
            return False

    if not isinstance(nuevos_datos, list):
        if isinstance(nuevos_datos, dict) and "productos" in nuevos_datos:
            nuevos_datos = nuevos_datos["productos"]
        else:
            print("❌ Formato JSON desconocido.")
            return False

    print(f"Total productos en archivo origen: {len(nuevos_datos)}")

    # Cargar productos existentes
    os.makedirs(os.path.dirname(PRODUCTOS_FILE), exist_ok=True)
    os.makedirs(IMAGES_DIR, exist_ok=True)

    existentes = []
    if os.path.exists(PRODUCTOS_FILE):
        with open(PRODUCTOS_FILE, 'r', encoding='utf-8') as f:
            try:
                existentes = json.load(f)
            except Exception:
                existentes = []

    existentes_ids = {p.get("id") for p in existentes if p.get("id")}
    print(f"Productos actuales en catálogo: {len(existentes_ids)}")

    # Cargar estado actual
    estado_data = {}
    if os.path.exists(ESTADO_FILE):
        with open(ESTADO_FILE, 'r', encoding='utf-8') as f:
            try:
                estado_data = json.load(f)
            except Exception:
                estado_data = {}

    # Filtrar nuevos productos
    productos_a_agregar = []
    for item in nuevos_datos:
        pid = item.get("id")
        if not pid:
            continue
        if pid not in existentes_ids:
            # Crear copia limpia sin el arreglo masivo de URLs para mantener productos.json ligero
            prod_clean = {
                "id": pid,
                "titulo": item.get("titulo", "Sin título"),
                "descripcion": item.get("descripcion", ""),
                "url": item.get("url", f"https://www.amazon.com.mx/dp/{pid}"),
                "paginaEncontrado": item.get("paginaEncontrado", 1),
                "urlPaginaListado": item.get("urlPaginaListado", ""),
                "tipoResena": item.get("tipoResena", "")
            }
            productos_a_agregar.append(prod_clean)
            existentes_ids.add(pid)

    if not productos_a_agregar:
        print("ℹ️ Todos los productos del archivo ya existen en el catálogo. Nada que agregar.")
        return True

    print(f"✨ Se detectaron {len(productos_a_agregar)} productos NUEVOS para importar.")

    # Respaldar archivos actuales
    if os.path.exists(PRODUCTOS_FILE):
        shutil.copyfile(PRODUCTOS_FILE, PRODUCTOS_FILE + ".bak")
    if os.path.exists(ESTADO_FILE):
        shutil.copyfile(ESTADO_FILE, ESTADO_FILE + ".bak")

    # Copiar imágenes
    archivos_origen = set(os.listdir(source_dir))
    imagenes_copiadas = 0

    print("\nCopiando imágenes correspondientes...")
    for idx, prod in enumerate(productos_a_agregar, 1):
        pid = prod["id"]
        
        # Inicializar estado si no existe
        if pid not in estado_data:
            estado_data[pid] = {
                "precio": "",
                "amazon_precio": "",
                "folio": "",
                "vendido": False
            }

        # Buscar imágenes para este producto
        # Formatos: {pid}_01.jpg, {pid}_02.jpg ...
        num = 1
        while True:
            if max_images_per_product > 0 and num > max_images_per_product:
                break
            
            num_str = f"{num:02d}"
            encontrada = False
            for ext in [".jpg", ".jpeg", ".png"]:
                img_name = f"{pid}_{num_str}{ext}"
                if img_name in archivos_origen:
                    src_file = os.path.join(source_dir, img_name)
                    dst_file = os.path.join(IMAGES_DIR, f"{pid}_{num_str}.jpg")
                    shutil.copyfile(src_file, dst_file)
                    imagenes_copiadas += 1
                    encontrada = True
                    break
            
            if not encontrada:
                break
            num += 1

    # Guardar productos.json actualizado
    existentes.extend(productos_a_agregar)
    with open(PRODUCTOS_FILE, 'w', encoding='utf-8') as f:
        json.dump(existentes, f, ensure_ascii=False, indent=2)

    # Guardar estado_productos.json actualizado
    with open(ESTADO_FILE, 'w', encoding='utf-8') as f:
        json.dump(estado_data, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 60)
    print("🎉 ¡IMPORTACIÓN COMPLETADA EXITOSAMENTE!")
    print("=" * 60)
    print(f"✅ Nuevos productos agregados al catálogo: {len(productos_a_agregar)}")
    print(f"✅ Total de productos ahora en catálogo: {len(existentes)}")
    print(f"✅ Nuevas imágenes copiadas a images/: {imagenes_copiadas}")
    print("\nPróximos pasos recomendados:")
    print("1. Ejecuta 'python3 scraper_amazon.py' para obtener los precios de referencia de Amazon.")
    print("2. Entra a http://localhost:8000/admin.html para asignarles Folio y tu Precio de venta.")
    print("3. Ejecuta './actualizar_sitio.sh' para publicar los cambios en internet.")
    print("=" * 60)
    return True

if __name__ == "__main__":
    carpeta = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_SOURCE_DIR
    max_imgs = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    importar_lote(carpeta, max_imgs)
