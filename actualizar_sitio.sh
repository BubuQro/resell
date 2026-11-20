#!/bin/bash

echo "=========================================="
echo "Iniciando actualización de la tienda..."
echo "=========================================="

# Directorio del proyecto
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

# Agregar todos los cambios (nuevos precios, productos marcados como vendidos, etc)
git add .

# Hacer el commit con la fecha y hora actual si hay cambios
FECHA=$(date +"%Y-%m-%d %H:%M:%S")
if git diff-index --quiet HEAD --; then
    echo "No hay cambios pendientes por guardar."
else
    git commit -m "Actualización de inventario y precios - $FECHA"
fi

# Subir los cambios a GitHub
echo "Subiendo cambios a GitHub..."
git push

echo "=========================================="
echo "¡Actualización completada exitosamente!"
echo "Tus clientes verán los cambios en un par de minutos."
echo "=========================================="
