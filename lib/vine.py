"""
Scraper de Amazon Vine con Playwright (sustituye los pasos manuales de la
extensión amazon-vine-scraper).

Usa la sesión del perfil de Chrome "Luz Yadira" (PERFIL_CHROME): en cada
corrida descifra sus cookies de Amazon y las inyecta en un Chrome propio
(~/.bubustore/chrome-pipeline), sin tocar tu Chrome abierto.

Los extractores JS son los mismos de amazon-vine-scraper/background/service-worker.js
(extractProductListing / extractProductFullDetail).
"""

import contextlib
import io
import json
import os
import random
import re
import shutil
import sqlite3
import subprocess
import tempfile
import time
import urllib.request

from .precios import extract_price, is_captcha

PERFIL_DIR = os.path.expanduser("~/.bubustore/chrome-pipeline")
CHROME_DIR = os.path.expanduser("~/Library/Application Support/Google/Chrome")
PERFIL_CHROME = "Luz Yadira"   # perfil de Chrome con la sesión de Amazon Vine
PAGINAS_MAX = 500

USER_AGENT = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
              '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36')

CAPTCHA_JS = """() => !!(
  document.querySelector('form[action*="validateCaptcha"]') ||
  document.querySelector('#captchacharacters') ||
  /robot\\s*check/i.test(document.title))"""

LISTADO_JS = r"""() => {
  try {
    const products = [];
    const seen = new Set();
    const container =
      document.querySelector('div.a-container.vvp-body') ||
      document.querySelector('.vvp-body') ||
      document.querySelector('#vvp-body') ||
      document.querySelector('[class*="vvp-body"]');
    if (!container) return { products: [], nextPageUrl: null, pageUrl: location.href, noContainer: true };

    for (const el of container.querySelectorAll('[data-asin],[data-item-asin],[data-order-line-item-id]')) {
      const asin = (el.getAttribute('data-asin') || el.getAttribute('data-item-asin') || '').toUpperCase();
      if (!asin || !/^[A-Z0-9]{10}$/.test(asin) || seen.has(asin)) continue;
      const linkEl = el.querySelector('a[href*="/dp/"]') || el.querySelector('a[href*="/gp/product/"]');
      const titleEl = el.querySelector('img') || el.querySelector('[class*="title"]') || el.querySelector('span.a-text-normal');
      seen.add(asin);
      products.push({
        id: asin,
        url: linkEl?.href || `${location.origin}/dp/${asin}`,
        title: titleEl?.alt?.trim() || titleEl?.textContent?.trim() || `Producto ${asin}`,
      });
    }

    if (products.length === 0) {
      for (const link of container.querySelectorAll('a[href*="/dp/"], a[href*="/gp/product/"]')) {
        const href = link.href || '';
        if (!href.includes('amazon.')) continue;
        const m = href.match(/\/dp\/([A-Z0-9]{10})/i) || href.match(/\/gp\/product\/([A-Z0-9]{10})/i);
        if (!m) continue;
        const asin = m[1].toUpperCase();
        if (seen.has(asin)) continue;
        const row = link.closest('tr, li, [class*="item"], [class*="product"], [class*="tile"], div.a-row, div.a-section');
        const imgEl = row?.querySelector('img') || link.querySelector('img');
        const titleSpan = row?.querySelector('[class*="title"], span.a-text-normal, h2, h3, h4');
        seen.add(asin);
        products.push({
          id: asin,
          url: `${location.origin}/dp/${asin}`,
          title: titleSpan?.textContent?.trim() || imgEl?.alt?.trim() || link.textContent?.trim() || `Producto ${asin}`,
        });
      }
    }

    let nextPageUrl = null;
    const candidates = [
      document.querySelector('li.a-last:not(.a-disabled) a'),
      document.querySelector('.a-pagination .a-last:not(.a-disabled) a'),
      document.querySelector('a[aria-label*="iguiente"]'),
      document.querySelector('a[aria-label*="ext"]'),
    ].filter(Boolean);
    for (const el of candidates) {
      if (el.href && el.href !== location.href && !el.closest('.a-disabled')) { nextPageUrl = el.href; break; }
    }
    if (!nextPageUrl) {
      const u = new URL(location.href);
      const cur = parseInt(u.searchParams.get('page') || '1', 10);
      const pag = document.querySelector('.a-pagination') || document.querySelector('[class*="pagination"]');
      if (pag) {
        const last = pag.querySelector('li.a-last, [class*="a-last"]');
        const isLast = last?.classList?.contains('a-disabled') || last?.querySelector('a') === null;
        if (!isLast) { u.searchParams.set('page', cur + 1); nextPageUrl = u.toString(); }
      }
    }
    return { products, nextPageUrl, pageUrl: location.href };
  } catch (err) {
    return { error: err.message, products: [], nextPageUrl: null };
  }
}"""

