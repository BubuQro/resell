#!/usr/bin/env python3
"""
Generador de Catálogo en PDF para compartir offline (BubuStore).
Lee data/productos.json y data/estado_productos.json, filtra todos los
productos disponibles con precio válido (igual que index.html / js/app.js)
y genera un catálogo visual en PDF listo para enviar por WhatsApp/Telegram.
"""

import io
import json
import math
import os
import re
import sys
from datetime import datetime

from PIL import Image
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PRODUCTOS_FILE = os.path.join(BASE_DIR, "data", "productos.json")
ESTADO_FILE = os.path.join(BASE_DIR, "data", "estado_productos.json")
IMAGES_DIR = os.path.join(BASE_DIR, "images")
QR_STORE_PATH = os.path.join(BASE_DIR, "qr_bubustore.png")

STORE_BASE_URL = "https://bubuqro.github.io/resell/"
TELEGRAM_URL = "https://t.me/+FsYQ0AKAyPFmZDIx"

# Paleta de colores idéntica al sitio web (css/style.css)
COLOR_BG = colors.HexColor("#EAEDED")
COLOR_SURFACE = colors.HexColor("#FFFFFF")
COLOR_IMG_BG = colors.HexColor("#F8F8F8")
COLOR_TEXT_PRIMARY = colors.HexColor("#0F1111")
COLOR_TEXT_SECONDARY = colors.HexColor("#565959")
COLOR_HEADER_BG = colors.HexColor("#131921")
COLOR_HEADER_SEC = colors.HexColor("#232F3E")
COLOR_ACCENT = colors.HexColor("#FFD814")
COLOR_ACCENT_BORDER = colors.HexColor("#FCD200")
COLOR_DANGER = colors.HexColor("#B12704")
COLOR_LINK = colors.HexColor("#007185")
COLOR_BORDER = colors.HexColor("#D5D9D9")
COLOR_AMZ_REF_BG = colors.HexColor("#F1F5F9")
COLOR_AMZ_REF_TXT = colors.HexColor("#64748B")
COLOR_TELEGRAM = colors.HexColor("#0088CC")


def clean_latin1_text(text: str) -> str:
    """Limpia emojis y caracteres fuera de Latin-1 para evitar cuadros vacíos en Helvetica."""
    if not text:
        return ""
    replacements = {
        "Anidaci?n": "Anidación",
        "anidaci?n": "anidación",
        "El?ctricas": "Eléctricas",
        "el?ctricas": "eléctricas",
        "El?ctrico": "Eléctrico",
        "el?ctrico": "eléctrico",
        "【": "[",
        "】": "]",
        "“": '"',
        "”": '"',
        "‘": "'",
        "’": "'",
        "—": "-",
        "–": "-",
        "…": "...",
        "•": "-",
        "|": " • ",
        "\n": " ",
        "\r": " ",
        "\t": " ",
    }
    for k, v in replacements.items():
        text = text.replace(k, v)

    # Conservar caracteres imprimibles Latin-1 (incluye acentos, ñ, ¿, ¡, °, $)
    cleaned_chars = []
    for ch in text:
        code = ord(ch)
        if 32 <= code <= 255 or ch in ("•",):
            cleaned_chars.append(ch)
        else:
            cleaned_chars.append(" ")
    cleaned = "".join(cleaned_chars)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    # Limpiar separadores repetidos al inicio
    cleaned = re.sub(r"^[•\-:\"\'\s]+", "", cleaned).strip()
    return cleaned


def clean_description(desc: str, titulo: str, folio: str, pid: str) -> str:
    """Filtra fragmentos de código CSS/JS (.aplus-v2) heredados del scraping de Amazon."""
    if not desc:
        return f"Producto disponible para entrega inmediata (Folio #{folio} • ID: {pid})."
    if ".aplus-v2" in desc or "logShoppableMetrics" in desc or "{ position:" in desc:
        return f"{titulo}. Artículo nuevo disponible para entrega inmediata. Toca la tarjeta para ver galería completa."
    return desc


