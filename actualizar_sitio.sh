#!/bin/bash
set -euo pipefail

echo "=========================================="
echo "Iniciando actualización de la tienda..."
echo "=========================================="

# Directorio del proyecto
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

# Asegurar que el hook de seguridad (bloquea tokens, logs, binarios) esté activo
git config core.hooksPath .githooks
chmod +x .githooks/pre-commit 2>/dev/null || true

# Regenerar el índice de fotos que usa el catálogo (no detiene la publicación si falla)
python3 generar_indice_imagenes.py || echo "⚠️  No se pudo regenerar data/imagenes.json; el catálogo buscará las fotos por nombre."

# Agregar los cambios (respeta .gitignore: no incluye token de Facebook, logs ni builds)
git add -A

# Hacer el commit con la fecha y hora actual si hay cambios
FECHA=$(date +"%Y-%m-%d %H:%M:%S")
if git diff --cached --quiet; then
    echo "No hay cambios pendientes por guardar."
else
    if ! git commit -m "Actualización de inventario y precios - $FECHA"; then
        echo "❌ El commit fue bloqueado (revisa los mensajes de arriba)."
        echo "   No se subió nada a GitHub."
        git reset -q
        exit 1
    fi
fi

# Subir los cambios a GitHub
echo "Subiendo cambios a GitHub..."
git push

echo "=========================================="
echo "¡Actualización completada exitosamente!"
echo "Tus clientes verán los cambios en un par de minutos."
echo "=========================================="
