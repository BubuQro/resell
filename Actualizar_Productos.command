#!/bin/bash
# Doble clic desde Finder: busca productos nuevos en Amazon Vine, descarga
# imágenes, los agrega al catálogo y les asigna precio (20–30 % menos que Amazon).
cd "$(dirname "$0")" || exit 1
PY="$(command -v python3)"
[ -x /Users/4x/miniforge3/bin/python3 ] && PY=/Users/4x/miniforge3/bin/python3
"$PY" pipeline_vine.py "$@"
echo
read -n 1 -s -r -p "Listo. Presiona cualquier tecla para cerrar..."