def wrap_text_lines(c, text: str, font_name: str, font_size: float, max_width: float, max_lines: int):
    """Divide un texto en hasta max_lines líneas ajustadas a max_width con elipsis si excede."""
    text = clean_latin1_text(text)
    if not text:
        return []

    words = text.split(" ")
    lines = []
    current = ""

    for idx, word in enumerate(words):
        test = f"{current} {word}".strip() if current else word
        if c.stringWidth(test, font_name, font_size) <= max_width:
            current = test
        else:
            if len(lines) == max_lines - 1:
                # Última línea permitida: truncar con "..."
                remaining = f"{current} {word}".strip()
                while remaining and c.stringWidth(remaining + "...", font_name, font_size) > max_width:
                    remaining = remaining[:-1].rstrip()
                lines.append((remaining + "...") if remaining else "...")
                return lines
            if current:
                lines.append(current)
                current = word
            else:
                # Palabra individual más larga que el ancho
                cut = word
                while cut and c.stringWidth(cut + "-", font_name, font_size) > max_width:
                    cut = cut[:-1]
                lines.append(cut + "-")
                current = ""

    if current and len(lines) < max_lines:
        lines.append(current)

    return lines


def load_optimized_image(img_path: str, max_px: int = 340) -> ImageReader:
    """Carga y redimensiona la imagen en memoria para mantener el PDF ligero y nítido."""
    with Image.open(img_path) as im:
        if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
            bg = Image.new("RGB", im.size, (248, 248, 248))
            rgba = im.convert("RGBA")
            bg.paste(rgba, mask=rgba.split()[3])
            im = bg
        else:
            im = im.convert("RGB")

        im.thumbnail((max_px, max_px), Image.Resampling.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=82, optimize=True)
        buf.seek(0)
        return ImageReader(buf), im.size


def parse_folio_sort_key(folio_val):
    if not folio_val:
        return (1, 999999, "")
    digits = re.sub(r"\D", "", str(folio_val))
    if digits:
        return (0, int(digits), str(folio_val))
    return (0, 999998, str(folio_val))


def load_available_products():
    with open(PRODUCTOS_FILE, "r", encoding="utf-8") as f:
        prod_data = json.load(f)
    products_list = prod_data.get("productos", prod_data) if isinstance(prod_data, dict) else prod_data

    with open(ESTADO_FILE, "r", encoding="utf-8") as f:
        state_data = json.load(f)

    available = []
    for p in products_list:
        pid = p.get("id")
        if not pid:
            continue
        st = state_data.get(pid, {})
        if st.get("vendido") is True:
            continue
        raw_price = st.get("precio")
        if raw_price is None or str(raw_price).strip() == "":
            continue
        try:
            price_num = int(round(float(str(raw_price).replace("$", "").replace(",", "").strip())))
        except ValueError:
            continue
        if price_num <= 0:
            continue

        available.append({
            "id": pid,
            "titulo": p.get("titulo", "Producto sin título"),
            "descripcion": p.get("descripcion", ""),
            "url": p.get("url") or f"https://www.amazon.com.mx/dp/{pid}",
            "precio": price_num,
            "amazon_precio": st.get("amazon_precio", ""),
            "folio": str(st.get("folio", "")).strip(),
        })

    # Ordenar por número de folio ascendente para fácil localización
    available.sort(key=lambda item: parse_folio_sort_key(item["folio"]))
    return available


