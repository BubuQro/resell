#!/usr/bin/env python3
"""
Genera un archivo CSV con todos los productos que tienen un código QR asociado.
Columnas: Numero_QR, ID_Producto, Descripcion_Producto
Ordenado ascendentemente por Numero_QR (1 al 182).
"""

import csv
import json
import os
import re

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PRODUCTOS_FILE = os.path.join(BASE_DIR, "data", "productos.json")
ESTADO_FILE = os.path.join(BASE_DIR, "data", "estado_productos.json")
OUTPUT_CSV_ROOT = os.path.join(BASE_DIR, "productos_con_qr.csv")
OUTPUT_CSV_DATA = os.path.join(BASE_DIR, "data", "productos_con_qr.csv")


def clean_text(text: str) -> str:
    if not text:
        return ""
    replacements = {
        "Anidaci?n": "Anidación",
        "anidaci?n": "anidación",
        "El?ctricas": "Eléctricas",
        "el?ctricas": "eléctricas",
        "El?ctrico": "Eléctrico",
        "el?ctrico": "eléctrico",
        "\n": " ",
        "\r": " ",
        "\t": " ",
    }
    for k, v in replacements.items():
        text = text.replace(k, v)
    return re.sub(r"\s+", " ", text).strip()


def generar_csv_qr():
    with open(PRODUCTOS_FILE, "r", encoding="utf-8") as f:
        prod_data = json.load(f)
    products_list = prod_data.get("productos", prod_data) if isinstance(prod_data, dict) else prod_data
    prod_map = {p.get("id"): p for p in products_list if p.get("id")}

    with open(ESTADO_FILE, "r", encoding="utf-8") as f:
        state_data = json.load(f)

    rows = []
    for pid, st in state_data.items():
        folio_str = str(st.get("folio", "")).strip()
        has_qr = st.get("qr_generado") is True or folio_str != ""
        if not has_qr or not folio_str:
            continue

        digits = re.sub(r"\D", "", folio_str)
        folio_num = int(digits) if digits else 999999

        prod = prod_map.get(pid, {})
        titulo = clean_text(prod.get("titulo", ""))
        descripcion = clean_text(prod.get("descripcion", ""))
        # Usar el título descriptivo del producto (igual que en productos_sin_precio.csv)
        texto_producto = titulo if titulo else descripcion

        rows.append((folio_num, folio_str, pid, texto_producto))

    # Ordenar por número de QR ascendente
    rows.sort(key=lambda r: (r[0], r[1]))

    for out_path in (OUTPUT_CSV_ROOT, OUTPUT_CSV_DATA):
        # utf-8-sig incluye BOM para que Excel en macOS/Windows reconozca acentos y ñ automáticamente
        with open(out_path, "w", encoding="utf-8-sig", newline="") as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(["Numero_QR", "ID_Producto", "Descripcion_Producto"])
            for _, folio_str, pid, texto_producto in rows:
                writer.writerow([folio_str, pid, texto_producto])

    print(f"✅ Archivo CSV generado con {len(rows)} productos con QR (ordenados del #{rows[0][1]} al #{rows[-1][1]}):")
    print(f"   • {OUTPUT_CSV_ROOT}")
    print(f"   • {OUTPUT_CSV_DATA}")


if __name__ == "__main__":
    generar_csv_qr()