DETALLE_JS = r"""() => {
  try {
    const titleEl =
      document.getElementById('productTitle') ||
      document.querySelector('h1#title span') ||
      document.querySelector('h1.product-title-word-break') ||
      document.querySelector('[data-feature-name="title"] h1');
    const title = titleEl?.textContent?.trim() || document.title;

    const descParts = [];
    document.querySelectorAll('#feature-bullets li:not(.aok-hidden) span.a-list-item').forEach((el) => {
      const t = el.textContent.trim();
      if (t) descParts.push(t);
    });
    if (descParts.length === 0) {
      const descEl = document.getElementById('productDescription') || document.querySelector('#aplus') ||
                     document.querySelector('[data-feature-name="productDescription"]');
      if (descEl) descParts.push(descEl.textContent.trim().substring(0, 2500));
    }

    const imageUrls = new Set();
    for (const script of document.querySelectorAll('script')) {
      const text = script.textContent;
      if (!text.includes('colorImages') && !text.includes('ImageBlockATF') && !text.includes('"main"')) continue;
      for (const re of [/"hiRes"\s*:\s*"(https?:\/\/[^"]+)"/g, /"large"\s*:\s*"(https?:\/\/[^"]+)"/g]) {
        let m;
        while ((m = re.exec(text)) !== null) {
          if (!m[1].includes('sprite') && !m[1].includes('transparent')) imageUrls.add(m[1]);
        }
      }
    }
    const block = document.getElementById('imageBlock') || document.querySelector('.image-block-wrapper') ||
                  document.querySelector('#imgTagWrapperId');
    (block || document).querySelectorAll('#altImages img, [data-a-image-name] img, .imageThumbnail img, #imageBlock img')
      .forEach((img) => {
        let src = img.getAttribute('data-old-hires') || img.getAttribute('data-a-hires') || img.src || '';
        if (!src.startsWith('http')) return;
        src = src.replace(/\._[A-Z][A-Z0-9_,]*_\./g, '.').replace(/\.+/g, '.');
        if (src.includes('amazon') || src.includes('ssl-images-amazon')) imageUrls.add(src);
      });
    const mainImg = document.getElementById('landingImage') || document.getElementById('imgBlkFront') ||
                    document.querySelector('#main-image-container img') || document.querySelector('.a-dynamic-image');
    if (mainImg) {
      const hi = mainImg.getAttribute('data-old-hires') || mainImg.getAttribute('data-a-hires') || mainImg.src;
      if (hi && hi.startsWith('http')) imageUrls.add(hi);
    }

    const seenBase = new Set();
    const deduped = [];
    for (const url of imageUrls) {
      if (!url || !url.startsWith('http')) continue;
      if (url.includes('sprite') || url.includes('icon') || url.includes('pixel.gif') || url.endsWith('.gif')) continue;
      const base = url.split('?')[0];
      if (!seenBase.has(base)) { seenBase.add(base); deduped.push(url); }
    }
    return { title, description: descParts.join(' | ') || title, imageUrls: deduped };
  } catch (err) {
    return { error: err.message, title: '', description: '', imageUrls: [] };
  }
}"""


