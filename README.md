# 🛍️ BubuStore — Catálogo y Panel de Administración (`amazon-resell`)

Sistema web y conjunto de herramientas en Python/Bash para administrar el inventario de productos, consultar precios de referencia en Amazon México, generar etiquetas térmicas QR, exportar el catálogo en PDF para compartir offline y publicar en redes sociales.

---

## 📂 Estructura Principal del Proyecto

```text
amazon-resell/
├── index.html                      # Catálogo público interactivo (filtros, buscador, rango de folios)
├── admin.html                      # Panel de administración (edición rápida de precios, folios y estado)
├── generador.html                  # Generador web de publicaciones para Facebook / Marketplace
├── server.py                       # Servidor HTTP multihilo expuesto en Red Local (0.0.0.0:8000) y API REST
├── iniciar_servidor.sh             # Script automatizado para levantar/detener el servidor en Red Local (LAN)
├── Iniciar_Servidor_LAN.command    # Acceso directo ejecutable con doble clic desde Finder en macOS
├── generar_catalogo_pdf.py         # Generador del catálogo completo en PDF para compartir offline
├── generar_qr.py                   # Generador de etiquetas térmicas QR (57x45 mm) para artículos sin QR
├── scraper_amazon.py               # Consultor de precios en Amazon México y cálculo automático (-20%)
├── importar_lote.py                # Importador masivo de nuevos lotes de productos e imágenes
├── bubu_facebook_post.py           # App de escritorio (Tkinter) para crear posts e imágenes para Facebook
├── actualizar_sitio.sh             # Script Git para desplegar cambios al sitio público (GitHub Pages)
├── data/
│   ├── productos.json              # Base de datos de productos (ASIN, título, descripción, URL)
│   ├── estado_productos.json       # Estado dinámico (precio venta, precio Amazon, folio, vendido, QR)
│   └── qr/                         # Imágenes PNG individuales de los códigos QR por folio
└── images/                         # Fotografías locales de los productos (<ASIN>_01.jpg ... _05.jpg)
```

---

## 🚀 1. Levantar el Proyecto en Red Local (LAN)

### `iniciar_servidor.sh` y `Iniciar_Servidor_LAN.command`
Automatizan el arranque de `server.py`, liberan el puerto `8000` si estaba ocupado, detectan la dirección IP local de tu Mac en el Wi-Fi, muestran un código QR en la terminal para escanear con el celular y abren el navegador.

#### Formas de ejecución:

1. **Con doble clic desde Finder (macOS):**
   Haz doble clic directamente sobre el archivo **`Iniciar_Servidor_LAN.command`**.

2. **En primer plano (muestra logs en vivo en la terminal):**
   ```bash
   ./iniciar_servidor.sh
   ```

3. **En segundo plano (modo daemon, deja libre la terminal):**
   ```bash
   ./iniciar_servidor.sh --bg
   ```

4. **Detener el servidor que corre en el puerto `8000`:**
   ```bash
   ./iniciar_servidor.sh --stop
   ```

#### Rutas disponibles una vez iniciado:
- **En tu misma Mac:**
  - Catálogo: `http://localhost:8000/index.html`
  - Administración: `http://localhost:8000/admin.html`
  - Generador de Posts: `http://localhost:8000/generador.html`
- **Desde cualquier celular o PC en tu mismo Wi-Fi (`<IP_LOCAL>` p. ej. `192.168.100.215`):**
  - Catálogo: `http://192.168.100.215:8000/index.html`
  - Administración: `http://192.168.100.215:8000/admin.html`
  - Catálogo PDF: `http://192.168.100.215:8000/Catalogo_Productos_BubuStore.pdf`

---

## 📄 2. Generar Catálogo en PDF para Compartir Offline

### `generar_catalogo_pdf.py`
Genera un catálogo visual en formato PDF (tamaño Carta, cuadrícula de `3 × 3` tarjetas por página) con todos los productos disponibles (`vendido != true` y con precio válido mayor a `$0`), ordenados por número de Folio ascendente. Ideal para enviar por WhatsApp, Telegram o correo electrónico.

#### Cómo ejecutarlo:
```bash
# Genera Catalogo_Productos_BubuStore.pdf (en la raíz y en data/)
python3 generar_catalogo_pdf.py

# Opcional: especificar un nombre de archivo personalizado
python3 generar_catalogo_pdf.py Mi_Catalogo_Offline.pdf
```

---

