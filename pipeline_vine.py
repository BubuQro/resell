#!/usr/bin/env python3
"""
Pipeline automático BubuStore: Amazon Vine → catálogo con precio de venta.

Un solo comando sustituye: extensión (Escanear + Imágenes) → importar_lote.py
→ scraper_amazon.py → actualizar excluir.json.

  1. Toma como exclusión los ASINs que ya están en data/productos.json
     (+ los descartes manuales de amazon-vine-scraper/content/excluir.json).
  2. Recorre Vine (completadas y/o pendientes) y detecta los productos nuevos.
  3. Por cada nuevo: título, descripción, imágenes HD y precio de Amazon,
     en una sola visita a la página del producto.
  4. Descarga hasta N imágenes a images/<ASIN>_NN.jpg y lo da de alta
     (productos.json + estado_productos.json) de inmediato → reanudable.
  5. Precio de venta 20–30 % debajo de Amazon (data/config_precios.json).
  6. Reintenta el precio de los productos que quedaron sin precio.
  7. Regenera data/imagenes.json.  Opcional: --qr  y  --publicar.

Uso:
  python3 pipeline_vine.py                 # corrida completa (ambos tipos)
  python3 pipeline_vine.py --dry-run       # solo lista los ASINs nuevos
  python3 pipeline_vine.py --max 10        # máximo 10 productos nuevos
  python3 pipeline_vine.py --solo-precios  # solo reintenta precios faltantes
  python3 pipeline_vine.py --qr --publicar # además folios/QR y GitHub Pages

Usa la sesión del perfil de Chrome "Luz Yadira" (se copia en cada corrida).
"""

import argparse
import datetime as dt
import logging
import os
import subprocess
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from lib import catalogo  # noqa: E402
from lib.precios import calcular_precio_venta, cargar_config, parse_precio  # noqa: E402

LOG_DIR = os.path.join(BASE_DIR, "logs")
log = logging.getLogger("pipeline")


def configurar_log():
    os.makedirs(LOG_DIR, exist_ok=True)
    archivo = os.path.join(LOG_DIR, f"pipeline_{dt.date.today():%Y%m%d}.log")
    fmt = logging.Formatter("%(asctime)s %(message)s", "%H:%M:%S")
    for h in (logging.StreamHandler(sys.stdout), logging.FileHandler(archivo, encoding="utf-8")):
        h.setFormatter(fmt)
        log.addHandler(h)
    log.setLevel(logging.INFO)
    return archivo


def notificar(mensaje, titulo="BubuStore"):
    """Notificación de macOS (no falla si no está disponible)."""
    try:
        texto = mensaje.replace('"', "'")
        subprocess.run(["osascript", "-e", f'display notification "{texto}" with title "{titulo}"'],
                       timeout=5, check=False, capture_output=True)
    except Exception:
        pass


def precio_cambios(amazon_precio, estado_actual, config, forzar=False):
    """Campos de estado a guardar para un precio de Amazon recién leído."""
    cambios = {"amazon_precio": amazon_precio}
    if forzar or parse_precio(estado_actual.get("precio")) is None:
        venta = calcular_precio_venta(amazon_precio, config)
        if venta:
            cambios["precio"] = venta
    return cambios


def sospechoso(amazon_precio):
    valor = parse_precio(amazon_precio)
    return valor is not None and valor < 50


