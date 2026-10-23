import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from PIL import Image, ImageTk, ImageDraw, ImageFont
import requests
import random
import re
import io
import threading
import tempfile
import os
import subprocess
import textwrap

PRODUCTOS_URL = 'https://jaxohua.github.io/bubustore/data/productos.json'
ESTADO_URL    = 'https://jaxohua.github.io/bubustore/data/estado_productos.json'
STORE_BASE_URL = 'https://jaxohua.github.io/bubustore/'

# ─── Control de Versiones ────────────────────────────────────────────────────
APP_VERSION = '1.2.0'
VERSION_HISTORY = [
    {
        "version": "1.2.0",
        "date": "2026-10-23",
        "changes": [
            "🔗 Enlace directo individual al producto con parámetro ?id= para abrir ficha modal.",
            "📋 Extracción y sección dedicada de Especificaciones Técnicas (medidas, material, piezas).",
            "🏷️ Integración de Folio de inventario en el texto y tarjeta.",
            "🔍 Buscador y selector de productos por título o folio, además de modo aleatorio.",
            "📋 Botón específico para copiar el texto formateado para Facebook.",
            "🖼️ Botones para copiar imagen al portapapeles y guardar archivo en disco.",
            "🔤 Ajuste automático de texto (word-wrap) en la tarjeta gráfica para evitar cortes."
        ]
    },
    {
        "version": "1.1.0",
        "date": "2026-09-27",
        "changes": [
            "🖼️ Tarjeta gráfica compuesta (foto + datos) generada con Pillow.",
            "📋 Soporte para copiar imagen compuesta al portapapeles en macOS.",
            "🏷️ Visualización de versión en la interfaz."
        ]
    },
    {
        "version": "1.0.0",
        "date": "2026-09-20",
        "changes": [
            "✨ Versión inicial: Selección aleatoria de productos y generación de texto para Facebook."
        ]
    }
]

# Referencias globales para garbage collector de Tkinter
_tk_preview_img    = None
_composite_img     = None   # PIL Image final de la tarjeta
_current_raw_photo = None   # PIL Image de la foto descargada del producto
_cached_productos  = []
_cached_estado     = {}
_available_items   = []     # Lista de tuplas (prod_dict, estado_dict)

# ─── Fonts del sistema (con fallback) ────────────────────────────────────────
FONT_PATHS = [
    "/System/Library/Fonts/Helvetica.ttc",
    "/System/Library/Fonts/SFNSText.ttf",
    "/System/Library/Fonts/Arial.ttf",
]

def _get_font(size):
    for path in FONT_PATHS:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()

# ─── Fetch data ───────────────────────────────────────────────────────────────
def fetch_data():
    try:
        r1 = requests.get(PRODUCTOS_URL, timeout=10)
        r1.raise_for_status()
        r2 = requests.get(ESTADO_URL, timeout=10)
        r2.raise_for_status()
        return r1.json(), r2.json()
    except Exception as e:
        messagebox.showerror("Error de red", f"No se pudo obtener el catálogo:\n{e}")
        return None, None