def draw_page_header(c, page_w, page_h, total_products, is_first_page=True):
    """Dibuja el encabezado del catálogo inspirado en index.html."""
    if is_first_page:
        header_h = 74
        y_top = page_h - header_h
        c.setFillColor(COLOR_HEADER_BG)
        c.rect(0, y_top, page_w, header_h, fill=1, stroke=0)

        # Franja inferior decorativa
        c.setFillColor(COLOR_HEADER_SEC)
        c.rect(0, y_top, page_w, 4, fill=1, stroke=0)

        # Título principal
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 17)
        c.drawString(22, page_h - 26, "Catálogo de Productos Exclusivos")

        # Subtítulo
        c.setFillColor(colors.HexColor("#CCCCCC"))
        c.setFont("Helvetica", 9.5)
        c.drawString(
            22,
            page_h - 42,
            f"Descubre las mejores ofertas y productos seleccionados  •  {total_products} artículos disponibles",
        )

        # Métodos de pago
        c.setFillColor(COLOR_ACCENT)
        c.setFont("Helvetica-Bold", 8.5)
        c.drawString(
            22,
            page_h - 58,
            "Pagos: Efectivo, Débito y Crédito (Meses sin intereses según tu banco)  •  Haz clic en cualquier producto para verlo online",
        )

        # Botón de Telegram a la derecha
        qr_size = 52
        qr_x = page_w - 22 - qr_size
        qr_y = y_top + 11

        if os.path.exists(QR_STORE_PATH):
            c.setFillColor(colors.white)
            c.roundRect(qr_x - 2, qr_y - 2, qr_size + 4, qr_size + 4, 4, fill=1, stroke=0)
            c.drawImage(QR_STORE_PATH, qr_x, qr_y, width=qr_size, height=qr_size, preserveAspectRatio=True, mask="auto")
            c.linkURL(STORE_BASE_URL, (qr_x - 2, qr_y - 2, qr_x + qr_size + 2, qr_y + qr_size + 2), relative=0)

        btn_w = 132
        btn_h = 22
        btn_x = qr_x - btn_w - 12
        btn_y = page_h - 36
        c.setFillColor(COLOR_TELEGRAM)
        c.roundRect(btn_x, btn_y, btn_w, btn_h, 11, fill=1, stroke=0)
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 8.5)
        c.drawCentredString(btn_x + btn_w / 2, btn_y + 7, "Únete al grupo de Telegram")
        c.linkURL(TELEGRAM_URL, (btn_x, btn_y, btn_x + btn_w, btn_y + btn_h), relative=0)

        # Link del catálogo web debajo del botón
        c.setFillColor(colors.HexColor("#E3F2FD"))
        c.setFont("Helvetica", 7.5)
        c.drawRightString(btn_x + btn_w, btn_y - 12, "Catálogo web: bubuqro.github.io/resell")
        c.linkURL(STORE_BASE_URL, (btn_x, btn_y - 16, btn_x + btn_w, btn_y - 2), relative=0)

        return header_h
    else:
        header_h = 34
        y_top = page_h - header_h
        c.setFillColor(COLOR_HEADER_BG)
        c.rect(0, y_top, page_w, header_h, fill=1, stroke=0)

        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 11)
        c.drawString(22, y_top + 11, "Catálogo de Productos Exclusivos")

        c.setFillColor(COLOR_ACCENT)
        c.setFont("Helvetica-Bold", 8)
        c.drawCentredString(page_w / 2, y_top + 12, "Pagos: Efectivo, Débito y Crédito")

        c.setFillColor(colors.HexColor("#E3F2FD"))
        c.setFont("Helvetica-Bold", 8)
        c.drawRightString(page_w - 22, y_top + 12, "Telegram / Compras  •  bubuqro.github.io/resell")
        c.linkURL(STORE_BASE_URL, (page_w - 220, y_top, page_w - 22, page_h), relative=0)
        return header_h


def draw_page_footer(c, page_w, page_num, total_pages, fecha_str):
    footer_h = 22
    c.setFillColor(COLOR_HEADER_SEC)
    c.rect(0, 0, page_w, footer_h, fill=1, stroke=0)

    c.setFillColor(colors.HexColor("#DDDDDD"))
    c.setFont("Helvetica", 7.5)
    c.drawString(22, 7, f"Catálogo Offline BubuStore  •  Generado el {fecha_str}  •  Precios en MXN")

    c.setFillColor(COLOR_ACCENT)
    c.setFont("Helvetica-Bold", 7.5)
    c.drawCentredString(page_w / 2 + 30, 7, "Ver catálogo interactivo en línea")
    c.linkURL(STORE_BASE_URL, (page_w / 2 - 50, 0, page_w / 2 + 110, footer_h), relative=0)

    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 8)
    c.drawRightString(page_w - 22, 7, f"Página {page_num} de {total_pages}")