def importar_nuevos(scraper, args, config, corrida):
    from lib.vine import descargar_imagenes

    excluidos = catalogo.ids_catalogo() | catalogo.ids_excluidos_extension()
    log.info(f"🚫 Exclusión: {len(excluidos)} ASINs (catálogo + excluir.json)")

    tipos = ["pending_review", "completed"] if args.tipo == "both" else [args.tipo]
    candidatos = []
    for tipo in tipos:
        restantes = args.max - len(candidatos) if args.max else None
        if restantes is not None and restantes <= 0:
            break
        encontrados = scraper.escanear_listado(tipo, excluidos | {c["id"] for c in candidatos},
                                               max_productos=restantes,
                                               corte_temprano=args.corte_temprano)
        candidatos.extend(encontrados)

    log.info(f"✨ Productos nuevos detectados: {len(candidatos)}")
    if args.dry_run:
        for c in candidatos:
            log.info(f"   • {c['id']}  {c.get('title', '')[:70]}")
        return

    for i, cand in enumerate(candidatos, 1):
        log.info(f"🔍 [{i}/{len(candidatos)}] {cand['id']} {cand.get('title', '')[:55]}")
        try:
            prod = scraper.extraer_detalle(cand)
        except Exception as e:
            log.info(f"   ⚠️  Error leyendo el producto: {e}")
            corrida["errores"].append(cand["id"])
            continue

        n_imgs = descargar_imagenes(prod["id"], prod["imagenes"], catalogo.IMAGES_DIR,
                                    maximo=args.max_imagenes, log=log.info)
        if n_imgs == 0:
            log.info("   ⚠️  Sin imágenes: se omite (se reintentará en la próxima corrida).")
            corrida["errores"].append(prod["id"])
            continue

        if not catalogo.agregar_productos([prod], backup=(i == 1)):
            continue
        corrida["importados"].append(prod["id"])

        amz = prod.get("amazon_precio")
        if amz:
            cambios = precio_cambios(amz, {}, config)
            catalogo.actualizar_estado({prod["id"]: cambios})
            aviso = "  ⚠️ revisar (muy barato)" if sospechoso(amz) else ""
            log.info(f"   🖼️  {n_imgs} fotos · 💰 Amazon {amz} → venta ${cambios.get('precio', '?')}{aviso}")
            if aviso:
                corrida["revisar"].append(prod["id"])
        else:
            log.info(f"   🖼️  {n_imgs} fotos · ⚪ sin precio (se reintentará)")
            corrida["sin_precio"].append(prod["id"])


def reintentar_precios(scraper, args, config, corrida):
    """Consulta precio a los ASINs sin amazon_precio (de esta y de corridas anteriores)."""
    estado = catalogo.cargar_estado()
    productos = {p["id"]: p for p in catalogo.cargar_productos()}
    ids = list(dict.fromkeys(corrida["sin_precio"]))
    if args.forzar:
        ids = list(dict.fromkeys(ids + corrida["importados"]))
    pendientes = [pid for pid in ids if pid in productos and
                  (args.forzar or not estado.get(pid, {}).get("amazon_precio"))]
    if not pendientes:
        corrida["sin_precio"] = []
        return

    log.info(f"\n💰 Reintentando precio de {len(pendientes)} productos...")
    siguen_sin_precio = []
    for i, pid in enumerate(pendientes, 1):
        try:
            amz = scraper.consultar_precio(productos[pid].get("url") or f"https://{args.dominio}/dp/{pid}")
        except Exception as e:
            log.info(f"   [{i}] {pid} ⚠️  {e}")
            amz = None
        if not amz:
            siguen_sin_precio.append(pid)
            log.info(f"   [{i}] {pid} ⚪ sin precio")
            continue
        cambios = precio_cambios(amz, estado.get(pid, {}), config, forzar=args.forzar)
        catalogo.actualizar_estado({pid: cambios})
        log.info(f"   [{i}] {pid} 💰 {amz} → venta ${cambios.get('precio', '(se conserva el actual)')}")
    corrida["sin_precio"] = siguen_sin_precio


def pasos_finales(args, corrida):
    try:
        import generar_indice_imagenes
        generar_indice_imagenes.main()
    except Exception as e:
        log.info(f"⚠️  No se pudo regenerar data/imagenes.json: {e}")

    if args.qr and corrida["importados"]:
        try:
            import generar_qr
            nombre = f"{dt.date.today():%d_%m_%y}_QR_Productos.pdf"
            generar_qr.generar_pdf_qr(nombre)
            corrida["pdf_qr"] = nombre
        except Exception as e:
            log.info(f"⚠️  Error generando QR: {e}")

    if args.publicar:
        log.info("☁️  Publicando en GitHub Pages...")
        r = subprocess.run([os.path.join(BASE_DIR, "actualizar_sitio.sh")], cwd=BASE_DIR)
        corrida["publicado"] = r.returncode == 0


