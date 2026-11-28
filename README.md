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
├── pipeline_vine.py                # ⭐ Pipeline automático: Vine → imágenes → catálogo → precios (un solo comando)
├── Actualizar_Productos.command    # Doble clic para ejecutar pipeline_vine.py
├── lib/                            # Módulos compartidos (catalogo.py, precios.py, vine.py)
├── launchd/                        # Tarea programada diaria de macOS (opcional)
├── tests/                          # Pruebas: python3 -m unittest discover -s tests
├── scraper_amazon.py               # Consultor de precios en Amazon México y cálculo automático (20–30 % menos)
├── importar_lote.py                # Importador masivo de nuevos lotes de productos e imágenes
├── bubu_facebook_post.py           # App de escritorio (Tkinter) para crear posts e imágenes para Facebook
├── actualizar_sitio.sh             # Script Git para desplegar cambios al sitio público (GitHub Pages)
├── data/
│   ├── productos.json              # Base de datos de productos (ASIN, título, descripción, URL)
│   ├── estado_productos.json       # Estado dinámico (precio venta, precio Amazon, folio, vendido, QR)
│   ├── config_precios.json         # Regla de descuento por tramos (20–30 %)
│   ├── ultima_corrida.json         # Resumen del último lote importado (local, no se publica)
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
Consulta en Amazon México el precio vigente de los artículos del catálogo, guarda el precio de referencia en `amazon_precio` y calcula automáticamente el precio de venta sugerido con **20–30 % de descuento** según `data/config_precios.json` (`precio`; no pisa un precio ya capturado salvo con `--forzar`) dentro de `data/estado_productos.json`.

#### Cómo ejecutarlo:
```bash
# Consultar todos los productos que aún no tienen precio de Amazon registrado
python3 scraper_amazon.py

# Consultar únicamente los productos del último lote importado (data/ultima_corrida.json)
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

## ⭐ 0. Actualización automática desde Amazon Vine (`pipeline_vine.py`)

Sustituye los pasos manuales *extensión → Escanear → Imágenes → `importar_lote.py` → `scraper_amazon.py` → actualizar `excluir.json`*.

```bash
python3 pipeline_vine.py                  # corrida completa (pendientes + completadas)
python3 pipeline_vine.py --dry-run        # solo muestra los ASINs nuevos, no escribe nada
python3 pipeline_vine.py --max 10         # máximo 10 productos nuevos
python3 pipeline_vine.py --corte-temprano 3   # deja de paginar tras 3 páginas sin nuevos
python3 pipeline_vine.py --solo-precios   # solo reintenta los productos sin precio
python3 pipeline_vine.py --qr --publicar  # además folios + PDF QR y sube a GitHub Pages
```
O doble clic en **`Actualizar_Productos.command`**.

**Qué hace:**
1. Excluye automáticamente los ASINs que ya están en `data/productos.json` (y los de `amazon-vine-scraper/content/excluir.json`).
2. Recorre Vine con Chrome (Playwright) y, por cada producto nuevo, en una sola visita obtiene título, descripción, imágenes HD y precio de Amazon.
3. Descarga hasta 5 fotos a `images/<ASIN>_NN.jpg`, da de alta el producto y le asigna el precio de venta. Cada producto se guarda al momento: si se interrumpe (Ctrl+C), la siguiente corrida continúa donde quedó.
4. Reintenta en cada corrida los productos que quedaron sin precio y regenera `data/imagenes.json`.
5. Avisa con una notificación de macOS al terminar (o si Amazon pide Captcha / inicio de sesión).

**Sesión de Amazon:** siempre se usa el perfil de Chrome **"Luz Yadira"** (constante `PERFIL_CHROME` en `lib/vine.py`, o `--perfil "Otro"`). En cada corrida se descifran sus cookies de Amazon (clave del llavero "Chrome Safe Storage"; la primera vez macOS pide permiso: elige **Permitir siempre**) y se inyectan en un Chrome propio (`~/.bubustore/chrome-pipeline`), sin tocar tu Chrome abierto. Si la sesión expira, vuelve a iniciar sesión en Amazon dentro de tu perfil "Luz Yadira" normal.

**Regla de precio (`data/config_precios.json`):** menos de $300 → 20 %, $300–$999 → 25 %, $1,000 o más → 30 %, ajustado a un precio terminado en 9 sin salir del rango 20–30 %. Los productos con precio de Amazon menor a $50 se marcan "por revisar". Los productos sin precio no aparecen en el catálogo público hasta que tengan uno.

**Ejecución diaria automática (opcional):**
```bash
cp launchd/com.bubustore.pipeline.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.bubustore.pipeline.plist
```
Corre todos los días a las 7:00 sin publicar; revisa en `admin.html` y publica con `./actualizar_sitio.sh` (o agrega `--publicar` al `.plist`). Logs en `logs/`.

---

## 🔄 Flujo de Trabajo Recomendado

> **Nuevo:** los pasos 1 y 2 los hace solo `python3 pipeline_vine.py` (ver sección 0). El flujo manual sigue disponible.

1. **Importar lote nuevo:**
   ```bash
   python3 importar_lote.py "/Volumes/Apple/Descargas/nuevo-lote"
   ```
2. **Obtener precios automáticos de Amazon (20–30 % menos):**
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


---

## 🔒 Seguridad del Repositorio

El repositorio es público (GitHub Pages), así que hay tres protecciones:

1. **`.gitignore`**: nunca se suben `data/facebook_config.json` (token de Facebook), `.env`, llaves, logs, PIDs, respaldos `.bak` ni los binarios de `GeneradorPubs/`.
2. **Hook `.githooks/pre-commit`**: bloquea el commit si detecta tokens/llaves en el contenido, archivos prohibidos o archivos de más de 50 MB. `actualizar_sitio.sh` lo activa solo (`git config core.hooksPath .githooks`); si clonas el repo en otra Mac, ejecuta ese comando una vez.
3. **`server.py`**: no sirve `.git/`, el token, scripts ni logs; rechaza peticiones de otros sitios web (CSRF); y la configuración/publicación de Facebook solo funciona desde la Mac que ejecuta el servidor (desde el celular se ve error 403).

> Si alguna vez un token llega a subirse por error, **revócalo de inmediato** en Facebook Developers: borrarlo del repo no basta porque queda en el historial.

---

## 🎨 Estilos y botón "Lo quiero"

- **Dos estilos:** BubuStore (predeterminado) y Clásico. El botón "Estilo…" del encabezado cambia entre ambos; la elección se recuerda en cada navegador (`js/theme.js`, colores en `css/style.css`).
- **"Lo quiero"** copia un mensaje con el folio, el precio y el enlace del producto, y abre el grupo de Telegram para pegarlo. Si quieres que abra un chat directo con el mensaje ya escrito, pon tu usuario de Telegram (sin `@`) en `TELEGRAM_USERNAME`, al inicio de `js/app.js`.
- **Enlaces compartibles:** `index.html?id=<ASIN>` abre directamente el detalle del producto (el botón "Compartir" del detalle los genera).