def draw_product_card(c, x, y, w, h, product):
    """Dibuja una tarjeta de producto idéntica en estilo a .product-card de index.html."""
    pid = product["id"]
    titulo = product["titulo"]
    descripcion = product["descripcion"]
    precio = product["precio"]
    amz_precio = product["amazon_precio"]
    folio = product["folio"]
    store_item_url = f"{STORE_BASE_URL}?id={pid}"

    # 1. Contenedor principal blanco redondeado
    c.setFillColor(COLOR_SURFACE)
    c.setStrokeColor(COLOR_BORDER)
    c.setLineWidth(0.7)
    c.roundRect(x, y, w, h, 6, fill=1, stroke=1)

    # 2. Área superior de imagen
    img_area_h = h * 0.46
    img_area_y = y + h - img_area_h

    c.saveState()
    path = c.beginPath()
    path.roundRect(x + 0.5, img_area_y, w - 1, img_area_h - 0.5, 5)
    c.clipPath(path, stroke=0)
    c.setFillColor(COLOR_IMG_BG)
    c.rect(x, img_area_y, w, img_area_h, fill=1, stroke=0)
    c.restoreState()

    # Línea divisoria bajo la imagen
    c.setStrokeColor(COLOR_BORDER)
    c.setLineWidth(0.5)
    c.line(x, img_area_y, x + w, img_area_y)

    # Dibujar foto principal (images/<id>_01.jpg)
    img_path = os.path.join(IMAGES_DIR, f"{pid}_01.jpg")
    if os.path.exists(img_path):
        try:
            img_reader, (iw, ih) = load_optimized_image(img_path, max_px=340)
            pad = 8
            avail_w = w - pad * 2
            avail_h = img_area_h - pad * 2
            scale = min(avail_w / iw, avail_h / ih)
            draw_w = iw * scale
            draw_h = ih * scale
            draw_x = x + (w - draw_w) / 2
            draw_y = img_area_y + (img_area_h - draw_h) / 2
            c.drawImage(img_reader, draw_x, draw_y, width=draw_w, height=draw_h, mask="auto")
        except Exception:
            pass

    # 3. Badge "OFERTA" arriba a la izquierda
    badge_h = 13
    badge_w = 38
    badge_x = x + 6
    badge_y = y + h - badge_h - 6
    c.setFillColor(COLOR_DANGER)
    c.roundRect(badge_x, badge_y, badge_w, badge_h, 3, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 6.5)
    c.drawCentredString(badge_x + badge_w / 2, badge_y + 3.8, "OFERTA")

    # 4. Badge de Folio arriba a la derecha
    if folio:
        folio_label = f"Folio #{folio}"
        c.setFont("Helvetica-Bold", 7.2)
        fw = c.stringWidth(folio_label, "Helvetica-Bold", 7.2) + 12
        fx = x + w - fw - 6
        fy = y + h - badge_h - 6
        c.setFillColor(COLOR_HEADER_BG)
        c.setStrokeColor(COLOR_ACCENT)
        c.setLineWidth(0.5)
        c.roundRect(fx, fy, fw, badge_h, 3, fill=1, stroke=1)
        c.setFillColor(COLOR_ACCENT)
        c.drawCentredString(fx + fw / 2, fy + 3.6, folio_label)

    # 5. Contenido inferior de la tarjeta
    pad_x = 8
    content_w = w - pad_x * 2
    cursor_y = img_area_y - 12

    # Título (2 líneas máximo, color azul enlace como en la web)
    title_lines = wrap_text_lines(c, titulo, "Helvetica-Bold", 8.2, content_w, max_lines=2)
    c.setFillColor(COLOR_LINK)
    c.setFont("Helvetica-Bold", 8.2)
    for line in title_lines:
        c.drawString(x + pad_x, cursor_y, line)
        cursor_y -= 10
    if len(title_lines) == 1:
        cursor_y -= 10  # Mantener alineación uniforme

    cursor_y -= 5

    # Precio de venta + precio de referencia Amazon
    price_str = f"{precio:,}"
    c.setFillColor(COLOR_TEXT_PRIMARY)
    c.setFont("Helvetica-Bold", 9.5)
    c.drawString(x + pad_x, cursor_y + 1, "$")
    sym_w = c.stringWidth("$", "Helvetica-Bold", 9.5) + 1
    c.setFont("Helvetica-Bold", 14.5)
    c.drawString(x + pad_x + sym_w, cursor_y, price_str)

    if amz_precio:
        amz_clean = clean_latin1_text(str(amz_precio))
        try:
            amz_num = float(re.sub(r"[^\d.]", "", amz_clean.replace(",", "")))
        except ValueError:
            amz_num = 0.0

        if amz_num > precio:
            ref_label = f"Amazon: {amz_clean}"
            c.setFont("Helvetica", 6.8)
            ref_w = c.stringWidth(ref_label, "Helvetica", 6.8) + 8
            ref_h = 11
            ref_x = x + w - pad_x - ref_w
            ref_y = cursor_y - 1

            c.setFillColor(COLOR_AMZ_REF_BG)
            c.roundRect(ref_x, ref_y, ref_w, ref_h, 2.5, fill=1, stroke=0)
            c.setFillColor(COLOR_AMZ_REF_TXT)
            c.drawString(ref_x + 4, ref_y + 2.8, ref_label)

            # Tachado sobre el monto de Amazon
            prefix_w = c.stringWidth("Amazon: ", "Helvetica", 6.8)
            strike_w = c.stringWidth(amz_clean, "Helvetica", 6.8)
            c.setStrokeColor(colors.HexColor("#94A3B8"))
            c.setLineWidth(0.6)
            c.line(
                ref_x + 4 + prefix_w,
                ref_y + 5.2,
                ref_x + 4 + prefix_w + strike_w,
                ref_y + 5.2,
            )

    cursor_y -= 13

    # Descripción corta (2 líneas máximo)
    clean_desc = clean_description(descripcion, titulo, folio, pid)
    desc_lines = wrap_text_lines(c, clean_desc, "Helvetica", 6.8, content_w, max_lines=2)
    c.setFillColor(COLOR_TEXT_SECONDARY)
    c.setFont("Helvetica", 6.8)
    for line in desc_lines:
        c.drawString(x + pad_x, cursor_y, line)
        cursor_y -= 8.5

    # 6. Botón inferior estilo píldora amarilla (Ver Detalles / ID)
    btn_h = 17
    btn_y = y + 6
    btn_x = x + pad_x
    btn_w = content_w

    c.setFillColor(COLOR_ACCENT)
    c.setStrokeColor(COLOR_ACCENT_BORDER)
    c.setLineWidth(0.6)
    c.roundRect(btn_x, btn_y, btn_w, btn_h, 8.5, fill=1, stroke=1)

    c.setFillColor(COLOR_TEXT_PRIMARY)
    c.setFont("Helvetica-Bold", 7.2)
    btn_text = f"Ver Detalles Online  •  {pid}"
    c.drawCentredString(btn_x + btn_w / 2, btn_y + 5.2, btn_text)

    # Enlace interactivo en toda la tarjeta hacia el producto en el catálogo web
    c.linkURL(store_item_url, (x, y, x + w, y + h), relative=0)