def main():
    ap = argparse.ArgumentParser(description="Pipeline automático Amazon Vine → BubuStore")
    ap.add_argument("--tipo", choices=["both", "completed", "pending_review"], default="both")
    ap.add_argument("--max", type=int, default=0, help="máximo de productos nuevos (0 = todos)")
    ap.add_argument("--max-imagenes", type=int, default=5)
    ap.add_argument("--corte-temprano", type=int, default=0,
                    help="dejar de paginar tras N páginas seguidas sin nuevos (0 = recorrer todo)")
    ap.add_argument("--dry-run", action="store_true", help="solo listar nuevos, sin escribir nada")
    ap.add_argument("--solo-precios", action="store_true", help="solo reintentar precios faltantes")
    ap.add_argument("--forzar", action="store_true", help="recalcular precio de venta aunque ya exista")
    ap.add_argument("--qr", action="store_true", help="asignar folios y generar PDF de etiquetas QR")
    ap.add_argument("--publicar", action="store_true", help="ejecutar actualizar_sitio.sh al final")
    ap.add_argument("--headless", action="store_true", help="sin ventana (puede provocar captchas)")
    ap.add_argument("--dominio", default="www.amazon.com.mx")
    ap.add_argument("--perfil", default=None,
                    help='perfil de Chrome con la sesión de Vine (por defecto "Luz Yadira")')
    args = ap.parse_args()

    archivo_log = configurar_log()
    inicio = dt.datetime.now()
    log.info("=" * 60)
    log.info(f"🍇 Pipeline Vine → BubuStore  ({inicio:%Y-%m-%d %H:%M})")
    log.info("=" * 60)

    previa = catalogo.load_json(catalogo.CORRIDA_FILE, {})
    # sin_precio arranca con los pendientes de la corrida anterior: si esta se
    # interrumpe antes de reintentarlos, no se pierden.
    corrida = {"inicio": inicio.isoformat(timespec="seconds"), "importados": [],
               "sin_precio": list(previa.get("sin_precio", [])), "revisar": [], "errores": []}
    config = cargar_config()

    try:
        with catalogo.bloqueo_pipeline():
            from lib.vine import PERFIL_CHROME, VineScraper, abrir_navegador
            perfil = args.perfil or PERFIL_CHROME
            log.info(f"👤 Perfil de Chrome: {perfil}")
            with abrir_navegador(headless=args.headless, perfil=perfil) as page:
                scraper = VineScraper(page, dominio=args.dominio, log=log.info, avisar=notificar)
                if not args.solo_precios:
                    scraper.asegurar_sesion()
                    importar_nuevos(scraper, args, config, corrida)
                if not args.dry_run:
                    reintentar_precios(scraper, args, config, corrida)
            if args.dry_run:
                return 0
            pasos_finales(args, corrida)
    except KeyboardInterrupt:
        log.info("\n🛑 Detenido por el usuario. Lo importado hasta ahora ya quedó guardado.")
        corrida["interrumpido"] = True
    except Exception as e:
        log.info(f"❌ Error: {e}")
        corrida["error"] = str(e)
        notificar(f"El pipeline falló: {e}")
        if args.dry_run:
            return 1
    finally:
        if not args.dry_run:
            corrida["fin"] = dt.datetime.now().isoformat(timespec="seconds")
            corrida["nuevos"] = len(corrida["importados"])
            if not corrida["importados"]:
                # "importados" representa el último lote: se conserva si hoy no hubo nuevos
                corrida["importados"] = previa.get("importados", [])
            catalogo.guardar_atomico(catalogo.CORRIDA_FILE, corrida)

    nuevos = corrida.get("nuevos", 0)
    resumen = (f"{nuevos} nuevos · {len(corrida['sin_precio'])} sin precio · "
               f"{len(corrida['revisar'])} por revisar · {len(corrida['errores'])} errores")
    log.info("=" * 60)
    log.info(f"🏁 {resumen}")
    log.info(f"📝 Log: {archivo_log}")
    if corrida["sin_precio"] or corrida["revisar"]:
        log.info("👉 Revisa en admin.html los productos sin precio o marcados para revisar.")
    log.info("=" * 60)
    notificar(resumen, "BubuStore · Vine actualizado")
    return 1 if corrida.get("error") else 0


if __name__ == "__main__":
    sys.exit(main())