## 🏷️ 3. Generar Etiquetas Térmicas QR de Productos Nuevos

### `generar_qr.py`
Identifica automáticamente todos los productos disponibles que aún **no** tienen código QR (`qr_generado != true` en `data/estado_productos.json`), les asigna números de **Folio consecutivos** a partir del último folio existente, crea los archivos PNG en `data/qr/` apuntando a `https://bubuqro.github.io/resell/?id=<ASIN>` y genera un PDF con formato de etiqueta térmica (`57mm × 45mm`) ordenado numéricamente por folio.

#### Cómo ejecutarlo:
```bash
# Genera el PDF de etiquetas QR y actualiza data/estado_productos.json
python3 generar_qr.py

# Opcional: indicar el nombre del PDF de salida
python3 generar_qr.py 16_11_26_QR_Productos
```

---

## 💰 4. Consultar Precios en Amazon México

### `scraper_amazon.py`
Consulta en Amazon México el precio vigente de los artículos del catálogo, guarda el precio de referencia en `amazon_precio` y calcula automáticamente el precio de venta sugerido con **20% de descuento** (`precio`) dentro de `data/estado_productos.json`.

#### Cómo ejecutarlo:
```bash
# Consultar todos los productos que aún no tienen precio de Amazon registrado
python3 scraper_amazon.py

# Consultar únicamente los productos del último lote importado
python3 scraper_amazon.py --nuevos

# Consultar un único producto por su código ASIN
python3 scraper_amazon.py B0FBQK55F9

# Limitar la consulta a los primeros N productos pendientes
python3 scraper_amazon.py --limit 20

# Forzar la actualización de precios aunque ya tengan uno guardado
python3 scraper_amazon.py --forzar
```

---

## 📦 5. Importar Nuevos Lotes de Productos e Imágenes

### `importar_lote.py`
Importa productos nuevos desde una carpeta exportada (que contenga `productos_completo_both.json` o `productos.json` y sus imágenes), agrega únicamente los ASINs que no existan aún en `data/productos.json` (creando respaldos `.bak` previos) y copia hasta 5 imágenes por producto a la carpeta `images/`.

#### Cómo ejecutarlo:
```bash
# Importar indicando la ruta de la carpeta descargada
python3 importar_lote.py "/ruta/a/carpeta/descargada"

# Opcional: indicar el máximo de imágenes a copiar por producto (ej. 5)
python3 importar_lote.py "/ruta/a/carpeta/descargada" 5
```

---

## 📱 6. Generador de Publicaciones para Facebook (App de Escritorio)

### `bubu_facebook_post.py`
Aplicación gráfica en Python (`Tkinter` + `Pillow`) que permite buscar productos por título o folio (o elegir uno al azar), generar automáticamente el texto persuasivo de venta con enlace directo y crear una tarjeta gráfica lista para copiar al portapapeles y pegar en grupos de Facebook o Marketplace.

#### Cómo ejecutarlo:
```bash
python3 bubu_facebook_post.py
```

---

## ☁️ 7. Publicar Cambios en el Sitio Web (GitHub Pages)

### `actualizar_sitio.sh`
Guarda todos los cambios locales de inventario, folios y precios en Git, crea un commit con fecha/hora actual y los sube a GitHub para actualizar la tienda pública en `https://bubuqro.github.io/resell/`.

#### Cómo ejecutarlo:
```bash
./actualizar_sitio.sh
```

---

## 🔄 Flujo de Trabajo Recomendado

1. **Importar lote nuevo:**
   ```bash
   python3 importar_lote.py "/Volumes/Apple/Descargas/nuevo-lote"
   ```
2. **Obtener precios automáticos de Amazon (-20%):**
   ```bash
   python3 scraper_amazon.py --nuevos
   ```
3. **Revisar o ajustar precios manualmente en el panel Admin:**
   ```bash
   ./iniciar_servidor.sh --bg
   ```
   *(En `admin.html`, escribe el precio o folio y presiona `Enter` para guardar al instante).*
4. **Generar códigos QR y etiquetas térmicas para los productos nuevos:**
   ```bash
   python3 generar_qr.py
   ```
5. **Generar el catálogo PDF actualizado para enviar por WhatsApp/Telegram:**
   ```bash
   python3 generar_catalogo_pdf.py
   ```
6. **Publicar cambios en la tienda en línea (GitHub Pages):**
   ```bash
   ./actualizar_sitio.sh
   ```