def generar_catalogo_pdf(output_filename="Catalogo_Productos_BubuStore.pdf"):
    products = load_available_products()
    if not products:
        print("No se encontraron productos disponibles con precio válido.")
        return

    output_path_data = os.path.join(BASE_DIR, "data", output_filename)
    output_path_root = os.path.join(BASE_DIR, output_filename)

    page_w, page_h = letter  # 612 x 792 pt
    cols = 3
    rows = 3
    per_page = cols * rows
    total_pages = math.ceil(len(products) / per_page)
    fecha_str = datetime.now().strftime("%d/%m/%Y")

    c = canvas.Canvas(output_path_root, pagesize=letter)
    c.setTitle("Catálogo de Productos Exclusivos - BubuStore")
    c.setAuthor("BubuStore")
    c.setSubject(f"Catálogo Offline con {len(products)} productos disponibles")

    margin_x = 18
    gap_x = 10
    gap_y = 10
    footer_h = 22

    card_w = (page_w - (margin_x * 2) - (gap_x * (cols - 1))) / cols

    for page_idx in range(total_pages):
        is_first = page_idx == 0

        # Fondo general gris claro igual que el sitio web
        c.setFillColor(COLOR_BG)
        c.rect(0, 0, page_w, page_h, fill=1, stroke=0)

        header_h = draw_page_header(c, page_w, page_h, len(products), is_first_page=is_first)
        draw_page_footer(c, page_w, page_idx + 1, total_pages, fecha_str)

        top_pad = 10
        bottom_pad = 10
        avail_grid_h = page_h - header_h - footer_h - top_pad - bottom_pad
        card_h = (avail_grid_h - (gap_y * (rows - 1))) / rows

        batch = products[page_idx * per_page : (page_idx + 1) * per_page]
        for i, prod in enumerate(batch):
            r = i // cols
            col = i % cols
            cx = margin_x + col * (card_w + gap_x)
            cy = page_h - header_h - top_pad - (r + 1) * card_h - r * gap_y
            draw_product_card(c, cx, cy, card_w, card_h, prod)

        c.showPage()

    c.save()

    # Guardar copia también en data/
    with open(output_path_root, "rb") as src, open(output_path_data, "wb") as dst:
        dst.write(src.read())

    size_mb = os.path.getsize(output_path_root) / (1024 * 1024)
    print(f"✅ Catálogo PDF generado exitosamente:")
    print(f"   • Productos incluidos: {len(products)}")
    print(f"   • Páginas: {total_pages}")
    print(f"   • Tamaño del archivo: {size_mb:.2f} MB")
    print(f"   • Ruta principal: {output_path_root}")
    print(f"   • Copia en data/: {output_path_data}")


if __name__ == "__main__":
    out_name = sys.argv[1] if len(sys.argv) > 1 else "Catalogo_Productos_BubuStore.pdf"
    generar_catalogo_pdf(out_name)