def pausa(min_s=1.2, max_s=2.4):
    time.sleep(random.uniform(min_s, max_s))


def resolver_perfil(nombre, chrome_dir=CHROME_DIR):
    """Nombre visible del perfil ("Luz Yadira") → carpeta ("Profile 5")."""
    estado = os.path.join(chrome_dir, "Local State")
    with open(estado, encoding="utf-8") as f:
        perfiles = json.load(f).get("profile", {}).get("info_cache", {})
    for carpeta, info in perfiles.items():
        if nombre in (carpeta, info.get("name")):
            return carpeta
    disponibles = ", ".join(f'"{i.get("name")}"' for i in perfiles.values())
    raise RuntimeError(f'No existe el perfil de Chrome "{nombre}". Disponibles: {disponibles}')


def _clave_chrome():
    """Clave AES de las cookies de Chrome (llavero de macOS: "Chrome Safe Storage")."""
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

    r = subprocess.run(["security", "find-generic-password", "-w", "-s", "Chrome Safe Storage"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError('No se pudo leer "Chrome Safe Storage" del llavero de macOS '
                           '(acepta el aviso del llavero con "Permitir siempre").')
    kdf = PBKDF2HMAC(algorithm=hashes.SHA1(), length=16, salt=b"saltysalt", iterations=1003)
    return kdf.derive(r.stdout.strip().encode())


def _descifrar(valor_cifrado, clave, con_hash):
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    if valor_cifrado[:3] != b"v10":
        return None
    dec = Cipher(algorithms.AES(clave), modes.CBC(b" " * 16)).decryptor()
    datos = dec.update(valor_cifrado[3:]) + dec.finalize()
    datos = datos[:-datos[-1]]          # quitar relleno PKCS7
    if con_hash:                         # DB v24+: 32 bytes de SHA256(dominio) al inicio
        datos = datos[32:]
    return datos.decode("utf-8")


def cookies_de_perfil(nombre, dominio="amazon", chrome_dir=CHROME_DIR):
    """
    Lee y descifra las cookies de `dominio` del perfil de Chrome `nombre`, en el
    formato de Playwright. Chrome no permite automatizar su carpeta principal,
    así que se inyectan en el navegador del pipeline en cada corrida (siempre
    con la sesión más reciente) sin tocar tu Chrome abierto.
    """
    carpeta = resolver_perfil(nombre, chrome_dir)
    origen = os.path.join(chrome_dir, carpeta, "Cookies")
    with tempfile.TemporaryDirectory() as tmp:
        copia = os.path.join(tmp, "Cookies")
        shutil.copy2(origen, copia)       # copia: Chrome mantiene el archivo bloqueado
        con = sqlite3.connect(copia)
        try:
            version = int((con.execute("select value from meta where key='version'").fetchone() or [0])[0])
            filas = con.execute(
                "select host_key, name, value, encrypted_value, path, expires_utc, is_secure, "
                "is_httponly, samesite from cookies where host_key like ?", (f"%{dominio}%",)).fetchall()
        finally:
            con.close()

    clave = _clave_chrome()
    cookies = []
    for host, name, value, enc, path, expires, secure, httponly, samesite in filas:
        try:
            valor = value or _descifrar(enc, clave, version >= 24)
        except Exception:
            valor = None
        if valor is None:
            continue
        same = {0: "None", 2: "Strict"}.get(samesite, "Lax")
        if same == "None" and not secure:
            same = "Lax"
        cookies.append({
            "name": name, "value": valor, "domain": host, "path": path or "/",
            "expires": (expires / 1e6 - 11644473600) if expires else -1,
            "httpOnly": bool(httponly), "secure": bool(secure), "sameSite": same,
        })
    return cookies


@contextlib.contextmanager
def abrir_navegador(headless=False, perfil=PERFIL_CHROME):
    from playwright.sync_api import sync_playwright

    os.makedirs(PERFIL_DIR, exist_ok=True)
    cookies = cookies_de_perfil(perfil) if perfil else []
    with sync_playwright() as pw:
        opciones = dict(
            user_data_dir=PERFIL_DIR,
            headless=headless,
            locale="es-MX",
            viewport={"width": 1280, "height": 900},
            args=["--disable-blink-features=AutomationControlled"],
        )
        ctx = pw.chromium.launch_persistent_context(channel="chrome", **opciones)
        if cookies:
            ctx.add_cookies(cookies)
        try:
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            yield page
        finally:
            ctx.close()


class VineScraper:
    def __init__(self, page, dominio="www.amazon.com.mx", log=print, avisar=None):
        self.page = page
        self.dominio = dominio
        self.log = log
        self.avisar = avisar or (lambda msg: None)

    # ── Navegación con manejo de sesión / captcha ─────────────
    def ir(self, url, espera=(1.5, 2.6)):
        self.page.goto(url, wait_until="domcontentloaded", timeout=45000)
        with contextlib.suppress(Exception):
            self.page.wait_for_load_state("load", timeout=15000)
        pausa(*espera)
        self.resolver_captcha()

    def hay_captcha(self):
        try:
            return self.page.evaluate(CAPTCHA_JS)
        except Exception:
            return False

    def resolver_captcha(self, max_espera=300):
        if not self.hay_captcha():
            return True
        self.log("⚠️  Amazon mostró un Captcha. Resuélvelo en la ventana de Chrome abierta...")
        self.avisar("Amazon pide un Captcha: resuélvelo en la ventana de Chrome.")
        fin = time.time() + max_espera
        while time.time() < fin:
            time.sleep(3)
            if not self.hay_captcha():
                self.log("✅ Captcha superado. Continuando...")
                pausa()
                return True
        raise RuntimeError("Tiempo de espera del Captcha agotado.")

    def url_vine(self, tipo, pagina=None):
        url = f"https://{self.dominio}/vine/vine-reviews?review-type={tipo}"
        return f"{url}&page={pagina}" if pagina else url

    def asegurar_sesion(self, max_espera=900):
        """Abre Vine; si Amazon pide iniciar sesión, espera a que el usuario lo haga."""
        self.ir(self.url_vine("pending_review"))
        if self._en_vine():
            return
        self.log("🔐 Inicia sesión en Amazon (cuenta Vine) en la ventana de Chrome que se abrió...")
        self.avisar("Inicia sesión en Amazon Vine en la ventana de Chrome.")
        fin = time.time() + max_espera
        while time.time() < fin:
            time.sleep(4)
            if "/vine/" in self.page.url and self._en_vine():
                self.log("✅ Sesión iniciada.")
                return
            if "/ap/" not in self.page.url and "/vine/" not in self.page.url:
                # El login terminó y Amazon redirigió a otra página
                with contextlib.suppress(Exception):
                    self.ir(self.url_vine("pending_review"))
        raise RuntimeError("No se detectó la sesión de Amazon Vine (tiempo agotado).")

    def _en_vine(self):
        if "/ap/signin" in self.page.url:
            return False
        try:
            return bool(self.page.query_selector('.vvp-body, #vvp-body, [class*="vvp-body"]'))
        except Exception:
            return False

    # ── Fase 1: listado paginado ──────────────────────────────
    def escanear_listado(self, tipo, excluidos, max_productos=None, corte_temprano=0):
        etiqueta = "Completadas" if tipo == "completed" else "Pendientes"
        aceptados, vistos, visitadas = [], set(), set()
        url, pagina, sin_nuevos, total_excl = self.url_vine(tipo), 1, 0, 0

        while url and pagina <= PAGINAS_MAX:
            if url in visitadas:
                break
            visitadas.add(url)
            self.ir(url, espera=(1.8, 2.8))
            r = self.page.evaluate(LISTADO_JS)
            if r.get("error") or r.get("noContainer"):
                self.log(f"⚠️  [{etiqueta}] Página {pagina}: no se pudo leer el listado "
                         f"({r.get('error') or 'contenedor vvp-body no encontrado'}).")
                break

            nuevos_pag = 0
            for p in r.get("products", []):
                asin = p["id"].upper()
                if asin in vistos:
                    continue
                vistos.add(asin)
                if asin in excluidos:
                    total_excl += 1
                    continue
                aceptados.append({**p, "id": asin, "_pagina": pagina,
                                  "_urlPagina": r.get("pageUrl") or url, "_tipo": tipo})
                nuevos_pag += 1

            self.log(f"📄 [{etiqueta}] Pág {pagina}: {len(r.get('products', []))} productos, {nuevos_pag} nuevos")
            if max_productos and len(aceptados) >= max_productos:
                return aceptados[:max_productos]

            sin_nuevos = 0 if nuevos_pag else sin_nuevos + 1
            if corte_temprano and sin_nuevos >= corte_temprano:
                self.log(f"⏹️  [{etiqueta}] {sin_nuevos} páginas seguidas sin productos nuevos: fin del escaneo.")
                break
            url = r.get("nextPageUrl")
            pagina += 1

        self.log(f"🚫 [{etiqueta}] Omitidos por estar ya en el catálogo: {total_excl}")
        return aceptados

    # ── Fase 2: detalle + URLs de imágenes ────────────────────
    def extraer_detalle(self, producto):
        self.ir(producto["url"])
        d = self.page.evaluate(DETALLE_JS)
        if d.get("error"):
            raise RuntimeError(d["error"])
        html = self.page.content()
        precio = None if is_captcha(html) else extract_price(html)
        return {
            "id": producto["id"],
            "titulo": d.get("title") or producto.get("title") or "",
            "descripcion": d.get("description") or producto.get("title") or "",
            "url": f"https://{self.dominio}/dp/{producto['id']}",
            "paginaEncontrado": producto.get("_pagina"),
            "urlPaginaListado": producto.get("_urlPagina"),
            "tipoResena": producto.get("_tipo"),
            "imagenes": normalizar_imagenes(d.get("imageUrls") or []),
            "amazon_precio": precio,
        }

    # ── Consulta de precio con la sesión del navegador ────────
    def consultar_precio(self, url):
        self.ir(url, espera=(2.0, 3.5))
        html = self.page.content()
        if is_captcha(html):
            return None
        return extract_price(html)


def normalizar_imagenes(urls):
    """Quita los sufijos de tamaño de la CDN (._AC_SX300_.) y elimina duplicados."""
    vistas, salida = set(), []
    for url in urls:
        limpia = re.sub(r"\._[A-Z][A-Z0-9_,]*_\.", ".", url.split("?")[0])
        if limpia not in vistas:
            vistas.add(limpia)
            salida.append(limpia)
    return salida


# ── Descarga de imágenes (CDN pública, sin navegador) ─────────
def descargar_imagenes(pid, urls, destino, maximo=5, log=print):
    """Guarda images/<ASIN>_NN.jpg (convierte a JPEG si llega PNG/WebP)."""
    try:
        from PIL import Image
    except ImportError:
        Image = None

    os.makedirs(destino, exist_ok=True)
    guardadas = 0
    for url in urls:
        if maximo and guardadas >= maximo:
            break
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=20) as resp:
                datos = resp.read()
        except Exception as e:
            log(f"   ⚠️  Imagen no descargada ({e})")
            continue
        if not datos:
            continue
        ruta = os.path.join(destino, f"{pid}_{guardadas + 1:02d}.jpg")
        if datos[:3] == b"\xff\xd8\xff" or Image is None:
            with open(ruta, "wb") as f:
                f.write(datos)
        else:
            try:
                with Image.open(io.BytesIO(datos)) as im:
                    im.convert("RGB").save(ruta, "JPEG", quality=90)
            except Exception as e:
                log(f"   ⚠️  Imagen inválida ({e})")
                continue
        guardadas += 1
        time.sleep(0.2)
    return guardadas
