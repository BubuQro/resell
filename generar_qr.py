#!/usr/bin/env python3
"""
Generador de códigos QR y plantilla PDF térmica (57x45 mm) para BubuStore.
Filtra los productos disponibles que aún no tienen QR ("qr_generado": true),
les asigna números de Folio/QR consecutivos, los ordena de menor a mayor
y genera el archivo PDF listo para imprimir.
"""

import os
import sys
import json
import shutil
import qrcode
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
QR_DIR = os.path.join(DATA_DIR, "qr")
PRODUCTOS_FILE = os.path.join(DATA_DIR, "productos.json")
ESTADO_FILE = os.path.join(DATA_DIR, "estado_productos.json")
STORE_BASE_URL = "https://bubuqro.github.io/resell/"


def generar_pdf_qr(output_name="4_11_26_QR_Productos.pdf"):
    if not output_name.lower().endswith(".pdf"):
        output_name += ".pdf"

    pdf_data_path = os.path.join(DATA_DIR, output_name)
    pdf_root_path = os.path.join(BASE_DIR, output_name)
    os.makedirs(QR_DIR, exist_ok=True)

    with open(PRODUCTOS_FILE, "r", encoding="utf-8") as f:
        productos = json.load(f)

    with open(ESTADO_FILE, "r", encoding="utf-8") as f:
        estado = json.load(f)

    existing_folios = [
        int(str(st.get("folio", "")).strip())
        for st in estado.values()
        if str(st.get("folio", "")).strip().isdigit()
    ]
    next_folio = (max(existing_folios) if existing_folios else 0) + 1

    pendientes_qr = []
    for p in productos:
        pid = p.get("id")
        if not pid:
            continue
        st = estado.get(pid, {})
        if st.get("vendido") is True or st.get("qr_generado") is True:
            continue

        f_str = str(st.get("folio", "")).strip()
        if f_str.isdigit():
            folio_num = int(f_str)
        else:
            folio_num = next_folio
            next_folio += 1

        pendientes_qr.append((folio_num, pid, p.get("titulo", "")))

    pendientes_qr.sort(key=lambda x: x[0])

    if not pendientes_qr:
        print("✅ Todos los productos disponibles ya cuentan con código QR.")
        return

    PAGE_W = 57 * mm
    PAGE_H = 45 * mm
    QR_SIZE = 26 * mm
    QR_X = (PAGE_W - QR_SIZE) / 2.0
    QR_Y = 17 * mm

    c = canvas.Canvas(pdf_data_path, pagesize=(PAGE_W, PAGE_H))

    for folio_num, pid, _ in pendientes_qr:
        target_url = f"{STORE_BASE_URL}?id={pid}"
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(target_url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")

        qr_filename = f"{folio_num:02d}_{pid}_folio_{folio_num}.png"
        qr_filepath = os.path.join(QR_DIR, qr_filename)
        img.save(qr_filepath)

        if pid not in estado:
            estado[pid] = {}
        estado[pid]["folio"] = str(folio_num)
        estado[pid]["qr_generado"] = True

        c.drawImage(qr_filepath, QR_X, QR_Y, width=QR_SIZE, height=QR_SIZE)
        c.setFont("Helvetica-Bold", 6.5)
        c.drawCentredString(PAGE_W / 2.0, 13.5 * mm, "Escanea para más detalles")
        c.drawCentredString(PAGE_W / 2.0, 10.0 * mm, "y catálogo completo.")
        c.setFont("Helvetica-Bold", 9)
        c.drawCentredString(PAGE_W / 2.0, 2.0 * mm, f"Folio: {folio_num}")
        c.showPage()

    c.save()
    shutil.copyfile(pdf_data_path, pdf_root_path)

    with open(ESTADO_FILE, "w", encoding="utf-8") as f:
        json.dump(estado, f, ensure_ascii=False, indent=2)

    print(f"✅ Generados {len(pendientes_qr)} códigos QR (Folio {pendientes_qr[0][0]} al {pendientes_qr[-1][0]}).")
    print(f"📄 PDF guardado en: {pdf_data_path}")


if __name__ == "__main__":
    nombre = sys.argv[1] if len(sys.argv) > 1 else "4_11_26_QR_Productos.pdf"
    generar_pdf_qr(nombre)