# ─── Extracción Inteligente de Beneficios y Especificaciones ─────────────────
def clean_sentence(text):
    text = text.strip()
    text = re.sub(r'^[【\[\s*•\-\*]+', '', text)
    text = re.sub(r'[】\]]\s*:?', ': ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    sentences = re.split(r'(?<=[.!?])\s+', text)
    first = sentences[0].strip()
    if len(first) < 25 and len(sentences) > 1:
        first = (first + ' ' + sentences[1]).strip()
    if len(first) > 160:
        first = first[:157].rsplit(' ', 1)[0] + '...'
    return first.strip()

def extract_benefits_and_specs(product):
    desc = product.get('descripcion', '')
    parts = [p.strip() for p in desc.split('|') if p.strip()]

    spec_keywords = [
        'medid', 'dimens', 'tamañ', 'cm', 'mm', 'metro', 'pulgad', 'diámetro',
        'material', 'fabricad', 'acero', 'aluminio', 'plástic', 'vidrio', 'poliéster', 'cerámic', 'madera', 'tela',
        'incluye', 'paquete', 'contenido', 'piezas', 'unidades', 'kit', 'set', 'recibirás',
        'capacidad', 'litro', 'ml', 'peso', 'kg', 'gram', ' g', 'oz',
        'potencia', 'watt', 'volt', 'batería', 'pila', 'recargable', 'motor',
        'porción', 'porciones', 'ingrediente', 'fórmula', 'ajuste', 'compatible'
    ]

    beneficios = []
    specs = []

    for pt in parts:
        cleaned = clean_sentence(pt)
        if not cleaned:
            continue
        pt_lower = pt.lower()
        is_spec = any(kw in pt_lower for kw in spec_keywords)

        if is_spec and len(specs) < 3:
            specs.append(cleaned)
        elif not is_spec and len(beneficios) < 3:
            beneficios.append(cleaned)

    # Balancear si una lista quedó vacía
    if not specs and len(beneficios) > 1:
        specs.append(beneficios.pop())
    elif not beneficios and len(specs) > 1:
        beneficios.append(specs.pop(0))

    if not beneficios:
        beneficios = ["Excelente calidad y durabilidad comprobada.", "Diseño práctico y funcional para el uso diario."]
    if not specs:
        specs = ["Consultar detalles específicos en la ficha de la tienda."]

    return beneficios[:3], specs[:3]

# ─── Generación de Texto de la Publicación ────────────────────────────────────
def generate_post_data(product, estado):
    ganchos = [
        "✨ ¡Hoy te recomendamos este producto!",
        "🔥 ¡Gran oportunidad en nuestro catálogo!",
        "⭐ ¡Descubre este artículo destacado!",
        "✨ ¡Calidad y excelente precio en BubuStore!",
        "🛍️ ¡No te quedes sin el tuyo!"
    ]
    gancho = random.choice(ganchos)
    titulo = product.get('titulo', 'Producto sin nombre').strip()
    product_id = product.get('id', '')

    # Folio
    folio = estado.get('folio')
    folio_text = f"🏷️ Folio: #{folio}" if folio else ""

    # Precio
    price = estado.get('precio')
    if not price:
        price = estado.get('amazon_precio', 'Consultar por mensaje')
    else:
        try:
            num = round(float(price))
            price = f"${num:,.0f}"
        except Exception:
            price = f"${price}" if not str(price).startswith('$') else str(price)

    # Beneficios y Especificaciones
    beneficios_list, specs_list = extract_benefits_and_specs(product)
    beneficios_str = "\n".join([f"✅ {b}" for b in beneficios_list])
    specs_str = "\n".join([f"🔹 {s}" for s in specs_list])

    # Enlace individual directo con ?id=
    if product_id:
        url_producto = f"{STORE_BASE_URL}?id={product_id}"
        url_line = f"🔗 Ver ficha y disponibilidad en tienda:\n{url_producto}"
    else:
        url_line = f"🔗 Ver en catálogo general:\n{STORE_BASE_URL}\n(Obtenido del catálogo general de BubuStore)"

    # Hashtags
    words = re.findall(r'\b[a-zA-ZáéíóúÁÉÍÓÚñÑ]{5,}\b', titulo)
    hashtags = ["#BubuStore"]
    for w in random.sample(words, min(len(words), 3)):
        hashtags.append(f"#{w.capitalize()}")
    hashtags_str = " ".join(hashtags)

    # Armar texto final
    bloques = [
        f"{gancho}\n{titulo}",
        f"{folio_text}\n💰 Precio: {price}".strip(),
        f"🌟 Beneficios destacados:\n{beneficios_str}",
        f"📋 Especificaciones técnicas:\n{specs_str}",
        url_line,
        "📩 Envíanos mensaje para coordinar tu compra o apartado.",
        hashtags_str
    ]

    post_text = "\n\n".join([b for b in bloques if b.strip()])
    return {
        "text": post_text,
        "gancho": gancho,
        "titulo": titulo,
        "folio": folio,
        "price": price,
        "beneficios": beneficios_list,
        "specs": specs_list,
        "url": f"{STORE_BASE_URL}?id={product_id}" if product_id else STORE_BASE_URL,
        "hashtags": hashtags_str,
        "product_id": product_id
    }

# ─── Crear tarjeta gráfica con Auto Word-Wrap ────────────────────────────────
def create_post_card(product_pil_img, post_info, card_width=660):
    PAD        = 26
    BG         = (255, 255, 255)
    HEADER_BG  = (24, 119, 242)      # Azul Facebook
    TITLE_CLR  = (20, 20, 35)
    SECTION_BG = (242, 245, 250)    # Gris suave para bloques
    TEXT_COLOR = (40, 40, 45)
    MUTED      = (110, 115, 130)

    font_title   = _get_font(20)
    font_bold    = _get_font(15)
    font_body    = _get_font(14)
    font_small   = _get_font(12)

    inner_w = card_width - (PAD * 2)

    # 1. Preparar foto
    if product_pil_img:
        aspect   = product_pil_img.height / max(1, product_pil_img.width)
        photo_w  = card_width
        photo_h  = int(photo_w * aspect)
        photo_h  = min(max(photo_h, 240), 400)
        prod_img = product_pil_img.resize((photo_w, photo_h), Image.LANCZOS)
    else:
        photo_h  = 0
        prod_img = None

    # Función auxiliar para wrap de texto y cálculo de altura
    def wrap_text(text, font, max_px):
        words = text.split()
        if not words:
            return [""]
        lines = []
        cur = []
        dummy = ImageDraw.Draw(Image.new('RGB', (1, 1)))
        for w in words:
            test_line = " ".join(cur + [w])
            bbox = dummy.textbbox((0, 0), test_line, font=font)
            w_px = bbox[2] - bbox[0]
            if w_px <= max_px or not cur:
                cur.append(w)
            else:
                lines.append(" ".join(cur))
                cur = [w]
        if cur:
            lines.append(" ".join(cur))
        return lines

    # Calcular contenido textual estructurado
    # Header gancho
    gancho_lines = wrap_text(post_info["gancho"], font_bold, inner_w)
    title_lines  = wrap_text(post_info["titulo"], font_title, inner_w)

    price_str = f"💰 Precio: {post_info['price']}"
    if post_info['folio']:
        price_str = f"🏷️ Folio: #{post_info['folio']}   |   {price_str}"
    price_lines = wrap_text(price_str, font_bold, inner_w)

    ben_wrapped = []
    for b in post_info["beneficios"]:
        ben_wrapped.extend(wrap_text(f"✅ {b}", font_body, inner_w))

    spec_wrapped = []
    for s in post_info["specs"]:
        spec_wrapped.extend(wrap_text(f"🔹 {s}", font_body, inner_w))

    url_lines = wrap_text(f"🔗 {post_info['url']}", font_small, inner_w)
    cta_lines = wrap_text("📩 Envíanos mensaje para coordinar tu compra.", font_bold, inner_w)
    hash_lines = wrap_text(post_info["hashtags"], font_small, inner_w)

    LINE_H = 22
    total_text_h = (
        len(gancho_lines) * 20 +
        len(title_lines) * 26 + 10 +
        len(price_lines) * 24 + 14 +
        24 + len(ben_wrapped) * LINE_H + 10 +
        24 + len(spec_wrapped) * LINE_H + 12 +
        len(url_lines) * 18 + 8 +
        len(cta_lines) * 22 + 8 +
        len(hash_lines) * 18 + PAD * 2
    )

    total_h = photo_h + total_text_h + 10
    card = Image.new('RGB', (card_width, total_h), BG)
    draw = ImageDraw.Draw(card)

    y = 0
    if prod_img:
        card.paste(prod_img, (0, 0))
        y = photo_h

    # Franja decorativa
    draw.rectangle([(0, y), (card_width, y + 5)], fill=HEADER_BG)
    y += 5 + PAD

    # Dibujar Gancho
    for l in gancho_lines:
        draw.text((PAD, y), l, fill=HEADER_BG, font=font_bold)
        y += 20

    # Dibujar Título
    for l in title_lines:
        draw.text((PAD, y), l, fill=TITLE_CLR, font=font_title)
        y += 26
    y += 6

    # Franja de Precio y Folio
    p_box_h = len(price_lines) * 24 + 10
    draw.rounded_rectangle([(PAD - 8, y), (card_width - PAD + 8, y + p_box_h)], radius=6, fill=SECTION_BG)
    for l in price_lines:
        draw.text((PAD, y + 5), l, fill=(15, 90, 40), font=font_bold)
        y += 24
    y += 14

    # Sección Beneficios
    draw.text((PAD, y), "🌟 Beneficios destacados:", fill=TITLE_CLR, font=font_bold)
    y += 22
    for l in ben_wrapped:
        draw.text((PAD + 6, y), l, fill=TEXT_COLOR, font=font_body)
        y += LINE_H
    y += 8

    # Sección Especificaciones Técnicas
    draw.text((PAD, y), "📋 Especificaciones técnicas:", fill=TITLE_CLR, font=font_bold)
    y += 22
    for l in spec_wrapped:
        draw.text((PAD + 6, y), l, fill=TEXT_COLOR, font=font_body)
        y += LINE_H
    y += 10

    # Enlace
    for l in url_lines:
        draw.text((PAD, y), l, fill=(20, 80, 180), font=font_small)
        y += 18
    y += 6

    # CTA
    for l in cta_lines:
        draw.text((PAD, y), l, fill=HEADER_BG, font=font_bold)
        y += 22
    y += 6

    # Hashtags
    for l in hash_lines:
        draw.text((PAD, y), l, fill=MUTED, font=font_small)
        y += 18

    # Borde sutil exterior
    draw.rectangle([(0, 0), (card_width - 1, total_h - 1)], outline=(215, 220, 230), width=1)
    return card

# ─── Funciones de Portapapeles (Texto / Imagen / Guardar) ─────────────────────
def copy_text_to_clipboard(root, text, status_var):
    if not text.strip():
        messagebox.showwarning("Vacío", "No hay texto generado para copiar.")
        return
    root.clipboard_clear()
    root.clipboard_append(text)
    root.update()
    status_var.set("✅ ¡Texto copiado al portapapeles! Listo para pegar en Facebook.")

def copy_image_to_clipboard(pil_img, status_var):
    if pil_img is None:
        messagebox.showwarning("Vacío", "No hay imagen disponible para copiar.")
        return
    with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as f:
        tmp_path = f.name
    try:
        pil_img.save(tmp_path, 'PNG')
        subprocess.run(
            ['osascript', '-e',
             f'set the clipboard to (read (POSIX file "{tmp_path}") as «class PNGf»)'],
            check=True, capture_output=True
        )
        status_var.set("✅ ¡Imagen copiada al portapapeles! Pégala con ⌘V.")
    except Exception as e:
        status_var.set(f"❌ Error al copiar imagen: {e}")
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass

def save_image_to_file(pil_img, default_name, status_var):
    if pil_img is None:
        messagebox.showwarning("Vacío", "No hay imagen generada para guardar.")
        return
    path = filedialog.asksaveasfilename(
        defaultextension=".png",
        filetypes=[("PNG Image", "*.png"), ("JPEG Image", "*.jpg"), ("Todos los archivos", "*.*")],
        initialfile=f"{default_name}.png"
    )
    if path:
        try:
            pil_img.save(path)
            status_var.set(f"💾 Imagen guardada correctamente en:\n{os.path.basename(path)}")
            messagebox.showinfo("Guardado", f"Imagen guardada en:\n{path}")
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo guardar la imagen:\n{e}")

# ─── Modal de Control de Versiones ───────────────────────────────────────────
def show_version_history(parent):
    dlg = tk.Toplevel(parent)
    dlg.title(f"Historial de Versiones · v{APP_VERSION}")
    dlg.geometry("520x420")
    dlg.configure(bg="#121220")
    dlg.transient(parent)
    dlg.grab_set()

    lbl = tk.Label(dlg, text=f"📦 BubuStore Post Generator — v{APP_VERSION}",
                   font=("Arial", 13, "bold"), fg="#e0e0ff", bg="#121220")
    lbl.pack(pady=(16, 8))

    txt = tk.Text(dlg, bg="#1a1a2e", fg="#d0d0e0", font=("Arial", 11),
                  padx=12, pady=12, wrap=tk.WORD, bd=0, highlightthickness=0)
    txt.pack(expand=True, fill=tk.BOTH, padx=16, pady=(0, 12))

    for item in VERSION_HISTORY:
        txt.insert(tk.END, f"Versión {item['version']}  ({item['date']})\n", "h_ver")
        for ch in item['changes']:
            txt.insert(tk.END, f"  • {ch}\n")
        txt.insert(tk.END, "\n")

    txt.tag_config("h_ver", foreground="#60a5fa", font=("Arial", 11, "bold"))
    txt.configure(state=tk.DISABLED)

    btn = tk.Button(dlg, text="Cerrar", command=dlg.destroy,
                    bg="#3a3aff", fg="white", padx=16, pady=6, relief=tk.FLAT)
    btn.pack(pady=(0, 14))

# ─── Mostrar preview en Canvas ───────────────────────────────────────────────
def show_preview(canvas, pil_card):
    global _tk_preview_img
    cw = canvas.winfo_width()  or 580
    ch = canvas.winfo_height() or 460
    scale  = min(cw / pil_card.width, ch / pil_card.height, 1.0)
    new_w  = max(1, int(pil_card.width  * scale))
    new_h  = max(1, int(pil_card.height * scale))
    thumb  = pil_card.resize((new_w, new_h), Image.LANCZOS)
    _tk_preview_img = ImageTk.PhotoImage(thumb)
    canvas.delete("all")
    canvas.create_image(cw // 2, ch // 2, image=_tk_preview_img, anchor=tk.CENTER)

# ─── Aplicación Principal ─────────────────────────────────────────────────────
class BubuPostApp:
    def __init__(self, root):
        self.root = root
        self.root.title(f"Generador de Publicaciones Facebook · BubuStore v{APP_VERSION}")
        self.root.geometry("860x720")
        self.root.minsize(760, 620)
        self.root.configure(bg="#0d0d18")

        self.status_var = tk.StringVar(value="Cargando catálogo...")
        self.current_post_info = None

        self._setup_style()
        self._build_header()
        self._build_search_bar()
        self._build_notebook()
        self._build_action_buttons()
        self._build_footer()

        # Iniciar carga de datos en segundo plano
        threading.Thread(target=self._initial_load, daemon=True).start()

    def _setup_style(self):
        style = ttk.Style()
        style.theme_use('default')
        style.configure("TNotebook", background="#0d0d18", borderwidth=0)
        style.configure("TNotebook.Tab", background="#1a1a2e", foreground="#b0b0d0",
                        padding=[14, 6], font=("Arial", 11))
        style.map("TNotebook.Tab",
                  background=[("selected", "#2a2a4e")],
                  foreground=[("selected", "#ffffff")])

    def _build_header(self):
        hdr = tk.Frame(self.root, bg="#0d0d18")
        hdr.pack(fill=tk.X, padx=16, pady=(10, 4))

        title = tk.Label(hdr, text="🛍️ BubuStore · Generador de Publicaciones Facebook",
                         font=("Arial", 14, "bold"), fg="#e0e0ff", bg="#0d0d18")
        title.pack(side=tk.LEFT)

        btn_ver = tk.Button(hdr, text=f"v{APP_VERSION} ℹ️", font=("Arial", 9, "bold"),
                            fg="#7080b0", bg="#18182c", activebackground="#2a2a48",
                            activeforeground="#ffffff", relief=tk.FLAT, padx=8, pady=3,
                            cursor="hand2", command=lambda: show_version_history(self.root))
        btn_ver.pack(side=tk.RIGHT)

    def _build_search_bar(self):
        sf = tk.Frame(self.root, bg="#16162a", padx=12, pady=8,
                      highlightbackground="#242442", highlightthickness=1)
        sf.pack(fill=tk.X, padx=16, pady=(0, 8))

        lbl_s = tk.Label(sf, text="🔍 Buscar Producto / Folio:", font=("Arial", 10, "bold"),
                         fg="#a0a0c8", bg="#16162a")
        lbl_s.pack(side=tk.LEFT, padx=(0, 8))

        self.search_entry = tk.Entry(sf, font=("Arial", 11), bg="#22223c", fg="#ffffff",
                                     insertbackground="white", bd=0, relief=tk.FLAT)
        self.search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8), ipady=4)
        self.search_entry.bind("<Return>", lambda e: self._on_search_select())

        self.btn_search = tk.Button(sf, text="Buscar", font=("Arial", 10),
                                    bg="#2563eb", fg="white", activebackground="#1d4ed8",
                                    relief=tk.FLAT, padx=12, pady=4, cursor="hand2",
                                    command=self._on_search_select)
        self.btn_search.pack(side=tk.LEFT, padx=(0, 8))

        self.btn_random = tk.Button(sf, text="🎲 Aleatorio", font=("Arial", 10, "bold"),
                                    bg="#059669", fg="white", activebackground="#047857",
                                    relief=tk.FLAT, padx=14, pady=4, cursor="hand2",
                                    command=self._generate_random)
        self.btn_random.pack(side=tk.LEFT)

    def _build_notebook(self):
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(expand=True, fill=tk.BOTH, padx=16, pady=(0, 8))

        # Tab 1: Texto formateado
        self.tab_text = tk.Frame(self.notebook, bg="#141424")
        self.notebook.add(self.tab_text, text="  📝 Texto de la Publicación  ")

        txt_frame = tk.Frame(self.tab_text, bg="#141424", padx=10, pady=10)
        txt_frame.pack(expand=True, fill=tk.BOTH)

        scroll = tk.Scrollbar(txt_frame)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self.text_widget = tk.Text(txt_frame, wrap=tk.WORD, font=("Arial", 12),
                                   bg="#1a1a2e", fg="#e8e8ff", insertbackground="white",
                                   bd=0, padx=12, pady=12, yscrollcommand=scroll.set)
        self.text_widget.pack(expand=True, fill=tk.BOTH)
        scroll.config(command=self.text_widget.yview)

        # Tab 2: Vista previa de tarjeta gráfica
        self.tab_card = tk.Frame(self.notebook, bg="#141424")
        self.notebook.add(self.tab_card, text="  🖼️ Tarjeta Gráfica Compuesta  ")

        card_frame = tk.Frame(self.tab_card, bg="#141424", padx=8, pady=8)
        card_frame.pack(expand=True, fill=tk.BOTH)

        self.canvas = tk.Canvas(card_frame, bg="#16162a", bd=0, highlightthickness=0)
        self.canvas.pack(expand=True, fill=tk.BOTH)
        self.canvas.create_text(380, 220, text="📸 La tarjeta gráfica aparecerá aquí",
                                fill="#404066", font=("Arial", 13))

    def _build_action_buttons(self):
        bf = tk.Frame(self.root, bg="#0d0d18")
        bf.pack(fill=tk.X, padx=16, pady=(0, 6))

        # Copiar texto
        self.btn_copy_text = tk.Button(bf, text="📋 Copiar Texto",
                                       font=("Arial", 11, "bold"),
                                       bg="#1d4ed8", fg="white", activebackground="#1e40af",
                                       relief=tk.FLAT, padx=14, pady=8, cursor="hand2",
                                       state=tk.DISABLED,
                                       command=self._copy_text)
        self.btn_copy_text.pack(side=tk.LEFT, padx=(0, 8))

        # Copiar imagen
        self.btn_copy_img = tk.Button(bf, text="🖼️ Copiar Tarjeta",
                                      font=("Arial", 11, "bold"),
                                      bg="#047857", fg="white", activebackground="#065f46",
                                      relief=tk.FLAT, padx=14, pady=8, cursor="hand2",
                                      state=tk.DISABLED,
                                      command=self._copy_card_image)
        self.btn_copy_img.pack(side=tk.LEFT, padx=(0, 8))

        # Guardar imagen
        self.btn_save_img = tk.Button(bf, text="💾 Guardar Imagen",
                                      font=("Arial", 11),
                                      bg="#4338ca", fg="white", activebackground="#3730a3",
                                      relief=tk.FLAT, padx=14, pady=8, cursor="hand2",
                                      state=tk.DISABLED,
                                      command=self._save_card_image)
        self.btn_save_img.pack(side=tk.LEFT, padx=(0, 8))

        # Copiar foto cruda
        self.btn_copy_photo = tk.Button(bf, text="📸 Copiar Solo Foto",
                                        font=("Arial", 10),
                                        bg="#374151", fg="white", activebackground="#1f2937",
                                        relief=tk.FLAT, padx=12, pady=8, cursor="hand2",
                                        state=tk.DISABLED,
                                        command=self._copy_raw_photo)
        self.btn_copy_photo.pack(side=tk.RIGHT)

    def _build_footer(self):
        foot = tk.Frame(self.root, bg="#080812")
        foot.pack(fill=tk.X, side=tk.BOTTOM)

        tk.Label(foot, textvariable=self.status_var, font=("Arial", 10),
                 fg="#8080a0", bg="#080812", anchor=tk.W, padx=14, pady=6).pack(fill=tk.X)

    # ─── Lógica de Datos ──────────────────────────────────────────────────────
    def _initial_load(self):
        global _cached_productos, _cached_estado, _available_items
        self.status_var.set("⏳ Descargando catálogo de BubuStore...")
        prods, est = fetch_data()
        if not prods or not est:
            self.status_var.set("❌ Error al conectar con BubuStore. Intenta de nuevo.")
            return

        _cached_productos = prods
        _cached_estado    = est

        _available_items = [
            (p, est.get(p.get('id'), {}))
            for p in prods
            if not est.get(p.get('id'), {}).get('vendido')
        ]

        count = len(_available_items)
        self.root.after(0, lambda: self.status_var.set(
            f"✅ Catálogo listo: {count} productos disponibles. Haz clic en '🎲 Aleatorio' o busca uno."
        ))
        # Generar primer producto automáticamente
        if _available_items:
            self.root.after(200, self._generate_random)

    def _generate_random(self):
        global _available_items
        if not _available_items:
            messagebox.showinfo("Catálogo", "No hay productos disponibles actualmente.")
            return
        item = random.choice(_available_items)
        self._process_product(item[0], item[1])

    def _on_search_select(self):
        global _available_items
        q = self.search_entry.get().strip().lower()
        if not q:
            self._generate_random()
            return

        # Buscar coincidencia por folio o título
        matches = []
        for p, est in _available_items:
            folio_str = str(est.get('folio', '')).lower()
            titulo_str = p.get('titulo', '').lower()
            if q == folio_str or f"#{q}" == folio_str or q in titulo_str or q in p.get('id', '').lower():
                matches.append((p, est))

        if not matches:
            messagebox.showinfo("Búsqueda", f"No se encontró ningún producto disponible para '{q}'.")
            return

        # Si hay varios, elegir el primero o mostrar opción
        self._process_product(matches[0][0], matches[0][1])

    def _process_product(self, prod, est):
        self.status_var.set(f"⏳ Procesando producto: {prod.get('titulo', '')[:40]}...")
        self.btn_random.configure(state=tk.DISABLED)
        self.btn_search.configure(state=tk.DISABLED)

        def _task():
            global _composite_img, _current_raw_photo
            post_info = generate_post_data(prod, est)
            self.current_post_info = post_info

            # Descargar imagen
            product_id = prod.get('id', '')
            img_url = f"{STORE_BASE_URL}images/{product_id}_01.jpg" if product_id else ""
            raw_pil = None
            if img_url:
                try:
                    resp = requests.get(img_url, timeout=10)
                    if resp.status_code == 200:
                        raw_pil = Image.open(io.BytesIO(resp.content)).convert('RGB')
                except Exception:
                    raw_pil = None

            _current_raw_photo = raw_pil
            card = create_post_card(raw_pil, post_info)
            _composite_img = card

            def _update_ui():
                # Actualizar texto
                self.text_widget.delete("1.0", tk.END)
                self.text_widget.insert(tk.END, post_info["text"])

                # Actualizar preview de tarjeta
                show_preview(self.canvas, card)

                # Activar botones
                self.btn_copy_text.configure(state=tk.NORMAL)
                self.btn_copy_img.configure(state=tk.NORMAL)
                self.btn_save_img.configure(state=tk.NORMAL)
                self.btn_copy_photo.configure(state=tk.NORMAL if raw_pil else tk.DISABLED)
                self.btn_random.configure(state=tk.NORMAL)
                self.btn_search.configure(state=tk.NORMAL)

                folio_part = f" (Folio #{post_info['folio']})" if post_info['folio'] else ""
                self.status_var.set(f"✅ Publicación lista{folio_part}: {prod.get('titulo', '')[:50]}")

            self.root.after(0, _update_ui)

        threading.Thread(target=_task, daemon=True).start()

    def _copy_text(self):
        text = self.text_widget.get("1.0", tk.END).strip()
        copy_text_to_clipboard(self.root, text, self.status_var)

    def _copy_card_image(self):
        global _composite_img
        copy_image_to_clipboard(_composite_img, self.status_var)

    def _copy_raw_photo(self):
        global _current_raw_photo
        copy_image_to_clipboard(_current_raw_photo, self.status_var)

    def _save_card_image(self):
        global _composite_img
        pid = self.current_post_info.get("product_id", "post_bubustore") if self.current_post_info else "post_bubustore"
        save_image_to_file(_composite_img, f"bubustore_{pid}", self.status_var)

def main():
    root = tk.Tk()
    app = BubuPostApp(root)
    root.mainloop()

if __name__ == '__main__':
    main()
